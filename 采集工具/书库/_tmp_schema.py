import sqlite3, os
p = r'F:\新建文件夹\read - 副本\采集工具\书库\data\library.db'
print('size', os.path.getsize(p))
c = sqlite3.connect('file:' + p.replace('\\', '/') + '?mode=ro', uri=True)
cur = c.cursor()
for n, t, s in cur.execute("select name, type, sql from sqlite_master where type='table'"):
    print(t, n, '|', (s or '').replace('\n', ' ')[:200])
