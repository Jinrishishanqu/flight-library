import sqlite3, io, re, os
db = r"F:\新建文件夹\read - 副本\采集工具\书库\data\library.db"
out = r"F:\新建文件夹\read - 副本\采集工具\_tmp_txt"
os.makedirs(out, exist_ok=True)
c = sqlite3.connect(db)
c.row_factory = sqlite3.Row
names = {22: ["南宫婉", "韩立", "银月", "元瑶", "冰凤", "黛儿", "黑脸"],
         444: ["张小凡", "苏茹", "田不易", "田灵儿", "陆雪琪", "齐昊"],
         340: ["古月", "唐舞麟", "王喆", "叶星澜", "许小言", "杨念夏", "娜儿", "墨蓝"]}
for wid, ns in names.items():
    rows = c.execute("select idx,title,content from chapters where work_id=? order by idx", (wid,)).fetchall()
    full = "\n".join(f"【第{r['idx']}节 {r['title'] or ''}】\n" + (r['content'] or "") for r in rows)
    with io.open(os.path.join(out, f"w{wid}_full.txt"), "w", encoding="utf-8") as f:
        f.write(full)
    paras = [p.strip() for p in re.split(r"\n+", full) if p.strip()]
    for n in ns:
        hits = [p for p in paras if n in p]
        with io.open(os.path.join(out, f"w{wid}_{n}.txt"), "w", encoding="utf-8") as f:
            f.write("\n\n".join(hits))
        print(wid, n, len(hits), sum(len(h) for h in hits))
    print(wid, "chars", len(full))
