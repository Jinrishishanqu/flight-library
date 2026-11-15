# -*- coding: utf-8 -*-
"""抽查某部作品在合并时被判为「独有」的段落，看是真的新内容还是同文的改写/分段差异。"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"
PUNCT = re.compile(r"[\s\u3000，。！？、；：「」『』“”‘’（）《》…—·\-~～,.!?;:\"'()\[\]{}*#]+")


def flat(s: str) -> str:
    return PUNCT.sub("", s or "")


def grams(t: str, n: int = 10) -> set[str]:
    s = flat(t)
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def paras(t: str) -> list[str]:
    return [p.strip() for p in re.split(r"[\r\n]+", t or "") if p.strip()]


def main() -> int:
    child, parent = int(sys.argv[1]), int(sys.argv[2])
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 6
    con = sqlite3.connect(DB)
    ptext = "\n".join(r[0] for r in con.execute(
        "SELECT content FROM chapters WHERE work_id=?", (parent,)))
    p_flat, p_grams = flat(ptext), grams(ptext)
    rows = con.execute(
        "SELECT ch.idx, ch.title, ch.content FROM chapters ch WHERE ch.work_id=? ORDER BY ch.idx",
        (child,)).fetchall()
    shown = 0
    for idx, title, content in rows:
        for p in paras(content):
            key = flat(p)[:24]
            if len(key) >= 12 and key in p_flat:
                continue
            pg = grams(p)
            cov = len(pg & p_grams) / len(pg) if pg else 0
            if cov >= 0.6:
                continue
            shown += 1
            print(f"--- 第{idx}节 {title} | 长度 {len(p)} | gram 覆盖 {cov:.2f}")
            print(p[:260])
            print()
            if shown >= limit:
                return 0
    print(f"（共 {shown} 段）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
