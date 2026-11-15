# -*- coding: utf-8 -*-
import sqlite3, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
db = r'F:\新建文件夹\read - 副本\采集工具\书库\data\library.db'
con = sqlite3.connect(db)
targets = [(409, '玉小刚'), (480, '庞博'), (480, '水月')]
for wid, name in targets:
    chaps = con.execute("select idx, title, content from chapters where work_id=? order by idx", (wid,)).fetchall()
    print("=" * 70)
    print("WORK", wid, name)
    n = 0
    for idx, title, content in chaps:
        content = content or ''
        for m in re.finditer(re.escape(name), content):
            n += 1
            if n > 14: break
            s = max(0, m.start() - 130)
            e = min(len(content), m.end() + 130)
            print(f"[ch{idx}] ...{content[s:e]}...".replace('\n', ' '))
            print()
        if n > 14: break
    print("shown:", n)
