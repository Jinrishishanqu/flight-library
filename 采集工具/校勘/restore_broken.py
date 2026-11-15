# -*- coding: utf-8 -*-
"""还原被标点打断的性/身体/情色词汇：X，Y / X、Y -> XY"""
import os, re, sys, collections

SRC = r"D:\article_tools\out\final17"
OUT = r"D:\article_tools\out\final18"

WORDS = """
肉棒 龟头 精液 射精 阴道 阴茎 阴唇 子宫 奶子 乳头 屁股 鸡巴 骚逼 小穴 淫水 高潮
淫穴 肉穴 肉洞 阳具 阴蒂 睾丸 乳房 淫荡 骚穴 肉屌 大屌 春药 爱液 骚货 骚屄 豪乳 巨乳
乳肉 乳尖 乳峰 双乳 玉乳 嫩肉 软肉 花穴 嫩穴 穴口 穴里 肉缝 肉臀 淫肉 媚肉 蜜穴 蜜汁
淫液 阴户 阴部 下体 私处 私密 花心 花唇 卵子 美穴 美肉 大龟 小穴 淫水 淫精
抽插 抽送 挺动 插进 进出 揉搓 揉弄 抚弄 舔舐 吸吮 吮吸 亲吻 玩弄 挑逗 交合 媾和
奸淫 强奸 调教 捆绑 束缚 勃起 痉挛 抽搐 颤抖 颤栗 酥麻 酸软 酥软 湿润 泥泞 泛滥
滚烫 灼热 胀痛 肿胀 撑满 胀大
赤裸 香肩 雪白 娇躯 玉手 玉足 细腰 柳腰 翘臀 腿根 腰肢 酥胸 乳沟 臀肉 股间 体香
香汗 潮红 羞红 媚眼 妖艳 美艳 绝美 光洁 滑腻 饱满 白嫩 白腻 光滑 水嫩 柔软
淫笑 淫叫 淫乱 淫邪 浪叫 骚浪 春情 情欲 淫欲 肉欲 性欲 快感 沉沦 堕落 羞耻 娇喘
娇吟 娇啼 呻吟 浪荡 放浪 妩媚 风情 媚态 香艳 艳情 春水 淫靡 秽液 白浊 精华 阳精
""".split()

WORDS = sorted(set(WORDS), key=len, reverse=True)
PAT = {}
for w in WORDS:
    alts = [re.escape(w[:i]) + r"[，、]" + re.escape(w[i:]) for i in range(1, len(w))]
    PAT[w] = re.compile("|".join(alts))


def fix(text, stat):
    for w in WORDS:
        p = PAT[w]

        def rep(m):
            stat[w] += 1
            return w
        text = p.sub(rep, text)
    return text


stat = collections.Counter()
files = changed = 0
os.makedirs(OUT, exist_ok=True)
for root, d, fs in os.walk(SRC):
    for fn in fs:
        if not fn.endswith(".txt"):
            continue
        src = os.path.join(root, fn)
        rel = os.path.relpath(src, SRC)
        dst = os.path.join(OUT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        t = open(src, encoding="utf-8", errors="replace", newline="").read()
        n = fix(t, stat)
        files += 1
        if n != t:
            changed += 1
        open(dst, "w", encoding="utf-8", newline="").write(n)

print("files=%d changed=%d total_hits=%d" % (files, changed, sum(stat.values())))
for w, c in stat.most_common():
    print("%s\t%d" % (w, c))
