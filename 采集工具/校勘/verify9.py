# -*- coding: utf-8 -*-
import os, re, sys
A = r"D:\article_tools\out\final7"
B = r"D:\article_tools\out\final9"
TARGETS = [
    r"斗破\《斗破苍穹之恋足大陆》-全篇-70.6w.txt",
    r"斗破\《异世界奇幻 穿越斗破苍穹·淫乱萧炎后宫》-全篇-17.9w.txt",
    r"斗破\《《斗破之掠美六界》（1-37）作者：堕落王子WOAD》-全篇-7.8w.txt",
    r"凡人修仙传\《凡人修仙传同人：第二魔仙》-全篇-55.2w.txt",
    r"斗破\《全是鸡巴套子的斗破苍穹》-全篇-1.7w.txt",
]
LIMIT = 12
for rel in TARGETS:
    fa, fb = os.path.join(A, rel), os.path.join(B, rel)
    if not os.path.exists(fb):
        print("MISSING", rel); continue
    with open(fa, "r", encoding="utf-8", errors="replace", newline="") as f:
        la = f.read().split("\n")
    with open(fb, "r", encoding="utf-8", errors="replace", newline="") as f:
        lb = f.read().split("\n")
    print(f"\n##### {rel}  lines {len(la)} -> {len(lb)}")
    n = 0
    for i in range(min(len(la), len(lb))):
        if la[i] != lb[i]:
            n += 1
            if n <= LIMIT:
                print(f"  @{i+1} OLD: {la[i][:170]}")
                print(f"  @{i+1} NEW: {lb[i][:170]}")
    print(f"  changed_lines={n}")
