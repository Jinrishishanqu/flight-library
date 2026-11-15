# -*- coding: utf-8 -*-
"""扫描正文字符集，标出可疑字符与同形字（UTS #39 confusables）。

用途：
  1) 列出正文里所有「非 ASCII、非汉字、非中文标点」的字符及频次 —— 这些通常是
     水印残留、打码符号、排版装饰，需要人工确认是否清理；
  2) 用 confusables.txt 对这些字符做 skeleton() 归一，若 skeleton 落在汉字区，
     说明它是「用外文字母伪装成汉字」的同形字（盗版站水印常用手法）。

confusables.txt 来自 https://www.unicode.org/Public/security/latest/confusables.txt
（Unicode License v3）。格式：源码位 ; 目标序列 ; 类别 # 注释

用法：
  python confusable_scan.py            # 扫 校勘版\
  python confusable_scan.py <dir>      # 扫指定目录
  python confusable_scan.py --skeleton # 额外列出 skeleton 变化的样本
"""
from __future__ import annotations

import collections
import pathlib
import sys
import unicodedata

ROOT = pathlib.Path(r"F:\新建文件夹\read - 副本")
CONF = ROOT / "采集工具" / "词库" / "confusables.txt"
OUT = ROOT / "采集工具" / "记录" / "字符集扫描.csv"

# 中文排版里合法出现的非汉字字符
CJK_PUNCT = set(
    "，。、；：？！“”‘’「」『』（）【】《》〈〉…—～·　"
    "\u3000\u2026\u2014\u2018\u2019\u201c\u201d"
)
KEEP_ASCII = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
                 "\n\r\t -_/:%.,'\"()[]")


def is_han(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def load_confusables() -> dict[str, str]:
    """单码位源 → 目标字符串。多码位源（如组合序列）忽略，语料里几乎不会出现。"""
    m: dict[str, str] = {}
    if not CONF.exists():
        return m
    for line in CONF.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 2:
            continue
        src, dst = parts[0], parts[1]
        if " " in src:
            continue                      # 多码位源，跳过
        try:
            s = chr(int(src, 16))
            d = "".join(chr(int(x, 16)) for x in dst.split())
        except ValueError:
            continue
        m[s] = d
    return m


def skeleton(text: str, table: dict[str, str], rounds: int = 3) -> str:
    """迭代替换到不动点。"""
    for _ in range(rounds):
        nxt = "".join(table.get(c, c) for c in text)
        if nxt == text:
            break
        text = nxt
    return text


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base = pathlib.Path(args[0]) if args else ROOT / "校勘版"
    want_skel = "--skeleton" in sys.argv

    table = load_confusables()
    print(f"confusables 条目：{len(table)}")

    freq: collections.Counter[str] = collections.Counter()
    where: dict[str, set[str]] = collections.defaultdict(set)
    files = sorted(base.rglob("*.txt"))
    for fp in files:
        t = fp.open("r", encoding="utf-8", errors="replace", newline="").read()
        for ch in t:
            if ch in KEEP_ASCII or ch in CJK_PUNCT or is_han(ch):
                continue
            freq[ch] += 1
            if len(where[ch]) < 4:
                where[ch].add(fp.name)

    print(f"扫描 {len(files)} 个文件，可疑字符 {len(freq)} 种 / {sum(freq.values())} 次\n")
    print(f"{'字符':<4}{'U+':<9}{'次数':>8}  {'skeleton':<12}{'skeleton是汉字':<16}示例文件")
    rows = []
    for ch, n in freq.most_common():
        sk = skeleton(ch, table)
        han = is_han(sk) if len(sk) == 1 else all(is_han(c) for c in sk)
        try:
            name = unicodedata.name(ch)
        except ValueError:
            name = "?"
        print(f"{ch:<4}U+{ord(ch):04X}{n:>8}  {sk!r:<12}{str(han):<16}{next(iter(where[ch]))[:40]}  [{name}]")
        rows.append((ch, f"U+{ord(ch):04X}", n, sk, int(han), "|".join(sorted(where[ch])[:3]), name))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        f.write("char,codepoint,count,skeleton,skeleton_is_han,files,name\n")
        for r in rows:
            f.write(",".join(f'"{str(x).replace(chr(34), chr(34)*2)}"' for x in r) + "\n")
    print(f"\n写出 {OUT}")

    if want_skel:
        han_like = [ch for ch, _ in freq.items() if is_han(skeleton(ch, table))]
        if han_like:
            print(f"\n同形字（skeleton 归到汉字）共 {len(han_like)} 种：{''.join(han_like)}")
        else:
            print("\n没有发现伪装成汉字的外文同形字")
    return 0


if __name__ == "__main__":
    sys.exit(main())
