import re, io
t = open(r'_txt\135.txt', encoding='utf-8').read()
for n in ['萧薰儿','古薰儿','魂薰儿','薰儿','药尘','药老']:
    print(n, t.count(n))
print('---- contexts of 萧薰儿')
for m in re.finditer('萧薰儿', t):
    print(repr(t[max(0,m.start()-60):m.start()+60]))
    print('---')
