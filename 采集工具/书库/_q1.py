import sqlite3, sys
c = sqlite3.connect(r'data/library.db')
print([r[0] for r in c.execute("select name from sqlite_master where type='table'")])
for tbl in ['works','chapters']:
    try:
        print(tbl, [d[1] for d in c.execute(f"PRAGMA table_info({tbl})")])
    except Exception as e:
        print(tbl, e)
