# -*- coding: utf-8 -*-
import sqlite3, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
db = r'F:\新建文件夹\read - 副本\采集工具\书库\data\library.db'
out = r'F:\新建文件夹\read - 副本\_tmp_txt'
os.makedirs(out, exist_ok=True)
con = sqlite3.connect(db)
for wid in (176, 480, 409):
    lines = []
    for idx, title, content in con.execute("select idx,title,content from chapters where work_id=? order by idx", (wid,)):
        lines.append(f"\n\n########## CH{idx} {title}\n")
        lines.append((content or '').replace('\n', '\n'))
    p = os.path.join(out, f"{wid}.txt")
    with open(p, 'w', encoding='utf-8') as f:
        f.write(''.join(lines))
    print(p, os.path.getsize(p))
