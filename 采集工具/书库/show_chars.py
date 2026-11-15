# -*- coding: utf-8 -*-
"""列出某部作品的角色档案概况（调试用）。"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "data" / "library.db"


def main() -> int:
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    ids = [int(x) for x in sys.argv[1:]]
    if not ids:
        print("用法：python show_chars.py <work_id...>")
        return 2
    for wid in ids:
        w = con.execute("SELECT title,char_count,chapter_count FROM works WHERE id=?",
                        (wid,)).fetchone()
        rs = list(con.execute(
            "SELECT name,role,gender,mentions,coverage,spread,score,origin FROM characters"
            " WHERE work_id=? ORDER BY score DESC", (wid,)))
        print(f"#{wid} 《{w['title']}》 {w['char_count']} 字 / {w['chapter_count']} 节"
              f" → {len(rs)} 人")
        for r in rs:
            cov = f"{r['coverage']:.2f}" if r["coverage"] is not None else " -- "
            span = f"{r['spread']:.2f}" if r["spread"] is not None else " -- "
            sc = f"{r['score']:.3f}" if r["score"] is not None else " --- "
            print(f"    {r['name']:8s} {r['role']} {r['gender']} m={r['mentions']:5d}"
                  f" cov={cov} span={span} sc={sc} {r['origin']}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
