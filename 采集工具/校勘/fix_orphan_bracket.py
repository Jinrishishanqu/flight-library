# -*- coding: utf-8 -*-
"""删除孤立的中文方括号 【 】（无法配对的那些），保留正常成对用法。

背景：早期清理删掉了部分半角 [ ，导致「【对话】」只剩右半边成了「对话】」。
成对的 【人物卡】 之类保持不动。

用法：python fix_orphan_bracket.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "校勘版_reflow")
OUT = os.path.join(ROOT, "校勘版_final")


def clean(t):
    """按行做栈式配对（行内优先，避免跨行错配），返回 (新文本, 删左数, 删右数)。

    行内孤立才算孤立：一行里有】没【，或反过来。跨行包裹的写法极少，
    冒这个险会让整段错位，不如保守按行。
    """
    nl = nr = 0
    lines = t.split("\n")
    for k, line in enumerate(lines):
        if "【" not in line and "】" not in line:
            continue
        stack = []
        drop = set()
        for i, c in enumerate(line):
            if c == "【":
                stack.append(i)
            elif c == "】":
                if stack:
                    stack.pop()
                else:
                    drop.add(i)
        for i in stack:
            drop.add(i)
        if not drop:
            continue
        nl += sum(1 for i in drop if line[i] == "【")
        nr += len(drop) - nl
        lines[k] = "".join(c for i, c in enumerate(line) if i not in drop)
    return "\n".join(lines), nl, nr


def main():
    total = {"files": 0, "changed": 0, "left": 0, "right": 0, "chars_in": 0, "chars_out": 0}
    detail = []
    for dirpath, _d, fns in os.walk(SRC):
        for fn in fns:
            if not fn.endswith(".txt"):
                continue
            fp = os.path.join(dirpath, fn)
            with open(fp, "r", encoding="utf-8", errors="replace", newline="") as f:
                raw = f.read()
            new, nl, nr = clean(raw)
            total["files"] += 1
            total["chars_in"] += len(raw)
            total["chars_out"] += len(new)
            if new != raw:
                total["changed"] += 1
                total["left"] += nl
                total["right"] += nr
                detail.append((nl + nr, fn))
            dest = os.path.join(OUT, os.path.relpath(fp, SRC))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8", newline="") as f:
                f.write(new)

    print(f"files={total['files']} changed={total['changed']} "
          f"LRM 删【{total['left']} 删】{total['right']}")
    print(f"chars {total['chars_in']} -> {total['chars_out']} "
          f"({total['chars_out'] - total['chars_in']})")
    detail.sort(reverse=True)
    for n, fn in detail[:12]:
        print(f"  {n:3d}  {fn}")


if __name__ == "__main__":
    main()
