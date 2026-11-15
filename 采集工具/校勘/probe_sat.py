# -*- coding: utf-8 -*-
"""用 wtpsplit 的 SaT 模型做语义分句，与自研 reflow 的规则分句对比。

SaT（Segment any Text, EMNLP 2024）多语言模型，85 语言含中文，
官方 lang_code='zh' 建议 target_length=45 spread=15。

用法：
  python probe_sat.py <文件> [段落序号]
  python probe_sat.py <文件> --longest     # 取最长段
"""
from __future__ import annotations

import pathlib
import sys


def load(p: pathlib.Path) -> str:
    return p.open("r", encoding="utf-8", errors="replace", newline="").read()


def paras(text: str) -> list[str]:
    out = []
    for line in text.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if s:
            out.append(s)
    return out


def reflow_split(s: str, target_max: int = 170) -> list[str]:
    """复刻 reflow.py 的规则：只在句末/对话边界切，累计到 target_max 再切。"""
    END = "。！？…」』）"
    SOFT = "，；、：—～·"
    BAD_HEAD = set("的地得着了过而则就都也又还且并但却是在被把让给对向从于之其此该很更最与和")
    depth = 0
    cuts = [0]
    for i, ch in enumerate(s):
        if ch == "「":
            depth += 1
        elif ch == "」":
            depth = max(0, depth - 1)
        elif depth == 0 and ch in END and i + 1 < len(s) and s[i + 1] not in BAD_HEAD:
            if i + 1 - cuts[-1] >= 60:
                cuts.append(i + 1)
    cuts.append(len(s))
    return [s[a:b] for a, b in zip(cuts, cuts[1:])]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    p = pathlib.Path(sys.argv[1])
    if not p.is_absolute():
        p = pathlib.Path(r"F:\新建文件夹\read - 副本") / p
    text = load(p)
    ps = paras(text)
    if "--longest" in sys.argv:
        idx = max(range(len(ps)), key=lambda i: len(ps[i]))
    else:
        nums = [a for a in sys.argv[2:] if a.isdigit()]
        idx = int(nums[0]) if nums else 0
    seg = ps[idx]
    print(f"文件 {p.name}")
    print(f"段落 #{idx}，{len(seg)} 字")
    print(f"开头：{seg[:80]}")
    print()

    from wtpsplit import SaT

    print("加载 sat-3l-sm …")
    sat = SaT("sat-3l-sm")
    try:
        sents = sat.split(seg, lang_code="zh", min_length=1, max_length=2000)
    except TypeError:
        sents = sat.split(seg)
    sents = [s for s in sents if s.strip()]
    print(f"SaT 切出 {len(sents)} 句，长度分布：{sorted(len(s) for s in sents)[:8]} … max {max(len(s) for s in sents)}")
    print(f"重建一致：{''.join(sents) == seg}")
    print()
    for s in sents[:12]:
        print(f"  [{len(s):>4}] {s[:70]}")

    print()
    mine = reflow_split(seg)
    print(f"reflow 规则切出 {len(mine)} 段，长度分布：{sorted(len(s) for s in mine)[:8]} … max {max(len(s) for s in mine)}")
    for s in mine[:8]:
        print(f"  [{len(s):>4}] {s[:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
