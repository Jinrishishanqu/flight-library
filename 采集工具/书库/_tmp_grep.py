import sqlite3, sys

DB = r'F:\新建文件夹\read - 副本\采集工具\书库\data\library.db'
c = sqlite3.connect('file:' + DB.replace('\\', '/') + '?mode=ro', uri=True)
c.text_factory = str

wid = int(sys.argv[1])
name = sys.argv[2]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 14
rad = int(sys.argv[4]) if len(sys.argv) > 4 else 200

w = c.execute("select id, title, source_work, genre, char_count, chapter_count, summary from works where id=?", (wid,)).fetchone()
print('WORK', w)
print('CHARS')
for r in c.execute("select name, role, gender, mentions, first_chapter, intro from characters where work_id=? order by mentions desc", (wid,)):
    print('  ', r[0], r[1], r[2], r[3], r[4], '|', (r[5] or '')[:80])

rows = c.execute("select idx, title, body_bi from chapters where work_id=? order by idx", (wid,)).fetchall()
print('CHAPTERS', len(rows))
hits = 0
for idx, title, body in rows:
    if not body:
        continue
    pos = 0
    while True:
        p = body.find(name, pos)
        if p < 0:
            break
        s = max(0, p - rad); e = min(len(body), p + len(name) + rad)
        print('\n[ch%d %s] %s' % (idx, title, body[s:e].replace('\n', ' ')))
        hits += 1
        pos = p + len(name)
        if hits >= limit:
            break
    if hits >= limit:
        break
print('\nSAMPLE HITS', hits)
