# -*- coding: utf-8 -*-
"""对比两版输出，抽取指定类别改动样本"""
import os, re, sys, collections

A = r"D:\article_tools\out\final7"
B = sys.argv[2] if len(sys.argv) > 2 else r"D:\article_tools\out\final11"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 50

ISO = re.compile(r"(?:[\u4e00-\u9fff]，){3,}")
PW = re.compile(r"(春|爱|淫|婊|骚|豪|巨|足|口|肛|屁)([^\u4e00-\u9fff…\r\n]){1,3}(药|液|叫|子|货|屄|乳|交|眼)")

rows = []
for root, dirs, fs in os.walk(A):
    for fn in fs:
        if not fn.lower().endswith(".txt"):
            continue
        fa = os.path.join(root, fn)
        rel = os.path.relpath(fa, A)
        fb = os.path.join(B, rel)
        if not os.path.exists(fb):
            continue
        with open(fa, "r", encoding="utf-8", errors="replace", newline="") as f:
            la = f.read().split("\n")
        with open(fb, "r", encoding="utf-8", errors="replace", newline="") as f:
            lb = f.read().split("\n")
        for i, (x, y) in enumerate(zip(la, lb)):
            if x == y:
                continue
            if ISO.search(x) or PW.search(x):
                rows.append((rel, i + 1, x.strip()[:120], y.strip()[:120]))

print(f"matched_lines={len(rows)}")
for rel, ln, x, y in rows[:LIMIT]:
    print(f"[{rel}:{ln}]")
    print(f"  - {x}")
    print(f"  + {y}")
