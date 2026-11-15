import sqlite3, sys

DB = r'F:\新建文件夹\read - 副本\采集工具\书库\data\library.db'
c = sqlite3.connect('file:' + DB.replace('\\', '/') + '?mode=ro', uri=True)
c.text_factory = str

wid = int(sys.argv[1])
name = sys.argv[2]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
rad = int(sys.argv[4]) if len(sys.argv) > 4 else 250

rows = c.execute("select idx, title, content, body_bi from chapters where work_id=? order by idx", (wid,)).fetchall()
print('CHAPTERS', len(rows), 'first lens', [(r[0], len(r[2] or ''), len(r[3] or '')) for r in rows[:3]])
hits = 0
for idx, title, body, bi in rows:
    text = body or ''
    if not text:
        continue
    pos = 0
    while True:
        p = text.find(name, pos)
        if p < 0:
            break
        s = max(0, p - rad); e = min(len(text), p + len(name) + rad)
        print('\n[ch%d %s] %s' % (idx, title, text[s:e].replace('\n', ' ')))
        hits += 1
        pos = p + len(name)
        if hits >= limit:
            break
    if hits >= limit:
        break
print('\nHITS', hits)
