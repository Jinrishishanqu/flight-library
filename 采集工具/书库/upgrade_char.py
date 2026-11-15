#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 characters 表补多维度档案列（幂等）。"""
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parent / "data" / "library.db"

COLS = [
    ("looks", "TEXT"),
    ("figure", "TEXT"),
    ("personality", "TEXT"),
    ("relations", "TEXT"),
    ("sexual", "TEXT"),
    ("sex_tags", "TEXT"),
]

if not DB.exists():
    sys.exit(f"数据库不存在：{DB}")

con = sqlite3.connect(DB)
have = {r[1] for r in con.execute("PRAGMA table_info(characters)")}
added = []
for name, typ in COLS:
    if name in have:
        continue
    con.execute(f"ALTER TABLE characters ADD COLUMN {name} {typ}")
    added.append(name)
con.commit()
con.close()

print("新增列：" + (", ".join(added) if added else "无（已是最新）"))
