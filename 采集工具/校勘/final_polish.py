# -*- coding: utf-8 -*-
"""final7：清理汉字间污染空格 + 高频错别字对（在 final6 基础上）"""
import os, re, json, collections

SRC = r"D:\article_tools\out\final6"
OUT = r"D:\article_tools\out\final7"

# 汉字之间的空白（含全角空格）→ 删除
CJK_GAP = re.compile(r"(?<=[\u4e00-\u9fff])[ \t\u3000]+(?=[\u4e00-\u9fff])")
# 汉字与中文标点之间的空白 → 删除
CJK_PUNCT_GAP = re.compile(r"(?<=[\u4e00-\u9fff，。！？、；：「」『』（）《》…—～])[ \t\u3000]+(?=[，。！？、；：」』）…—～])")
# 标点后接汉字前的空白 → 删除
PUNCT_CJK_GAP = re.compile(r"(?<=[，。！？、；：「」『』（）《》…—～])[ \t\u3000]+(?=[\u4e00-\u9fff])")

TYPOS = [
    ("呻咛", "呻吟"),
    ("孜孜不厌", "孜孜不倦"),
    ("按耐", "按捺"),
    ("紧崩", "紧绷"),
    ("一泄如注", "一泻如注"),
    ("不能自己", "不能自已"),
    ("迫不急待", "迫不及待"),
    ("一股作气", "一鼓作气"),
    ("由然而生", "油然而生"),
    ("既使", "即使"),
    ("既便", "即便"),
    ("竟然", "竟然"),
]

def process(t, c):
    t, n = CJK_PUNCT_GAP.subn("", t); c["gap_punct"] = n
    t, n = PUNCT_CJK_GAP.subn("", t); c["gap_afterpunct"] = n
    for a, b in TYPOS:
        if a == b:
            continue
        cnt = t.count(a)
        if cnt:
            t = t.replace(a, b)
            c["typo_" + a] = cnt
    t, n = CJK_GAP.subn("", t); c["gap_cjk"] = n
    return t

def main():
    os.makedirs(OUT, exist_ok=True)
    tot = collections.Counter()
    nf = ch = 0
    for root, dirs, fs in os.walk(SRC):
        for fn in fs:
            if not fn.lower().endswith(".txt"):
                continue
            fp = os.path.join(root, fn)
            rel = os.path.relpath(fp, SRC)
            with open(fp, "r", encoding="utf-8", errors="replace", newline="") as f:
                t0 = f.read()
            c = collections.Counter()
            t = process(t0, c)
            dest = os.path.join(OUT, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="") as fh:
                fh.write(t)
            nf += 1
            if t != t0:
                ch += 1
            tot.update(c)
    print(f"files={nf} changed={ch}")
    for k in sorted(tot):
        if tot[k]:
            print(f"{k}\t{tot[k]}")

if __name__ == "__main__":
    main()
