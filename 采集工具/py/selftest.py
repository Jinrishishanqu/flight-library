# -*- coding: utf-8 -*-
"""外部工具链自检：确认每个包在本机可用并输出能力样例。"""
import io
import sys

out = io.StringIO()


def w(*a):
    print(*a, file=out)


import ftfy
import opencc
import cn2an
import rapidfuzz
from rapidfuzz import fuzz
import datasketch
import trafilatura
import charset_normalizer
import regex

w("python", sys.version.split()[0])
w("ftfy", ftfy.__version__)
w("ftfy mojibake:", ftfy.fix_text("ä¸­æ–‡æµ‹è¯•"))
w("ftfy 半角乱码:", ftfy.fix_text("ï¼šä¸€ä¸ª"))

cc_t2s = opencc.OpenCC("t2s")
cc_s2t = opencc.OpenCC("s2t")
w("opencc t2s:", cc_t2s.convert("蕭炎與納蘭嫣然、薰兒"))
w("opencc s2t:", cc_s2t.convert("萧炎与纳兰嫣然、薰儿"))

w("cn2an 三十一 ->", cn2an.cn2an("三十一", "smart"))
w("cn2an 两百零三 ->", cn2an.cn2an("两百零三", "smart"))
w("cn2an 第一千零一回 ->", cn2an.cn2an("一千零一", "smart"))

s1 = "萧炎走进房间，看见薰儿正坐在窗边发呆。"
s2 = "萧炎走进房间，看到薰儿正坐在窗边发呆。"
w("rapidfuzz ratio:", round(fuzz.ratio(s1, s2), 1))
w("rapidfuzz partial:", round(fuzz.partial_ratio(s1, s2), 1))
w("rapidfuzz token_sort:", round(fuzz.token_sort_ratio(s1, s2), 1))

_m = datasketch.MinHash(num_perm=64)
_m.update("测试文本内容".encode("utf-8"))
w("datasketch MinHash digest:", _m.digest()[:6].tolist())
w("datasketch LSH ok:", type(datasketch.MinHashLSH(threshold=0.8, num_perm=64)).__name__)
w("trafilatura", trafilatura.__version__)
w("charset_normalizer", charset_normalizer.__version__)
w("regex", regex.__version__)

try:
    import onnxruntime
    w("onnxruntime", onnxruntime.__version__)
except Exception as e:
    w("onnxruntime MISSING:", e)

try:
    import rapidocr_onnxruntime
    w("rapidocr_onnxruntime", "ok")
except Exception as e:
    w("rapidocr_onnxruntime MISSING:", type(e).__name__)

try:
    import pycorrector
    w("pycorrector", getattr(pycorrector, "__version__", "ok"))
except Exception as e:
    w("pycorrector MISSING:", type(e).__name__)

try:
    import zhconv
    w("zhconv ok", zhconv.convert("蕭炎", "zh-cn"))
except Exception as e:
    w("zhconv MISSING:", type(e).__name__)

sys.stdout.reconfigure(encoding="utf-8")
print(out.getvalue())
