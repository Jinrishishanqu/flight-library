# -*- coding: utf-8 -*-
"""把场景性错字变体统一回正写（校勘版已交付层）。

本轮：萧黛儿 → 萧薰儿（295 处 / 5 个文件）。
用法：python fix_variant_names.py [--apply]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(r"F:\新建文件夹\read - 副本")
CANON = ROOT / "校勘版"

PAIRS = [
    ("萧黛儿", "萧薰儿"),   # 萧黛儿是萧薰儿的场景错误变体
]


def main() -> int:
    apply = "--apply" in sys.argv
    total = 0
    files = 0
    for p in sorted(CANON.rglob("*.txt")):
        t = p.open("r", encoding="utf-8", errors="replace", newline="").read()
        orig = t
        per = []
        for bad, good in PAIRS:
            n = t.count(bad)
            if n:
                t = t.replace(bad, good)
                per.append(f"{bad}->{good} x{n}")
                total += n
        if t != orig:
            files += 1
            print(f"{p.relative_to(CANON)} | " + ", ".join(per))
            if apply:
                p.open("w", encoding="utf-8", newline="").write(t)
    print(f"\nfiles={files} hits={total} apply={apply}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
