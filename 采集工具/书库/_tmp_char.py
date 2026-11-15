import sqlite3, sys

DB = r'F:\新建文件夹\read - 副本\采集工具\书库\data\library.db'
c = sqlite3.connect('file:' + DB.replace('\\', '/') + '?mode=ro', uri=True)
c.text_factory = str
wid = 449
rows = c.execute("select idx, content from chapters where work_id=? order by idx", (wid,)).fetchall()
full = '\n'.join((r[1] or '') for r in rows)
print('total chars', len(full))
for t in ['冉绝', '玉', '刚', '小刚', '玉小刚', '大师', '宓妃', '赵仲卿']:
    print(t, full.count(t))
