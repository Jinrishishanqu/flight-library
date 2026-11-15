import sqlite3, sys, re, json
c = sqlite3.connect(r'data/library.db')
names_by_work = {135: ['萧薰儿','药尘'], 367: ['唐舞桐','王秋儿','橘子'], 479: ['伊轻舞'], 124: ['萧炎']}
out = {}
for wid, names in names_by_work.items():
    rows = list(c.execute("select idx,title,content from chapters where work_id=? order by idx", (wid,)))
    print('='*30, wid, 'chapters', len(rows), 'chars', sum(len(r[2] or '') for r in rows))
    for r in rows:
        print('  ch', r[0], r[1], len(r[2] or ''))
