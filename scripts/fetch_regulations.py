#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
船舶低碳情报 —— 法规原文直采 → 生成 RSS 源
════════════════════════════════════════════════════════════════════════

【为什么需要这个脚本】
IMO、船级社、海事局这类机构**官网全都没有 RSS**（实测：DNV 403 / LR 404 /
ABS 404 / ClassNK 无 / CCS 无 / IMO 全是 JS 动态渲染 / 海事局无）。
资讯媒体只会"谈论"法规，不会发布法规原文，所以纯靠 RSS 抓，
「法规前沿」永远只有二手新闻，没有实质性的规则、指南、规范、标准。

本脚本直接抓这些机构官网的**公告列表页**，把「标题 + 日期 + 链接」
提取出来，生成一个标准 RSS 源，喂给 TrendRadar。
于是这些官方文件就会像普通 RSS 条目一样，进入报告、并被 AI 引用。

【它抓什么】
    中国船级社 CCS   —— 规范 / 指南 / 规范指南征求意见 / 中国海事法规 / 材料设备指南
    中国海事局 MSA   —— 船舶技术法规 / 通知公告
（只抓公开列表页，不做任何登录或绕过访问控制）

【怎么用】
    python scripts/fetch_regulations.py                    # 默认 90 天窗口
    python scripts/fetch_regulations.py --days 30          # 只看最近 30 天
    python scripts/fetch_regulations.py --show             # 顺便把抓到的条目打印出来
    python scripts/fetch_regulations.py --out regfeed/reg_feed.xml

【设计要点】
    · 只用 Python 标准库，不依赖 requests / feedparser，任何环境都能跑
    · 单个源失败绝不影响其它源；全部失败也只是生成一个空 feed，不会中断爬虫
    · 按「链接里的 id」去重（CCS 的规范/指南/总览三页大量重叠，必须去重）
    · 输出 RSS 2.0，TrendRadar 用 feedparser 解析，RSS/Atom 都吃
    · ★进详情页补「文号 / 生效日期」——列表页没有这两项，AI 建法规表时只能填「—」；
      详情页里它们通常明写着，抓下来写进 <description>，AI 才有据可填（见下方说明）
    · ★船舶低碳相关性过滤——船级社「规范/指南」栏是全专业的，不滤会把有效信息淹掉

