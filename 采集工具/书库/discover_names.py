"""从作品正文中发现人名候选（不依赖 guard 词表），用于原创角色识别。

思路：
1) 姓氏法：百家姓常见单姓/复姓 + 1~2 字
2) 称谓法：XX大人 / XX娘娘 / XX公子 / XX姑娘 / XX夫人 / XX师父 …
3) 频次 + 上下文可信度双重过滤（person_score ≥ 0.5）

用法：python discover_names.py <work_id> [--top 30]
"""
from __future__ import annotations

import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "采集工具" / "书库" / "data" / "library.db"

SURNAME = (
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄"
    "和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁"
    "杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍"
    "虞万支柯昝管卢莫经房裘缪干解应宗丁宣贲邓郁单杭洪包诸左石崔吉钮龚"
    "程嵇邢滑裴陆荣翁荀羊於惠甄曲家封芮羿储靳汲邴糜松井段富巫乌焦巴弓"
    "牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙"
    "叶幸司韶郜黎蓟薄印宿白怀蒲邰从鄂索咸籍赖卓蔺屠蒙池乔阴鬱胥能苍双"
    "闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍卻璩桑桂濮牛寿通边扈燕冀郏浦尚农"
    "温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘"
    "匡国文寇广禄阙东欧殳沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空"
    "曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
)
SURNAME2 = (
    "欧阳", "太史", "端木", "上官", "司马", "东方", "独孤", "南宫", "万俟", "闻人",
    "夏侯", "诸葛", "尉迟", "公羊", "赫连", "澹台", "皇甫", "宗政", "濮阳", "公冶",
    "太叔", "申屠", "公孙", "慕容", "仲孙", "钟离", "长孙", "宇文", "司徒", "鲜于",
    "司空", "闾丘", "子车", "亓官", "司寇", "巫马", "公西", "颛孙", "壤驷", "公良",
    "漆雕", "乐正", "宰父", "谷梁", "拓跋", "夹谷", "轩辕", "令狐", "段干", "百里",
    "呼延", "东郭", "南门", "羊舌", "微生", "梁丘", "左丘", "东门", "西门", "南荣",
)

# 名字里绝不会出现的字（虚词、动词、量词、方位、代词等）
BAD_NAME_CHAR = set(
    "的了着过而则就都也又还且并但却是在被把让给对向从于之其此该很更最与和"
    "等以为及或如若故因由使将即虽即使然于甚何等些个只仅却才再又很太更最"
    "不没别莫勿未无有不非否吗呢吧啊呀么哦噢唉嗯喂哎"
    "一二三四五六七八九十百千万亿两几半些许"
    "上下左右前后里外中内间旁边处所时候年月日天"
    "说笑看听想走跑站坐起立来去到回出进开合推拉抓"
    "手眼口舌身心面头脸眉眼鼻耳唇齿颈肩背腰腿脚"
    "大小多少长短高低新旧老少男女"
    "道是有人我你他她它们自己这那些什么怎么为何"
    "力量气息声音光芒神色表情动作身体事情东西"
    "师兄师弟师姐师妹师父师尊弟子长老宗主族人"
    "一处一切一些一样一边一直一起一同一阵一时"
)

# 称谓词：出现在名字后面
TITLE_SUFFIX = (
    "大人", "娘娘", "公子", "姑娘", "夫人", "太太", "小姐", "少爷", "老爷",
    "师父", "师尊", "师兄", "师弟", "师姐", "师妹", "弟子", "长老", "宗主",
    "族长", "家主", "陛下", "殿下", "将军", "元帅", "掌门", "帮主", "教主",
    "前辈", "道友", "仙子", "圣女", "少主", "姑娘", "大王", "女王", "女帝",
)

# 名字常用字（第 3 字必须是其中之一，否则视为词被切坏，如「冷汗瞬」「经地胡」）
# 由现有 67 个已确认角色名的末尾字 + 常用姓名用字合成
NAME_CHAR = set(
    "三东久书仙俊儿元冬凡动卡厉夭妍娜婉尘幽晨月林桃桐楠檀欢泰浩清潇灵炎"
    "然环琪瑶璃白眉石立竹素老舞荣莎蚕贝雅雪静韵鳞麟龙"
    "远轩柱鱼妃峰刚强华明亮军平安福贵才文武德义礼智信忠孝仁爱和顺兴旺"
    "发达昌盛康健寿喜乐庆祥瑞吉利贞洁秀丽艳芳香玉珍珠宝金银铁钢山河"
    "海江湖川原野田土木森松柏梅兰菊荷莲杏柳杨榕枫云霞露霜冰雨风雷电光"
    "辉煌星辰日天地乾坤宇宙洪荒玄黄凤虎豹狼鹰鹤鹏鸿雁燕莺蝶蝉虾蟹龟蛇虫"
    "伟芳英慧巧娟淑惠翠芝萍红娥玲芬彩春兰凤梅琳环荣爱妹霞香莺媛艳瑞嘉"
    "琼勤珍莉桂娣叶璧璐娅琦晶茜秋珊锦黛青倩婷姣娴瑾颖露怡婵雁蓓纨仪荷"
    "丹蓉君琴蕊薇菁梦岚苑婕馨瑗琰融园艺咏卿聪澜纯毓悦昭爽琬茗羽希宁欣"
    "飘育滢馥筠柔霭凝晓霄芸菲寒伊亚宜可姬舒影荔枝丽妮子公子玉龙凤仙魔帝"
    "勇毅俊军平保辉力明永健世广志兴良仁波贵福生元胜学祥发新利飞彬富"
    "顺信杰涛昌成康星光达岩中茂进有坚彪博诚先敬震振壮会思群豪心邦承"
    "言之清凡风云天宇轩然澈寒尘汐洛琛珩瑾珏彦承允泽昀昱曜曦曦"
    "璧玉琳琪瑶璃璇玥珂珊玥瑛瑄琰璐琬璋琥珀琳琅"
)

