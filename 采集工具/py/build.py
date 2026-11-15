# -*- coding: utf-8 -*-
"""
build.py —— 用 Python 引擎把「原文」里尚未处理的书生成为「校对后文章」。

与 校对.ps1 的区别：不再做「行宽接回 + 章号合并」的硬规则，而是走
normalize.normalize_text()（ftfy 乱码修复 / opencc 繁转简 / 噪声词库过滤
/ 标点半角转全角 / 段落重建 / 空白整理），输出统一 UTF-8 BOM + CRLF。

用法：
  python build.py                 # 只处理清单里没有的源
  python build.py --all           # 全量重建（危险，会覆盖已人工整合的产物）
  python build.py --ip 斗破       # 只处理某个归类目录
  python build.py --dry           # 只列清单

登记：追加/更新 采集工具/记录/校对清单.csv（列与 校对.ps1 一致）。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import pathlib
import re
import sys

from normalize import normalize_text, write_out

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "原文"
OUT = ROOT / "校对后文章"
PLAN = ROOT / "采集工具" / "记录" / "校对清单.csv"
SKIP_DIRS = {"_校勘版"}

COLS = ["Time", "Ip", "Output", "Sources", "InChars", "OutChars", "Verified", "Chars"]


def chars(t: str) -> int:
    return len(re.sub(r"\s", "", t))


def wc_tag(n: int) -> str:
    if n >= 10000:
        return f"{round(n / 10000.0, 1)}w".replace(".0w", "w")
    return f"{n}字"


def book_title(stem: str) -> str:
    s = re.sub(r"^pixiv-\d+-", "", stem)
    s = re.sub(r"^qbtr-\d+-", "", s)
    s = re.sub(r"[-－](全本|全篇|完结)[-－]?.*$", "", s)
    s = re.sub(r"\(\s*\d+\s*[千w万]?字?\s*\)$", "", s)
    s = re.sub(r"[\\/:*?\"<>|]", "_", s).strip()
    return s or stem


def load_done() -> set[str]:
    done: set[str] = set()
    if not PLAN.exists():
        return done
    with open(PLAN, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            for p in (row.get("Sources") or "").split("|"):
                if p.strip():
                    done.add(os.path.normcase(os.path.abspath(p.strip())))
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--ip", default="")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--newer", type=int, default=0, help="只处理 N 分钟内改动的源")
    args = ap.parse_args(argv)

    done = load_done() if not args.all else set()
    todo = []
    for p in sorted(SRC.rglob("*.txt")):
        rel = p.relative_to(SRC)
        if any(part in SKIP_DIRS or part.startswith("_") for part in rel.parts[:-1]):
            continue
        ip = rel.parts[0] if len(rel.parts) > 1 else "待归类"
        if args.ip and ip != args.ip:
            continue
        if os.path.normcase(os.path.abspath(p)) in done:
            continue
        if args.newer:
            age = (dt.datetime.now().timestamp() - p.stat().st_mtime) / 60.0
            if age > args.newer:
                continue
        todo.append((ip, p))
    if args.limit:
        todo = todo[: args.limit]

    print(f"待处理 {len(todo)} 份")
    if args.dry:
        for ip, p in todo[:40]:
            print(" ", ip, "|", p.name)
        return 0

    rows = []
    for ip, p in todo:
        raw = p.read_bytes()
        res = normalize_text(raw)
        text = res.text if hasattr(res, "text") else str(res)
        n = chars(text)
        if n < 300:
            print("SKIP 过短", p.name, n)
            continue
        title = book_title(p.stem)
        stem = f"《{title}》-全篇-{wc_tag(n)}"
        outdir = OUT / ip
        outdir.mkdir(parents=True, exist_ok=True)
        out = outdir / f"{stem}.txt"
        k = 2
        while out.exists():
            out = outdir / f"{stem}-{k}.txt"
            k += 1
        write_out(str(out), text)
        rows.append({
            "Time": dt.datetime.now().isoformat(timespec="seconds"),
            "Ip": ip,
            "Output": str(out),
            "Sources": str(p),
            "InChars": chars(res.stats.get("in_text", "")) or n,
            "OutChars": n,
            "Verified": "True",
            "Chars": n,
        })
        print(f"OK   {ip:6} {out.name}")

    if rows:
        new = not PLAN.exists()
        with open(PLAN, "a", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLS)
            if new:
                w.writeheader()
            w.writerows(rows)
    print(f"生成 {len(rows)} 份 -> {PLAN.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
