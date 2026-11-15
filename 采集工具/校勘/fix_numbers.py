# -*- coding: utf-8 -*-
"""数字层清理：全角数字归一、拆散数字串合拢、数字与连字符间空格。

背景：早期 OCR / 转录留下
    依１曰散发着     → 依旧散发着
    从１５７４- １５８９ → 从1574-1589
    2 0多年          → 20多年

用法：python fix_numbers.py
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "校勘版")
OUT = os.path.join(ROOT, "校勘版_num")

# 全角数字 → 半角
FW = "０１２３４５６７８９"
HALF = "0123456789"
FW_MAP = str.maketrans(FW, HALF)

# 数字被空格拆开：2 0 多 → 20多；１ ５ ７ ４ → 1574
SPREAD = re.compile(r"\d(?:[ \t]\d)+")
# 数字与连接号之间的空格
DASH1 = re.compile(r"(?<=\d)[ \t]+([-－—–])")
DASH2 = re.compile(r"([-－—–])[ \t]+(?=\d)")

# 定点修正
EXACT = [
    ("依1曰", "依旧"),
    ("依１曰", "依旧"),
]


def fix(t):
    st = {"fw": 0, "spread": 0, "dash": 0, "exact": 0}

    def _spread(m):
        st["spread"] += 1
        return re.sub(r"[ \t]", "", m.group(0))

    def _d1(m):
        st["dash"] += 1
        return m.group(1)

    def _d2(m):
        st["dash"] += 1
        return m.group(1)

    for a, b in EXACT:
        if a in t:
            st["exact"] += t.count(a)
            t = t.replace(a, b)

    # 先合拢拆散串（此时还是全角数字，单独处理全角）
    t2 = SPREAD.sub(_spread, t)
    t = t2

    n_fw = sum(t.count(c) for c in FW)
    if n_fw:
        st["fw"] = n_fw
        t = t.translate(FW_MAP)

    t = DASH1.sub(_d1, t)
    t = DASH2.sub(_d2, t)
    return t, st


def main():
    total = {"files": 0, "changed": 0, "fw": 0, "spread": 0, "dash": 0, "exact": 0,
             "chars_in": 0, "chars_out": 0}
    for dirpath, _d, fns in os.walk(SRC):
        for fn in fns:
            if not fn.endswith(".txt"):
                continue
            fp = os.path.join(dirpath, fn)
            with open(fp, "r", encoding="utf-8", errors="replace", newline="") as f:
                raw = f.read()
            new, st = fix(raw)
            total["files"] += 1
            total["chars_in"] += len(raw)
            total["chars_out"] += len(new)
            for k in ("fw", "spread", "dash", "exact"):
                total[k] += st[k]
            if new != raw:
                total["changed"] += 1
            dest = os.path.join(OUT, os.path.relpath(fp, SRC))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="") as f:
                f.write(new)
    print(f"files={total['files']} changed={total['changed']}")
    print(f"全角数字 {total['fw']}  拆散数字串 {total['spread']}  "
          f"连接号空格 {total['dash']}  定点 {total['exact']}")
    print(f"chars {total['chars_in']} -> {total['chars_out']} "
          f"({total['chars_out'] - total['chars_in']})")


if __name__ == "__main__":
    main()
