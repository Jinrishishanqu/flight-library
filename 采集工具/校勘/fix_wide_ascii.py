# -*- coding: utf-8 -*-
"""清理残留的「全角 ASCII 字母数字」与全角引号 ＂。

背景：早前的符号统一只处理了「」『』“”与全角括号，漏了两类：
  1. 全角字母数字   ＰＳ ＮＴＲ ＳＭ Ｍ属性 Ｇ点 Ｄ罩杯 Ｔｒｕｅ Ｎ次 ＢＵＧ ｘ589年
  2. 全角引号 U+FF02 ＂ 与 U+FF07 ＇

规则（保守，逐条可核对）：
  - 全角数字/字母 → 半角，只在「与其他全角 ASCII 相邻或独立成词」时转换（无脑映射也是安全的，
    因为这些字符本就不该出现在中文正文里）
  - ＂ 与 ＇：先看是否夹在中文标点旁，是则删（`？＂嘴上` → `？嘴上`），否则转半角 " 与 '
  - 私有区字符 U+E000–U+F8FF：默认只报告不处理（需人工确认）

用法：
  python fix_wide_ascii.py --dry
  python fix_wide_ascii.py --apply
"""
from __future__ import annotations

import collections
import pathlib
import re
import sys

ROOT = pathlib.Path(r"F:\新建文件夹\read - 副本")
SRC = ROOT / "校勘版"
OUT = ROOT / "校勘版_wide"

FW = {chr(0xFF10 + i): str(i) for i in range(10)}
FW.update({chr(0xFF21 + i): chr(0x41 + i) for i in range(26)})
FW.update({chr(0xFF41 + i): chr(0x61 + i) for i in range(26)})

FW_RUN = re.compile("[\uff10-\uff19\uff21-\uff3a\uff41-\uff5a]+")
PUNCT = "，。、；：？！…—～·（）【】《》「」『』“”‘’ \r\n\t"


def fix_fw(s: str) -> str:
    return FW_RUN.sub(lambda m: "".join(FW[ch] for ch in m.group(0)), s)


def fix_quote(s: str) -> tuple[str, int]:
    """＂ ＇ 夹在中文里就删，否则转半角。"""
    n = 0
    out = []
    for i, ch in enumerate(s):
        if ch not in "\uff02\uff07":
            out.append(ch)
            continue
        prev = s[i - 1] if i else ""
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if (prev in PUNCT or nxt in PUNCT) or ("\u4e00" <= prev <= "\u9fff") or ("\u4e00" <= nxt <= "\u9fff"):
            n += 1
            continue
        out.append('"' if ch == "\uff02" else "'")
        n += 1
    return "".join(out), n


def main() -> int:
    apply = "--apply" in sys.argv
    do_quote = "--quotes" in sys.argv
    files = sorted(SRC.rglob("*.txt"))
    stat = collections.Counter()
    changed_files = 0
    samples: list[str] = []
    for fp in files:
        raw = fp.open("r", encoding="utf-8", errors="replace", newline="").read()
        t = raw
        m = FW_RUN.findall(t)
        if m:
            stat["全角ASCII串"] += len(m)
            stat["全角ASCII字符"] += sum(len(x) for x in m)
            for x in m[:2]:
                i = t.find(x)
                samples.append(f"{fp.relative_to(SRC)}: …{t[max(0,i-12):i+len(x)+12]}…".replace("\n", "\\n"))
        t = fix_fw(t)
        if do_quote:
            t, nq = fix_quote(t)
            stat["全角引号"] += nq
        else:
            stat["全角引号(未动)"] += len(re.findall("[\uff02\uff07]", t))
        priv = re.findall("[\ue000-\uf8ff]", t)
        stat["私有区(未处理)"] += len(priv)

        if t != raw:
            changed_files += 1
            if apply:
                rel = fp.relative_to(SRC)
                dest = OUT / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.open("w", encoding="utf-8", newline="").write(t)
        elif apply:
            rel = fp.relative_to(SRC)
            dest = OUT / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.open("w", encoding="utf-8", newline="").write(raw)

    for k, v in stat.items():
        print(f"{k}: {v}")
    print(f"改动文件: {changed_files} / {len(files)}")
    print()
    for s in samples[:30]:
        print("  " + s)
    if not apply:
        print("\n（--dry，未写盘；加 --apply 写到 校勘版_wide）")
    else:
        print(f"\n已写出 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
