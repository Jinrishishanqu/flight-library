#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""角色档案：只从**本书**正文抽取，不跨书合并（同一人物在不同作品里人设不同）。

维度：
  intro        引言 —— 只取首次出场节附近，尽量不剧透
  story        本作经历 —— 首 / 中 / 末各取一条，带节号
  looks        外貌        figure  身体
  personality  性格        relations 关系
  sexual       性 / 做爱描写（多条）
  sex_tags     性相关标签

用法：
  python build_characters.py              # 全库刷新
  python build_characters.py --work 1     # 单部
  python build_characters.py --limit 8    # 每部最多几张卡
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DB = HERE / "data" / "library.db"
GUARD = ROOT / "采集工具" / "词库" / "guard.txt"

NON_CHAR = {
    "萧家", "魂族", "云岚宗", "迦南学院", "史莱克学院", "魔兽山脉", "七宝琉璃宗",
    "斗气大陆", "塔戈尔沙漠", "唐门", "昊天宗", "武魂殿",
    "斗者", "斗师", "斗王", "斗皇", "斗宗", "斗尊", "斗帝", "封号斗罗", "魂师",
    "魂天帝", "冰帝", "雪帝", "银月", "橘子",
}

TITLES = [
    "封号斗罗", "大长老", "二长老", "大宗主", "圣女", "圣子", "仙子", "女王", "女帝",
    "女皇", "宗主", "族长", "家主", "少主", "长老", "护法", "老祖",
    "封尊", "天尊", "魔尊", "妖王", "龙王", "斗帝", "斗圣", "斗尊", "斗宗",
]

SENT_SPLIT = re.compile(r"(?<=[。！？…」』])")
DESC_HINT = re.compile(r"(?:是|乃|身为|作为|名叫|叫做|本是|曾是|原是|成了|成为|生得|长得|号称|人称|被称)")
BAD_HEAD = set("的地得着了过而则就都也又还且并但却是在被把让给对向从于之其此很更最与和"
               "等以为及或如若故因由使将即虽即便即使并且然而于是当然")
# 事件性动词：用于挑「经历」句
ACT_KW = re.compile(
    r"决定|答应|开始|终于|却被|竟被|被|把|让|冲|跪|抱|推|拉|逃|救|杀|打|骂|笑|哭|叫|"
    r"成为|进入|退|夺|抢|护|藏|骗|逼|求|嫁|娶|收|赐|罚|背叛|救下|挡在|倒在|发现|得知|"
    r"看见|遇见|遇上|来到|离开|带|拿|抓|绑|拖|压|撕|扯|脱|灌|喂|逼问|威胁|答应|承诺")

LOOKS_F = re.compile(
    r"肌肤|皮肤|容貌|容颜|眉眼|眼眸|长发|秀发|青丝|身姿|身段|身材|模样|五官|"
    r"嘴唇|绝美|清丽|娇艳|妖娆|美艳|秀丽|姿色|脸颊|脖颈|黛眉|凤目|明眸|俏脸|"
    r"眉目|曲线|气质|白衣|长裙")
LOOKS_M = re.compile(
    r"英俊|俊美|俊朗|剑眉|星目|面容|面貌|眉眼|神色|脸颊|身材|高大|挺拔|气质|"
    r"嘴角|目光|眼神|轮廓|下颌|少年|男子")
FIGURE_F = re.compile(
    r"乳房|双乳|乳肉|乳沟|胸脯|臀|玉腿|大腿|小腿|腰肢|柳腰|玉足|脚踝|香肩|"
    r"娇躯|玉体|身段|私处|小穴|阴户|蜜穴|花穴|肌肤|肉缝|幽谷|玉颈|玉背|胴体")
FIGURE_M = re.compile(
    r"高大|挺拔|健壮|肌肉|胸膛|肩宽|身躯|身板|魁梧|体格|阳刚|结实|"
    r"手臂|手指|腰腹|双腿|身形|体魄|下身|阳物|胴体")
