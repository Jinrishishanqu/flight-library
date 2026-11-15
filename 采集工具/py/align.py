# -*- coding: utf-8 -*-
"""
align.py —— 用 rapidfuzz 做章节级对齐，替代 章对齐.ps1 的「前 300 字 3-gram Dice」。

章对齐.ps1 的问题：只看每章开头 300 字，短章或开头雷同就直接误判；慢（纯 PS）。
这里：
  - 按 `第N章` 切章（中文数字用 cn2an，兼容「第一百二十三章」）；
  - 每章正文去空白后，用 rapidfuzz.fuzz.ratio 对全部候选章做一次矩阵比较
    （C 实现，几千章也在秒级），取最优；
  - 同时报「A 章被 B 章包含」的覆盖率，区分「同章不同版本」与「B 章是 A 章的超集」。

用法：
  python align.py --a 甲.txt --b 乙.txt
  python align.py --a 甲.txt --b 乙.txt --min-sim 60 --csv 采集工具/记录/章对齐.csv
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import re
import sys

import cn2an
import regex
from rapidfuzz import fuzz

CH = regex.compile(r"第\s*([0-9０-９零〇一二三四五六七八九十百千万两]+)\s*[章回节]\s*[：:、.，,　 ]*\s*([^\r\n]{0,60})")
NORM = regex.compile(r"\s+")


def to_int(s: str) -> int:
    s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return int(cn2an.cn2an(s, "smart"))
    except Exception:
        return 0


def split_chapters(text: str) -> list[dict]:
    text = text.replace("\r\n", "\n")
    ms = list(CH.finditer(text))
    out: list[dict] = []
    if not ms:
        body = NORM.sub("", text)
        return [{"no": 0, "title": "(全文)", "body": body, "chars": len(body)}]
    head = NORM.sub("", text[: ms[0].start()])
    if len(head) > 200:
        out.append({"no": 0, "title": "(前言)", "body": head, "chars": len(head)})
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        body = NORM.sub("", text[m.end(): end])
        out.append({"no": to_int(m.group(1)), "title": m.group(2).strip(), "body": body, "chars": len(body)})
    return out


def coverage(big: str, small: str, blk: int = 300) -> float:
    if not small:
        return 0.0
    hit = tot = 0
    for i in range(0, len(small), blk):
        seg = small[i: i + blk]
        tot += 1
        if fuzz.partial_ratio(seg, big) >= 85:
            hit += 1
    return round(hit / tot * 100, 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--min-sim", type=float, default=55.0)
    ap.add_argument("--csv", default="")
    args = ap.parse_args(argv)

    A = split_chapters(pathlib.Path(args.a).read_text(encoding="utf-8-sig", errors="replace"))
    B = split_chapters(pathlib.Path(args.b).read_text(encoding="utf-8-sig", errors="replace"))
    print(f"A {len(A)} 段 / {sum(x['chars'] for x in A)} 字    B {len(B)} 段 / {sum(x['chars'] for x in B)} 字")

    rows = []
    used: set[int] = set()
    for a in A:
        best = None
        for j, b in enumerate(B):
            if j in used and a["no"]:
                continue
            if not a["body"] or not b["body"]:
                continue
            sim = fuzz.ratio(a["body"][:3000], b["body"][:3000])
            if best is None or sim > best[1]:
                best = (j, sim)
        if not best or best[1] < args.min_sim:
            continue
        j, sim = best
        b = B[j]
        used.add(j)
        cov = coverage(b["body"], a["body"]) if len(a["body"]) < len(b["body"]) else coverage(a["body"], b["body"])
        rows.append({
            "A章": a["no"], "A标题": a["title"], "A字": a["chars"],
            "B章": b["no"], "B标题": b["title"], "B字": b["chars"],
            "相似": round(sim, 1), "覆盖%": cov,
            "取值": "B（超集）" if (cov >= 95 and b["chars"] > a["chars"]) else "A",
        })

    only_a = [x for i, x in enumerate(A) if all(r["A章"] != x["no"] for r in rows)]
    only_b = [x for i, x in enumerate(B) if i not in used]
    for r in rows:
        print(f"  A{r['A章']:>4} ≒ B{r['B章']:>4}  相似 {r['相似']:>5}  覆盖 {r['覆盖%']:>5}%  取{r['取值']}  {r['A标题'][:16]}")
    print(f"对齐 {len(rows)} 对；A 独有 {len(only_a)}；B 独有 {len(only_b)}")
    if only_a:
        print("  A 独有:", ", ".join(str(x["no"]) for x in only_a[:20]))
    if only_b:
        print("  B 独有:", ", ".join(str(x["no"]) for x in only_b[:20]))

    if args.csv:
        path = pathlib.Path(args.csv)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["A章", "A标题", "A字", "B章", "B标题", "B字", "相似", "覆盖%", "取值"])
            w.writeheader()
            w.writerows(rows)
        print("报告 ->", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
