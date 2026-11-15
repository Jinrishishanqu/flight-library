import sqlite3, io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
db = r"F:\新建文件夹\read - 副本\采集工具\书库\data\library.db"
con = sqlite3.connect(db); cur = con.cursor()
for wid in (445, 409):
    rows = cur.execute("select idx,title,content from chapters where work_id=? order by idx", (wid,)).fetchall()
    out = []
    for idx, title, c in rows:
        out.append("########## CH%s %s\n%s" % (idx, title, c))
    t = "\n".join(out)
    open(r"F:\新建文件夹\read - 副本\_tmp_txt\%d.txt" % wid, "w", encoding="utf-8").write(t)
    print(wid, len(rows), len(t))
