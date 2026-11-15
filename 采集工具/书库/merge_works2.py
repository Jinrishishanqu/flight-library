# -*- coding: utf-8 -*-
"""按「章号 + 文件内顺序」合并同作异名/分卷。

用户要求（m07847）：
- 不要生硬地把内容堆到末尾，要按上下文排序后拼接
- 排序的对象是**原文件**，同一个原文件内的章节顺序不动

做法：
1. 从子作品里取出主本没有的段落（段级去重，前 24 字比对）
2. 把这些段落组装成「子章节」，章号从子作品标题里的「第N章」取，取不到就继承上一节
3. 主本章节 + 子章节一起按 (章号, 主本优先, 原序) 稳定排序，重写 idx

用法：python merge_works2.py [--dry|--apply]
"""
import io
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_db import bigram_cn, chap_no, load_text  # noqa: E402

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"
ROOT = HERE.parents[1]
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 人工确认过的配对：(子作品 id, 主本 id)
PAIRS = [
    (160, 162), (161, 162),      # 斗破淫传分卷 -> 斗破淫传
    (196, 197),                  # 萧薰儿的征程短版 -> 长版
    (202, 168), (203, 168), (204, 168), (205, 168),  # 改编版各章独立文件 -> 合本
    (367, 388),                  # 邪恶主神短版 -> 霍雨浩的邪恶主神（重合 0.99）
    (373, 381),                  # 霍雨浩x王秋儿 -> 霍雨浩与王秋儿（重合 0.81）
]

PUNCT = re.compile(r"\s+")
# 只认「第N章」，不认「第N节」（后者是按字数切出来的）
CHAP_ONLY = re.compile(r"^第[0-9零一二三四五六七八九十百千两]+章")


def flat(s: str) -> str:
    return PUNCT.sub("", s or "")


def split_paras(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"[\r\n]+", text) if p.strip()]


def unique_text(child_text: str, parent_flat: str) -> tuple[str, int, int]:
    """返回 (独有正文, 总段数, 被覆盖段数)。"""
    keep, total, dup = [], 0, 0
    for p in split_paras(child_text):
        total += 1
        key = flat(p)[:24]
        if len(key) >= 12 and key in parent_flat:
            dup += 1
            continue
        keep.append(p)
    return "\n".join(keep), total, dup


def chapters_of(con, wid: int) -> list[tuple[int, str, str]]:
    return [
        (r[0], r[1] or "", r[2] or "")
        for r in con.execute(
            "SELECT idx, title, content FROM chapters WHERE work_id=? ORDER BY idx", (wid,)
        )
    ]


def main():
    apply = "--apply" in sys.argv
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # 重置上一次的合并状态，保证幂等
    if apply:
        con.execute("UPDATE works SET merged_into=NULL WHERE merged_into IS NOT NULL")
        con.commit()

    for child_id, parent_id in PAIRS:
        cw = con.execute("SELECT id,title FROM works WHERE id=?", (child_id,)).fetchone()
        pw = con.execute("SELECT id,title FROM works WHERE id=?", (parent_id,)).fetchone()
        if not cw or not pw:
            print(f"!! 缺作品 {child_id}->{parent_id}")
            continue

        p_chs = chapters_of(con, parent_id)
        p_flat = flat("\n".join(c[2] for c in p_chs))
        c_chs = chapters_of(con, child_id)

        # 子章节的章号：从子作品标题取，取不到就沿用上一节的章号
        m = re.search(r"第[0-9零一二三四五六七八九十百千两]+章", cw["title"] or "")
        child_no = chap_no(m.group(0)) if m else None

        entries = []   # (章号, 主本优先, 原序, 标题, 内容)
        for i, (idx, title, content) in enumerate(p_chs):
            no = chap_no(title) or (entries[-1][0] if entries else 0)
            entries.append((no, 0, i, title, content))

        added = 0
        for j, (idx, title, content) in enumerate(c_chs):
            body, total, dup = unique_text(content, p_flat)
            if len(body) < 200:
                continue
            no = (chap_no(title) if CHAP_ONLY.match(title or "") else None) or child_no or 0
            entries.append((no, 1, j, f"另版 · {title}" if title else "另版", body))
            added += 1
            print(f"  + #{child_id}《{cw['title'][:22]}》第 {j + 1} 节 -> 章{no}"
                  f"  覆盖 {dup}/{total} 段，独有 {len(body)} 字")

        entries.sort(key=lambda e: (e[0], e[1], e[2]))

        print(f"{child_id}《{cw['title'][:22]}》-> {parent_id}《{pw['title'][:22]}》"
              f"  主本 {len(p_chs)} 节 + 新增 {added} 节 = {len(entries)} 节")
        if not apply:
            continue

        con.execute("DELETE FROM chapters WHERE work_id=?", (parent_id,))
        con.executemany(
            "INSERT INTO chapters (work_id,idx,title,is_real_title,content,body_bi,char_count)"
            " VALUES (?,?,?,?,?,?,?)",
            [
                (parent_id, n, title, 1 if title.startswith("第") or "·" in title else 0,
                 body, bigram_cn(body), len(body))
                for n, (_, _, _, title, body) in enumerate(entries, 1)
            ],
        )
        tot = sum(len(e[4]) for e in entries)
        con.execute(
            "UPDATE works SET chapter_count=?, char_count=?, reading_minutes=?,"
            " updated_at=datetime('now','localtime') WHERE id=?",
            (len(entries), tot, max(1, round(tot / 400)), parent_id),
        )
        con.execute("UPDATE works SET merged_into=? WHERE id=?", (parent_id, child_id))
        con.commit()

    if not apply:
        print("\n（--dry：未改库）")
        con.close()
        return

    con.close()
    print("\n重灌 FTS …")
    import subprocess
    subprocess.run([sys.executable, str(HERE / "refresh_fts.py")], check=False)


if __name__ == "__main__":
    main()
