# -*- coding: utf-8 -*-
import sqlite3, sys, io, os, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
db = r'F:\新建文件夹\read - 副本\采集工具\书库\data\library.db'
con = sqlite3.connect(db)
tabs = [r[0] for r in con.execute("select name from sqlite_master where type='table'")]
print("TABLES:", tabs)
for t in tabs:
    try:
        cols = [c[1] for c in con.execute(f"PRAGMA table_info({t})")]
    except Exception as e:
        cols = []
    print(t, cols)
