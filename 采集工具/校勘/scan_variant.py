import os, re, collections
B = r"D:\article_tools\out\final9"
WORDS = """肉棒 龟头 精液 射精 阴道 阴茎 阴唇 子宫 奶子 乳头 屁股 鸡巴 骚逼 小穴 淫水 高潮
淫穴 肉穴 肉洞 阳具 阴蒂 睾丸 乳房 淫荡 骚穴 肉屌 大屌 骚货 婊子 屄 屌 咪咪 屁眼
菊花 后庭 口交 肛交 乳交 足交 颜射 内射 中出 淫叫 浪叫 春药 媚药 淫液 蜜穴 花穴 花核
奶头 阴阜 包皮 前列腺 精ye 爱液 淫乱 骚妇 荡妇 淫妇 淫娃 巨乳 爆乳 豪乳 奶瓜 肥臀
骚屄 贱货 淫具 阳物 阴户 牝 雌 骚货 浪货 骚蹄子 淫纹 淫术 催情 发情 春潮 淫液""".split()

PAT = {}
for w in WORDS:
    if len(w) < 2:
        continue
    body = r"[^\u4e00-\u9fff\r\n]{1,3}".join(map(re.escape, list(w)))
    PAT[w] = re.compile(body)

hit = collections.Counter()
sample = []
for r, d, fs in os.walk(B):
    for fn in fs:
        if not fn.endswith(".txt"):
            continue
        fp = os.path.join(r, fn)
        with open(fp, encoding="utf-8", errors="replace", newline="") as f:
            t = f.read()
        for w, p in PAT.items():
            for m in p.finditer(t):
                s = m.group()
                if s == w:
                    continue
                hit[s] += 1
                if len(sample) < 60:
                    a = max(0, m.start() - 25); b = min(len(t), m.end() + 25)
                    sample.append((os.path.relpath(fp, B), s, t[a:b].replace("\n", " ").replace("\r", "")))
print("VARIANTS", sum(hit.values()), "KINDS", len(hit))
for s, n in hit.most_common(60):
    print(f"  {s}\t{n}")
print("--- samples ---")
for rel, s, ctx in sample:
    print(f"[{s}] {rel} | {ctx}")
