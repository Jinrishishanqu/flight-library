import sqlite3
con=sqlite3.connect(r"F:\新建文件夹\read - 副本\采集工具\书库\data\library.db")
con.row_factory=sqlite3.Row
print("--- chars of work 169 ---")
for r in con.execute("SELECT id,name,role,gender,mentions,first_chapter,length(bio) as bl FROM characters WHERE work_id=169 ORDER BY mentions DESC"):
    print(dict(r))
print("--- works row 169 ---")
w=con.execute("SELECT id,title,source_work,char_count,chapter_count,tags FROM works WHERE id=169").fetchone()
print(dict(w))
print(con.execute("SELECT COUNT(*) FROM chapters WHERE work_id=169").fetchone()[0])
