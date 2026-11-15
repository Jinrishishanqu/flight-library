import os, re
B = r"D:\article_tools\out\final9"
P = re.compile(r"\^\.")
for r, d, fs in os.walk(B):
    for fn in fs:
        if not fn.endswith(".txt"):
            continue
        fp = os.path.join(r, fn)
        with open(fp, encoding="utf-8", errors="replace", newline="") as f:
            t = f.read()
        for m in P.finditer(t):
            a = max(0, m.start() - 45); b = min(len(t), m.end() + 45)
            print(os.path.relpath(fp, B), m.start())
            print("   ", repr(t[a:b]))
