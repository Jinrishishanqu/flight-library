# -*- coding: utf-8 -*-
import re, sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
p = r'F:\新建文件夹\read - 副本\_tmp_txt\176.txt'
t = open(p, encoding='utf-8').read()
# split into sentences
sents = re.split(r'(?<=[。！？\n])', t)
names = ['紫妍', '彩鳞', '美杜莎', '萧潇', '萧炎', '薰儿']
import collections
for nm in names:
    print('==========', nm)
    hits = [s.strip().replace('\n',' ') for s in sents if nm in s]
    for s in hits:
        if len(s) < 8:
            continue
        print(('-' + s)[:300])
    print()
