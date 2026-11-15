# -*- coding: utf-8 -*-
"""专名一致性扫描 + 台账生成（只用标准库，不依赖 torch/pycorrector）

用法:
    python scan_names.py <lexicon_dir> <target> [--apply OUT_DIR]

target 可以是单个 .txt 或目录（递归）。
输出:
    hits.csv   台账: file,offset,variant,canon,context
    stats.txt  汇总
--apply 时额外写出修正后文本到 OUT_DIR，并生成 patch.csv（含 diff 定位）
"""
import sys, os, csv, io
from pathlib import Path

def load_lexicon(lex_dir):
    guard = []
    p = Path(lex_dir) / "guard.txt"
    if p.exists():
        guard = [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    conf = {}
    p = Path(lex_dir) / "confusion.txt"
    if p.exists():
        for l in p.read_text(encoding="utf-8").splitlines():
            l = l.strip()
            if not l or l.startswith("#"):
                continue
            parts = l.replace("\t", " ").split()
            if len(parts) >= 2:
                conf[parts[0]] = parts[1]
    return guard, conf

def iter_files(target):
    t = Path(target)
    if t.is_file():
        yield t
    else:
        for p in sorted(t.rglob("*.txt")):
            yield p

def ctx_of(text, i, ln):
    a = max(0, i - 20)
    b = min(len(text), i + ln + 20)
    s = text[a:b].replace("\r", "").replace("\n", "\u23ce")
    return s

def main():
    if len(sys.argv) < 3:
        print("usage: scan_names.py <lexicon_dir> <target> [--apply OUT_DIR]")
        return 2
    lex_dir, target = sys.argv[1], sys.argv[2]
    apply_dir = None
    if "--apply" in sys.argv:
        apply_dir = sys.argv[sys.argv.index("--apply") + 1]
        Path(apply_dir).mkdir(parents=True, exist_ok=True)

    guard, conf = load_lexicon(lex_dir)
    print(f"lexicon: guard={len(guard)} confusion={len(conf)}")

    hits = []
    per_word = {}
    nfiles = 0
    nchars = 0

    for fp in iter_files(target):
        try:
            with open(fp, "r", encoding="utf-8", errors="replace", newline="") as fh:
                text = fh.read()
        except Exception as e:
            print(f"SKIP {fp}: {e}")
            continue
        nfiles += 1
        nchars += len(text)
        rel = str(fp)
        file_hits = []
        for bad, good in conf.items():
            start = 0
            while True:
                i = text.find(bad, start)
                if i < 0:
                    break
                file_hits.append((i, bad, good))
                per_word[bad] = per_word.get(bad, 0) + 1
                start = i + 1
        file_hits.sort()
        for i, bad, good in file_hits:
            hits.append((rel, i, bad, good, ctx_of(text, i, len(bad))))

        if apply_dir and file_hits:
            out = text
            for i, bad, good in sorted(file_hits, key=lambda x: -x[0]):
                out = out[:i] + good + out[i + len(bad):]
            dest = Path(apply_dir) / fp.name
            with open(dest, "w", encoding="utf-8", newline="") as fh:
                fh.write(out)
            # 台账：用位置信息反推旧/新上下文
            with (Path(apply_dir) / "patch.csv").open("a", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                if f.tell() == 0:
                    w.writerow(["file", "offset", "old", "new", "context"])
                for i, bad, good in file_hits:
                    w.writerow([rel, i, bad, good, ctx_of(text, i, len(bad))])

    with open("hits.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["file", "offset", "variant", "canon", "context"])
        for row in hits:
            w.writerow(row)

    lines = [
        f"files={nfiles} chars={nchars} hits={len(hits)}",
        "--- per variant ---",
    ]
    for k, v in sorted(per_word.items(), key=lambda x: -x[1]):
        lines.append(f"{k} -> {conf[k]} : {v}")
    Path("stats.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print("wrote hits.csv / stats.txt" + (f" + {apply_dir}" if apply_dir else ""))
    return 0

if __name__ == "__main__":
    sys.exit(main())
