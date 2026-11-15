#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""成品统计：给 校勘版 出一份可直接贴进报告的指标表。"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "校勘版"

CHAP = re.compile(r"第[0-9零一二三四五六七八九十百千两]+[章节回]")
SENT_END = "。！？…」』）"


def walk():
    for p in sorted(SRC.rglob("*.txt")):
        yield p


def main():
    files = chars = lines = paras = 0
    dist = {"<=60": 0, "61-120": 0, "121-200": 0, "201-400": 0, "401-800": 0,
            "801-2000": 0, ">2000": 0}
    worst = []
    glued = 0
    for p in walk():
        raw = p.open("r", encoding="utf-8", errors="replace", newline="").read()
        files += 1
        chars += len(raw)
        ls = raw.replace("\r\n", "\n").split("\n")
        lines += len(ls)
        for ln in ls:
            s = ln.strip()
            if not s:
                continue
            paras += 1
            n = len(s)
            if n <= 60:
                dist["<=60"] += 1
            elif n <= 120:
                dist["61-120"] += 1
            elif n <= 200:
                dist["121-200"] += 1
            elif n <= 400:
                dist["201-400"] += 1
            elif n <= 800:
                dist["401-800"] += 1
            elif n <= 2000:
                dist["801-2000"] += 1
            else:
                dist[">2000"] += 1
            if n > 800:
                worst.append((n, str(p.relative_to(SRC)), s[:40]))
        # 章标题被吞：出现「第N章」但前面不是行首/空行
        for m in CHAP.finditer(raw):
            i = m.start()
            if i > 0 and raw[i - 1] not in "\n\r":
                glued += 1

    worst.sort(reverse=True)
    out = {
        "files": files,
        "chars": chars,
        "lines": lines,
        "paras": paras,
        "dist": dist,
        "chap_not_at_line_start": glued,
        "worst": worst[:5],
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
