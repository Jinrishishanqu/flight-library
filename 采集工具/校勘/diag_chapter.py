# -*- coding: utf-8 -*-
"""诊断章标题形态：第N章 后面接什么、行有多长、标题能否与正文分离。"""
import os
import re
import sys
import collections

sys.stdout.reconfigure(encoding="utf-8")

SRC = r"F:\新建文件夹\read - 副本\校勘版"

CH = re.compile(r"第[0-9零一二三四五六七八九十百千两]+[章节回]")
NUM = re.compile(r"[0-9零一二三四五六七八九十百千两]+")

stats = collections.Counter()
samples = collections.defaultdict(list)
line_len_after = []

for dirpath, _dirnames, filenames in os.walk(SRC):
    for fn in filenames:
        if not fn.endswith(".txt"):
            continue
        fp = os.path.join(dirpath, fn)
        with open(fp, "r", encoding="utf-8", errors="replace", newline="") as f:
            t = f.read()
        for m in CH.finditer(t):
            tail = t[m.end():m.end() + 60]
            # 前后文
            prev = t[max(0, m.start() - 6):m.start()]
            kind = None
            if not tail:
                kind = "eof"
            elif tail[0] in " \u3000\t":
                kind = "space"
            elif tail[0] == "\r" or tail[0] == "\n":
                kind = "newline"
            elif re.match(r"[^\u4e00-\u9fff]", tail[0]):
                kind = "punct"
            else:
                kind = "glued"          # 直接粘汉字
            # 前方是否有换行（章节是否从行首开始）
            at_line_start = prev.endswith("\n") or prev.endswith("\r") or m.start() == 0
            stats[kind] += 1
            if not at_line_start:
                stats["NOT_LINE_START"] += 1
            if kind == "glued":
                # 粘连后 40 字里有没有标点；取到第一个标点的长度
                mm = re.search(r"[，。！？、；：…]", tail)
                cut = mm.start() if mm else len(tail)
                line_len_after.append(cut)
                if len(samples["glued"]) < 12:
                    samples["glued"].append(fn + " || " + repr(t[m.start():m.end() + 46]))
            if kind == "space" and len(samples["space"]) < 6:
                samples["space"].append(fn + " || " + repr(t[m.start():m.end() + 40]))

print("== 第N章 之后第一个字符的类型 ==")
for k, v in stats.most_common():
    print(f"  {k:14s} {v}")
print()
print(f"== 粘连型（第N章 后直接汉字），共 {len(line_len_after)} 处 ==")
if line_len_after:
    line_len_after.sort()
    n = len(line_len_after)
    print(f"  到首个标点的字数分布: min={line_len_after[0]} "
          f"p25={line_len_after[n//4]} med={line_len_after[n//2]} "
          f"p75={line_len_after[3*n//4]} max={line_len_after[-1]}")
    print(f"  ≤24 字: {sum(1 for x in line_len_after if x <= 24)}  "
          f"≤30 字: {sum(1 for x in line_len_after if x <= 30)}")
print()
print("== glued 样本 ==")
for s in samples["glued"]:
    print("  " + s)
print()
print("== space 样本 ==")
for s in samples["space"]:
    print("  " + s)

# 超长段分布
print()
print("== 段长分布（校勘版） ==")
buckets = collections.Counter()
longest = []
for dirpath, _dirnames, filenames in os.walk(SRC):
    for fn in filenames:
        if not fn.endswith(".txt"):
            continue
        fp = os.path.join(dirpath, fn)
        with open(fp, "r", encoding="utf-8", errors="replace", newline="") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                L = len(s)
                if L <= 60:
                    buckets["<=60"] += 1
                elif L <= 120:
                    buckets["61-120"] += 1
                elif L <= 200:
                    buckets["121-200"] += 1
                elif L <= 400:
                    buckets["201-400"] += 1
                elif L <= 800:
                    buckets["401-800"] += 1
                elif L <= 2000:
                    buckets["801-2000"] += 1
                else:
                    buckets[">2000"] += 1
                if L > 800:
                    longest.append((L, fn))
for k in ["<=60", "61-120", "121-200", "201-400", "401-800", "801-2000", ">2000"]:
    print(f"  {k:10s} {buckets[k]}")
longest.sort(reverse=True)
print(f"  >800 字段落共 {len(longest)} 个，最长 5 个：")
for L, fn in longest[:5]:
    print(f"    {L:7d}  {fn}")
