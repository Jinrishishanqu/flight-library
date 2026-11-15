# -*- coding: utf-8 -*-
"""对比 clean1 前后同一位置的文本，抽样人工核验"""
import os, sys, json, random, difflib

SRC = r"D:\article_tools\work\校对后文章"
OUT = r"D:\article_tools\out\clean1"
led = json.load(open(os.path.join(OUT, "_ledger.json"), encoding="utf-8"))

targets = sys.argv[1:] or [
    "斗破/《异世界奇幻 穿越斗破苍穹·淫乱萧炎后宫》-全篇-17.9w.txt",
    "斗破/《斗破苍穹之恋足大陆》-全篇-70.6w.txt",
    "斗破/《斗破苍穹同人系列》-全篇-34w.txt",
    "凡人修仙传/《凡人修仙传同人：第二魔仙》-全篇-55.2w.txt",
    "大主宰/《大主宰九幽林静》-全篇-1.6w.txt",
]

for rel in targets:
    a = os.path.join(SRC, rel)
    b = os.path.join(OUT, rel)
    if not (os.path.exists(a) and os.path.exists(b)):
        print(f"[skip] {rel}")
        continue
    with open(a, "r", encoding="utf-8", errors="replace", newline="") as f:
        ta = f.read()
    with open(b, "r", encoding="utf-8", errors="replace", newline="") as f:
        tb = f.read()
    print(f"\n{'='*70}\n{rel}\n  chars {len(ta)} -> {len(tb)}")
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    ops = [o for o in sm.get_opcodes() if o[0] != "equal"]
    print(f"  diff_blocks={len(ops)}")
    for op, i1, i2, j1, j2 in ops[:6]:
        pre = ta[max(0, i1-30):i1].replace("\r", "").replace("\n", "⏎")
        old = ta[i1:i2].replace("\r", "").replace("\n", "⏎")
        new = tb[j1:j2].replace("\r", "").replace("\n", "⏎")
        print(f"  [{op}] …{pre}")
        print(f"     OLD: {old[:120]!r}")
        print(f"     NEW: {new[:120]!r}")
