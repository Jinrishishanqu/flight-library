# -*- coding: utf-8 -*-
"""蓝色书吧（lanseshuba.org）爬虫。

背景：lanseshuba.org 是旧第一版主 PC 站 d1bz.net 的跳转目标，书目量比
m.diyibanzhu.space 大得多。它的正文是 JS 异步加载的，但接口已逆出：

    GET /read/<book>/<chapter>.html?ajax=1&_=<ts>
    Header: X-Requested-With: XMLHttpRequest
    -> 返回正文 HTML 片段（单章可带 _2 / _3 ... 分页）

反爬点：
  1. 少量汉字被替换成 <img class="zi" data-word="字">，真字在 data-word 里。
  2. 正文里插「地址发布页 / 最新网址」广告行，交给 normalize.py 的噪声库清掉。

用法：
  python bsc.py --kw 斗破苍穹 --max-books 20 --max-chapters 300
  python bsc.py --book 82986 --max-chapters 300
  python bsc.py --kw 斗破苍穹 --dry          # 只列书目，不抓正文
"""
from __future__ import annotations

import argparse
import csv
import html as htmllib
import os
import pathlib
import random
import re
import sys
import time

import requests
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from normalize import normalize_text, write_out  # noqa: E402

BASE = "https://lanseshuba.org"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
ROOT = pathlib.Path(__file__).resolve().parents[2]

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": UA,
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": BASE + "/",
        })
        _session = s
    return _session


def get(url: str, *, ajax: bool = False, retries: int = 5) -> str:
    hdr = {"X-Requested-With": "XMLHttpRequest"} if ajax else {}
    last = None
    for i in range(retries):
        try:
            r = session().get(url, headers=hdr, timeout=18)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or "utf-8"
                return r.text
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        time.sleep(1.5 * (i + 1) + random.uniform(0, 0.8))
    raise RuntimeError(f"取页失败 {url} -> {last}")


def post(url: str, data: dict, retries: int = 3) -> str:
    last = None
    for i in range(retries):
        try:
            r = session().post(url, data=data, timeout=30)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or "utf-8"
                return r.text
            last = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        time.sleep(1.5 * (i + 1) + random.uniform(0, 0.8))
    raise RuntimeError(f"搜索失败 {url} -> {last}")


# ---------------- 搜索 ----------------
BOOK_LINK = re.compile(r'href="/book/(\d+)/"[^>]*>\s*([^<]{1,300}?)\s*<')


def search(kw: str, max_books: int) -> list[tuple[str, str]]:
    txt = post(BASE + "/search/", {"searchkey": kw})
    seen, out = set(), []
    for bid, title in BOOK_LINK.findall(txt):
        title = htmllib.unescape(title).strip()
        if bid in seen or not title:
            continue
        seen.add(bid)
        out.append((bid, title))
        if len(out) >= max_books:
            break
    return out


# ---------------- 目录 ----------------
CHAP_LINK = re.compile(r'href="/read/(\d+)/(\d+)\.html"[^>]*>\s*([^<]{1,300}?)\s*<')


H1 = re.compile(r"<h1(?P<attr>[^>]*)>\s*(?P<inner>.*?)\s*</h1>", re.S)


def parse_title(page: str) -> str:
    """书名：跳过 class=logo 的站名 h1，取第一个真书名 h1。"""
    for m in H1.finditer(page):
        attr = m.group("attr") or ""
        if "logo" in attr:
            continue
        t = htmllib.unescape(re.sub(r"<[^>]+>", "", m.group("inner"))).strip()
        t = re.sub(r"[\r\n\t]+", " ", t).strip()
        if t and t != "蓝色书吧":
            return t
    m = re.search(r"<title>(.*?)</title>", page, re.S)
    if m:
        parts = [x.strip() for x in htmllib.unescape(m.group(1)).split("_")]
        for x in parts:
            x = re.sub(r"小说免费全文阅读$", "", x).strip()
            if x and "蓝色书吧" not in x:
                return x
    return ""


def toc(bid: str, max_chapters: int) -> tuple[str, list[tuple[str, str]]]:
    first = get(f"{BASE}/index/{bid}/")
    title = parse_title(first)

    order: list[str] = []
    names: dict[str, str] = {}
    pages = [1]
    got = {int(x) for x in re.findall(rf'/index/{bid}/(\d+)/', first) if int(x) <= 500}
    if got:
        pages = [1] + sorted(got)

    for pno in pages:
        page = first if pno == 1 else get(f"{BASE}/index/{bid}/{pno}/")
        for _b, cid, cname in CHAP_LINK.findall(page):
            if cid in names:
                continue
            names[cid] = htmllib.unescape(cname).strip()
            order.append(cid)
        if len(order) >= max_chapters:
            break
        time.sleep(0.15)

    return title, [(cid, names[cid]) for cid in order[:max_chapters]]


