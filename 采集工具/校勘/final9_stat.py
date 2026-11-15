# -*- coding: utf-8 -*-
import os, re, collections
A = r"D:\article_tools\out\final7"
B = r"D:\article_tools\out\final9"

def stat(root):
    n = ch = 0
    for r, d, fs in os.walk(root):
        for fn in fs:
            if fn.endswith(".txt"):
                n += 1
                with open(os.path.join(r, fn), "r", encoding="utf-8", errors="replace", newline="") as f:
                    ch += len(f.read())
    return n, ch

na, ca = stat(A)
nb, cb = stat(B)
print(f"final7: files={na} chars={ca}")
print(f"final9: files={nb} chars={cb} delta={cb-ca} ({(cb-ca)/ca*100:.2f}%)")

# 绿帽文件引号检查
rel = r"斗破\《绿帽之斗破苍穹》-全篇-59.5w.txt"
fb = os.path.join(B, rel)
if os.path.exists(fb):
    with open(fb, "r", encoding="utf-8", errors="replace", newline="") as f:
        t = f.read()
    cnt = collections.Counter({"『": t.count("『"), "』": t.count("』"),
                               "「": t.count("「"), "」": t.count("」"),
                               "“": t.count("“"), "”": t.count("”"),
                               "‘": t.count("‘"), "’": t.count("’")})
    print("绿帽:", dict(cnt))
    for i, line in enumerate(t.split("\n")[:8], 1):
        print(f"  {i}: {line[:100]}")

# 全库引号平衡
bal = collections.Counter()
for r, d, fs in os.walk(B):
    for fn in fs:
        if not fn.endswith(".txt"):
            continue
        with open(os.path.join(r, fn), "r", encoding="utf-8", errors="replace", newline="") as f:
            t = f.read()
        for a, b in [("“", "”"), ("‘", "’"), ("「", "」"), ("『", "』")]:
            bal[a] += t.count(a); bal[b] += t.count(b)
print("全库引号:", dict(bal))

# 残留可疑字符
SUS = re.compile(r"[╒╗╜╞╡∷★☆]|地址发布|发布邮箱|最新发布|寻回|找回|\^\.")
hit = collections.Counter()
for r, d, fs in os.walk(B):
    for fn in fs:
        if not fn.endswith(".txt"):
            continue
        with open(os.path.join(r, fn), "r", encoding="utf-8", errors="replace", newline="") as f:
            for m in SUS.finditer(f.read()):
                hit[m.group()] += 1
print("残留可疑:", dict(hit) if hit else "无")
