# -*- coding: utf-8 -*-
import os, re, collections
R = r"D:\article_tools\out\final15"
cq = collections.Counter()
cb = collections.Counter()
for root, d, fs in os.walk(R):
    for fn in fs:
        if not fn.endswith(".txt"):
            continue
        p = os.path.join(root, fn)
        t = open(p, encoding="utf-8", errors="replace", newline="").read()
        for m in re.finditer(r"@", t):
            a = m.start()
            cq[t[max(0, a - 30):a + 30].replace("\r", "").replace("\n", "|")] += 1
        for m in re.finditer(r"\\", t):
            a = m.start()
            cb[t[max(0, a - 30):a + 30].replace("\r", "").replace("\n", "|")] += 1
print("=== @ x%d ===" % sum(cq.values()))
for k, v in cq.most_common(12):
    print(f"{v}\t{k}")
print("=== backslash x%d ===" % sum(cb.values()))
for k, v in cb.most_common(12):
    print(f"{v}\t{k}")
