# -*- coding: utf-8 -*-
"""
refresh.py —— 源文件被「入库.ps1」REPL 升级后，用新引擎重建对应校对稿。

只处理「单一源 + 输出名以书名开头」的行，避开已人工整合的合并件
（如《斗破·薰儿线回目连载》，其 Sources 是多条、输出名带「·」）。

用法：
  python refresh.py --dry            # 列出需要重建的行
  python refresh.py --apply          # 重建并改名、更新清单
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import pathlib
import re
import sys

from normalize import decode_bytes, normalize_text, write_out

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLAN = ROOT / "采集工具" / "记录" / "校对清单.csv"
COLS = ["Time", "Ip", "Output", "Sources", "InChars", "OutChars", "Verified", "Chars"]
MERGED = re.compile(r"[·・]|合集|合并|^\d+~|-[0-9]+~[0-9]+-")


def chars(t: str) -> int:
    return len(re.sub(r"\s", "", t))


def wc_tag(n: int) -> str:
    if n >= 10000:
        return f"{round(n / 10000.0, 1)}w".replace(".0w", "w")
    return f"{n}字"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args(argv)
    if not args.apply:
        args.dry = True

    with open(PLAN, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    todo = []
    for r in rows:
        srcs = [s for s in (r.get("Sources") or "").split("|") if s.strip()]
        out = pathlib.Path(r.get("Output") or "")
        if len(srcs) != 1 or not out.name:
            continue
        if MERGED.search(out.name):
            continue
        src = pathlib.Path(srcs[0])
        if src.suffix.lower() != ".txt":
            continue
        if not src.exists():
            continue
        if not out.exists():
            head0 = re.sub(r"-[0-9.]+w?$|-[0-9]+字$", "", out.stem)
            cands = sorted(out.parent.glob(head0 + "-*")) if out.parent.exists() else []
            if not cands:
                continue
            out = cands[0]
        sc = chars(decode_bytes(src.read_bytes())[0])
        oc = chars(decode_bytes(out.read_bytes())[0])
        if sc <= oc * 1.15:
            continue          # 源没有明显变大，无需重建
        todo.append((r, src, out))

    print(f"需重建 {len(todo)} 份")
    for r, src, out in todo:
        print(f"  {r['Ip']:6} {out.name}  <-  {src.name}")
    if args.dry:
        return 0

    for r, src, out in todo:
        res = normalize_text(src.read_bytes())
        text = res.text
        n = chars(text)
        if n < 300:
            print("SKIP 过短", src.name, n)
            continue
        head = re.sub(r"-[0-9.]+w?|-[0-9]+字$", "", out.stem)
        head = re.sub(r"-[0-9.]+w$", "", head)
        new = out.with_name(f"{head}-{wc_tag(n)}{out.suffix}")
        write_out(str(new), text)
        if new != out and out.exists():
            out.unlink()
        r["Time"] = dt.datetime.now().isoformat(timespec="seconds")
        r["Output"] = str(new)
        r["OutChars"] = str(n)
        r["Chars"] = str(n)
        r["Verified"] = "True"
        print(f"OK   {new.name}")

    with open(PLAN, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    print("清单已更新")
    return 0


if __name__ == "__main__":
    sys.exit(main())
