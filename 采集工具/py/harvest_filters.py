# -*- coding: utf-8 -*-
"""
从成熟书源项目 SoNovel 的规则文件里提取站点正文过滤规则（filterTxt / filterTag），
汇总成本地噪声词库，供 normalize.py 直接复用 —— 不重复造轮子。

用法：python harvest_filters.py --rules 归档/参考项目/SoNovel/SoNovel/rules --out 采集工具/噪声词库.json
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

SPLIT = re.compile(r"(?<!\\)\|")


def iter_rules(rules_dir: pathlib.Path):
    for p in sorted(rules_dir.glob("*.json*")):
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if isinstance(data, dict):
            data = [data]
        for src in data:
            if isinstance(src, dict):
                yield p.name, src


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", default="归档/参考项目/SoNovel/SoNovel/rules")
    ap.add_argument("--out", default="采集工具/噪声词库.json")
    args = ap.parse_args(argv)

    pats: list[dict] = []
    tags: set[str] = set()
    names = 0
    for fname, src in iter_rules(pathlib.Path(args.rules)):
        names += 1
        ch = src.get("chapter") or {}
        ft = ch.get("filterTxt") or ""
        for part in SPLIT.split(ft):
            part = part.strip()
            if len(part) >= 4:
                pats.append({"site": src.get("name", "?"), "rule": part})
        tg = ch.get("filterTag") or ""
        for t in tg.split(","):
            t = t.strip()
            if t:
                tags.add(t)

    # 去重（同一正则多处出现只留一次）
    seen, uniq = set(), []
    for p in pats:
        if p["rule"] in seen:
            continue
        seen.add(p["rule"])
        uniq.append(p)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(
        {"source": "SoNovel rules", "count": len(uniq), "filterTag": sorted(tags), "patterns": uniq},
        open(args.out, "w", encoding="utf-8"),
        ensure_ascii=False,
        indent=1,
    )
    print(f"{names} 个书源，提取 {len(uniq)} 条正文过滤规则，{len(tags)} 个标签 -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
