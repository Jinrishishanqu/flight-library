# -*- coding: utf-8 -*-
"""手工修正最后两处 path_source。

- #172 大千绿帽RPG系统：原文只有「21～40」那一卷，正文正是它，指纹因
  开头标题与「不好意思各位…」之间夹了 \r\n\r\n 而拼不出连续串。
- #95 绝色小医仙：多段指纹把同目录另一篇（开头句相同）也带进来了，
  正文实际只来自 绝色小医仙.txt。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"

FIX = {
    172: r"原文\斗破\pixiv-27378364-斗破苍穹x大主宰x武动乾坤之大千绿帽RPG系统21～40.txt",
    95: r"原文\大主宰\绝色小医仙.txt",
}


def main() -> int:
    con = sqlite3.connect(DB)
    for wid, path in FIX.items():
        cur = con.execute("UPDATE works SET path_source=? WHERE id=?", (path, wid))
        print(f"#{wid} -> {path}  ({cur.rowcount} 行)")
    con.commit()
    n = con.execute(
        "SELECT COUNT(*) FROM works WHERE merged_into IS NULL AND (path_source IS NULL OR path_source='')"
    ).fetchone()[0]
    print(f"仍有 path_source 的可见作品：{n}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
