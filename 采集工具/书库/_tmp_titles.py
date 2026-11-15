import sqlite3, sys
DB = r'F:\新建文件夹\read - 副本\采集工具\书库\data\library.db'
c = sqlite3.connect('file:' + DB.replace('\\', '/') + '?mode=ro', uri=True)
c.text_factory = str
wid = int(sys.argv[1])
for r in c.execute("select idx, title, char_count from chapters where work_id=? order by idx", (wid,)):
    print(r[0], r[1], r[2])
