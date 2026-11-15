# -*- coding: utf-8 -*-
"""检测「单字+标点+单字」形态的防和谐断词，用后缀集中度判别"""
import os, re, collections, json

R = r"D:\article_tools\out\final17"
PAIR = re.compile(r"([\u4e00-\u9fff])[，。、；：]([\u4e00-\u9fff])")
HEAD = re.compile(r"([\u4e00-\u9fff])[，。、；：]")

pair = collections.Counter()
head = collections.Counter()
for root, d, fs in os.walk(R):
    for fn in fs:
        if not fn.endswith(".txt"):
            continue
        t = open(os.path.join(root, fn), encoding="utf-8", errors="replace", newline="").read()
        pair.update(m.group(1) + m.group(2) for m in PAIR.finditer(t))
        head.update(m.group(1) for m in HEAD.finditer(t))

cands = []
for k, v in pair.items():
    if v < 2:
        continue
    h = head[k[0]]
    if h == 0:
        continue
    ratio = v / h
    if ratio >= 0.5:
        cands.append((v, round(ratio, 2), k))
cands.sort(reverse=True)
print("candidates=%d" % len(cands))
for v, r, k in cands[:120]:
    print(f"{v}\t{r}\t{k}")
with open(r"D:\article_tools\out\break_cands.json", "w", encoding="utf-8") as f:
    json.dump([[k, v, r] for v, r, k in cands], f, ensure_ascii=False, indent=0)
