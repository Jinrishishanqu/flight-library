import sqlite3, json
db = r"F:\新建文件夹\read - 副本\采集工具\书库\data\library.db"
c = sqlite3.connect(db)
c.row_factory = sqlite3.Row
for wid in (22, 444, 340):
    w = c.execute("select id,title,source_work,char_count,chapter_count,summary from works where id=?", (wid,)).fetchone()
    print("=== work", wid, dict(w) if w else None)
    for r in c.execute("select id,name,aliases,role,gender,mentions,title,intro,first_chapter,bio,bio_at,origin,score from characters where work_id=? order by mentions desc", (wid,)):
        d = dict(r)
        d['bio'] = (d['bio'] or '')[:80]
        d['intro'] = (d['intro'] or '')[:80]
        print(d)
print("=== bios of 24/26/31/32")
for wid in (24, 26, 31, 32):
    n = c.execute("select count(*), sum(case when bio is null or bio='' then 1 else 0 end) from characters where work_id=?", (wid,)).fetchone()
    print(wid, tuple(n))
# sample an existing full bio for style/length reference
r = c.execute("select work_id,name,bio from characters where length(bio)>200 limit 1").fetchone()
print("=== sample bio", r['work_id'], r['name'], len(r['bio']))
print(r['bio'][:1200])
