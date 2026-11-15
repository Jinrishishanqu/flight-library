# -*- coding: utf-8 -*-
"""
fix_glyph.py — 形近错字 / 重复字 / 人称订正
输入 校勘版 -> 输出 校勘版_new

只做「有明确频次证据」的替换：
  闻言 1186 : 闻然 19
  猛地 3454 : 猛得 34
  日后  461 : 曰后  5
  白皙 1696 : 白勺  1
  三千  191 : 三干  1
不碰：。。/，，/了了 —— 浪叫拖音与口语风格，非错字。
"""
import re
import sys
from pathlib import Path

SRC = Path(r"F:\新建文件夹\read - 副本\校勘版")
OUT = Path(r"F:\新建文件夹\read - 副本\校勘版_new")

# (名称, 正则, 替换)  —— 顺序执行
RULES = [
    ("白勺", r"白勺", "的"),
    # 日/曰
    ("曰出曰落", r"曰出曰落", "日出日落"),
    ("曰落曰出", r"曰落曰出", "日落日出"),
    ("曰后", r"曰后", "日后"),
    ("X曰", r"(?<=[数今昨明次当几早平昔])曰", "日"),
    ("干作千", r"(?<=[一二三四五六七八九十几数])干(?=[年月日里万次天青])", "千"),
    # 词的误写
    ("闻然", r"闻然", "闻言"),
    ("猛得", r"猛得", "猛地"),
    # 重复字
    ("的的", r"(?<!真)的的(?![确话])", "的"),
    ("坐在了了", r"坐在了了", "坐在了"),
]

# 人称/句读个例（上下文精确）
EXACT = [
    ("她他舌尖", "他舌尖"),
    ("把他她传送", "把他传送"),
    ("被她他奸淫", "被他奸淫"),
    ("看他她的样子", "看她的样子"),
    ("怎么她他妈的还有", "怎么他妈的还有"),
    ("「她他妈的还有", "「他妈的还有"),
    ("这是他她自己的一个毛病", "这是她自己的一个毛病"),
    ("两个站在他她身边的元门弟子", "两个站在她身边的元门弟子"),
    ("救了他她命的东西", "救了她命的东西"),
    ("她他你送我", "她送你"),
]

stats = {}
total_files = 0
changed_files = 0


def process(text: str) -> str:
    for name, pat, rep in RULES:
        text, n = re.subn(pat, rep, text)
        if n:
            stats[name] = stats.get(name, 0) + n
    for old, new in EXACT:
        c = text.count(old)
        if c:
            text = text.replace(old, new)
            stats["exact:" + old[:8]] = stats.get("exact:" + old[:8], 0) + c
    return text


def main():
    global total_files, changed_files
    files = sorted(SRC.rglob("*.txt"))
    orig_chars = 0
    new_chars = 0
    for fp in files:
        total_files += 1
        rel = fp.relative_to(SRC)
        t = fp.open("r", encoding="utf-8", errors="replace", newline="").read()
        orig_chars += len(t)
        nt = process(t)
        new_chars += len(nt)
        dest = OUT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8", newline="") as f:
            f.write(nt)
        if nt != t:
            changed_files += 1

    print(f"files={total_files} changed={changed_files}")
    print(f"chars {orig_chars} -> {new_chars}  delta={new_chars - orig_chars}")
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {k}\t{v}")


if __name__ == "__main__":
    main()
