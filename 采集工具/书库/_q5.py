import re
def ctx(path, names, win=350, cap=24):
    t = open(path, encoding='utf-8').read()
    print('#'*20, path, len(t))
    for n in names:
        print(f'[{n}] count={t.count(n)}')
    for n in names:
        seen = []
        for m in re.finditer(n, t):
            s = max(0, m.start()-win); e = min(len(t), m.start()+win)
            if seen and s < seen[-1][1]:
                continue
            seen.append((s,e))
            if len(seen) > cap: break
        print(f'===== {n} contexts ({len(seen)})')
        for s,e in seen:
            print(t[s:e].replace('\n',' '))
            print('  ~~~')
ctx(r'_txt\479.txt', ['伊轻舞'], 400, 14)
ctx(r'_txt\124.txt', ['萧炎'], 320, 16)
ctx(r'_txt\367.txt', ['唐舞桐','王冬儿','冬儿'], 120, 3)
