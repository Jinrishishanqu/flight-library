# -*- coding: utf-8 -*-
"""把结构性可疑点导成可复核的清单（不做任何改写）。

输出（均落 采集工具\\记录\\）：
    章标题待判定.csv   — 第N章 与后文连在同一行的位置
    长句待判定.csv     — 单句 > 200 字（句 = 段内以 。！？…」』 切分）
    长段待判定.csv     — 单段 > 250 字
    章头重复.csv       — 章标题后首句在本作其他章重复出现（疑似错章/串章）

每行带 prev / hit / next 三段上下文，便于人工或模型判断。
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(r"F:\新建文件夹\read - 副本")
SRC = ROOT / "校勘版_chap"
REC = ROOT / "采集工具" / "记录"

CHAP = re.compile(r"第[0-9零一二三四五六七八九十百千两]{1,6}[章节回]")
SENT_SPLIT = re.compile(r"(?<=[。！？…」』])")


def ctx(t: str, a: int, b: int, pad: int = 24):
    return (t[max(0, a - pad):a].replace("\r\n", " ").replace("\n", " "),
            t[a:b].replace("\r\n", " ").replace("\n", " "),
            t[b:b + pad].replace("\r\n", " ").replace("\n", " "))


def main() -> int:
    only = None
    if "--file" in sys.argv:
        only = sys.argv[sys.argv.index("--file") + 1]
    REC.mkdir(parents=True, exist_ok=True)

    rows_chap, rows_sent, rows_par, rows_head = [], [], [], []
    n_files = 0

    for p in sorted(SRC.rglob("*.txt")):
        rel = str(p.relative_to(SRC))
        if only and only not in rel:
            continue
        n_files += 1
        t = p.open("r", encoding="utf-8", errors="replace", newline="").read()
        lines = t.split("\n")

        heads = []  # 章标题 + 首句，用于串章检测

        for li, ln in enumerate(lines, 1):
            s = ln.strip()
            if not s:
                continue
            # 1) 章标题粘连
            m = CHAP.match(s)
            if m and len(s) > 40:
                prev, hit, nxt = ctx(s, 0, m.end(), 40)
                rows_chap.append({
                    "file": rel, "line": li, "len": len(s),
                    "chap": s[:m.end()], "prev": prev,
                    "hit": s[m.end():m.end() + 60], "next": "",
                    "full": s[:200],
                })
            # 2) 长段
            if len(s) > 250:
                prev, hit, nxt = ctx(s, 0, 60, 30)
                rows_par.append({"file": rel, "line": li, "len": len(s),
                                 "head": s[:70], "tail": s[-40:], "full": s[:300]})
            # 3) 长句
            if len(s) > 150:
                off = 0
                for part in SENT_SPLIT.split(s):
                    if len(part) > 200:
                        a = s.find(part, off)
                        b = a + len(part)
                        off = b
                        prev, hit, nxt = ctx(s, a, min(b, a + 60), 30)
                        rows_sent.append({
                            "file": rel, "line": li, "len": len(part),
                            "prev": prev, "head": part[:80],
                            "hit": part[:120], "next": part[-30:],
                        })
            # 4) 章头首句重复
            if m and len(s) <= 40:
                heads.append((li, s.strip()))

        # 章头首句重复检测
        if len(heads) >= 3:
            first_sent = {}
            for li, title in heads:
                # 找下一非空行首句
                for j in range(li, min(li + 3, len(lines))):
                    body = lines[j].strip()
                    if body and not CHAP.match(body):
                        k = 0
                        for part in SENT_SPLIT.split(body):
                            k += len(part)
                            if k >= 12:
                                break
                        key = body[:24]
                        if len(key) >= 12:
                            first_sent.setdefault(key, []).append((li, title))
                        break
            for key, hits in first_sent.items():
                if len(hits) > 1:
                    rows_head.append({"file": rel, "count": len(hits),
                                      "first_sent": key,
                                      "where": "; ".join(f"L{a}:{b}" for a, b in hits[:6])})

    def dump(name, rows, cols):
        fp = REC / name
        with fp.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"  {name:24s} {len(rows):5d} 行 -> {fp}")

    print(f"扫描 {n_files} 文件，目录 {SRC}")
    dump("章标题待判定.csv", rows_chap, ["file", "line", "len", "chap", "hit", "full"])
    dump("长句待判定.csv", rows_sent, ["file", "line", "len", "prev", "head", "next"])
    dump("长段待判定.csv", rows_par, ["file", "line", "len", "head", "tail"])
    dump("章头重复.csv", rows_head, ["file", "count", "first_sent", "where"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