# 名字首字不可能出现的字（否则是「后韩风」这类跨词切分）
# 高频非人名词 / 形容词，容易被当成「姓+名」
STOP_WORDS = set("""
温柔 安静 安心 明白 清楚 高兴 快乐 愤怒 惊讶 疑惑 冷笑 微笑 沉默 平静
淡淡 轻轻 缓缓 慢慢 顿时 瞬间 忽然 突然 似乎 仿佛 好像 依旧 仍然 依然
白色 红色 黑色 青色 金色 银色 灰色 紫色 蓝色 绿色 黄色
江湖 江山 河山 山峰 山谷 天下 天子 王八 王道 王者 白玉 白金 黄金
苏打 苏醒 苏生 华丽 华夏 陈述 陈列 郑重 王者 马路 马虎 柳树 林间
何等 何况 何时 何处 何必 何况 金钱 金属 金石 毛病 毛皮 石头 石榴
""".split())

BAD_TAIL = set("地得着的然着了过著们么呢吧啊呀")
BAD_NAME_HEAD = set("后前中上下里外内这那何每某各该本原来去到从向对把被让使给和与同跟及并或而则就都也又还且但却是在")

SENT_SPLIT = re.compile(r"[。！？…\n]")


def person_score(text: str, name: str) -> float:
    """名字作主语/宾语的上下文占比。"""
    n = text.count(name)
    if n == 0:
        return 0.0
    hits = 0
    start = 0
    while True:
        i = text.find(name, start)
        if i < 0:
            break
        start = i + 1
        after = text[i + len(name): i + len(name) + 2]
        before = text[i - 1] if i > 0 else "。"
        ok_after = any(after.startswith(w) for w in (
            "道", "说", "笑", "问", "答", "怒", "叹", "点头", "摇头", "看", "听",
            "便", "也", "却", "又", "已", "正", "把", "被", "将", "向", "对",
            "和", "与", "给", "让", "低", "抬", "转", "站", "坐", "走", "跑",
            "伸", "的", "一", "不", "在", "是", "心", "身", "眼", "脸", "手",
        ))
        ok_before = before in "。！？…”’」』：；、，\n \t（《" or before == ""
        if ok_after or ok_before:
            hits += 1
    return hits / n


def find_candidates(full: str, top: int = 40) -> list[tuple[int, str]]:
    cnt: Counter[str] = Counter()

    # 1) 姓氏法：复姓优先
    for s2 in SURNAME2:
        for m in re.finditer(re.escape(s2) + r"[\u4e00-\u9fff]{1,2}", full):
            w = m.group(0)
            if len(w) >= 3 and not (set(w[2:]) & BAD_NAME_CHAR) and w[-1] in NAME_CHAR:
                cnt[w] += 1
    for s1 in SURNAME:
        for m in re.finditer(re.escape(s1) + r"[\u4e00-\u9fff]{1,2}", full):
            w = m.group(0)
            tail = w[1:]
            if set(tail) & BAD_NAME_CHAR:
                continue
            # 两字、三字候选的末字都必须是常见姓名用字（挡掉「金币」「毕竟」「屈辱」）
            if w[-1] not in NAME_CHAR:
                continue
            cnt[w] += 1

    # 2) 称谓法：X大人 / X娘娘 前 2~3 字
    for suf in TITLE_SUFFIX:
        for m in re.finditer(r"[\u4e00-\u9fff]{2,3}" + re.escape(suf), full):
            w = m.group(0)[: -len(suf)]
            if len(w) >= 2 and not (set(w) & BAD_NAME_CHAR):
                cnt[w] += 1

    out: list[tuple[int, str]] = []
    for w, n in cnt.items():
        if n < 6:
            continue
        if w in STOP_WORDS:
            continue
        if w[0] in BAD_NAME_HEAD or w[-1] in BAD_TAIL:
            continue
        if person_score(full, w) < 0.5:
            continue
        # 三字候选若前两字单独高频（如「冉绝」3698 次 vs「冉绝刚」12 次），说明是切坏的
        if len(w) == 3 and full.count(w[:2]) >= n * 3:
            continue
        out.append((n, w))
    out.sort(reverse=True)

    # 去前缀包含：有「王冬儿」就不要「王冬」
    keep: list[tuple[int, str]] = []
    seen: set[str] = set()
    for n, w in out:
        if any(w != o and o.startswith(w) for o in seen):
            continue
        if any(w != o and w.startswith(o) for o in seen):
            # w 是已收词的前缀 → 用长的替换短的
            keep = [(m, x) for m, x in keep if x != o] if False else keep
            continue
        seen.add(w)
        keep.append((n, w))
    return keep[:top]


def main() -> int:
    wid = int(sys.argv[1])
    top = 30
    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    w = con.execute("SELECT id,title FROM works WHERE id=?", (wid,)).fetchone()
    chs = con.execute(
        "SELECT content FROM chapters WHERE work_id=? ORDER BY idx", (wid,)
    ).fetchall()
    full = "\n".join(r["content"] for r in chs)
    print(f"# {w['title']}  {len(full)} 字符")
    for n, name in find_candidates(full, top):
        print(f"{n:6d}  {name:8s} score={person_score(full, name):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
