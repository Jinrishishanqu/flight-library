import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
t = open(r"F:\新建文件夹\read - 副本\_tmp_txt\445.txt", encoding="utf-8").read()
print("### 445 青云山 count", len(re.findall("青云山", t)))
for m in re.finditer("青云山", t):
    s = max(0, m.start()-110)
    print("...", t[s:m.start()+110].replace("\n", " "), "\n---")
print("### 445 head")
print(t[:1500])
