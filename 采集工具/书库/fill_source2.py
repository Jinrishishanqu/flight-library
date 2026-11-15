# -*- coding: utf-8 -*-
"""第二次补 `path_source`：校对清单里没有记录的作品，用文件名在 `原文\\` 里反查。

匹配规则（从严到宽，取第一个非空结果）：
1. 去装饰后的文件名完全相同
2. 相似度 ≥ 0.90
3. 相似度 ≥ 0.82 且原文目录与 `source_work` 同名

同名的多个分卷（`(1)(2)`、`1~3-`、`4-`）合并为 `|` 连接的多路径。

用法：
    python fill_source2.py
    python fill_source2.py --apply
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

from rapidfuzz import fuzz

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DB = HERE / "data" / "library.db"
SRC_ROOT = ROOT / "原文"

DECOR = [
    (re.compile(r"^\d+\s*[~\-－—]\s*\d+\s*[-_—]?\s*"), ""),
    (re.compile(r"^\d+\s*[-_]\s*"), ""),
    (re.compile(r"\s*\(\d+\)\s*$"), ""),
    (re.compile(r"\s*（\d+）\s*$"), ""),
    (re.compile(r"-?\d+(\.\d+)?[wW万](\d+)?字?$"), ""),
    (re.compile(r"-?\d+[千kK](\d+)?字?$"), ""),
    (re.compile(r"-?合集.*$"), ""),
    (re.compile(r"-?全篇.*$"), ""),
    (re.compile(r"-?独立\s*\d+\s*篇$"), ""),
]


def clean(name: str) -> str:
    s = name.strip()
    # 《书名》-全篇-1.2w 这类，去掉书名号后「》」会落在中间，必须全局删
    s = s.replace("《", "").replace("》", "")
    for _ in range(3):
        before = s
        for rx, rep in DECOR:
            s = rx.sub(rep, s)
        s = s.strip(" -—_·、.")
        if s == before:
            break
    return s


def main() -> int:
    apply_ = "--apply" in sys.argv
    con = sqlite3.connect(DB, timeout=60)
    missing = con.execute(
        "SELECT id,title,path_canon,source_work FROM works "
        "WHERE merged_into IS NULL AND (path_source IS NULL OR path_source='') ORDER BY id"
    ).fetchall()
    print(f"待补 {len(missing)} 部")

    files = list(SRC_ROOT.rglob("*.txt"))
    index = [(p, clean(p.stem)) for p in files]
    print(f"原文文件 {len(files)} 个")

    fixed = []
    for wid, title, pc, src_work in missing:
        stem = Path((pc or "").replace("/", "\\")).stem
        core = clean(stem) or clean(title)
        if not core:
            continue
        exact = [p for p, c in index if c == core]
        pick: list[Path] = []
        if exact:
            pick = exact
        else:
            scored = [(fuzz.ratio(core, c), p, c) for p, c in index if c]
            scored.sort(reverse=True)
            if scored and scored[0][0] >= 90:
                top = [x for x in scored if x[0] == scored[0][0]]
                pick = [x[1] for x in top]
            elif scored and scored[0][0] >= 82:
                same = [x for x in scored if x[0] >= 82 and src_work
                        and x[1].parent.name == src_work]
                if same:
                    pick = [x[1] for x in same[:3]]
        if not pick:
            print(f"  跳过 #{wid} {title[:22]}（core={core}）")
            continue
        rel = "|".join(str(p.relative_to(ROOT)).replace("/", "\\") for p in sorted(pick))
        fixed.append((rel, wid))
        print(f"  #{wid:<4} {title[:22]:<22} -> {rel[:88]}")

    print(f"\n命中 {len(fixed)} / {len(missing)}")
    if apply_ and fixed:
        con.executemany("UPDATE works SET path_source=? WHERE id=?", fixed)
        con.commit()
        n = con.execute(
            "SELECT COUNT(*) FROM works WHERE merged_into IS NULL AND path_source IS NOT NULL AND path_source <> ''"
        ).fetchone()[0]
        tot = con.execute("SELECT COUNT(*) FROM works WHERE merged_into IS NULL").fetchone()[0]
        print(f"已写库：path_source {n} / {tot}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
