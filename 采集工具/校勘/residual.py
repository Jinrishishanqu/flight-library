# -*- coding: utf-8 -*-
"""残留枚举（对任意输出目录）"""
import os, re, collections, sys

OUT = sys.argv[1] if len(sys.argv) > 1 else r"D:\article_tools\out\clean2"
rx = re.compile(r"[^\u4e00-\u9fff\s，。！？、；：「」『』（）《》…—～·\"'“”‘’]{5,}")
c = collections.Counter()
files = 0
for root, dirs, fs in os.walk(OUT):
    dirs[:] = [d for d in dirs if not d.startswith("_")]
    for fn in fs:
        if not fn.lower().endswith(".txt"):
            continue
        files += 1
        with open(os.path.join(root, fn), "r", encoding="utf-8", errors="replace", newline="") as f:
            t = f.read()
        for m in rx.finditer(t):
            c[m.group()] += 1
print(f"files={files} distinct={len(c)} total={sum(c.values())}")
for s, n in c.most_common(30):
    print(f"{n}\t{s!r}")
