# -*- coding: utf-8 -*-
import sqlite3, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
db = r'F:\新建文件夹\read - 副本\采集工具\书库\data\library.db'
con = sqlite3.connect(db)
# 409 chapter titles
print("409 chapters:")
for r in con.execute("select idx,title,char_count from chapters where work_id=409 order by idx"):
    print(r)
print()
print("characters table for these works:")
for wid in (445, 176, 409, 480):
    print("--- work", wid)
    for r in con.execute("select name,role,gender,mentions,first_chapter,origin,coverage,spread,score from characters where work_id=? order by mentions desc", (wid,)):
        print(r)
print()
for pat in ['小刚', '玉小', '大师']:
    tot = 0
    for idx, title, content in con.execute("select idx,title,content from chapters where work_id=409"):
        c = content or ''
        tot += c.count(pat) + (title or '').count(pat)
    print(pat, tot)
