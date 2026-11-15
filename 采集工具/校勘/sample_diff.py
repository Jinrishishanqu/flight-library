# -*- coding: utf-8 -*-
"""抽样对比：原始 vs 校勘版，输出差异行（限制条数）"""
import os, re, sys, difflib

SRC = r"D:\article_tools\work\校对后文章"
DST = r"D:\article_tools\out\final2"

def pick(n=8):
    rows = []
    for root, dirs, fs in os.walk(DST):
        for fn in fs:
            if not fn.lower().endswith(".txt"):
                continue
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, DST)
            op = os.path.join(SRC, rel)
            if not os.path.exists(op):
                continue
            sa = os.path.getsize(op); sb = os.path.getsize(fp)
            rows.append((sa - sb, rel))
    rows.sort(reverse=True)
    return rows[:n]

def main():
    print("=== 体积变化最大的文件 ===")
    for d, rel in pick(12):
        print(f"{d:>8} \t{rel}")
    print("\n=== 差异样本 ===")
    for d, rel in pick(4):
        op = os.path.join(SRC, rel); np_ = os.path.join(DST, rel)
        a = open(op, encoding="utf-8", errors="replace", newline="").read().split("\n")
        b = open(np_, encoding="utf-8", errors="replace", newline="").read().split("\n")
        print(f"\n##### {rel}  ({len(a)} -> {len(b)} 行)")
        cnt = 0
        for line in difflib.unified_diff(a, b, lineterm="", n=0):
            if line.startswith(("---", "+++")):
                continue
            if cnt >= 14:
                break
            print(line[:220])
            cnt += 1

if __name__ == "__main__":
    main()
