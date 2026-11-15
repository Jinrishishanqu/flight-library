# -*- coding: utf-8 -*-
import os, difflib, sys
SRC=r"D:\article_tools\out\final7"; DST=r"D:\article_tools\out\final8"
rows=[]
for root,dirs,fs in os.walk(DST):
    for f in fs:
        if not f.lower().endswith(".txt"): continue
        rel=os.path.relpath(os.path.join(root,f),DST)
        a=os.path.getsize(os.path.join(SRC,rel)); b=os.path.getsize(os.path.join(root,f))
        rows.append((a-b,rel))
rows.sort(reverse=True)
for d,rel in rows[:5]:
    a=open(os.path.join(SRC,rel),encoding="utf-8",errors="replace",newline="").read().split("\n")
    b=open(os.path.join(DST,rel),encoding="utf-8",errors="replace",newline="").read().split("\n")
    print(f"\n##### {rel}  size_delta={d}")
    n=0
    for line in difflib.unified_diff(a,b,lineterm="",n=0):
        if line.startswith(("---","+++")): continue
        if n>=10: break
        print(line[:200]); n+=1