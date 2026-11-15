import sqlite3, os
c = sqlite3.connect(r'data/library.db')
os.makedirs(r'_txt', exist_ok=True)
for wid in [124, 479, 135, 367]:
    rows = list(c.execute("select idx,title,content from chapters where work_id=? order by idx", (wid,)))
    buf = []
    for r in rows:
        buf.append(f"\n\n########## CH {r[0]} {r[1]} ##########\n")
        buf.append(r[2] or '')
    with open(rf'_txt\{wid}.txt', 'w', encoding='utf-8') as f:
        f.write(''.join(buf))
    print(wid, 'ok')
