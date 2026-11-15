import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
t = open(r"F:\新建文件夹\read - 副本\_tmp_txt\409.txt", encoding="utf-8").read()
print("### 玉小刚:", len(re.findall("玉小刚", t)), "### 大师:", len(re.findall("大师", t)), "### 大师姐:", len(re.findall("大师姐", t)))
for m in list(re.finditer("大师", t))[:6]:
    s = max(0, m.start()-120)
    print("...", t[s:m.start()+150].replace("\n", " "), "\n---")
print("### head"); print(t[:1200])
