# -*- coding: utf-8 -*-
"""打印被打断词汇的上下文，供人工判定"""
import os, re, sys

SRC = r"D:\article_tools\out\final17"
target = sys.argv[1] if len(sys.argv) > 1 else "臀"
p = re.compile(re.escape(target[0]) + r"[，、]" + re.escape(target[1]))

n = 0
for root, d, fs in os.walk(SRC):
    for fn in fs:
        if not fn.endswith(".txt"):
            continue
        fp = os.path.join(root, fn)
        t = open(fp, encoding="utf-8", errors="replace", newline="").read()
        for m in p.finditer(t):
            a = max(0, m.start() - 22)
            b = min(len(t), m.end() + 22)
            ctx = t[a:b].replace("\r", "").replace("\n", "⏎")
            print("%s | %s" % (fn, ctx))
            n += 1
            if n >= 60:
                print("...truncated")
                sys.exit(0)
print("total=%d" % n)
