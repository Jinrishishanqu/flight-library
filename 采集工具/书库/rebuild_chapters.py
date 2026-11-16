# -*- coding: utf-8 -*-
"""只重建 chapters 表（保留 works / characters / tags / AI 摘要与角色 bio）。

用法：
    python rebuild_chapters.py --dry        只出报告，不改库
    python rebuild_chapters.py              真正重建
"""
import csv, io, json, sqlite3, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_db import (  # noqa: E402
    CHAPTER_RE, load_text, split_chapters, split_long, bigram_cn,
    MIN_AVG, GAP_RATIO, GAP_ABS, MAX_REAL_CHAPTER, GAP_MIN_COVER,
)

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"
ROOT = HERE.parents[1]
RECORD = ROOT / "采集工具" / "记录"

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def analyze(text: str):
    """返回 (模式, 真章数, 平均章长, 最大间隔/中位间隔, 说明)"""
    marks = list(CHAPTER_RE.finditer(text))
    if len(marks) < 3:
        return ("按字数切", len(marks), 0, 0, "章标记少于 3 个")
    gaps = [marks[i + 1].start() - marks[i].end() for i in range(len(marks) - 1)]
    body_len = len(text) - marks[0].end()
    avg = body_len / len(marks)
    med = sorted(gaps)[len(gaps) // 2] if gaps else 0
    ratio = (max(gaps) / max(med, 1)) if gaps else 0
    if avg > MIN_AVG:
        return ("按字数切", len(marks), avg, ratio, f"平均章长 {avg:.0f} 字 > {MIN_AVG}，标记只覆盖局部")
    covered = sum(
        (marks[i + 1].start() if i + 1 < len(marks) else len(text)) - marks[i].end()
        for i in range(len(marks))
    )
    if gaps and max(gaps) > max(GAP_RATIO * med, GAP_ABS):
        if covered / max(1, body_len) >= GAP_MIN_COVER:
            return ("按原文分章（部分）", len(marks), avg, ratio,
                    f"标记断裂但覆盖 {covered / body_len:.0%}，洞内按字数切")
        return ("按字数切", len(marks), avg, ratio, f"最大间隔是中位的 {ratio:.1f} 倍，标记断裂")
    return ("按原文分章", len(marks), avg, ratio, "")


def main():
    dry = "--dry" in sys.argv
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    # 只重建「独立作品」：merged_into 非空的是已并入副本，
    # 「被别的作品并入的主本」也不能按原文重建 —— 会丢掉子本追加进来的章节。
    works = con.execute(
        "SELECT id,title,path_canon,chapter_count,char_count FROM works w "
        "WHERE merged_into IS NULL "
        "  AND NOT EXISTS (SELECT 1 FROM works x WHERE x.merged_into = w.id) "
        "ORDER BY id"
    ).fetchall()
    skipped = con.execute(
        "SELECT COUNT(*) FROM works w WHERE EXISTS "
        "(SELECT 1 FROM works x WHERE x.merged_into = w.id)"
    ).fetchone()[0]
    if skipped:
        print(f"跳过 {skipped} 部「已合并主本」：按原文重建会丢掉子本追加的章节")

    rows, changed = [], 0
    for w in works:
        p = Path(w["path_canon"])
        if not p.is_absolute():
            p = ROOT / "校勘版" / p
        if not p.exists():
            rows.append([w["id"], w["title"], "文件缺失", "", w["chapter_count"], "", "", "", ""])
            continue
        text = load_text(p)
        mode, nmarks, avg, ratio, why = analyze(text)
        seps = split_chapters(text)
        new_n = len(seps)
        real = sum(1 for s in seps if s[1] == 1)
        rows.append([
            w["id"], w["title"], mode, nmarks,
            w["chapter_count"], new_n, real,
            f"{avg:.0f}" if avg else "", why,
        ])
        if dry:
            continue

        if new_n == w["chapter_count"] and real == 0 and mode == "按字数切":
            continue  # 结果一样，跳过写入

        con.execute("DELETE FROM chapters WHERE work_id=?", (w["id"],))
        con.executemany(
            "INSERT INTO chapters (work_id,idx,title,is_real_title,content,body_bi,char_count)"
            " VALUES (?,?,?,?,?,?,?)",
            [
                (w["id"], i, title, is_real, content, bigram_cn(content), len(content))
                for i, (title, is_real, content) in enumerate(seps, 1)
            ],
        )
        con.execute(
            "UPDATE works SET chapter_count=?, reading_minutes=? WHERE id=?",
            (new_n, max(1, round(w["char_count"] / 400)), w["id"]),
        )
        changed += 1
        if changed % 50 == 0:
            print(f"  …{changed} 部已重建", flush=True)

    header = ["work_id", "书名", "模式", "章标记数", "原节数", "新节数", "真标题节数", "平均章长", "降级原因"]
    RECORD.mkdir(parents=True, exist_ok=True)
    out = RECORD / "章节划分报告.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        cw = csv.writer(f)
        cw.writerow(header)
        cw.writerows(rows)

    mode_cnt = {}
    for r in rows:
        mode_cnt[r[2]] = mode_cnt.get(r[2], 0) + 1
    print(json.dumps(mode_cnt, ensure_ascii=False))
    print(f"报告 -> {out}")

    if dry:
        print("（--dry：未改库）")
        con.close()
        return

    con.commit()
    # contentless FTS5 不支持 'rebuild' 命令，只能整表重建后重灌
    con.execute("DROP TABLE IF EXISTS chapters_fts")
    con.execute(
        "CREATE VIRTUAL TABLE chapters_fts USING fts5("
        "title, body_bi, work_title, content='', tokenize='unicode61 remove_diacritics 0')"
    )
    fts_rows = con.execute(
        "SELECT c.id, c.title, c.body_bi, w.title FROM chapters c JOIN works w ON w.id=c.work_id"
    ).fetchall()
    con.executemany(
        "INSERT INTO chapters_fts(rowid,title,body_bi,work_title) VALUES (?,?,?,?)",
        [(r[0], bigram_cn(r[1] or ""), r[2], bigram_cn(r[3] or "")) for r in fts_rows],
    )
    con.execute("INSERT INTO chapters_fts(chapters_fts) VALUES('optimize')")
    con.commit()
    tot = con.execute("SELECT COUNT(*) FROM chapters").fetchone()[0]
    real = con.execute("SELECT COUNT(*) FROM chapters WHERE is_real_title=1").fetchone()[0]
    print(f"重建完成：{changed} 部有变动，总节数 {tot}，其中真标题 {real}")
    con.close()


if __name__ == "__main__":
    main()
