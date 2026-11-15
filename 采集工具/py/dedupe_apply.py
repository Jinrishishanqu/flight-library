# -*- coding: utf-8 -*-
"""
dedupe_apply.py —— 按 dedupe.py 报告里相似度 >= TH 的「可移出」条目移到 归档/重复_根级/去重/。

保守：只处理 report 里同一组内相似度 >= --min-sim 的条目，且保留项字数 >= 移出项
（避免把「完整版」当重复删掉）。0.95 以上基本都是同文异名，0.82~0.94 的留人工。
"""
from __future__ import annotations

import argparse
import csv
import pathlib
import shutil
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
DST = ROOT / "归档" / "重复_根级" / "去重"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="采集工具/记录/重复检测.csv")
    ap.add_argument("--min-sim", type=float, default=0.95)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    rows = list(csv.DictReader(open(ROOT / args.report, encoding="utf-8-sig")))
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["组"]].append(r)

    plan = []
    for gid, items in groups.items():
        sim = max(float(r["相似度"]) for r in items)
        if sim < args.min_sim:
            continue
        keep = [r for r in items if r["建议"] == "保留"]
        drop = [r for r in items if r["建议"] != "保留"]
        if not keep or not drop:
            continue
        kmax = max(int(r["去空白字数"]) for r in keep)
        for r in drop:
            if int(r["去空白字数"]) <= kmax:
                plan.append((gid, sim, keep[0]["文件"], r["文件"]))

    print(f"待移出 {len(plan)} 份（相似度 >= {args.min_sim}）")
    for gid, sim, k, d in plan:
        print(f"  组{gid} {sim:.3f} 留 {pathlib.Path(k).name[:40]}  移 {pathlib.Path(d).name[:40]}")

    if not args.apply:
        return 0

    moved = 0
    for gid, sim, k, d in plan:
        src = ROOT / d
        if not src.exists():
            print("缺文件", d)
            continue
        dst = DST / src.parent.name
        dst.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst / src.name))
        moved += 1
    print(f"已移出 {moved} 份 -> {DST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
