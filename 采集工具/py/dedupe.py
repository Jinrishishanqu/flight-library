# -*- coding: utf-8 -*-
"""
全库近重复检测 —— datasketch MinHash LSH 替代 5-gram Jaccard 两两比较。

用法：
  python dedupe.py --dir 校对后文章 --out 记录/重复检测.csv [--threshold 0.85] [--shingle 5]
输出：组号,相似度,文件,字数；每组保留字数最多者，其余标记为可移出。
"""
from __future__ import annotations

import argparse
import csv
import os
import pathlib
import re
import sys

import regex
from datasketch import MinHash, MinHashLSH

SKIP_DIR = re.compile(r"\\_[^\\]+\\")


def iter_txt(root: pathlib.Path):
    for p in sorted(root.rglob("*.txt")):
        if any(part.startswith("_") for part in p.relative_to(root).parts[:-1]):
            continue
        yield p


def body_of(path: pathlib.Path, head_chars: int = 40000) -> str:
    t = path.read_text(encoding="utf-8-sig", errors="replace")
    t = regex.sub(r"\s", "", t)
    return t[:head_chars]


def shingles(s: str, k: int = 5) -> set[str]:
    if len(s) <= k:
        return {s}
    return {s[i : i + k] for i in range(0, len(s) - k + 1, 1)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="校对后文章")
    ap.add_argument("--out", default="采集工具/记录/重复检测.csv")
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--shingle", type=int, default=5)
    ap.add_argument("--num-perm", type=int, default=128)
    ap.add_argument("--chars", type=int, default=40000)
    args = ap.parse_args(argv)

    root = pathlib.Path(args.dir)
    files = list(iter_txt(root))
    print(f"扫描 {len(files)} 个文件", file=sys.stderr)

    lsh = MinHashLSH(threshold=args.threshold, num_perm=args.num_perm)
    mhs: dict[str, MinHash] = {}
    sizes: dict[str, int] = {}
    texts: dict[str, str] = {}
    for i, p in enumerate(files):
        body = body_of(p, args.chars)
        texts[str(p)] = body
        mh = MinHash(num_perm=args.num_perm)
        for sh in shingles(body, args.shingle):
            mh.update(sh.encode("utf-8"))
        key = f"f{i}"
        mhs[key] = mh
        sizes[key] = len(body)
        lsh.insert(key, mh)

    pairs: list[tuple[float, str, str]] = []
    for key, mh in mhs.items():
        for other in lsh.query(mh):
            if other <= key:
                continue
            j = mh.jaccard(mhs[other])
            if j >= args.threshold:
                a = files[int(key[1:])]
                b = files[int(other[1:])]
                pairs.append((j, str(a), str(b)))

    # 连通分量分组
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _, a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    groups: dict[str, list[str]] = {}
    for _, a, b in pairs:
        groups.setdefault(find(a), set()).update([a, b])

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["组", "相似度", "文件", "去空白字数", "建议"])
        for gi, (root_key, members) in enumerate(sorted(groups.items()), 1):
            members = sorted(members, key=lambda f: -os.path.getsize(f))
            best = members[0]
            for m in members:
                j = max(
                    (p[0] for p in pairs if {p[1], p[2]} <= set(members) and m in (p[1], p[2])),
                    default=0.0,
                )
                w.writerow([gi, f"{j:.3f}", m, sum(1 for c in texts[m]), "保留" if m == best else "可移出"])
    print(f"发现 {len(groups)} 组重复，涉及 {sum(len(v) for v in groups.values())} 个文件 -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
