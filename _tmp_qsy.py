import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
t = open(r"F:\新建文件夹\read - 副本\_tmp_txt\480.txt", encoding="utf-8").read()
for m in re.finditer("水月", t):
    s = max(0, m.start()-100)
    print("...", t[s:m.start()+120].replace("\n", " "), "\n---")
