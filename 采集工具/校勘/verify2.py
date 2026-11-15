# -*- coding: utf-8 -*-
"""窗口抽样验证：在原文里定位锚点，取前后窗口，与清洗版同锚点内容对照"""
import os, sys

SRC = r"D:\article_tools\work\校对后文章"
OUT = r"D:\article_tools\out\clean1"

# (文件, 锚点, 说明)  锚点必须原文里有、清洗后被改掉或保留
CASES = [
    ("斗破/《异世界奇幻 穿越斗破苍穹·淫乱萧炎后宫》-全篇-17.9w.txt", "最|新|网", "广告水印"),
    ("斗破/《斗破苍穹之恋足大陆》-全篇-70.6w.txt", "恋足大陆", "开篇正常段"),
    ("凡人修仙传/《凡人修仙传同人：第二魔仙》-全篇-55.2w.txt", "&nbsp", "实体残留"),
    ("大主宰/《大主宰九幽林静》-全篇-1.6w.txt", "牡尘", "专名"),
    ("斗破/《斗破苍穹同人系列》-全篇-34w.txt", "Rou棒", "拼音打码"),
]

def read(p):
    with open(p, "r", encoding="utf-8", errors="replace", newline="") as f:
        return f.read()

def win(t, i, pad=80):
    return t[max(0, i-pad):i+pad].replace("\r", "").replace("\n", "⏎")

for rel, anchor, tag in CASES:
    a, b = os.path.join(SRC, rel), os.path.join(OUT, rel)
    if not (os.path.exists(a) and os.path.exists(b)):
        print(f"[skip] {rel}")
        continue
    ta, tb = read(a), read(b)
    i = ta.find(anchor)
    print(f"\n{'='*72}\n[{tag}] {os.path.basename(rel)}  chars {len(ta)}->{len(tb)}")
    if i < 0:
        print("  anchor not in source")
        continue
    print(f"  OLD @{i}: {win(ta,i)!r}")
    # 用锚点邻域去新版里定位：取锚点前 12 字作为新锚
    pre = ta[max(0, i-12):i]
    j = tb.find(pre) if pre else -1
    if j < 0:
        # 退化：用锚点前 6 字
        pre2 = ta[max(0, i-6):i]
        j = tb.find(pre2) if pre2 else -1
        pre = pre2
    if j >= 0:
        k = j + len(pre)
        print(f"  NEW @{k}: {win(tb,k)!r}")
    else:
        print("  NEW: anchor neighborhood lost (whole segment may be deleted)")
