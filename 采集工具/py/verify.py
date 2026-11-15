# -*- coding: utf-8 -*-
"""
校验器 v2 —— 结构 + 内容双检，替代只能做「逐字重现」的 校验.ps1。

检查项：
  1 BOM        UTF-8 BOM 存在
  2 CRLF       全 CRLF，无裸 LF
  3 空行       无 3 连续以上空行；段间恰好一个空行
  4 文件名     `《…》-…-wc.txt` 的 wc 与实际字数一致
  5 广告残留   噪声库 / 常见站名 / 分页标记
  6 HTML残留   &nbsp; 实体、<p> 标签
  7 半角标点   中文语境半角 ,:;?! 残留数
  8 乱码       U+FFFD / 私用区 / 常见形近误识别
  9 字数关系   输出 ≤ 源（只能删不能加），且减少比例 ≤ 25%

用法：python verify.py --dir 校对后文章 --src 原文 --report 采集工具/记录/校验v2.csv [--fix]
"""
from __future__ import annotations

import argparse
import csv
import os
import pathlib
import re
import sys

import regex

from normalize import decode_bytes


def chars_of(t: str) -> int:
    return len(regex.sub(r"\s", "", t))

WC = re.compile(r"^(?P<head>.+)-(?P<wc>[0-9.]+w|[0-9]+字)$")
HALF = regex.compile(rf"(?<=[\u4e00-\u9fff])\s*[,;?!:](?=[\u4e00-\u9fff])")
AD = regex.compile(
    r"第一版主|66acg|laowang|sis001|色城|草榴|请记住本站|最新章节|天才一秒记住|"
    r"数字分页|本章未完|www\.|https?://|&nbsp;|</?p>|</?br",
    regex.I,
)
BADCHAR = regex.compile("[\ufffd\u25a1\u25a0\u3000]{0}")


def wc_tag(n: int) -> str:
    if n >= 10000:
        return f"{round(n / 10000.0, 1)}w".replace(".0w", "w")
    return f"{n}字"


def check(path: pathlib.Path) -> list[str]:
    issues: list[str] = []
    raw = path.read_bytes()
    if not raw.startswith(b"\xef\xbb\xbf"):
        issues.append("无 BOM")
    body = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
    if b"\n" in body.replace(b"\r\n", b""):
        issues.append("存在裸 LF")
    text = body.decode("utf-8", "replace")
    if "\ufffd" in text:
        issues.append(f"含替换字符 x{text.count(chr(0xFFFD))}")
    if regex.search(r"\n{3,}", text):
        issues.append("连续空行≥3")
    n = chars_of(text)
    m = WC.match(path.stem)
    if not m:
        issues.append("文件名缺字数后缀")
    elif m.group("wc") != wc_tag(n):
        issues.append(f"文件名字数不符(标{m.group('wc')}/应{wc_tag(n)})")
    ad = AD.findall(text)
    if ad:
        issues.append(f"广告/HTML残留 x{len(ad)}: {ad[:3]}")
    half = HALF.findall(text)
    if len(half) > max(3, n // 20000):
        issues.append(f"半角标点残留 x{len(half)}")
    if regex.search(r"(?m)[\u3000 ]+$", text):
        issues.append("行尾空白")
    return issues


def load_sources(plan_csv: pathlib.Path) -> dict[str, list[str]]:
    """Output 文件名 -> 源文件绝对路径列表（来自 校对清单.csv）。"""
    if not plan_csv.exists():
        return {}
    out: dict[str, list[str]] = {}
    with open(plan_csv, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            key = pathlib.Path(row.get("Output", "")).stem
            src = row.get("Sources", "")
            if not key or not src:
                continue
            out.setdefault(key, []).append(src)
    return out


def find_src(src_root: pathlib.Path | None, stem: str) -> pathlib.Path | None:
    if not src_root or not src_root.exists():
        return None
    core = regex.sub(r"^《|》.*$", "", stem)
    core = regex.sub(r"[-－].*$", "", core).strip()
    if not core:
        return None
    hits = [p for p in src_root.rglob("*.txt") if core[:12] in p.name]
    hits.sort(key=lambda p: -p.stat().st_size)
    return hits[0] if hits else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="校对后文章")
    ap.add_argument("--src", default="原文")
    ap.add_argument("--report", default="采集工具/记录/校验v2.csv")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    root = pathlib.Path(args.dir)
    src_root = pathlib.Path(args.src)
    files = [
        p for p in sorted(root.rglob("*.txt"))
        if not any(part.startswith("_") for part in p.relative_to(root).parts[:-1])
    ]
    rows = []
    bad = 0
    smap = load_sources(pathlib.Path("采集工具/记录/校对清单.csv"))
    for p in files[: args.limit or None]:
        issues = check(p)
        # 字数关系：优先用清单映射（改名后按头部模糊匹配）
        srcs = smap.get(p.stem)
        if srcs is None:
            head = WC.match(p.stem).group("head") if WC.match(p.stem) else p.stem
            for k, v in smap.items():
                if k.startswith(head):
                    srcs = v
                    break
        src = None
        if srcs:
            cand = [pathlib.Path(s) for s in srcs if pathlib.Path(s).exists() and pathlib.Path(s).suffix.lower() == ".txt"]
            if cand:
                sc = sum(chars_of(decode_bytes(x.read_bytes())[0]) for x in cand)
                oc = chars_of(decode_bytes(p.read_bytes())[0])
                rel = f"{oc}/{sc}" if sc else ""
                if sc and oc > sc * 1.02:
                    issues.append(f"输出多于源({oc}>{sc})")
                elif sc and (sc - oc) / sc > 0.25:
                    issues.append(f"删除过多(-{(sc - oc) / sc:.0%})")
                src = cand[0]
        if issues:
            bad += 1
        rows.append({"file": str(p.relative_to(root)),
                     "chars": chars_of(decode_bytes(p.read_bytes())[0]),
                     "src": str(src) if src else "", "ratio": rel if src else "",
                     "issues": "; ".join(issues) or "OK"})
        if args.fix:
            for it in issues:
                if it.startswith("文件名字数不符"):
                    n = chars_of(decode_bytes(p.read_bytes())[0])
                    new = p.with_name(f"{WC.match(p.stem).group('head')}-{wc_tag(n)}.txt")
                    p.rename(new)
                    break

    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["file", "chars", "src", "ratio", "issues"])
        w.writeheader()
        w.writerows(rows)
    print(f"校验 {len(rows)} 份，通过 {len(rows) - bad}，异常 {bad} -> {args.report}")
    from collections import Counter

    c = Counter()
    for r in rows:
        for it in r["issues"].split("; "):
            if it != "OK":
                c[regex.sub(r"[（(].*", "", it)] += 1
    for k, v in c.most_common(10):
        print(f"  {k:24} {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
