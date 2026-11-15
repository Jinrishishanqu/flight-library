import sqlite3, os
c=sqlite3.connect(r"F:\新建文件夹\read - 副本\采集工具\书库\data\library.db")
os.makedirs(r"F:\新建文件夹\read - 副本\采集工具\书库\data\_dump", exist_ok=True)
for wid in (426,398,48,428):
    w=c.execute("select id,title,source_work,char_count,chapter_count,tags from works where id=?",(wid,)).fetchone()
    print(w)
    rows=c.execute("select idx,title,content from chapters where work_id=? order by idx",(wid,)).fetchall()
    out=r"F:\新建文件夹\read - 副本\采集工具\书库\data\_dump\%d.txt"%wid
    with open(out,"w",encoding="utf-8") as f:
        for idx,t,body in rows:
            f.write("\n===== 第%s节 %s =====\n"%(idx,t or ""))
            f.write(body)
    print("  chars:", sum(len(r[2]) for r in rows), "->", out)
