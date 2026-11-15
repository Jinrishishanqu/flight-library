# -*- coding: utf-8 -*-
"""章标题粘连修复：把「第N章标题正文…」切成「第N章 标题」+ 正文两段。

只插入换行（不改任何原有字符），删除插入的空白后与原文字节一致（可逆）。

判定只用**强信号**，宁可少切不切错：
  S1 标题词重现  —— 行首 N 字在后面再次出现（作者常在正文开头重提主角/地名）
  S2 正文起始词  —— 自从/当时/这时/原来/却说/话说/不知/数日/第二天… 出现在 3..20 位
  S3 纯标题行    —— 行长 <= 34 且无句末标点，直接视为纯标题，不切

用法：
    python fix_chapters.py --dry
    python fix_chapters.py --dry --file 斗破苍穹老乞丐
    python fix_chapters.py                 # 写出到 校勘版_chap
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"F:\新建文件夹\read - 副本")
SRC = ROOT / "校勘版"
OUT = ROOT / "校勘版_chap"
REPORT = ROOT / "采集工具" / "记录" / "章标题切分.json"

CHAP = re.compile(r"^第[0-9零一二三四五六七八九十百千两]+[章节回]")
SEPS = "、：:．.·・-—　 "
PUNCT = "，。！？；：、「」『』（）()【】…—~～!?,.;:"
END_PUNCT = "。！？…」』\"'"
# 标题尾部这些字说明标题还没说完（回退用）
BAD_TAIL = set("的了着过而则就都也又还且并但却是在被把让给对向从于之其此很更最与和的及或"
               "为以所因由使将即虽并如若故并且然而于是当然个些般样"
               "会时后前中内里上下出来去起说到想看听笑道地得么呢吧啊呀")
BODY_WORDS = ("自从", "当时", "这时", "此时", "此后", "这时", "原来", "却说", "话说",
              "不知", "数日", "几天", "次日", "翌日", "第二天", "第二日", "一个月后",
              "月光", "夜色", "清晨", "傍晚", "时间", "此刻", "当下", "随即", "转眼")
BODY_HEAD = set("自从当这那在此第翌次故原话却不已曾正仍旧更越渐忽猛骤突便才又竟向朝对把被让使令将"
                "一二三四五六七八九十百千万几两某但而随到从自有据时同刚")


def trim_tail(t: str) -> str:
    """把标题末尾的标点/虚词回退掉。"""
    while t and (t[-1] in PUNCT or t[-1] in BAD_TAIL):
        t = t[:-1]
    return t


def candidates(rest: str):
    """返回 [(pos, score, tag)]，pos = rest 中标题结束位置。"""
    out = []
    n = len(rest)
    # S1 标题词重现：取行首 3/4/5 字，在后面（>=6）再次出现的位置
    for wlen in (5, 4, 3):
        if n <= wlen + 6:
            continue
        key = rest[:wlen]
        for m in re.finditer(re.escape(key), rest[wlen:], ):
            p = m.start() + wlen
            if 4 <= p <= 22:
                out.append((p, 5, f"S1_echo{wlen}"))
    # S2 正文起始词
    for w in BODY_WORDS:
        p = rest.find(w)
        if 3 <= p <= 22:
            out.append((p, 4, f"S2_{w}"))
    return out


def best_split(rest: str):
    cands = candidates(rest)
    best = None
    for pos, score, tag in cands:
        title = trim_tail(rest[:pos])
        if len(title) < 3:
            continue
        body = rest[len(title):]
        if len(body) < 8:
            continue
        s = score
        if title[-1] in BAD_TAIL:
            continue
        if 4 <= len(title) <= 14:
            s += 1
        if best is None or s > best[1] or (s == best[1] and len(title) < len(best[0])):
            best = (title, s, tag, body)
    return best


def process_text(text: str, fname: str, stats: Counter, samples: list, limit: int):
    out = []
    for line in text.split("\n"):
        s = line.strip()
        m = CHAP.match(s)
        if not m:
            out.append(line)
            continue
        rest = s[m.end():]
        if not rest.strip():
            out.append(line)
            continue
        # S3 纯标题行：短、无句末标点
        if len(s) <= 34 and not any(c in END_PUNCT for c in s):
            stats["pure_title"] += 1
            out.append(line)
            continue
        r = best_split(rest)
        if not r:
            stats["no_signal"] += 1
            if len(samples) < limit:
                samples.append({"file": fname, "kind": "no_signal", "text": s[:70]})
            out.append(line)
            continue
        title, score, tag, body = r
        stats["split"] += 1
        stats[f"tag_{tag.split('_')[0]}"] += 1
        if len(samples) < limit:
            samples.append({"file": fname, "kind": "split", "tag": tag, "score": score,
                            "chap": m.group(0), "title": title, "body": body[:46]})
        indent = line[: len(line) - len(line.lstrip())]
        out.append(f"{indent}{m.group(0)}{' ' if rest[0] in SEPS else ''}{title}")
        out.append("")
        out.append(body)
    return "\n".join(out)


def main() -> int:
    dry = "--dry" in sys.argv
    only = None
    if "--file" in sys.argv:
        only = sys.argv[sys.argv.index("--file") + 1]

    files = sorted(SRC.rglob("*.txt"))
    stats = Counter()
    samples = []
    changed = 0
    fails = []

    for p in files:
        rel = str(p.relative_to(SRC))
        if only and only not in rel:
            continue
        raw = p.open("r", encoding="utf-8", errors="replace", newline="").read()
        new = process_text(raw, rel, stats, samples, 30)
        if new == raw:
            continue
        # 可逆校验：去掉全部空白后必须一致
        if re.sub(r"\s+", "", raw) != re.sub(r"\s+", "", new):
            fails.append(rel)
            stats["FAIL"] += 1
            continue
        changed += 1
        if not dry:
            dst = OUT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.open("w", encoding="utf-8", newline="").write(new)

    print(f"{'[DRY] ' if dry else ''}files={len(files)} changed={changed}")
    for k, v in sorted(stats.items()):
        print(f"  {k:16s} {v}")
    if fails:
        print("  不可逆文件:", fails[:5])
    print("\n样本：")
    for s in samples[:24]:
        if s["kind"] == "split":
            print(f"  [{s['tag']:12s}] {s['chap']} | T={s['title']} | B={s['body'][:32]}")
        else:
            print(f"  [no_signal ] {s['text'][:64]}")
    if not dry:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({"stats": dict(stats), "samples": samples},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n输出 -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
