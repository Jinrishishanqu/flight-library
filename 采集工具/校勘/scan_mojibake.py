# -*- coding: utf-8 -*-
"""扫描全库的 mojibake / 解码失败迹象（现有清洗从未处理这一类）。
输出：采集工具\记录\mojibake普查.csv + 控制台汇总
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import regex

ROOT = Path(r"F:\新建文件夹\read - 副本")
TREE = ROOT / "校勘版"
OUT = ROOT / "采集工具" / "记录" / "mojibake普查.csv"

PATS = {
    "U+FFFD": regex.compile(r"\ufffd"),
    "cp1252_mojibake": regex.compile(r"(?:â€[\x80-\xbf\u2018-\u201d\u2013\u2014]|Ã[\x80-\xbf\u0080-\u00bf])"),
    "gbk_classic": regex.compile(r"(?:锟斤拷|烫烫烫|屯屯屯|锘匡豢|鐨勬|涓€)"),
    "latin_space": regex.compile(r"[\u00a0\u2007\u202f]"),
    "zw_chars": regex.compile(r"[\u200b-\u200f\u2060\ufeff]"),
    "soft_hyphen": regex.compile(r"[\u00ad\u200c\u200d]"),
}


def main() -> int:
    rows = []
    totals = {k: 0 for k in PATS}
    files = {k: 0 for k in PATS}
    n = 0
    for fp in sorted(TREE.rglob("*.txt")):
        n += 1
        t = fp.open("r", encoding="utf-8", errors="replace", newline="").read()
        rel = str(fp.relative_to(ROOT))
        for k, p in PATS.items():
            hits = p.findall(t)
            if hits:
                c = len(hits)
                totals[k] += c
                files[k] += 1
                samples = []
                for m in list(p.finditer(t))[:3]:
                    s = max(0, m.start() - 12)
                    samples.append(t[s:m.end() + 12].replace("\r", " ").replace("\n", "⏎"))
                rows.append({"kind": k, "count": c, "file": rel, "samples": " | ".join(samples)})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["kind", "count", "file", "samples"])
        w.writeheader()
        w.writerows(rows)
    print(f"files={n}")
    for k in PATS:
        print(f"{k:18s} 出现 {totals[k]:7d} 次 / {files[k]:4d} 个文件")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
