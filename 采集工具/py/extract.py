# -*- coding: utf-8 -*-
"""
extract.py —— 用 trafilatura 从网页/HTML 里抽正文，替代手写正则的 抽正文.ps1。

为什么换：trafilatura 是经过大规模评测的正文抽取器（readability/justext 之上再优化），
能自动去掉导航、评论、页脚、广告块，不必为每个站点写锚点规则。

用法：
  python extract.py --url https://m.diyibanzhu.space/view/735002.html
  python extract.py --file page.html --out out.txt
  python extract.py --dir 归档/临时/html --outdir 归档/临时/txt
  python extract.py --url URL --format txt|markdown|json   （默认 txt）
  python extract.py --url URL --favor-precision           （更激进地只留正文）

输出统一走 normalize 的落盘规则（UTF-8 BOM + CRLF），可直接投喂 build.py。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import requests
import trafilatura

from normalize import write_out

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def fetch(url: str, proxy: str | None = None) -> str:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
    r = s.get(url, timeout=30, proxies={"http": proxy, "https": proxy} if proxy else None)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() in ("iso-8859-1", "ascii"):
        r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def extract(html: str, url: str = "", fmt: str = "txt", precision: bool = False) -> str:
    kw = dict(
        url=url or None,
        include_comments=False,
        include_tables=False,
        favor_precision=precision,
        deduplicate=True,
    )
    if fmt == "markdown":
        kw["output_format"] = "markdown"
        kw["include_formatting"] = True
    elif fmt == "json":
        kw["output_format"] = "json"
    else:
        kw["output_format"] = "txt"
    out = trafilatura.extract(html, **kw)
    return out or ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="")
    ap.add_argument("--file", default="")
    ap.add_argument("--dir", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--outdir", default="归档/临时/txt")
    ap.add_argument("--format", default="txt", choices=["txt", "markdown", "json"])
    ap.add_argument("--favor-precision", action="store_true")
    ap.add_argument("--proxy", default="")
    args = ap.parse_args(argv)

    jobs: list[tuple[str, str]] = []
    if args.url:
        jobs.append((args.url, fetch(args.url, args.proxy or None)))
    if args.file:
        p = pathlib.Path(args.file)
        jobs.append((str(p), p.read_text(encoding="utf-8", errors="replace")))
    if args.dir:
        for p in sorted(pathlib.Path(args.dir).glob("*.htm*")):
            jobs.append((str(p), p.read_text(encoding="utf-8", errors="replace")))
    if not jobs:
        ap.print_help()
        return 2

    ok = 0
    for src, html in jobs:
        text = extract(html, url=src if src.startswith("http") else "", fmt=args.format,
                       precision=args.favor_precision)
        n = len(text)
        if n < 200:
            print(f"MISS {src} -> {n} 字（正文抽取失败）")
            continue
        if args.out and len(jobs) == 1:
            dst = pathlib.Path(args.out)
        else:
            stem = pathlib.Path(src).stem if not src.startswith("http") else src.rstrip("/").split("/")[-1]
            dst = pathlib.Path(args.outdir) / f"{stem}.txt"
        dst.parent.mkdir(parents=True, exist_ok=True)
        write_out(str(dst), text)
        ok += 1
        print(f"OK   {dst}  {n} 字")
    print(f"抽取 {ok}/{len(jobs)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
