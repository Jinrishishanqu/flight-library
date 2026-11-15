# -*- coding: utf-8 -*-
"""修复 文档\阅读站-设计规范.md 中「标 → 题」的误替换。

只做定点替换，不碰「问题 / 主题 / 题材 / 题目 / 议题」等正常词。
"""
import re
import sys
from pathlib import Path

FP = Path(r"F:\新建文件夹\read - 副本\文档\阅读站-设计规范.md")

# 顺序很重要：长串优先
RULES = [
    ("题题", "标题"),
    ("题签", "标签"),
    ("题记", "标记"),
    ("指题", "指标"),
    ("鼠题", "鼠标"),
    ("题点", "标点"),
    ("图题", "图标"),
    ("宽字距小题", "宽字距小标"),
    ("小字题原作名", "小字标原作名"),
    ("右侧题该节字数", "右侧标该节字数"),
]

def main() -> int:
    raw = FP.open("r", encoding="utf-8", errors="replace", newline="").read()
    out = raw
    counts = {}
    for old, new in RULES:
        n = out.count(old)
        if n:
            counts[f"{old} → {new}"] = n
            out = out.replace(old, new)
    if out == raw:
        print("no change")
        return 0
    FP.open("w", encoding="utf-8", newline="").write(out)
    for k, v in counts.items():
        print(f"{k}: {v}")
    print(f"len {len(raw)} -> {len(out)}")
    # 残留危险词
    left = re.findall(r"题[签记题点]", out)
    print("residual suspicious:", left[:10] if left else "none")
    return 0

if __name__ == "__main__":
    sys.exit(main())