PERSON_KW = re.compile(
    r"性格|脾气|性子|温柔|冷漠|高傲|倔强|善良|狠辣|沉稳|冲动|天真|单纯|狡黠|心机|"
    r"沉默|活泼|娇蛮|任性|冷艳|清冷|妩媚|骄傲|木讷|憨|怯|羞|大胆|害羞|羞涩")
REL_KW = re.compile(
    r"妻子|夫君|丈夫|娘子|夫人|姐姐|妹妹|哥哥|弟弟|师父|师尊|弟子|母亲|女儿|"
    r"师妹|师姐|少爷|小姐|未婚妻|情人|奴婢|侍女|青梅竹马|夫妻|儿媳|嫂子|婶|"
    r"表姐|表妹|堂姐|堂妹|岳母|婆婆|姑姑|姨妈|老师|学生")
SEX_KW = re.compile(
    r"肉棒|肉刃|阳具|龟头|鸡巴|精液|射精|射在|内射|小穴|肉穴|淫穴|蜜穴|花穴|穴口|"
    r"淫水|爱液|蜜汁|高潮|泄身|呻吟|娇喘|抽插|抽送|插进|挺进|顶进|撞击|舔|吸吮|吮|"
    r"乳头|乳尖|乳晕|阴蒂|阴唇|阴道|后庭|菊门|谷道|破处|处女|初夜|敏感|淫荡|骚|"
    r"口交|吞吐|含住|肛|肏|奸淫|强暴|骑|跪|捆绑|调教|春药|发情|欲火|痉挛|夹紧|"
    r"摩擦|揉搓|抚弄|抵住|肠壁|子宫|裹住|紧致")

SEX_TAG_MAP = [
    ("肉棒", r"肉棒|肉刃|阳具|龟头|鸡巴"),
    ("射精", r"射精|射在|内射|精液|白浊"),
    ("小穴", r"小穴|肉穴|蜜穴|花穴|穴口|阴户"),
    ("淫水", r"淫水|爱液|蜜汁|淫液"),
    ("高潮", r"高潮|泄身|痉挛"),
    ("呻吟", r"呻吟|娇喘|浪叫"),
    ("口交", r"口交|吞吐|含住|吸吮|舔"),
    ("肛交", r"后庭|菊门|谷道|肛"),
    ("破处", r"破处|处女|初夜|第一次"),
    ("调教", r"调教|捆绑|绑|骑|跪|鞭|绳"),
    ("春药", r"春药|发情|欲火|媚药"),
    ("乳头", r"乳头|乳尖|乳晕"),
    ("阴蒂", r"阴蒂|阴唇"),
    ("足交", r"玉足|脚|足"),
    ("敏感", r"敏感"),
    ("淫荡", r"淫荡|骚|淫乱"),
]


def load_guard() -> list[str]:
    if not GUARD.exists():
        sys.exit(f"缺少专名词表：{GUARD}")
    out = []
    for ln in GUARD.read_text("utf-8").splitlines():
        w = ln.strip()
        if w and not w.startswith("#") and w not in NON_CHAR:
            out.append(w)
    return out


def clip(s: str, n: int = 46) -> str:
    s = s.strip()
    return s if len(s) <= n else s[:n].rstrip() + "…"


def pick_intro(chs, name: str) -> str | None:
    """引言只取首现节及其后一节，避免剧透后文。"""
    picked, got = [], False
    for c in chs:
        if name in c["content"]:
            got = True
        if got:
            for s in SENT_SPLIT.split(c["content"]):
                if name in s:
                    picked.append(s.strip())
            break
    # 相邻一节补一些
    if got:
        seen = False
        for c in chs:
            if name in c["content"]:
                if seen:
                    picked += [s.strip() for s in SENT_SPLIT.split(c["content"]) if name in s]
                    break
                seen = True

    def ok(t: str) -> bool:
        return 12 <= len(t) <= 88 and t and t[0] not in BAD_HEAD

    for s in picked:            # 一档：判断句且名字靠前
        if ok(s) and DESC_HINT.search(s) and s.find(name) <= 6:
            return clip(s, 56)
    for s in picked:            # 二档：判断句
        if ok(s) and DESC_HINT.search(s):
            return clip(s, 56)
    for s in picked:            # 三档：旁白句（不含对话）
        if ok(s) and "「" not in s:
            return clip(s, 56)
    for s in picked:            # 四档：任意
        if ok(s):
            return clip(s, 56)
    return None


