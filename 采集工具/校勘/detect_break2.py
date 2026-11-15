# -*- coding: utf-8 -*-
"""断词检测 v2：连写高频 + 断开极罕见 + 非功能字  => 判为异常断词"""
import os, re, collections, json

R = r"D:\article_tools\out\final17"
PAIR = re.compile(r"([\u4e00-\u9fff])[，。、；：]([\u4e00-\u9fff])")
BI = re.compile(r"(?=([\u4e00-\u9fff])([\u4e00-\u9fff]))")

FUNC = set("的了在是我你他她它们这那就也很都又还和与把被给对从到说要想会能可不为有着过啊呀吧呢嘛哦嗯吗么个地得之其所以如果但因而且并或则于一有不没最更太多少些什怎哪谁何")

pair_cnt = collections.Counter()
bi_cnt = collections.Counter()

for root, d, fs in os.walk(R):
    for fn in fs:
        if not fn.endswith(".txt"):
            continue
        t = open(os.path.join(root, fn), encoding="utf-8", errors="replace", newline="").read()
        pair_cnt.update(m.group(1) + m.group(2) for m in PAIR.finditer(t))
        bi_cnt.update(a + b for a, b in BI.findall(t))

print("pairs=%d bigrams=%d" % (len(pair_cnt), len(bi_cnt)))

cands = []
for k, pc in pair_cnt.items():
    if pc < 1:
        continue
    x, y = k[0], k[1]
    if x == y:
        continue
    if x in FUNC or y in FUNC:
        continue
    jc = bi_cnt.get(k, 0)
    if jc < 20:
        continue
    ratio = pc / jc
    if ratio < 0.15:
        cands.append((pc, jc, round(ratio, 4), k))

cands.sort(key=lambda r: (-r[0] / max(r[1], 1), -r[0]))
print("candidates=%d" % len(cands))
for pc, jc, r, k in cands:
    print(f"{k}\t断开{pc}\t连写{jc}\tratio={r}")
with open(r"D:\article_tools\out\break_cands2.json", "w", encoding="utf-8") as f:
    json.dump([[k, pc, jc, r] for pc, jc, r, k in cands], f, ensure_ascii=False, indent=0)