════════════════════════════════════════════════════════════════════════
"""

import argparse
import html as html_mod
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

# ────────────────────────────────────────────────────────────────────────
# 站点清单
# ────────────────────────────────────────────────────────────────────────
# 字段说明：
#   id        —— 源的短标识（日志用）
#   name      —— 显示名（进日志）
#   issuer    —— 发布机构（会拼进条目标题，AI 建表时需要知道是谁发的）
#   url       —— 公告列表页地址
#   exclude   —— 可选，标题命中这个正则就丢掉（剔除招录、比选、考试等噪音）
#
# ⚠️ 站点改版会导致某个源失效。失效时该源只是少几条，不影响其它源。
#    排查方法：加 --show 看哪个源返回 0 条，再对照下面的 URL 是否还通。
SOURCES = [
    # ── 中国船级社（规范、指南是船厂设计选型最直接的合规依据）──
    {
        "id": "ccs-spec",
        "name": "中国船级社 · 规范/指南",
        "issuer": "中国船级社",
        "url": "https://www.ccs.org.cn/ccswz/special?columnid=201900002000000011&id=0",
    },
    {
        "id": "ccs-rules",
        "name": "中国船级社 · 规范",
        "issuer": "中国船级社",
        "url": "https://www.ccs.org.cn/ccswz/special?columnid=201900002000000016&id=0",
    },
    {
        "id": "ccs-guides",
        "name": "中国船级社 · 指南",
        "issuer": "中国船级社",
        "url": "https://www.ccs.org.cn/ccswz/special?columnid=201900002000000293&id=0",
    },
    {
        "id": "ccs-consult",
        "name": "中国船级社 · 规范指南征求意见",
        "issuer": "中国船级社",
        "url": "https://www.ccs.org.cn/ccswz/columnList?columnid=201900002000000413",
    },
    {
        "id": "ccs-cnregs",
        "name": "中国船级社 · 中国海事法规",
        "issuer": "中国海事局",
        "url": "https://www.ccs.org.cn/ccswz/columnList?columnid=202006161032321078",
    },
    {
        "id": "ccs-material",
        "name": "中国船级社 · 材料设备指南",
        "issuer": "中国船级社",
        "url": "https://www.ccs.org.cn/ccswz/specialguid?columnid=201900002000000172&id=0",
    },
    # ── 中国海事局（船舶技术法规的法定发布机构）──
    {
        "id": "msa-tech",
        "name": "中国海事局 · 船舶技术法规",
        "issuer": "中华人民共和国海事局",
        "url": "https://www.msa.gov.cn/f92f8b93a6c8440789f0ed717704ceac/index.jhtml",
    },
    {
        "id": "msa-notice",
        "name": "中国海事局 · 通知公告",
        "issuer": "交通运输部海事局",
        "url": "https://www.msa.gov.cn/0308a18057ab4e0e923620fbed32b5ef/index.jhtml",
        # 招录、比选、考试类公告与法规情报无关，直接丢掉
        "exclude": r"招聘|公务员|面试|拟录用|录用|考试|比选|中标|采购|询价|"
                   r"公示|培训业务|渔船|游艇|帆船|体育运动船艇|党建|精神文明",
    },
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

DATE_RE = re.compile(r"(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})")
TAG_RE = re.compile(r"<[^>]+>")
ANCHOR_RE = re.compile(r'<a\s[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I)
SKIP_HREF_RE = re.compile(
    r"^(javascript:|mailto:|#)|\.(css|js|png|jpe?g|gif|ico|svg|woff2?|ttf|pdf|zip)(\?|$)", re.I)

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


# ────────────────────────────────────────────────────────────────────────
# 船舶低碳相关性白名单（★ 这道闸是本次新增的核心）
# ────────────────────────────────────────────────────────────────────────
# ⚠️ 为什么必须要有这道闸：
#   船级社的「规范 / 指南」栏目是**全专业**的 —— 结构、材料、焊接、消防、
#   救生、海洋平台、油气田设施、集装箱…… 船舶低碳只是其中很小的一簇。
#   实测 77 条原始条目里，真正与绿色低碳相关的只有 18 条左右，其余是
#   《钢质海船入级规范》《材料与焊接规范》《集装箱检验规范》这类通用规范。
#   它们塞进「法规前沿」只会把真正有用的信息淹掉，所以一律拦下。
#
# 判据：标题命中下面任一关键词才放行（命中即保留，纯白名单、不做反向排除）。
#   「宁可漏、不可滥」—— 漏掉的通用规范本来也不是要看的。
#
# ⚠️ 改这个词表时注意两个坑：
#   1. 不要用裸「CCS」当关键词 —— 它既是「中国船级社」的缩写，也是
#      「碳捕集封存」的缩写，会把 CCS 发布的**所有**文件全放进来。
#      要表达碳捕集，用「碳捕集 / CCUS」即可。
#   2. 不要用裸「液化气体」—— 会命中《散装运输液化气体船舶构造与设备规范》
#      这类**运输船**规范（那是货物运输，不是低碳）。要表达 LNG/LPG 燃料，
#      用「液化天然气 / 液化石油气燃料」这种带燃料语境的写法。
LOWCARBON_RE = re.compile(
    # ── 替代燃料 ──
    r"氨燃料|氨动力|氨发动机|甲醇|甲烷逃逸|"
    r"氢燃料|氢动力|液氢|储氢|供氢|氢加注|氢能|"
    r"液化天然气|LNG|液化石油气燃料|LPG燃料|"
    r"生物燃料|生物柴油|生物甲醇|乙醇|乙烷|"
    r"替代燃料|新能源|清洁能源|绿色燃料|燃料全生命周期|可持续燃料|"
    # ── 电动化与储能 ──
    r"电池动力|纯电|储能|燃料电池|岸电|直流综合电力|混合动力|超级电容|电动船舶|"
    # ── 能效与排放 ──
    r"能效|排放|温室气体|碳排放|碳强度|碳足迹|脱碳|减碳|零排放|净零|碳中和|"
    r"EEDI|EEXI|CII|NOx|SOx|硫含量|氮氧化物|硫氧化物|颗粒物|"
    r"废气清洗|脱硫|脱硝|选择性催化|"
    # ── 绿色与可再生 ──
    r"绿色|低碳|环保|可再生|风能|风帆|风力辅助|太阳能|光伏|空气润滑|余热回收|"
    r"碳捕集|CCUS|能效设计指数",
    re.I)


# ────────────────────────────────────────────────────────────────────────
# ★详情页补字段：文号 / 生效日期 / 文件性质
# ────────────────────────────────────────────────────────────────────────
# 为什么必须补这一层：
#   列表页只有「标题 + 日期 + 链接」。而 AI 在「二、法规前沿」建表时要填
#   「文件号 / 强制 / 生效日期」三列 —— 这三列在列表页里**一个字都没有**，
#   提示词又明令「不得编造」，结果就是整列全是「—」（用户实际反馈的问题）。
#
#   实测（2026-10-15，15 条逐条进详情页核对）这两个字段是**真实存在**的：
#     · CCS 指南/规范详情页 → 「发布时间：… | 生效日期：2026-10-01 00:00:00」
#     · 海事局详情页        → 「文号：海船规函〔2025〕2287号」
#                             「自2026年3月1日起施行」
#   取出来写进 RSS 的 <description>，AI 才有据可填。
#
# ⚠️ 抽取原则：**只认页面上明写的字段**。抽不到就返回空，在 feed 里写成
#    「未载明」——「查过了，没有」本身就是有用信息，AI 就不会去编。
#    绝不推断日期、绝不自行编编号。
#
# 关于「文件性质」与「强制性」：
#   · 文件性质（规范 / 指南 / 规则 / 征求意见稿）是**官方文件名里本来就有的字**，
#     属于事实；
#   · 强制性是由文件性质按固定规则映射出来的**推定值**，写进 feed 时带括号注明依据，
#     AI 那边也只当推荐值用，不当成文件自己的声明。
_PLAIN_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_WS_RUN_RE = re.compile(r"\s+")

# 文号：「文号：海船规函〔2025〕2287号」「文号：2026年第1号公告」
_DOC_NO_RE = re.compile(r"文号\s*[:：]\s*([^\s｜|，,。；;]{1,40})")
_DOC_NO_EMPTY = {"", "无", "无。", "无文号", "暂无", "—", "-", "－", "／", "/"}

# 生效日期：CCS 写带标签的「生效日期：2026-10-01」，
#          海事局写在正文里「自2026年3月1日起施行」
# 带标签的优先（那是页面结构字段），抓不到再退到正文句式。
_EFF_LABEL_RE = re.compile(
    r"(?:生效|施行|实施)日期\s*[:：]\s*"
    r"(20\d{2})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})")
_EFF_VERB_RE = re.compile(
    r"自\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*起\s*"
    r"(?:施行|生效|实施|执行)")


def html_to_text(page_html):
    """把详情页 HTML 压成一行纯文本（去脚本样式 → 去标签 → 还原实体 → 清空白）。"""
    t = _PLAIN_SCRIPT_RE.sub(" ", page_html)
    t = _TAG_STRIP_RE.sub(" ", t)
    t = html_mod.unescape(t).replace("\u00a0", " ")
    return _WS_RUN_RE.sub(" ", t)


def extract_detail_meta(page_html):
    """从法规详情页抽 {doc_no, effective}。抽不到的键不出现，绝不猜。"""
    txt = html_to_text(page_html)
    meta = {}
    m = _DOC_NO_RE.search(txt)
    if m:
        v = m.group(1).strip().strip("：:。")
        if v not in _DOC_NO_EMPTY:
            meta["doc_no"] = v
    m = _EFF_LABEL_RE.search(txt) or _EFF_VERB_RE.search(txt)
    if m:
        try:
            meta["effective"] = "%04d-%02d-%02d" % (int(m.group(1)),
                                                    int(m.group(2)),
                                                    int(m.group(3)))
        except ValueError:
            pass
    return meta


# 文件性质 → (性质名, 强制性说明)，按顺序取首个命中。
# ⚠️ 顺序不能乱：「指南」必须排在「规范/规则」前面 ——
#    《新能源清洁能源动力船舶适用内河船舶技术规范条款实施指南》同时含
#    「规范」和「指南」，它本质是指导性文件，按「规范」判会错成强制。
_NATURE_RULES = (
    (re.compile(r"征求意见|初稿|草案"), "征求意见稿", "未定（草案，尚未生效）"),
    (re.compile(r"实施指南|指南|指导性"), "指南", "否（指南为推荐性技术文件）"),
    (re.compile(r"暂行规则|检验技术规则|规范|规则"),
     "规范/规则", "是（规范或法定规则，强制执行）"),
)


def classify(title):
    """按官方文件名判定 (文件性质, 强制性说明)。都不中则归「其他 / 未载明」。"""
    for pat, nature, note in _NATURE_RULES:
        if pat.search(title):
            return nature, note
    return "其他", "未载明"


# ────────────────────────────────────────────────────────────────────────
# 抓取
# ────────────────────────────────────────────────────────────────────────
def fetch(url, timeout=25, retries=2):
    """抓一个页面，返回 (html文本, 最终URL)。全部重试失败抛异常。"""
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                raw = r.read(4_000_000)
                final = r.geturl()
            for enc in ("utf-8", "gb18030", "gbk"):
                try:
                    return raw.decode(enc).lstrip("\ufeff"), final
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", "replace").lstrip("\ufeff"), final
        except Exception as e:                       # noqa: BLE001 - 任何异常都要能降级
            last = e
            if i < retries:
                time.sleep(1.5 * (i + 1))
    raise last


# ────────────────────────────────────────────────────────────────────────
# 解析
# ────────────────────────────────────────────────────────────────────────
# 语言切换 / 导航类锚点，不是正文条目
NAV_RE = re.compile(
    r"^(English|EN|日本語|한국어|中文|简体|繁體|网站地图|联系我们|无障碍|"
    r"登录|注册|RSS|首页|返回顶部|更多|more|More|MENU|菜单|搜索|"
    r"版权声明|隐私政策|使用条款)$", re.I)

# 正文条目链接的特征：详情页路径里一定有 article / detail / id= 之一。
# 用它把「栏目导航链接」挡在门外（例如海事局右上角的 English 会跳到 en.msa.gov.cn）。
DETAIL_RE = re.compile(r"(article|detail|id=)", re.I)


def extract(html, final_url):
    """从列表页 HTML 里提取 [(datetime, 标题, 链接)]。

    策略：遍历所有 <a>，锚点文本当标题，在其后 400 字符 / 前 300 字符
    范围内找最近的日期。这对「标题+日期」表格和「日期在标题内」两种版式都有效。
    另外要求链接是「详情页」且与列表页同域，否则视为导航链接丢弃。
    """
    from urllib.parse import urljoin, urlsplit
    base_host = urlsplit(final_url).netloc
    out = []
    for m in ANCHOR_RE.finditer(html):
        href, inner = m.group(1), m.group(2)
        href = html_mod.unescape(href)               # HTML 里的 &amp; 要还原成 &
        if SKIP_HREF_RE.search(href):
            continue
        full = urljoin(final_url, href)
        if urlsplit(full).netloc != base_host:      # 跨域 → 导航链接
            continue
        if not DETAIL_RE.search(full):              # 非详情页 → 导航链接
            continue
        title = clean_title(html_mod.unescape(TAG_RE.sub("", inner)))
        if len(title) < 6 or NAV_RE.match(title):
            continue
        tail = html[m.end(): m.end() + 400]
        head = html[max(0, m.start() - 300): m.start()]
        d = DATE_RE.search(tail) or DATE_RE.search(head)
        if not d:
            continue
        try:
            dt = datetime(int(d.group(1)), int(d.group(2)), int(d.group(3)),
                          9, 0, tzinfo=timezone(timedelta(hours=8)))
        except ValueError:
            continue
        out.append((dt, title, full))
    return out


def clean_title(t):
    """清掉锚点文本里夹带的日期和多余标点。

    海事局的锚点文本常写成「……的通知 2026-10-14」，日期被包在 <a> 里，
    不剥掉的话会跟着进标题，污染 AI 建表。
    """
    t = DATE_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t.strip("》").strip()


def dedupe_key(url):
    """CCS 的链接形如 .../specialDetail?id=202609031076494076，用 id 做去重键。"""
    m = re.search(r"[?&]id=(\d{6,})", url)
    return "id:" + m.group(1) if m else "url:" + url.split("#")[0]


def norm_title(t):
    return re.sub(r"[\s《》（）()【】\[\]、，,。.：:；;“”\"'\-—－·|｜]+", "", t).lower()


# 跨源去重用的「核心名」：把同一份文件的两种写法收敛到同一个键。
#   中国船级社《甲醇燃料内河加注趸船技术与检验指南》
#   交通运输部海事局《……关于发布《甲醇燃料内河加注趸船技术与检验指南》的通告》
#   → 两者核心名相同，只保留较早遇到的那条。
_CORE_SHELL_RE = re.compile(
    r"(中华人民共和国|中国|交通运输部|海事局|船级社|关于|发布|公开|征求|意见|"
    r"的|通知|通告|公告|函|初稿|征求意见稿|请?求|等文件|版本)")
_CORE_PUNCT_RE = re.compile(r"[\s《》（）()【】\[\]、，,。.：:；;“”\"'\-—－_·|｜/]+")


def core_title(t, issuer=""):
    s = _CORE_PUNCT_RE.sub("", t)
    if issuer:
        s = s.replace(_CORE_PUNCT_RE.sub("", issuer), "")
    s = _CORE_SHELL_RE.sub("", s)
    s = re.sub(r"20\d{2}", "", s)
    return s.lower()


# ────────────────────────────────────────────────────────────────────────
# 主流程
# ────────────────────────────────────────────────────────────────────────
def collect(days, verbose=True, relevance_filter=True, dropped_out=None,
            detail_fetch=True, detail_delay=1.0, detail_stats_out=None):
    cutoff = datetime.now(timezone(timedelta(hours=8))) - timedelta(days=days)
    seen_key, seen_core = set(), set()
    items, stats = [], []

    for src in SOURCES:
        t0 = time.time()
        try:
            html, final = fetch(src["url"])
        except Exception as e:                       # noqa: BLE001
            stats.append((src["name"], -1, 0, "抓取失败: %s: %s" % (type(e).__name__, str(e)[:60])))
            if verbose:
                print("  ✗ %-26s 抓取失败：%s: %s" % (src["name"], type(e).__name__, str(e)[:60]))
            continue

        rows = extract(html, final)
        ex = re.compile(src["exclude"]) if src.get("exclude") else None
        issuer = src["issuer"]
        kept_in_window = 0
        dropped_offtopic = 0
        for dt, title, url in rows:
            if dt < cutoff:
                continue
            kept_in_window += 1
            if ex and ex.search(title):
                continue
            # ★ 船舶低碳相关性闸门：与低碳无关的通用规范直接丢掉
            if relevance_filter and LOWCARBON_RE.search(title) is None:
                dropped_offtopic += 1
                if dropped_out is not None:
                    dropped_out.append((dt, title))
                continue
            k = dedupe_key(url)
            ct = core_title(title, issuer)
            if k in seen_key or (len(ct) >= 12 and ct in seen_core):
                continue
            seen_key.add(k)
            if len(ct) >= 12:
                seen_core.add(ct)
            # 标题里带上发布机构，AI 建法规表时才知道是谁发的。
            # 用「机构｜文件名」而不是「机构《文件名》」——后者遇到标题本身
            # 已带书名号（如「关于《船舶应用氨燃料指南》2026 征求意见」）会套两层。
            already = any(w in title for w in (issuer, "海事局", "船级社", "交通运输部"))
            disp = title if already else "%s｜%s" % (issuer, title)
            # 文件性质与强制性由官方文件名推定（见 classify 的说明）
            nature, mandatory = classify(title)
            items.append({
                "title": disp,
                "url": url,
                "date": dt,
                "source": src["name"],
                "nature": nature,          # 规范/规则 · 指南 · 征求意见稿 · 其他
                "mandatory": mandatory,    # 推定值，带依据说明
                "doc_no": "",              # ↓ 第二遍进详情页才填
                "effective": "",           # ↓
            })
        stats.append((src["name"], kept_in_window, dropped_offtopic,
                      "%.1fs" % (time.time() - t0)))
        if verbose:
            print("  ✓ %-26s 窗口内 %3d 条 → 低碳相关 %2d 条（滤掉 %2d 条无关）%.1fs"
                  % (src["name"], kept_in_window, kept_in_window - dropped_offtopic,
                     dropped_offtopic, time.time() - t0))

    # ★第二遍：逐条进详情页补「文号 / 生效日期」。
    #   放在去重之后 —— 只对最终保留的条目抓，重复条目不会白抓一遍。
    #   任何一条失败都只是少几个字段，绝不影响主流程（法规条目照常进 feed）。
    if detail_fetch and items:
        hit = 0
        for it in items:
            try:
                page, _ = fetch(it["url"], timeout=25, retries=1)
                meta = extract_detail_meta(page)
                it["doc_no"] = meta.get("doc_no", "")
                it["effective"] = meta.get("effective", "")
                if it["doc_no"] or it["effective"]:
                    hit += 1
            except Exception:                        # noqa: BLE001
                pass
            time.sleep(detail_delay)
        if detail_stats_out is not None:
            detail_stats_out.append((hit, len(items)))
        if verbose:
            print("  ⓘ 详情页补字段：%d/%d 条取到「文号」或「生效日期」"
                  % (hit, len(items)))

    items.sort(key=lambda x: x["date"], reverse=True)
    return items, stats


def build_rss(items, days):
    now = datetime.now(timezone(timedelta(hours=8)))
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<rss version="2.0">',
             '  <channel>',
             '    <title>船舶低碳 · 法规原文直采（IMO / 船级社 / 海事局）</title>',
             '    <link>https://www.ccs.org.cn/</link>',
             '    <description>由中国船级社、中国海事局官网公告列表直采的规则·指南·规范·标准原文条目'
             '（窗口 %d 天，共 %d 条）。每条目附「文件性质 / 文号 / 生效日期 / 强制性」四项，'
             '取自详情页或按文件名推定，供 AI 填「法规清单表」使用。'
             '本源由 scripts/fetch_regulations.py 生成。</description>'
             % (days, len(items)),
             '    <language>zh-CN</language>',
             '    <lastBuildDate>%s</lastBuildDate>' % format_datetime(now)]
    for it in items:
        # ★<description> 是 AI 唯一能看到「标题之外」的地方（配套补丁 [G] 把它带进提示词）。
        #   四个字段的口径：
        #     · 文件性质 —— 官方文件名里的字（规范/指南/规则/征求意见稿），事实
        #     · 文号     —— 详情页「文号：」原值；没有就写「未载明」
        #     · 生效日期 —— 详情页「生效日期：」或正文「自…起施行」；没有写「未载明」
        #     · 强制性   —— 由文件性质推定的推荐值，括号里注明了依据
        #   写「未载明」而不是留空，是为了让 AI 明确知道「查过了、没有」，
        #   从而安心填「—」，而不是去脑补。
        desc = " ｜ ".join([
            "发布/更新日期：%s" % it["date"].strftime("%Y-%m-%d"),
            "发布机构：%s" % it["source"],
            "文件性质：%s" % it.get("nature", "其他"),
            "文号：%s" % (it.get("doc_no") or "未载明"),
            "生效日期：%s" % (it.get("effective") or "未载明"),
            "强制性：%s" % it.get("mandatory", "未载明"),
            "原文链接：%s" % it["url"],
        ])
        lines += [
            '    <item>',
            '      <title>%s</title>' % escape(it["title"]),
            '      <link>%s</link>' % escape(it["url"]),
            '      <guid isPermaLink="false">%s</guid>' % escape(it["url"]),
            '      <pubDate>%s</pubDate>' % format_datetime(it["date"]),
            '      <description>%s</description>' % escape(desc),
            '    </item>',
        ]
    lines += ['  </channel>', '</rss>', '']
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="法规原文直采 → RSS")
    ap.add_argument("--days", type=int, default=365,
                    help="只保留最近 N 天的条目（默认 365）。法规是低频发布，"
                         "而且一条 3 月生效的规则全年都相关，窗口别设太窄；"
                         "第一次跑会把全年清单一次带入，之后每期只报新增。")
    ap.add_argument("--out", default="regfeed/reg_feed.xml",
                    help="输出的 RSS 文件路径（默认 regfeed/reg_feed.xml）")
    ap.add_argument("--show", action="store_true", help="把抓到的条目打印出来")
    ap.add_argument("--min", type=int, default=1,
                    help="少于这个条数就打印告警（默认 1）")
    ap.add_argument("--no-filter", action="store_true",
                    help="关闭「船舶低碳相关性」过滤，输出原始全量条目。"
                         "只用于排查（看站点到底发了什么），送进报告的永远是过滤后的结果。")
    ap.add_argument("--dump-dropped", action="store_true",
                    help="顺便打印被相关性过滤丢掉的那些条目，便于核对该不该滤")
    ap.add_argument("--no-detail", action="store_true",
                    help="跳过「进详情页补文号/生效日期」这一步（快很多，但 feed 里"
                         "这两项会全是「未载明」）。只在调试抓取本身时用。")
    args = ap.parse_args()

    print("=" * 74)
    print("法规原文直采 —— 中国船级社 / 中国海事局官网公告")
    print("窗口：最近 %d 天 ｜ 船舶低碳相关性过滤：%s ｜ 详情页补字段：%s"
          % (args.days,
             "关（--no-filter）" if args.no_filter else "开",
             "关（--no-detail）" if args.no_detail else "开"))
    print("=" * 74)

    dropped_log = [] if args.dump_dropped else None
    detail_log = []
    items, stats = collect(args.days, relevance_filter=not args.no_filter,
                           dropped_out=dropped_log, detail_fetch=not args.no_detail,
                           detail_stats_out=detail_log)

    out_path = args.out
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(build_rss(items, args.days))

    print("-" * 74)
    ok = [s for s in stats if s[1] >= 0]
    raw_total = sum(s[1] for s in ok)
    dropped_total = sum(s[2] for s in ok)
    print("源汇总：成功 %d / %d" % (len(ok), len(stats)))
    print("过滤前窗口内 %d 条 → 滤掉 %d 条与低碳无关 → 输出 %d 条"
          % (raw_total, dropped_total, len(items)))
    if detail_log:
        hit, total = detail_log[0]
        print("详情页补字段：%d/%d 条取到「文号」或「生效日期」"
              "（其余在 feed 里标「未载明」，AI 会填「—」）" % (hit, total))
    for name, n, dropped, note in stats:
        print("   %s %-26s %s" % ("✓" if n >= 0 else "✗", name,
                                  note if n < 0 else "窗口 %d 条，保留 %d，滤掉 %d（%s）"
                                  % (n, n - dropped, dropped, note)))

    if args.dump_dropped and dropped_log:
        print("-" * 74)
        print("被「船舶低碳相关性」过滤丢掉的条目（%d 条，按日期倒序）：" % len(dropped_log))
        for dt, title in sorted(dropped_log, reverse=True):
            print("   [丢] %s  %s" % (dt.strftime("%Y-%m-%d"), title))

    if args.show:
        print("-" * 74)
        for it in items:
            print("   %s  %s" % (it["date"].strftime("%Y-%m-%d"), it["title"]))
            print("               %s" % it["url"])
            print("               性质=%s ｜ 文号=%s ｜ 生效日期=%s ｜ 强制性=%s"
                  % (it.get("nature", "其他"),
                     it.get("doc_no") or "未载明",
                     it.get("effective") or "未载明",
                     it.get("mandatory", "未载明")))

    print("-" * 74)
    print("已写出：%s（%d 条）" % (out_path, len(items)))
    if len(ok) == 0:
        print("⚠️  所有源都抓取失败 —— 如果这是在 GitHub Actions 里出现，"
              "说明这些国内站点对境外 IP 不通，报告将退回纯 RSS 模式。")
    elif len(items) < args.min:
        print("⚠️  捕获条数偏少，可能窗口太窄或站点改版。")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())