def pick_title(text: str, name: str) -> str | None:
    sep = "，、 　·"
    tally: dict[str, list[int]] = {}
    for t in TITLES:
        gaps = []
        for m in re.finditer(re.escape(name) + "([" + sep + "]{0,2})" + re.escape(t), text):
            gaps.append(len(m.group(1)))
        for m in re.finditer(re.escape(t) + "([" + sep + "]{0,2})" + re.escape(name), text):
            gaps.append(len(m.group(1)))
        if gaps:
            tally[t] = gaps
    if not tally:
        return None
    best = max(tally.items(), key=lambda kv: (len(kv[1]), -min(kv[1])))
    t, gaps = best
    return t if len(gaps) >= 2 else None


FEM_CHAR = set("眉婉妍婷雅娜娇娟媛芳蕾薇霞蓉莲兰芝芹柔娴静淑嫣妃姬娥婵嫱姝妮妹姐娘嫂婆母女娥妮嫣嫣嫣丽倩琬莹樱蝶燕莺凤月雪霜露香玉珠翠绮绫罗裙钗黛胭脂粉")
MALE_CHAR = set("炎尘凡浩强峰龙虎刚军伟勇杰豪雄阳山石铁钢雷霆锋峰斌武魂帝尊")
FEM_WORDS = ("小姐", "姑娘", "少女", "女子", "夫人", "妻子", "媳妇", "女帝", "女王", "圣女",
             "仙子", "丫鬟", "侍女", "美女", "女孩", "女儿", "姐姐", "妹妹", "母亲", "娘亲",
             "师娘", "女修", "女性", "师妹", "师姐", "红颜", "佳人", "丽人", "美妇", "少妇")
MALE_WORDS = ("少年", "男子", "青年", "少爷", "公子", "男人", "父亲", "爸爸", "丈夫", "师兄",
              "师弟", "男修", "男性", "老者", "老头", "老汉", "大汉", "汉子")


def guess_gender(text: str, name: str) -> str:
    """代词 → 称呼词 → 名字用字，三级投票；都不足以判定就返回「不明」。"""
    f = h = 0
    fw = hw = 0
    for m in re.finditer(re.escape(name), text):
        win = text[m.end(): m.end() + 10]
        f += win.count("她")
        h += win.count("他")
        around = text[max(0, m.start() - 8): m.end() + 12]
        fw += sum(around.count(w) for w in FEM_WORDS)
        hw += sum(around.count(w) for w in MALE_WORDS)
    # 1) 名字用字最可靠（「萧炎」的「炎」、「柳眉」的「眉」）
    score_f = sum(1 for c in name if c in FEM_CHAR)
    score_m = sum(1 for c in name if c in MALE_CHAR)
    if score_f > score_m:
        return "女"
    if score_m > score_f:
        return "男"
    # 2) 称呼词
    if fw + hw >= 2 and fw > hw * 1.5:
        return "女"
    if fw + hw >= 2 and hw > fw * 1.5:
        return "男"
    # 3) 代词（阈值提高，后宫文里「她」到处都是）
    if f + h >= 12 and f > h * 2.0:
        return "女"
    if f + h >= 12 and h > f * 2.0:
        return "男"
    return "不明"


