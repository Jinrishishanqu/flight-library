# -*- coding: utf-8 -*-
"""
把规范化结果落回 校对后文章，并按新字数改名（文件名规则与 校验.ps1 一致）。

用法：
  python apply_norm.py --norm 归档/临时/norm --dst 校对后文章 --bak 归档/临时/norm_bak [--apply]

文件名：`《Title》-span-wc.txt`；wc = ≥10000 时 `x.yw`（去掉 .0），否则 `N字`。
"""
from __future__ import annotations

import argparse
import csv
import os
import pathlib
import re
import shutil
import sys

import regex

# 与 校验.ps1 一致
RENAME = re.compile(r"^(?P<head>.+)-(?P<wc>[0-9.]+w|[0-9]+字)$")


def wc_tag(chars: int) -> str:
    if chars >= 10000:
        s = f"{round(chars / 10000.0, 1)}w"
        return s.replace(".0w", "w")
    return f"{chars}字"


def chars_of(text: str) -> int:
    return len(regex.sub(r"\s", "", text))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--norm", default="归档/临时/norm")
    ap.add_argument("--dst", default="校对后文章")
    ap.add_argument("--bak", default="归档/临时/norm_bak")
    ap.add_argument("--report", default="采集工具/记录/规范化.csv")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    norm_root = pathlib.Path(args.norm)
    dst_root = pathlib.Path(args.dst)
    bak_root = pathlib.Path(args.bak)
    rows = []
    for src in sorted(norm_root.rglob("*.txt")):
        rel = src.relative_to(norm_root)
        old = dst_root / rel
        if not old.exists():
            rows.append({"rel": str(rel), "action": "skip-missing"})
            continue
        new_text = src.read_text(encoding="utf-8-sig", errors="replace")
        n_chars = chars_of(new_text)
        stem = old.stem
        m = RENAME.match(stem)
        if m:
            new_stem = f"{m.group('head')}-{wc_tag(n_chars)}"
        else:
            new_stem = f"{stem}-{wc_tag(n_chars)}"
        new = old.with_name(new_stem + ".txt")
        changed = old.read_bytes() != src.read_bytes() or old.name != new.name
        rows.append(
            {
                "rel": str(rel),
                "old": old.name,
                "new": new.name,
                "chars": n_chars,
                "changed": int(changed),
                "renamed": int(old.name != new.name),
            }
        )
        if not args.apply or not changed:
            continue
        bak = bak_root / rel
        bak.parent.mkdir(parents=True, exist_ok=True)
        if not bak.exists():
            shutil.copy2(old, bak)
        if old.name != new.name and new.exists():
            # 目标名已存在且内容不同 → 保留新名加序号，绝不覆盖
            new = old.with_name(f"{new_stem}-2.txt")
        old.write_text(src.read_text(encoding="utf-8-sig", errors="replace"), encoding="utf-8-sig", newline="\r\n")
        if old.name != new.name:
            old.rename(new)

    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["rel"])
        w.writeheader()
        w.writerows(rows)
    changed = sum(1 for r in rows if r.get("changed"))
    renamed = sum(1 for r in rows if r.get("renamed"))
    print(f"{'已应用' if args.apply else '预演'}：{len(rows)} 个文件，内容变化 {changed}，需改名 {renamed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
