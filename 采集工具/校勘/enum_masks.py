# -*- coding: utf-8 -*-
"""枚举所有打码 token 的真实形态，供建映射表"""
import os, re, sys, collections

ROOT = r"D:\article_tools\work\校对后文章"

rx_py = re.compile(r"[A-Za-z]{2,10}(?=[液精穴道棒茎头胸臀裙腿干插射淫欲肉体肉鸽乳阴户唇舌臀尻肚腹股])")
rx_box = re.compile(r".{4}[囗□]{1,3}.{4}")
rx_pipe = re.compile(r".{3}[|｜].{3}")
rx_star = re.compile(r".{4}[*＊﹡]{2,}.{4}")

py = collections.Counter(); box = collections.Counter(); pipe = collections.Counter(); star = collections.Counter()

for root, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if not d.startswith("_")]
    for fn in files:
        if not fn.lower().endswith(".txt"): continue
        try:
            with open(os.path.join(root, fn), "r", encoding="utf-8", errors="replace", newline="") as fh:
                t = fh.read()
        except Exception: continue
        for m in rx_py.finditer(t):
            py[m.group()] += 1
        for m in rx_box.finditer(t):
            box[m.group()] += 1
        for m in rx_pipe.finditer(t):
            pipe[m.group()] += 1
        for m in rx_star.finditer(t):
            star[m.group()] += 1

def dump(name, c, top=60):
    print(f"\n=== {name} (distinct={len(c)}, total={sum(c.values())}) ===")
    for k, v in c.most_common(top):
        print(f"{v}\t{k!r}")

dump("PINYIN token", py)
dump("BOX ctx", box)
dump("PIPE ctx", pipe, 40)
dump("STAR ctx", star, 40)
