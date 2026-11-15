# -*- coding: utf-8 -*-
import sqlite3, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
db = r'F:\新建文件夹\read - 副本\采集工具\书库\data\library.db'
con = sqlite3.connect(db)
n = 0
for idx, title, content in con.execute("select idx,title,content from chapters where work_id=409 order by idx"):
    c = content or ''
    for m in re.finditer('大师', c):
        n += 1
        s = max(0, m.start() - 120); e = min(len(c), m.end() + 120)
        print(f"[ch{idx}] ...{c[s:e]}...".replace('\n', ' '))
        print()
print("total", n)
