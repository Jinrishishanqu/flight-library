# -*- coding: utf-8 -*-
import sqlite3, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
db = r'F:\新建文件夹\read - 副本\采集工具\书库\data\library.db'
con = sqlite3.connect(db)
targets = [(445, ['云山']), (176, ['紫妍', '萧潇']), (409, ['玉小刚']), (480, ['秦瑶', '庞博', '水月'])]
for wid, names in targets:
    row = con.execute("select title, source_work, char_count from works where id=?", (wid,)).fetchone()
    print("=" * 70)
    print("WORK", wid, row)
    chaps = con.execute("select idx, title, content from chapters where work_id=? order by idx", (wid,)).fetchall()
    print("chapters:", [(c[0], c[1], len(c[2] or '')) for c in chaps])
    for name in names:
        print("-" * 60)
        print("NAME", name)
        n = 0
        for idx, title, content in chaps:
            content = content or ''
            for m in re.finditer(re.escape(name), content):
                n += 1
                s = max(0, m.start() - 200)
                e = min(len(content), m.end() + 200)
                print(f"[ch{idx}] ...{content[s:e]}...")
                print()
        print("total occurrences:", n)