# 人名可信度：名字后接对话/动作动词、或位于句首、或前接「的/和/与」等，才算像人名。
PERSON_NEXT = ("道", "说", "笑", "问", "答", "怒", "叹", "哼", "点头", "摇头", "看", "听",
               "想", "便", "也", "却", "又", "已", "正", "把", "被", "将", "向", "对",
               "和", "与", "给", "让", "低", "抬", "转", "站", "坐", "走", "跑", "伸")
PERSON_PREV = set("，。！？…「」』『\"\"‘’\n \t、；：和与对向给被让把的")


def person_score(text: str, name: str) -> float:
    """0~1。普通名词（如「清水」）会得分很低：它多被量词/动词修饰，后面跟的不是对话动词。"""
    tot = text.count(name)
    if tot == 0:
        return 0.0
    good = 0
    for m in re.finditer(re.escape(name), text):
        nxt = text[m.end(): m.end() + 2]
        prev = text[m.start() - 1] if m.start() else ""
        if any(nxt.startswith(w) for w in PERSON_NEXT):
            good += 1
        elif prev in PERSON_PREV:
            good += 1
    return good / tot


PUNCT_CL = "，。！？；：\r\n"
ANDATIVE = set("朝向对被让使给把和与同替帮为叫令跟于")


def clause_of(t: str, i: int) -> str:
    """返回 i 所在分句（按中文标点切）。"""
    lo = 0
    for c in PUNCT_CL:
        j = t.rfind(c, 0, i)
        if j + 1 > lo:
            lo = j + 1
    hi = len(t)
    for c in PUNCT_CL:
        j = t.find(c, i)
        if 0 <= j < hi:
            hi = j
    return t[lo:hi]


def best_sents(sents, name: str, kw, n=1, lo=14, hi=90, need_name=True, near=10, gap=14) -> list[str]:
    """挑最佳句。三条硬约束防串人：
    1) 名字必须靠前（pos<=10）且前面不是介词（「朝/被/对…」），即名字作主语；
    2) 关键词必须与名字同分句；
    3) 名字与其后 gap 字之内必须出现关键词——覆盖「X的Y」「X那双Y」这类标准描写句式。
    """
    cand = []
    for s in sents:
        t = s.strip()
        if not (lo <= len(t) <= hi):
            continue
        if t[0] in BAD_HEAD:
            continue
        pos = t.find(name)
        if pos < 0:
            continue
        if pos > 10:
            continue
        if pos > 0 and t[pos - 1] in ANDATIVE:
            continue
        cl = clause_of(t, pos)
        head = cl[: gap + len(name)]
        hits = [m.start() for m in kw.finditer(head)]
        if not hits:
            continue
        score = len(hits) * 2
        if pos <= 2:
            score += 3
        score -= len(t) / 120.0
        cand.append((score, t))
    cand.sort(key=lambda x: -x[0])
    out, seen = [], set()
    for _, t in cand:
        key = t[:16]
        if key in seen:
            continue
        seen.add(key)
        out.append(clip(t, 76))
        if len(out) >= n:
            break
    return out


