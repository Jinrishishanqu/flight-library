# -*- coding: utf-8 -*-
import os, re, collections
R = r"D:\article_tools\out\final14"
ascii_q = re.compile(r'[\u4e00-\u9fff]"[^"\r\n]{0,40}')
hash_pat = re.compile(r'.{0,20}#.{0,20}')
cq = collections.Counter()
ch = collections.Counter()
for root, d, fs in os.walk(R):
    for fn in fs:
        if not fn.endswith(".txt"):
            continue
        p = os.path.join(root, fn)
        t = open(p, encoding="utf-8", errors="replace", newline="").read()
        for m in re.finditer(r'"', t):
            a = m.start()
            cq[t[max(0, a - 25):a + 25].replace("\r", "").replace("\n", "|")] += 1
        for m in re.finditer(r'#', t):
            a = m.start()
            ch[t[max(0, a - 20):a + 20].replace("\r", "").replace("\n", "|")] += 1
print("=== 半角双引号 剩余 %d 处，前 15 上下文 ===" % sum(cq.values()))
for k, v in cq.most_common(15):
    print(f"{v}\t{k}")
print("=== # 剩余 %d 处，前 15 上下文 ===" % sum(ch.values()))
for k, v in ch.most_common(15):
    print(f"{v}\t{k}")
