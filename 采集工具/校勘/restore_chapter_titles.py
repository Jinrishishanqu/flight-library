# -*- coding: utf-8 -*-
"""用原文的章标题行，修复校勘版里「标题与正文被接成一行」的问题。

根因：排版层（S1）的接行规则把短标题行当成被硬换行的正文，接到了下一段前面。
      原文里标题本来是独立行（`第2章、情挑大小姐` 后面紧跟空行）。

做法：从原文提取章标题行 → 在校勘版里按章序定位（忽略空白差异）→
      若标题后紧跟非空字符，插入 `\\r\\n\\r\\n`。只插入空白，可逆。

用法：
    python restore_chapter_titles.py --dry
    python restore_chapter_titles.py             # 输出到 校勘版_chap
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(r"F:\新建文件夹\read - 副本")
PROOF = ROOT / "校对后文章"
CANON = ROOT / "校勘版"
OUT = ROOT / "校勘版_chap"
MANIFEST = ROOT / "采集工具" / "记录" / "校对清单.csv"
REPORT = ROOT / "采集工具" / "记录" / "章标题恢复.json"

CHAP_LINE = re.compile(r"^[ \t　]*(第[0-9零一二三四五六七八九十百千两]+[章节回][^\r\n]{0,48})[ \t　\r]*$")
# 标题里不应出现句末标点；含这些的整行更可能是正文
NOT_TITLE = "。！？…"


def read_any(p: Path) -> str:
    """先 UTF-8，失败退 gb18030。"""
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            return p.open("r", encoding=enc, errors="strict", newline="").read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return p.open("r", encoding="utf-8", errors="replace", newline="").read()


def titles_of(src: Path) -> list[str]:
    t = read_any(src)
    out = []
    for line in t.split("\n"):
        m = CHAP_LINE.match(line)
        if not m:
            continue
        title = m.group(1).strip()
        if any(c in NOT_TITLE for c in title):
            continue
        if len(title) < 3:
            continue
        out.append(title)
    return out


# 比对时丢弃的字符：空白 + 各类引号（校勘版把弯引号统一成「」，原文可能是“”）
DROP_CHARS = set(" \t\r\n\u3000\u00a0“”‘’「」『』\"\u0027")
# 标题尾部的收引号：插入换行时要跳过去
CLOSE_Q = set("”’」』\"")


def clean_map(raw: str):
    """返回 (clean_text, idx[])：idx[i] = clean 第 i 字符在 raw 中的下标。"""
    chars = []
    idx = []
    for i, ch in enumerate(raw):
        if ch in DROP_CHARS:
            continue
        chars.append(ch)
        idx.append(i)
    return "".join(chars), idx


def norm_title(s: str) -> str:
    return "".join(ch for ch in s if ch not in DROP_CHARS)


def main() -> int:
    dry = "--dry" in sys.argv
    only = None
    if "--file" in sys.argv:
        only = sys.argv[sys.argv.index("--file") + 1]

    rows = list(csv.DictReader(MANIFEST.open(encoding="utf-8-sig")))
    stats = Counter()
    samples = []
    changed = 0
    per_file = []

    # 先全量镜像，保证输出目录完整；改动的文件随后覆盖
    if not dry:
        import shutil
        shutil.copytree(CANON, OUT, dirs_exist_ok=True)

    for r in rows:
        outp = Path(r["Output"])
        try:
            rel = outp.relative_to(PROOF)
        except ValueError:
            stats["skip_not_under_proof"] += 1
            continue
        canon = CANON / rel
        if not canon.exists():
            stats["skip_no_canon"] += 1
            continue
        if only and only not in str(rel):
            continue
        srcs = [Path(s) for s in r["Sources"].split("|") if s.strip()]
        titles = []
        for s in srcs:
            if s.exists():
                titles.extend(titles_of(s))
            else:
                stats["src_missing"] += 1
        if not titles:
            stats["no_titles"] += 1
            continue

        raw = canon.open("r", encoding="utf-8", errors="replace", newline="").read()
        ctext, cmap = clean_map(raw)
        pos = 0
        inserted = []
        miss = 0
        for ti, title in enumerate(titles):
            ct = norm_title(title)
            if not ct:
                continue
            end = -1
            f = ctext.find(ct, pos)
            if f >= 0:
                end = f + len(ct)
            else:
                # 回退一：全库找整串
                f = ctext.find(ct)
                if f >= 0:
                    end = f + len(ct)
            if end < 0:
                # 回退二：双锚（前 8 字 + 末 3 字），容忍正文以外的改动
                a1 = ct[:8]
                a2 = ct[-3:] if len(ct) > 8 else ct
                f1 = ctext.find(a1, pos)
                if f1 < 0:
                    f1 = ctext.find(a1)
                if f1 >= 0:
                    f2 = ctext.find(a2, f1, f1 + len(ct) + 24)
                    if f2 >= 0:
                        end = f2 + len(a2)
            if end < 0:
                miss += 1
                continue
            pos = end
            raw_end = cmap[end - 1] + 1
            # 已经断开？（后面是换行或结尾）
            j = raw_end
            nxt = raw[j: j + 3]
            if not nxt or nxt[0] in "\r\n":
                stats["already_ok"] += 1
                continue
            # 跳过标题尾部的收引号，再插换行
            while j < len(raw) and raw[j] in CLOSE_Q:
                j += 1
            inserted.append(j)
            stats["need_break"] += 1

        if inserted:
            buf = []
            last = 0
            for p in sorted(inserted):
                buf.append(raw[last:p])
                buf.append("\r\n\r\n")
                last = p
            buf.append(raw[last:])
            new = "".join(buf)
            if re.sub(r"\s+", "", new) != re.sub(r"\s+", "", raw):
                stats["FAIL"] += 1
                continue
            changed += 1
            per_file.append({"file": str(rel), "breaks": len(inserted), "miss": miss})
            if len(samples) < 20:
                p0 = sorted(inserted)[0]
                samples.append({"file": str(rel), "ctx": raw[max(0, p0 - 30): p0 + 30]})
            if not dry:
                dst = OUT / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.open("w", encoding="utf-8", newline="").write(new)
        elif miss:
            stats["file_all_miss"] += 1

        # 全量镜像：未改动的文件也要进输出目录，否则目录不完整
        if not dry and not inserted:
            dst = OUT / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.open("wb").write(canon.open("rb").read())

    print(f"{'[DRY] ' if dry else ''}rows={len(rows)} changed={changed}")
    for k, v in sorted(stats.items()):
        print(f"  {k:24s} {v}")
    if per_file:
        per_file.sort(key=lambda x: -x["breaks"])
        print("\n断开最多的文件：")
        for x in per_file[:12]:
            print(f"  {x['breaks']:4d} 断  miss={x['miss']:3d}  {x['file']}")
    for s in samples[:6]:
        print(f"\n  [{s['file']}]\n    {s['ctx']!r}")
    if not dry:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({"stats": dict(stats), "per_file": per_file},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n输出 -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