# ---------------- 正文 ----------------
DATE_ONLY = re.compile(r"^\d{2,4}[-/.]\d{1,2}[-/.]\d{1,2}(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?$")
JUNK = {
    "开始阅读", "加入书签", "上一章", "下一章", "返回目录", "目录", "章节目录",
    "上一页", "下一页", "加入书架", "投推荐票", "举报", "手机版", "电脑版",
}
IMG_WORD = re.compile(r'<img[^>]*?data-word="([^"]*)"[^>]*?>', re.S)
ANY_IMG = re.compile(r"<img[^>]*?>", re.S)
BLOCK_END = re.compile(r"</\s*(?:p|div|br)\s*/?>|<br\s*/?>", re.I)


def html_to_text(frag: str) -> str:
    frag = htmllib.unescape(frag)
    frag = IMG_WORD.sub(lambda m: m.group(1), frag)
    frag = ANY_IMG.sub("", frag)
    frag = BLOCK_END.sub("\n", frag)
    frag = re.sub(r"<[^>]+>", "", frag)
    frag = frag.replace("\u00a0", " ").replace("\u3000", "\u3000")
    lines = [ln.strip() for ln in frag.split("\n")]
    keep = []
    for ln in lines:
        if not ln:
            continue
        if DATE_ONLY.match(ln) or ln in JUNK:
            continue
        keep.append(ln)
    return "\n".join(keep)


def chapter(bid: str, cid: str) -> str:
    parts: list[str] = []
    pno = 1
    while pno <= 12:
        suffix = "" if pno == 1 else f"_{pno}"
        ts = int(time.time() * 1000)
        url = f"{BASE}/read/{bid}/{cid}{suffix}.html?ajax=1&_={ts}"
        try:
            frag = get(url, ajax=True)
        except RuntimeError:
            break
        if "章节内容加载中" in frag:
            break
        txt = html_to_text(frag)
        flat = re.sub(r"\s", "", txt)
        if len(flat) < 20:
            break
        if parts and flat == re.sub(r"\s", "", parts[-1]):   # 服务端把 _N 重定向回第一页
            break
        if any(flat in re.sub(r"\s", "", x) for x in parts):  # 重复内容
            break
        parts.append(txt)
        pno += 1
        time.sleep(0.2)
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kw", default="")
    ap.add_argument("--book", default="")
    ap.add_argument("--max-books", type=int, default=20)
    ap.add_argument("--max-chapters", type=int, default=300)
    ap.add_argument("--delay", type=int, default=350)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--outdir", default=str(ROOT / "采集工具" / "raw"))
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--no-clean", action="store_true", help="不做 normalize 清洗，原样落盘")
    args = ap.parse_args(argv)

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    logp = ROOT / "采集工具" / "记录" / "蓝书采集.csv"
    logp.parent.mkdir(parents=True, exist_ok=True)
    newlog = not logp.exists()
    fh = open(logp, "a", encoding="utf-8-sig", newline="")
    wr = csv.writer(fh)
    if newlog:
        wr.writerow(["Time", "Source", "Id", "Title", "Query", "Chapters", "Chars", "File"])

    books: list[tuple[str, str]] = []
    if args.book:
        books = [(args.book, parse_title(get(f"{BASE}/index/{args.book}/")) or args.book)]
    elif args.kw:
        books = search(args.kw, args.max_books)
        print(f"搜索「{args.kw}」命中 {len(books)} 本")
    else:
        ap.error("需要 --kw 或 --book")

    if args.dry:
        for bid, title in books:
            print(f"  {bid}\t{title}")
        fh.close()
        return 0

    for bid, title in books:
        try:
            real, chapters = toc(bid, args.max_chapters)
            real = real or title
            print(f"[{bid}] {real}  {len(chapters)} 章", flush=True)
            body: list[str] = []
            results: list[tuple[int, str, str]] = []

            def _one(pair):
                idx, (cid, cname) = pair
                try:
                    t = chapter(bid, cid)
                except Exception as e:  # noqa: BLE001
                    print(f"    章 {cid} 失败：{e}", flush=True)
                    return idx, cname, ""
                if args.delay:
                    time.sleep(args.delay / 1000.0)
                return idx, cname, t

            pairs = list(enumerate(chapters))
            done = 0
            with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
                for idx, cname, t in ex.map(_one, pairs):
                    done += 1
                    if done % 5 == 0 or done == len(pairs):
                        print(f"    {done}/{len(pairs)} 章", flush=True)
                    results.append((idx, cname, t))

            for idx, cname, t in sorted(results, key=lambda x: x[0]):
                if not t.strip():
                    continue
                if cname and cname not in ("上一章", "下一章") and cname not in JUNK:
                    body.append(cname)
                body.append(t)

            raw = "\n\n".join(body)
            text = raw if args.no_clean else normalize_text(raw).text
            chars = len(re.sub(r"\s", "", text))
            safe = re.sub(r'[\\/:*?"<>|]', "_", real).strip() or bid
            dst = outdir / f"{safe}.txt"
            k = 2
            while dst.exists():
                dst = outdir / f"{safe}-{k}.txt"
                k += 1
            write_out(str(dst), text)
            wr.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), "lanseshuba", bid, real,
                         args.kw, len(chapters), chars, dst.name])
            print(f"    -> {dst.name}  {chars} 字", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[{bid}] {title} 失败：{e}", flush=True)

    fh.close()
    print("蓝书采集完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
