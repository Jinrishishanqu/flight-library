# -*- coding: utf-8 -*-
"""把残留的全角双引号 ＂(U+FF02) 按出现顺序交替转成「」。

项目正文的引号口径是直角引号「」，但 9 个文件里还留着 574 个 ＂
（《斗破苍穹同人系列》274、《斗破苍穹－黑暗奴隶拍卖大会》267 等）。
这些书的原文就是用 ＂ 当对话引号，成对出现，按顺序交替即可正确还原。

奇数个残留在文件末尾会保留原样并报告出来，交人工确认。

用法：
  python fix_fullwidth_quotes.py --dry
  python fix_fullwidth_quotes.py --apply
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(r"F:\新建文件夹\read - 副本")
SRC = ROOT / "校勘版_wide"
OUT = ROOT / "校勘版_q"


def convert(t: str) -> tuple[str, int, int]:
    """按「栈」判定：文件里已有的「」参与配对，＂ 视栈状态决定开/闭。

    栈空 → ＂ 当开引号「；栈非空 → 当闭引号」。
    这样与早前 D_quote 已转好的部分协不错位。
    """
    out = []
    depth = 0
    n = 0
    for ch in t:
        if ch == "「":
            depth += 1
            out.append(ch)
        elif ch == "」":
            depth = max(0, depth - 1)
            out.append(ch)
        elif ch == "\uff02":
            if depth == 0:
                out.append("「")
                depth += 1
            else:
                out.append("」")
                depth -= 1
            n += 1
        else:
            out.append(ch)
    return "".join(out), n, depth


def main() -> int:
    apply = "--apply" in sys.argv
    files = sorted(SRC.rglob("*.txt"))
    total = changed = 0
    for fp in files:
        raw = fp.open("r", encoding="utf-8", errors="replace", newline="").read()
        new, n, left = convert(raw)
        if n:
            total += n
            if raw != new:
                changed += 1
            flag = "  ⚠ 奇数个：最后一个是未闭合的「，需人工补 」" if left else ""
            print(f"  {fp.relative_to(SRC)}: ＂{n} → 「」{flag}")
        if apply:
            rel = fp.relative_to(SRC)
            dest = OUT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.open("w", encoding="utf-8", newline="").write(new)
    print(f"\n共转换 {total} 个 ＂，改动 {changed} 文件")
    if apply:
        print(f"已写出 {OUT}")
    else:
        print("（--dry，未写盘）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
