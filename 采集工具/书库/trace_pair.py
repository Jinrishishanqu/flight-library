# -*- coding: utf-8 -*-
"""并排读两篇的开头/结尾/章节标题，用于判断「续 / 前传 / 新篇」是否同一作品。

用法：python trace_pair.py <id1> <id2> [id3 ...]
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"


def head(t: str, n: int = 260) -> str:
    t = re.sub(r"\s+", "", t or "")
    return t[:n]


def tail(t: str, n: int = 200) -> str:
    t = re.sub(r"\s+", "", t or "")
    return t[-n:]


def main() -> int:
    ids = [int(x) for x in sys.argv[1:]]
    if len(ids) < 2:
        print(__doc__)
        return 2
    con = sqlite3.connect(DB)
    for i in ids:
        w = con.execute("SELECT id,title,char_count,source_work,path_canon FROM works WHERE id=?", (i,)).fetchone()
        if not w:
            print(f"!! 无 #{i}")
            continue
        chs = list(con.execute("SELECT idx,title,content FROM chapters WHERE work_id=? ORDER BY idx", (i,)))
        allt = "".join(c[2] or "" for c in chs)
        print(f"\n{'=' * 70}")
        print(f"#{w[0]} 《{w[1]}》 {w[2]} 字 / {len(chs)} 节 / {w[3]}")
        print(f"文件: {w[4]}")
        print(f"节标题: " + " | ".join(c[1] for c in chs[:12]) + (" …" if len(chs) > 12 else ""))
        print(f"开头: {head(allt, 300)}")
        print(f"结尾: …{tail(allt, 220)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
