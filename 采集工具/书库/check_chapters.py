# -*- coding: utf-8 -*-
"""统计：修好 CRLF 后，全库每部作品能识别出多少真正的章标记。

输出对比表，供决定是否重建章节。
"""
import sqlite3, sys, io, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_db import CHAPTER_RE, load_text  # noqa: E402

DB = Path(__file__).resolve().parent / "data" / "library.db"
ROOT = Path(__file__).resolve().parents[2]
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def main():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id,title,path_canon,chapter_count FROM works ORDER BY id").fetchall()
    stat = {"with_marks": 0, "no_marks": 0, "missing_file": 0, "total_marks": 0}
    diffs = []
    for w in rows:
        p = Path(w["path_canon"])
        if not p.is_absolute():
            p = ROOT / "校勘版" / p
        if not p.exists():
            stat["missing_file"] += 1
            continue
        t = load_text(p)
        n = len(CHAPTER_RE.findall(t))
        if n >= 3:
            stat["with_marks"] += 1
            stat["total_marks"] += n
            diffs.append((w["id"], w["title"], w["chapter_count"], n))
        else:
            stat["no_marks"] += 1
    print(json.dumps(stat, ensure_ascii=False))
    print(f"\n会改变节数的作品（现有节数 vs 真章数），差异最大的 25 部：")
    diffs.sort(key=lambda x: abs(x[3] - x[2]), reverse=True)
    for wid, title, cur, real in diffs[:25]:
        print(f"  {wid:4d} {title[:28]:30s} 现在 {cur:4d} 节 -> 真章 {real:4d}")
    same = sum(1 for d in diffs if d[2] == d[3])
    print(f"\n节数不变: {same}   会变: {len(diffs) - same}")
    con.close()


if __name__ == "__main__":
    main()
