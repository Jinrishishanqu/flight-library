# -*- coding: utf-8 -*-
import os, re
R = r"D:\article_tools\out\final13"
pat = re.compile(r"[\u4e00-\u9fff]\\[\u4e00-\u9fff]")
n = 0
for root, d, fs in os.walk(R):
    for fn in fs:
        if not fn.endswith(".txt"):
            continue
        p = os.path.join(root, fn)
        t = open(p, encoding="utf-8", errors="replace", newline="").read()
        for m in pat.finditer(t):
            n += 1
            a, b = m.start(), m.end()
            print(f"[{os.path.relpath(p, R)}] {repr(t[max(0,a-30):b+30])}")
print("total", n)