def pick_story(chs, name: str, k: int = 3) -> list[dict]:
    """本作经历：按节推进取首 / 中 / 末三个代表事件句，带节号。"""
    per = []
    for c in chs:
        body = c["content"]
        if name not in body:
            continue
        best = None
        for s in SENT_SPLIT.split(body):
            t = s.strip()
            if not (16 <= len(t) <= 74):
                continue
            if t[0] in BAD_HEAD:
                continue
            if name not in t:          # 经历句必须本人在场，否则会串到同节其他角色
                continue
            sc = 2 if ACT_KW.search(t) else 0
            if "「" not in t:
                sc += 1
            if 0 <= t.find(name) <= 8:
                sc += 1
            if best is None or sc > best[0]:
                best = (sc, t)
        if best:
            per.append((c["idx"], best[1]))
    if not per:
        return []
    if len(per) <= k:
        picks = list(range(len(per)))
    else:
        picks = [0, len(per) // 2, len(per) - 1]
    out, seen = [], set()
    for i in picks:
        idx, t = per[i]
        key = t[:14]
        if key in seen:
            continue
        seen.add(key)
        out.append({"i": idx, "t": clip(t, 68)})
    return out


def pick_relations(text: str, name: str, others: list[str]) -> str | None:
    if not others:
        return None
    alts = "|".join(re.escape(o) for o in others if o != name)
    if not alts:
        return None
    rels = REL_KW.pattern
    cnt: dict[str, int] = {}

    # 「甲的师父 乙」——名字在前
    for m in re.finditer(re.escape(name) + r"的(" + rels + r")", text):
        tail = text[m.end(): m.end() + 12]
        for o in others:
            if o != name and o and o in tail:
                k = f"{m.group(1)} {o}"
                cnt[k] = cnt.get(k, 0) + 1
                break
    # 「乙的师父 甲」——名字在后
    for m in re.finditer(r"(" + alts + r")的(" + rels + r")", text):
        tail = text[m.end(): m.end() + 1 + len(name)]
        if name in tail:
            k = f"{m.group(1)}的{m.group(2)}"
            cnt[k] = cnt.get(k, 0) + 1
    # 「师父霍雨浩」——关系词紧接名字之前
    for m in re.finditer(r"(" + rels + r")[，、 ]{0,2}" + re.escape(name), text):
        k = f"被称作{m.group(1)}"
        cnt[k] = cnt.get(k, 0) + 1
    if not cnt:
        # 退化：只取「甲的REL」描述本身
        m = re.search(re.escape(name) + r"的(" + rels + r")", text)
        return f"的{m.group(1)}" if m else None
    top = sorted(cnt.items(), key=lambda kv: -kv[1])[:2]
    return "、".join(k for k, _ in top)


def build_work(con, wid: int, guard: list[str], limit: int) -> int:
    chs = con.execute(
        "SELECT idx, content FROM chapters WHERE work_id=? ORDER BY idx", (wid,)
    ).fetchall()
    if not chs:
        return 0
    full = "\n".join(c["content"] for c in chs)

    first_idx: dict[str, int] = {}
    for c in chs:
        body = c["content"]
        for w in guard:
            if w not in first_idx and w in body:
                first_idx[w] = c["idx"]

    hits = []
    for w in guard:
        n = full.count(w)
        if n >= 3:
            hits.append((n, w))
    hits.sort(reverse=True)

    present = {w for _, w in hits}
    hits = [(n, w) for n, w in hits
            if not any(o != w and o.startswith(w) and o in present for o in present)]
    # 人名可信度过滤：排除「清水」「银月」这类普通词被当成角色
    hits = [(n, w) for n, w in hits if person_score(full, w) >= 0.30]
    orig = {w for _, w in hits}          # guard 命中 = 原作角色

    # 通用人名发现 = 作者原创角色（不在 guard 里的）
    try:
        from discover_names import find_candidates
        disc = [(n, w) for n, w in find_candidates(full, limit * 3) if w not in orig]
    except Exception:
        disc = []
    seen_d = set()
    for n, w in disc:
        if any(w != o and (o.startswith(w) or w.startswith(o)) for o in orig | seen_d):
            continue
        seen_d.add(w)
        hits.append((n, w))
    hits.sort(reverse=True)
    hits = hits[:limit]
    if not hits:
        con.execute("DELETE FROM characters WHERE work_id=?", (wid,))
        return 0

    total = hits[0][0]
    names = [w for _, w in hits]

    paras = [p for p in full.split("\n") if p.strip()]
    para_of: dict[str, list[str]] = {n: [] for n in names}
    for p in paras:
        for n in names:
            if n in p:
                para_of[n].append(p)

    # 重建前先留住已有的 AI 生成内容（bio 成本高，不能丢）
    old_bio = {r["name"]: (r["bio"], r["bio_at"])
               for r in con.execute(
                   "SELECT name,bio,bio_at FROM characters WHERE work_id=?", (wid,))
               if r["bio"] and r["bio"].strip()}

    con.execute("DELETE FROM characters WHERE work_id=?", (wid,))
    n_done = 0
    for mentions, name in hits:
        sents_name = [s for s in SENT_SPLIT.split(full) if name in s][:300]
        sents_para: list[str] = []
        for p in para_of[name][:400]:
            sents_para.extend(SENT_SPLIT.split(p))

        gender = guess_gender(full, name)
        if gender == "男":
            looks_kw, fig_kw = LOOKS_M, FIGURE_M
            alt = (LOOKS_F, FIGURE_F)
        elif gender == "女":
            looks_kw, fig_kw = LOOKS_F, FIGURE_F
            alt = (LOOKS_M, FIGURE_M)
        else:
            looks_kw, fig_kw = LOOKS_F, FIGURE_F
            alt = (LOOKS_M, FIGURE_M)

        intro = pick_intro(chs, name)
        story = pick_story(chs, name)
        title = pick_title(full, name)
        ratio = mentions / total if total else 0
        role = "主角" if ratio >= 0.34 or mentions >= total * 0.5 else (
            "配角" if ratio >= 0.1 else "提及")
        if role == "提及":
            continue   # 只保留主角与配角
        hue = sum(ord(ch) for ch in name) % 6

        looks = best_sents(sents_name, name, looks_kw, n=1, need_name=True)
        if not looks:
            looks = best_sents(sents_name, name, alt[0], n=1, need_name=True)
        figure = best_sents(sents_name, name, fig_kw, n=1, need_name=True)
        if not figure:
            figure = best_sents(sents_name, name, alt[1], n=1, need_name=True)
        person = best_sents(sents_name, name, PERSON_KW, n=1, need_name=True)
        rel = pick_relations(full, name, names)
        sexual = best_sents(sents_para, name, SEX_KW, n=3, lo=16, hi=86)

        tags, joined = [], "".join(sexual)
        for tag, pat in SEX_TAG_MAP:
            c = len(re.findall(pat, joined))
            if c:
                tags.append((c, tag))
        tags.sort(reverse=True)

        origin = "原作" if name in orig else "原创"
        ob = old_bio.get(name)

        con.execute(
            "INSERT OR REPLACE INTO characters"
            " (work_id,name,aliases,role,gender,mentions,title,intro,first_chapter,hue,"
            "  looks,figure,personality,relations,sexual,sex_tags,story,origin,bio,bio_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (wid, name, None, role, gender, mentions, title, intro,
             first_idx.get(name), hue,
             looks[0] if looks else None,
             figure[0] if figure else None,
             person[0] if person else None,
             rel,
             "\n".join(sexual) if sexual else None,
             json.dumps([t for _, t in tags[:6]], ensure_ascii=False) if tags else None,
             json.dumps(story, ensure_ascii=False) if story else None,
             origin,
             ob[0] if ob else None,
             ob[1] if ob else None))
        n_done += 1
    con.commit()
    return n_done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=int, default=None)
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()

    if not DB.exists():
        sys.exit(f"数据库不存在：{DB}")
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    guard = load_guard()

    ids = [args.work] if args.work else [
        r["id"] for r in con.execute("SELECT id FROM works ORDER BY id")]

    tot = 0
    for i, wid in enumerate(ids, 1):
        tot += build_work(con, wid, guard, args.limit)
        if i % 50 == 0:
            print(f"  [{i}/{len(ids)}] {tot} 角色", flush=True)
    print(f"完成：{len(ids)} 部作品，写入 {tot} 条角色档案")
    for col in ("intro", "story", "looks", "figure", "personality", "relations", "sexual"):
        n = con.execute(
            f"SELECT COUNT(*) FROM characters WHERE {col} IS NOT NULL AND {col}<>''"
        ).fetchone()[0]
        print(f"  {col:12s}{n}")
    con.close()


if __name__ == "__main__":
    main()
