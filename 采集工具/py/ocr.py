# -*- coding: utf-8 -*-
"""
离线 OCR —— RapidOCR(PP-OCRv4 ONNX) 替代 Windows WinRT OCR。

优势：
  * 不依赖 PS5.1 / WinRT，任意 python 环境可跑
  * 中文识别率高，自带方向分类，可处理长截图
  * 输出按行聚类并保留阅读顺序

用法：
  python ocr.py --in 图.png [--out 文本.txt] [--lang ch] [--min-score 0.5]
  python ocr.py --dir 归档/临时/shot --outdir 归档/临时/ocr
"""
from __future__ import annotations

import argparse
import os
import pathlib
import statistics
import sys

try:
    from rapidocr_onnxruntime import RapidOCR
except Exception as e:  # pragma: no cover
    print("需要 rapidocr-onnxruntime：uv pip install rapidocr-onnxruntime", file=sys.stderr)
    raise


_engine: RapidOCR | None = None


def engine() -> RapidOCR:
    global _engine
    if _engine is None:
        _engine = RapidOCR()
    return _engine


def group_lines(boxes: list[list[list[float]]], texts: list[str], scores: list[float], min_score: float):
    """按 y 中心聚类成行，行内按 x 排序。"""
    items = []
    for box, txt, sc in zip(boxes, texts, scores):
        if sc < min_score:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append(((min(ys) + max(ys)) / 2, min(xs), max(ys) - min(ys), txt, sc))
    if not items:
        return []
    items.sort(key=lambda t: (t[0], t[1]))
    heights = [t[2] for t in items]
    tol = max(6.0, statistics.median(heights) * 0.6)
    lines, cur, cur_y = [], [], None
    for it in items:
        if cur_y is None or abs(it[0] - cur_y) <= tol:
            cur.append(it)
            cur_y = it[0] if cur_y is None else (cur_y + it[0]) / 2
        else:
            lines.append(sorted(cur, key=lambda t: t[1]))
            cur, cur_y = [it], it[0]
    if cur:
        lines.append(sorted(cur, key=lambda t: t[1]))
    out = []
    for ln in lines:
        s = ""
        prev_x2 = None
        for _, x1, _, txt, _ in ln:
            if prev_x2 is not None and x1 - prev_x2 > 12:
                s += " "
            s += txt
            prev_x2 = x1 + len(txt) * 8
        out.append(s.strip())
    return out


def ocr_image(path: str, min_score: float = 0.5) -> list[str]:
    res, _ = engine()(path)
    if not res:
        return []
    boxes = [r[0] for r in res]
    texts = [r[1] for r in res]
    scores = [float(r[2]) for r in res]
    return group_lines(boxes, texts, scores, min_score)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src")
    ap.add_argument("--out", dest="dst")
    ap.add_argument("--dir", dest="srcdir")
    ap.add_argument("--outdir", dest="dstdir")
    ap.add_argument("--min-score", type=float, default=0.5)
    args = ap.parse_args(argv)

    if args.src:
        lines = ocr_image(args.src, args.min_score)
        text = "\n".join(lines) + "\n"
        if args.dst:
            os.makedirs(os.path.dirname(os.path.abspath(args.dst)), exist_ok=True)
            with open(args.dst, "w", encoding="utf-8-sig", newline="\r\n") as fh:
                fh.write(text)
        print(f"{len(lines)} 行 / {len(''.join(lines))} 字")
        return 0

    if args.srcdir and args.dst:
        src = pathlib.Path(args.srcdir)
        imgs = [p for p in sorted(src.rglob("*")) if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp")]
        allt: list[str] = []
        for p in imgs:
            allt.extend(ocr_image(str(p), args.min_score))
        os.makedirs(os.path.dirname(os.path.abspath(args.dst)), exist_ok=True)
        with open(args.dst, "w", encoding="utf-8-sig", newline="\r\n") as fh:
            fh.write("\n".join(allt) + "\n")
        print(f"{len(imgs)} 图 -> {len(allt)} 行 / {len(''.join(allt))} 字")
        return 0

    if args.srcdir and args.dstdir:
        src = pathlib.Path(args.srcdir)
        dst = pathlib.Path(args.dstdir)
        imgs = [p for p in sorted(src.rglob("*")) if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp")]
        for p in imgs:
            lines = ocr_image(str(p), args.min_score)
            out = dst / (p.stem + ".txt")
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", encoding="utf-8-sig", newline="\r\n") as fh:
                fh.write("\n".join(lines) + "\n")
            print(f"{p.name} -> {out.name}  {len(lines)} 行")
        return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
