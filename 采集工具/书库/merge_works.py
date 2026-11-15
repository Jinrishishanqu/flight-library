# -*- coding: utf-8 -*-
"""把同一作品的分卷/短版并入主本。

做法（可逆）：
1. 子作品的章节追加到主本末尾，标题前加「【原：子书名】」
2. 子作品写 merged_into = 主本 id，前端默认不显示
3. 主本重建 FTS

用法：
    python merge_works.py --dry
    python merge_works.py --apply
"""
import io
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_db import bigram_cn  # noqa: E402

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def flat(s: str) -> str:
    return re.sub(r"\s+", "", s)


def unique_paras(child_text: str, parent_flat: str) -> str:
    """逐段过滤掉主本里已经有的内容，只留子作品独有的段落。"""
    keep = []
    for p in child_text.split("\n"):
        p = p.strip()
        if not p:
            continue
        key = flat(p)[:24]
        if len(key) >= 12 and key in parent_flat:
            continue
        keep.append(p)
    return "\n".join(keep)

# 确定的合并关系：子 -> 主（依据见 docs/阅读站说明.md「重复作品整合」）
PAIRS = [
    (160, 162),   # 斗破淫传(6k)          -> 斗破淫传(13k)
    (161, 162),   # 斗破淫传1纳兰劫(4k)     -> 斗破淫传(13k)
    (196, 197),   # 萧薰儿的征程(56k)      -> 萧薰儿的征程(84k)
    (202, 168),   # 改编版 第三章          -> 斗破苍穹-改编版(合集)
    (203, 168),   # 改编版 第二章          -> 合集
    (204, 168),   # 改编版 第五章          -> 合集
    (205, 168),   # 改编版 第四章          -> 合集
]


def ensure_column(con):
    cols = [r[1] for r in con.execute("PRAGMA table_info(works)")]
    if "merged_into" not in cols:
        con.execute("ALTER TABLE works ADD COLUMN merged_into INTEGER")
        con.commit()
        print("已加列 works.merged_into")


def main():
    dry = "--apply" not in sys.argv
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    ensure_column(con)

    rows = []
    for child, parent in PAIRS:
        c = con.execute("SELECT id,title,char_count,chapter_count FROM works WHERE id=?", (child,)).fetchone()
        p = con.execute("SELECT id,title,char_count,chapter_count FROM works WHERE id=?", (parent,)).fetchone()
        if not c or not p:
            print(f"!! 缺作品 {child}->{parent}")
            continue
        rows.append((child, c["title"], c["char_count"], c["chapter_count"],
                     parent, p["title"], p["char_count"], p["chapter_count"]))

    print(f"{'子':>4} {'书名':26s} {'字':>7} {'节':>4}  ->  {'主':>4} {'书名':26s} {'字':>7} {'节':>4}")
    for r in rows:
        print(f"{r[0]:>4} {r[1][:26]:26s} {r[2]:>7} {r[3]:>4}  ->  {r[4]:>4} {r[5][:26]:26s} {r[6]:>7} {r[7]:>4}")

    if dry:
        print("\n（--dry：未改动。加 --apply 执行）")
        con.close()
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = HERE / "data" / f"library_before_merge_{stamp}.db"
    con.execute("VACUUM INTO ?", (str(bak),))
    print(f"备份 -> {bak}")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    moved = 0
    skipped = 0
    for child, parent in PAIRS:
        c = con.execute("SELECT title FROM works WHERE id=?", (child,)).fetchone()
        p = con.execute("SELECT title FROM works WHERE id=?", (parent,)).fetchone()
        if not c or not p:
            continue
        base = con.execute(
            "SELECT COALESCE(MAX(idx),0) FROM chapters WHERE work_id=?", (parent,)
        ).fetchone()[0]
        parent_flat = flat("".join(
            r["content"] for r in con.execute(
                "SELECT content FROM chapters WHERE work_id=? ORDER BY idx", (parent,))
        ))
        chs = con.execute(
            "SELECT title,is_real_title,content FROM chapters WHERE work_id=? ORDER BY idx", (child,)
        ).fetchall()
        added = 0
        for ch in chs:
            body = unique_paras(ch["content"], parent_flat)
            if len(flat(body)) < 200:
                skipped += 1
                continue
            title = f"【原：{c['title']}】{ch['title']}"
            con.execute(
                "INSERT INTO chapters (work_id,idx,title,is_real_title,content,body_bi,char_count)"
                " VALUES (?,?,?,?,?,?,?)",
                (parent, base + added + 1, title, ch["is_real_title"], body,
                 bigram_cn(body), len(body)),
            )
            added += 1
            parent_flat += flat(body)
        moved += added
        con.execute("UPDATE works SET merged_into=? WHERE id=?", (parent, child))
        tot = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(char_count),0) FROM chapters WHERE work_id=?", (parent,)
        ).fetchone()
        con.execute(
            "UPDATE works SET chapter_count=?, char_count=?, reading_minutes=?, updated_at=? WHERE id=?",
            (tot[0], tot[1], max(1, round(tot[1] / 400)), now, parent),
        )
        print(f"  {child} -> {parent}：新增 {added} 节"
              f"（{len(chs)} 节里去掉重复后），主本现有 {tot[0]} 节 / {tot[1]} 字")

    con.commit()

    # 重建 FTS（contentless 表只能整表重来）
    con.execute("DROP TABLE IF EXISTS chapters_fts")
    con.execute(
        "CREATE VIRTUAL TABLE chapters_fts USING fts5("
        "title, body_bi, work_title, content='', tokenize='unicode61 remove_diacritics 0')"
    )
    con.execute(
        "INSERT INTO chapters_fts(rowid,title,body_bi,work_title) "
        "SELECT c.id, c.title, c.body_bi, w.title FROM chapters c JOIN works w ON w.id=c.work_id"
    )
    con.execute("INSERT INTO chapters_fts(chapters_fts) VALUES('optimize')")
    con.commit()

    vis = con.execute("SELECT COUNT(*) FROM works WHERE merged_into IS NULL").fetchone()[0]
    tot_ch = con.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
    print(f"\n完成：并入 {moved} 节；可见作品 {vis} 部，总节数 {tot_ch}")
    con.close()


if __name__ == "__main__":
    main()
