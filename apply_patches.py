#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TrendRadar 船舶低碳推送 —— 源码补丁脚本（幂等，可重复执行）

═══════════════════════════════════════════════════════════════════
  ★★★ 平时不需要手动运行它 ★★★
═══════════════════════════════════════════════════════════════════
本脚本已经被写进 .github/workflows/crawler.yml，GitHub 每次跑爬虫
之前会自动先执行它、把源码改好，再启动主程序。你要做的只是保证
下面两个文件都在仓库里：

    patches/apply_patches.py            ← 本文件
    .github/workflows/crawler.yml       ← 里面含 "Apply low-carbon patches" 那一步

▸ 怎么确认它跑过了：
    Actions 日志里找到 "Apply low-carbon patches" 这一步 ——
      绿勾 ✅ = 补丁已生效，可以看到 ✓ 列表和语法检查结果
      橙勾 ⚠️ = 脚本没传上去、或路径不对（不影响爬虫继续跑）

▸ 什么时候才需要手动运行：
    ① 在本地调试时；
    ② 升级程序（重新下载 master）覆盖了源码改动之后。
    手动用法 —— 先 cd 到 TrendRadar 项目根目录（能看到 trendradar/ 和 config/ 的那层），
    再执行下面任意一条：

        python patches/apply_patches.py .       # 脚本在 patches/ 子目录里
        python apply_patches.py                 # 脚本就在根目录时
        python apply_patches.py D:/TrendRadar-master    # 直接指定项目路径

    ⚠️ 报 "python 不是内部或外部命令" 就改用 python3；
    ⚠️ 报 "目录不像 TrendRadar 项目" 说明你不在项目根目录，先 cd 过去。

▸ 它是幂等的：重复运行不会重复修改，第二次执行会显示「已打过，跳过」。
═══════════════════════════════════════════════════════════════════

包含以下补丁（顺序执行，全部幂等）：

  [D] AI 分析板块标题改为「船舶低碳情报双周报」场景措辞
      板块标题（核心热点态势 / 舆论风向争议 / 异动与弱信号 / RSS 深度洞察 /
      研判策略建议）是**硬编码在 trendradar/ai/formatter.py 里的**，
      config.yaml 没有任何字段可以覆盖。不改代码，报告里就一直是
      「舆论风向争议」这种与法规情报无关的标题。
      本补丁把 5 个渲染器（企业微信/飞书共用 markdown、钉钉、纯文本、
      Telegram、HTML 报告）里的标题一并替换为中文序号板块：
          核心热点态势   → 一、本期要览
          舆论风向争议   → 二、法规前沿
          异动与弱信号   → 三、产业动态
          RSS 深度洞察   → 四、能源分类
          研判策略建议   → 五、研发启示
          头部标题       → ✨ 船舶低碳情报双周报
      本补丁兼容三种历史状态：原版标题、v2 双周报版标题
      （本期法规要览 / 法规解读与分歧 / 前瞻信号与时间表 / 关键参数与硬数据 /
      研发启示与合规建议）、以及更早的 v1 技术日报版
      （今日技术主线 / 技术路线与分歧 / 弱信号与风向标 / 研发启示），
      都能一步迁移到情报汇编版，可反复重跑。
      需配合 config/ai_analysis_prompt.txt（v3.0.0 情报汇编版）一起使用。

  [F] AI 正文的极简 Markdown 真正渲染成 HTML（★ 排版效果的关键）
      原版 HTML 报告是这样渲染 AI 正文的：
          content_html = _escape_html(content).replace("\\n", "<br>")
      也就是**整段 HTML 转义后直接换行**，于是报告页面里出现了：
          · 字面星号 —— 提示词要求写的 `**要点标签**：` 原样显示成 **要点标签**：
          · 光秃秃的 > —— 结论行的引用标记原样显示成 &gt;
          · 表格根本画不出来 —— 竖线全变成纯文本
      本补丁新增 render_md_block_html()，把 AI 输出的极简 Markdown
      真正渲染成 HTML：
          > 一句话结论        → 强调引用条
          1. **标题**：正文    → 带序号徽标的条目
          · **标签**：正文     → 带圆点的条目
          | a | b |           → 真正的 <table>（含表头与隔行底色）
      并同时给推送渠道（企业微信/飞书/钉钉/Telegram）加了表格降级：
      markdown 频道渲染不了表格，会自动把表行改成
          · 1 ｜ IGC规则修正案 ｜ MSC.523(106)
      这样企业微信里也不会出现一堆竖线。
      配套在 trendradar/report/html.py 注入 .ai-md-* 样式（含深色模式）。

  [A] AI 客户端支持 ai.extra_params  （解决「AI 返回空响应」的省钱方案）
      原版 config.yaml 里读了 extra_params 但**从未使用**（只在 loader.py 出现一次，
      client.py 的 __init__ 和 chat() 都没读），所以想关闭思考模型没法配。
      补丁后可以在 config.yaml 写：
          ai:
            extra_params:
              extra_body:
                thinking: {type: disabled}
      或降思考强度：
          ai:
            extra_params:
              reasoning_effort: low

  [B] 空响应诊断
      模型返回空正文时，直接打印 finish_reason 与 reasoning_tokens，
      并给出下一步建议，不用再去猜。

  [C] RSS 抓取改用浏览器 User-Agent（解决 WorldCargo News / Container News /
      龙de船人 的 403 Forbidden）

  [E] SMTP 登录名可与发件邮箱不同（接入 Brevo 等「发信中继」服务的必要改动）
      原版 trendradar/notification/senders.py 写死了
          server.login(from_email, password)
      ——登录名被强制等于发件邮箱地址。但凡「登录名不是邮箱」的发信中继服务
      都接不上，例如：
          Brevo   登录名形如 7abcde@smtp-brevo.com（不是邮箱）
          Resend  登录名固定为字面量 resend
          SendGrid 登录名固定为字面量 apikey
      补丁后，登录名改从环境变量 / Secret  EMAIL_SMTP_USER  读取；
      **不设置该变量时行为与原来完全一致**（回退到发件邮箱），因此本补丁
      对现有 163/QQ/Gmail 配置零影响，可放心常驻。
      注意：EMAIL_FROM 仍用作邮件的 From 头，必须保持是服务商已验证的发件地址。

  [G] 把 RSS 摘要带进 AI 提示词  （解决「法规表的文件号/强制/生效日期三列全是 —」）
      法规直采源的 <description> 里带着「文件性质 / 文号 / 生效日期 / 强制性」
      四个字段（由 scripts/fetch_regulations.py 从法规详情页抓取），但原版程序
      **用户压根看不到**——摘要在两步里被丢掉：
        ① trendradar/core/analyzer.py 的 count_rss_frequency()：按关键词分组时
           **重新构造了一个 title_data 字典**，只搬 title/source/time/url 等，
           summary 不在其中 → 原字典里的 summary 到这里就没了；
        ② trendradar/ai/analyzer.py 的 _prepare_news_content()：构造 RSS 行时
           只拼「[来源] 标题 | 时间」，即使摘要还在也不会写进去。
      本补丁在①②各插一段，把摘要补回来（① 保留字段、② 追加到行尾）。

      ⚠️ ② 处**只对法规直采源追加**（靠摘要里的「文件性质：」标记识别）：
         若给全部 RSS 条目都加摘要，450 条候选会多出几万字符，白白吃掉提示词
         预算（还可能把真正需要分析的条目挤出 max_news_for_analysis）。

  [H] 报告顶部信息卡适配「纯 RSS 运行」
      热榜命中 0/0、热榜平台 --、新增热点 0 三格与「AI 分析 0 + 111」
      在纯 RSS 运行下恒为无意义值；改为条件渲染（platform_total > 0 才显示），
      日后重新开启热榜源时格子自动恢复。

  [I] 报告搜索框加「看得见的反馈」
      原版 handleSearch() 只把不匹配的条目 display:none，别的什么都不做；
      而 AI 双周报不参与搜索又占着页面最上方，真正会被搜索的 RSS 条目在
      页面最底部 —— 用户在搜索框里打字，眼前毫无变化，观感是「搜索没反应」
      （实测确认过滤其实生效了，只是看不见）。
      补丁后：输入框下方实时显示「命中 N 条 · 仅下方 RSS 条目」+「跳到第一条 ↓」；
      命中条目黄底高亮；滤空的分组整组隐藏、分组计数同步改成「命中 N 条」；
      清空关键词后全部还原。

  [J] 搜索加「中英同义词别名表」（叠加在 [I] 之上）
      用户搜「氨动力散货船」命中 0 条。实测：该词全页出现 10 处，**全部在
      AI 双周报里**（是 AI 把英文新闻译成中文后的概括用词），而 RSS 原标题是
      英文 —— ammonia-powered bulker / dry bulk carrier / bulk carrier。
      搜索是纯子串匹配、不做翻译，中文词必然 0 命中；刚好搜的就是英文标题时，
      用户却只记得中文说法（他是在上面 AI 双周报里读到这个词的）。
      补丁后：内置一张「同义簇」表（中文词与英文词同组，如
          氨燃料 / 氨动力 / 氨 / ammonia / nh3 / ammonia-powered
          散货船 / bulker / bulk carrier / dry bulk
      ），查询词命中任一成员，就把整组词一起拿去检索，命中后再把「实际用上的
      同义词」写进提示条（如「命中 5 条 · 同义词 ammonia / bulker 一并检索」）。
      反向同样成立：搜 ammonia 也能搜到中文标题的「氨燃料…」条目。
      ⚠️ 仍不搜 AI 双周报正文（成稿不拆散）；要加词直接改脚本里的
      SEARCH_SYNONYMS 数组即可，中英文词条都能加。

  [K] AI 正文 ↔ RSS 条目「交叉引用」（论文式：正文标引用，点一下跳到原文）
      用户想要「像论文文献和正文交叉引用那样的效果，在看 AI 分析时能定位到
      对应的 RSS」。原版两头都没有「句柄」：提示词里每条只有
      「- [来源] 标题 | 时间」，AI 无从指认某一条；报告里
      <div class="rss-item"> 也没有 id，正文无处可跳。补四块：
        ① ai/analyzer.py  每条 RSS 行加行首编号「- [#12] [来源] 标题 | 时间」，
           编号即「本条在 rss_items 里的顺序位」，与报告页天然一致；
        ② ai/formatter.py 把 AI 正文里的引用标记（#12）/（#12、14）/（#12-14）
           渲染成可点击徽标 —— 先转义再拼 HTML，不会引入注入风险；
        ③ report/html.py  每个 RSS 条目加 id="rss-12" + 可见的 #12 徽标；
           只给「主区」编号，「新增区」传 id_prefix="" 避免重复编号；
        ④ report/html.py  注入一段 JS（在原 </script> 之前）：
             · 点徽标 → 平滑滚到对应条目并闪烁 2.4s；
             · 编号越界（AI 误引）→ 标灰划掉 + 标题说明 + 控制台告警；
             · 被引用的条目显示「↩ 被引用 N 处」，点它跳回正文第一处；
             · 自动兜底：AI 漏标的段落，用「英文专名 + 中英同义词簇」做一次
               **保守**匹配（要求至少有 1 个只出现在 ≤2 个条目里的专名，
               或同义词簇强命中），命中的徽标是虚线样式、悬停写明「仅供参考」。
      视觉上：已标注=实线蓝底；自动兜底=虚线黄底；越界=灰底划掉。
      ⚠️ 需配合 config/ai_analysis_prompt.txt（v3.3.0 起）的「引用规范」，
         否则 AI 不会标引用，只剩自动兜底那一半能力；
      ⚠️ AI 输出是运行时生成的，历史报告不会追溯补引用，要重跑一次才看得到；
      ⚠️ 纯文本推送渠道（企业微信 / 飞书 / 钉钉 / Telegram）里 (#12) 只能原样
         显示，读者可照编号去网页版找 —— HTML / 邮件渠道才是完整体验。

注意：程序自带版本检查只对 config/ 下的配置文件做「只读」比对，不覆盖源码；
但**升级程序（重新下载 master）会覆盖以上改动**，届时重跑本脚本即可。
"""

import io
import os
import re
import sys

UA_OLD_1 = '"User-Agent": "TrendRadar/2.0 RSS Reader (https://github.com/trendradar)"'
UA_OLD_2 = '"User-Agent": "TrendRadar/2.0 RSS Reader"'
UA_NEW = ('"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
          'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"')

MARK_A = "★补丁A"
MARK_B = "★补丁B"
MARK_D = "★补丁D"
MARK_E = "★补丁E"
MARK_F = "★补丁F"
MARK_G = "★补丁G"
MARK_H = "★补丁H"
MARK_I = "★补丁I"
MARK_J = "★补丁J"
MARK_K = "★补丁K"

HEAD_TITLE = "✨ 船舶低碳情报双周报"

# [D] 板块标题映射：原词 -> 新词
#     这些字符串在 formatter.py 中只作为板块标题出现（各 5 处，分别对应
#     markdown / 钉钉 / 纯文本 / Telegram / HTML 五个渲染器），可安全全量替换。
#
#     ⚠️ 注意「研发启示」这一项被**故意排除**在映射表之外：
#        它是「研发启示与合规建议」的子串，按普通替换会变成
#        「五、研发启示与合规建议」。它由下方 _patch_bare_yanfa() 用带
#        前后视断言的正则单独处理。
TITLE_MAP = [
    # ① 双周报 v2 版标题（本期在线的状态）→ 情报汇编版
    ("✨ 船舶低碳法规双周报", HEAD_TITLE),
    ("本期法规要览", "一、本期要览"),
    ("法规解读与分歧", "二、法规前沿"),
    ("前瞻信号与时间表", "三、产业动态"),
    ("关键参数与硬数据", "四、能源分类"),
    ("研发启示与合规建议", "五、研发启示"),
    # ② 原版标题 → 情报汇编版（首次打补丁走这一组）
    ("✨ AI 热点分析", HEAD_TITLE),
    ("核心热点态势", "一、本期要览"),
    ("舆论风向争议", "二、法规前沿"),
    ("异动与弱信号", "三、产业动态"),
    ("RSS 深度洞察", "四、能源分类"),
    ("研判策略建议", "五、研发启示"),
    # ③ 更早的 v1 技术日报版标题 → 情报汇编版
    ("✨ AI 低碳技术情报", HEAD_TITLE),
    ("今日技术主线", "一、本期要览"),
    ("技术路线与分歧", "二、法规前沿"),
    ("弱信号与风向标", "三、产业动态"),
]

# ──────────────────────────────────────────────────────────────────────
# [F] 注入到 trendradar/ai/formatter.py 的渲染函数
#     字符串内一律只用双引号，避免与外层三引号冲突。
# ──────────────────────────────────────────────────────────────────────
MD_HELPERS = """def _md_tables_to_lines(text: str) -> str:
    # ★补丁F：把 Markdown 表格降级成一行一条，供推送渠道使用。
    #   企业微信 / 飞书 / 钉钉 / Telegram 都渲染不了表格，直接原样发出去
    #   会是一堆竖线。这里把
    #       | 序号 | 文件名称 | 文件号 |
    #       | --- | --- | --- |
    #       | 1 | IGC规则修正案 | MSC.523(106) |
    #   变成
    #       · 1 ｜ IGC规则修正案 ｜ MSC.523(106)
    #   HTML 报告不走这里（它走 render_md_block_html，会画真表格）。
    if not text or "|" not in text:
        return text
    out = []
    for raw in text.replace("\\r\\n", "\\n").replace("\\r", "\\n").split("\\n"):
        s = raw.strip()
        if re.fullmatch(r"\\|[\\s:\\-|]+\\|", s):
            continue                      # 表头分隔行，丢弃
        if s.startswith("|") and s.endswith("|") and s.count("|") >= 2:
            cells = [c.strip() for c in s.strip("|").split("|")]
            cells = [c for c in cells if c]
            if cells:
                out.append("· " + " ｜ ".join(cells))
            continue
        out.append(raw)
    return "\\n".join(out)


def _md_inline_html(text: str) -> str:
    # ★补丁F：行内 Markdown —— 先做 HTML 转义，再把 **加粗** 换成 <strong>
    out = _escape_html(text)
    out = re.sub(r"\\*\\*(.+?)\\*\\*", r"<strong>\\1</strong>", out)
    return out


def render_md_block_html(text: str) -> str:
    # ★补丁F：把 AI 正文的极简 Markdown 渲染成 HTML（HTML 报告 / 邮件用）
    #   支持： > 结论行 / 1. 编号条目 / · 圆点条目 / | 表格 | / 普通段落
    #   不认识的内容一律按纯文本段落输出，绝不吞掉内容。
    if not text:
        return ""
    lines = text.replace("\\r\\n", "\\n").replace("\\r", "\\n").split("\\n")
    parts = []
    i = 0
    n = len(lines)

    def _cells(s):
        return [c.strip() for c in s.strip().strip("|").split("|")]

    while i < n:
        s = lines[i].strip()

        if not s:
            i += 1
            continue

        # ---- 表格：本行是表头，且下一行是 | --- | --- | 分隔行 ----
        if (s.startswith("|") and s.endswith("|") and s.count("|") >= 2
                and i + 1 < n
                and re.fullmatch(r"\\|[\\s:\\-|]+\\|", lines[i + 1].strip())):
            header = _cells(s)
            i += 2
            body = []
            while i < n:
                t = lines[i].strip()
                if t.startswith("|") and t.endswith("|") and t.count("|") >= 2:
                    body.append(_cells(t))
                    i += 1
                else:
                    break
            th = "".join("<th>" + _md_inline_html(c) + "</th>" for c in header)
            trs = []
            for row in body:
                tds = "".join("<td>" + _md_inline_html(c) + "</td>" for c in row)
                trs.append("<tr>" + tds + "</tr>")
            parts.append(
                '<div class="ai-md-tablewrap"><table class="ai-md-table">'
                "<thead><tr>" + th + "</tr></thead>"
                "<tbody>" + "".join(trs) + "</tbody></table></div>"
            )
            continue

        # ---- 结论行 ----
        if s.startswith(">"):
            parts.append('<div class="ai-md-lead">'
                         + _md_inline_html(s.lstrip("> ").strip()) + "</div>")
            i += 1
            continue

        # ---- 阿拉伯数字编号条目 ----
        m = re.match(r"^(\\d{1,2})[.、)]\\s*(.+)$", s)
        if m:
            parts.append(
                '<div class="ai-md-item"><span class="ai-md-num">' + m.group(1)
                + '</span><div class="ai-md-text">'
                + _md_inline_html(m.group(2)) + "</div></div>"
            )
            i += 1
            continue

        # ---- · / • / - 圆点条目 ----
        if s[0] in "·•" or re.match(r"^[-*+]\\s+", s):
            if s[0] in "·•":
                body_text = s[1:].strip()
            else:
                body_text = re.sub(r"^[-*+]\\s+", "", s).strip()
            parts.append(
                '<div class="ai-md-item"><span class="ai-md-dot">●</span>'
                '<div class="ai-md-text">' + _md_inline_html(body_text) + "</div></div>"
            )
            i += 1
            continue

        # ---- 普通段落 ----
        parts.append('<p class="ai-md-p">' + _md_inline_html(s) + "</p>")
        i += 1

    return "".join(parts)


"""

# ──────────────────────────────────────────────────────────────────────
# [F] 注入到 trendradar/report/html.py 的样式（含深色模式）
# ──────────────────────────────────────────────────────────────────────
CSS_ANCHOR = "            .ai-error {"
CSS_BLOCK = """            /* ★船舶低碳情报双周报：AI 正文的 Markdown 渲染样式 */
            .ai-block-content.ai-md { white-space: normal; }
            .ai-md-lead {
                font-size: 14px;
                font-weight: 600;
                color: #075985;
                background: #f0f9ff;
                border-left: 3px solid #0ea5e9;
                padding: 10px 12px;
                border-radius: 0 6px 6px 0;
                margin: 0 0 12px 0;
                line-height: 1.65;
            }
            .ai-md-item {
                display: flex;
                align-items: flex-start;
                gap: 8px;
                margin-bottom: 8px;
                line-height: 1.65;
            }
            .ai-md-num {
                flex: 0 0 auto;
                min-width: 20px;
                margin-top: 2px;
                padding: 0 5px;
                border-radius: 4px;
                background: #0ea5e9;
                color: #ffffff;
                font-size: 12px;
                font-weight: 600;
                line-height: 18px;
                text-align: center;
                font-variant-numeric: tabular-nums;
            }
            .ai-md-dot { flex: 0 0 auto; color: #0ea5e9; font-size: 9px; line-height: 23px; }
            .ai-md-text { flex: 1 1 auto; min-width: 0; }
            .ai-md-text strong { color: #0c4a6e; font-weight: 600; }
            .ai-md-p { margin: 0 0 8px 0; }
            .ai-md-tablewrap { overflow-x: auto; margin: 4px 0 12px 0; -webkit-overflow-scrolling: touch; }
            table.ai-md-table { border-collapse: collapse; width: 100%; font-size: 13px; }
            table.ai-md-table th, table.ai-md-table td {
                border: 1px solid #bae6fd;
                padding: 6px 8px;
                text-align: left;
                vertical-align: top;
                line-height: 1.55;
            }
            table.ai-md-table th {
                background: #e0f2fe;
                color: #075985;
                font-weight: 600;
                white-space: nowrap;
            }
            table.ai-md-table tbody tr:nth-child(even) { background: #f8fbff; }

"""

CSS_DARK_ANCHOR = "            body.dark-mode .ai-block-content { color: #cbd5e1; }"
CSS_DARK_BLOCK = """
            /* ★船舶低碳情报双周报：Markdown 渲染样式（深色模式） */
            body.dark-mode .ai-md-lead {
                background: #0f2740;
                color: #bae6fd;
                border-left-color: #38bdf8;
            }
            body.dark-mode .ai-md-text strong { color: #bae6fd; }
            body.dark-mode table.ai-md-table th,
            body.dark-mode table.ai-md-table td { border-color: #1e3a5f; }
            body.dark-mode table.ai-md-table th { background: #0f2740; color: #bae6fd; }
            body.dark-mode table.ai-md-table tbody tr:nth-child(even) { background: #10202f; }"""


def read(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def replace_once(text, old, new, label, log):
    """替换；要求 old 出现且仅出现一次"""
    n = text.count(old)
    if n == 0:
        log.append("  ✗ %s：未找到锚点（可能程序版本不同，已跳过）" % label)
        return text, False
    if n > 1:
        log.append("  ✗ %s：锚点出现 %d 次，存在歧义，已跳过" % (label, n))
        return text, False
    log.append("  ✓ %s" % label)
    return text.replace(old, new), True


def patch_ai_client(root, log):
    path = os.path.join(root, "trendradar", "ai", "client.py")
    if not os.path.exists(path):
        log.append("  ✗ 找不到 trendradar/ai/client.py，跳过 [A][B]")
        return
    text = read(path)

    # ---------- [A] extra_params 生效 ----------
    if MARK_A in text:
        log.append("  = [A] extra_params 支持：已打过，跳过")
    else:
        anchor_a = '        self.fallback_models = config.get("FALLBACK_MODELS", [])\n'
        new_a = anchor_a + (
            "        # ★补丁A：让 ai.extra_params 真正生效（原版只读取、不使用）\n"
            "        #   典型用途：关闭 DeepSeek V4 系列默认开启的思考模式\n"
            "        #     ai:\n"
            "        #       extra_params:\n"
            "        #         extra_body:\n"
            "        #           thinking: {type: disabled}\n"
            "        self.extra_params = config.get(\"EXTRA_PARAMS\", {}) or {}\n"
        )
        text, _ = replace_once(text, anchor_a, new_a, "[A] client.__init__ 读取 extra_params", log)

        anchor_b = "        # 合并其他额外参数\n"
        new_b = (
            "        # ★补丁A：合并 ai.extra_params（原样透传给 LiteLLM，如 extra_body / reasoning_effort）\n"
            "        if self.extra_params:\n"
            "            for _k, _v in self.extra_params.items():\n"
            "                if _k not in params:\n"
            "                    params[_k] = _v\n\n"
        ) + anchor_b
        text, _ = replace_once(text, anchor_b, new_b, "[A] client.chat 透传 extra_params", log)

    # ---------- [B] 空响应诊断 ----------
    if MARK_B in text:
        log.append("  = [B] 空响应诊断：已打过，跳过")
    else:
        anchor_c = "        return content or \"\"\n"
        new_c = (
            "        # ★补丁B：空正文诊断——思考模型常把 max_tokens 全用在思维链上\n"
            "        if not content:\n"
            "            try:\n"
            "                _fr = response.choices[0].finish_reason\n"
            "                _rt = None\n"
            "                _usage = getattr(response, \"usage\", None)\n"
            "                if _usage is not None:\n"
            "                    _det = getattr(_usage, \"completion_tokens_details\", None)\n"
            "                    if _det is not None:\n"
            "                        _rt = getattr(_det, \"reasoning_tokens\", None)\n"
            "                print(\"[AI][空响应] finish_reason=%s, reasoning_tokens=%s\" % (_fr, _rt))\n"
            "                if _fr == \"length\":\n"
            "                    print(\"[AI][空响应] 思维链耗尽了 max_tokens。\"\n"
            "                          \"请调大 ai.max_tokens（建议 32768），\"\n"
            "                          \"或在 ai.extra_params 里关闭思考 thinking.type=disabled\")\n"
            "            except Exception:\n"
            "                pass\n"
            "        return content or \"\"\n"
        )
        text, _ = replace_once(text, anchor_c, new_c, "[B] client.chat 空响应诊断", log)

    write(path, text)


def patch_rss_ua(root, log):
    targets = [
        os.path.join(root, "trendradar", "crawler", "rss", "fetcher.py"),
        os.path.join(root, "trendradar", "crawler", "rss", "parser.py"),
    ]
    for path in targets:
        if not os.path.exists(path):
            log.append("  ✗ 找不到 %s，跳过" % os.path.relpath(path, root))
            continue
        text = read(path)
        name = os.path.basename(path)
        if UA_NEW in text:
            log.append("  = [C] %s：已打过，跳过" % name)
            continue
        hit = False
        for old in (UA_OLD_1, UA_OLD_2):
            if old in text:
                text = text.replace(old, UA_NEW)
                hit = True
        if hit:
            write(path, text)
            log.append("  ✓ [C] %s 已改为浏览器 UA" % name)
        else:
            log.append("  ✗ [C] %s：未找到原 UA，跳过" % name)


def patch_section_titles(root, log):
    """[D] 把 AI 分析板块标题改为船舶低碳情报双周报的中文序号板块"""
    path = os.path.join(root, "trendradar", "ai", "formatter.py")
    if not os.path.exists(path):
        log.append("  ✗ 找不到 trendradar/ai/formatter.py，跳过 [D]")
        return
    text = read(path)

    # 幂等判据：全部目标标题都已存在 → 说明已是情报汇编版，直接跳过。
    #   不用补丁标记判断，是为了兼容「已打过旧版补丁」的文件：
    #   那种状态下标记存在、但标题是旧版，必须继续迁移。
    targets = [new for _, new in TITLE_MAP] + [HEAD_TITLE]
    if all(t in text for t in targets):
        log.append("  = [D] 板块标题改名：已是情报汇编版，跳过")
        return

    changed = []
    for old, new in TITLE_MAP:
        if new in text:
            # 目标词已存在就跳过，避免二次替换
            continue
        n = text.count(old)
        if n == 0:
            continue          # 当前文件不含这个历史标题，属正常，不必报告
        text = text.replace(old, new)
        changed.append((old, new, n))

    # 「研发启示」单独处理：它是「研发启示与合规建议」的子串，
    #   用前后视断言保证只在「独立成标题」时替换，
    #   且不会把已经改好的「五、研发启示」再改一次。
    if "五、研发启示" not in text:
        n_bare = len(re.findall(r"(?<![、\w])研发启示(?![与])", text))
        if n_bare:
            text = re.sub(r"(?<![、\w])研发启示(?![与])", "五、研发启示", text)
            changed.append(("研发启示", "五、研发启示", n_bare))

    if changed:
        # 先清掉可能已存在的旧版补丁标记（含早期版本重复插入的历史遗留），
        # 再统一写一份新的，保证反复运行不会堆积重复注释。
        text = re.sub(r"(?m)^# ★补丁D：[^\n]*\n(?:^#   [^\n]*\n)*", "", text)

        anchor = "def _escape_html(text: str) -> str:"
        marker = (
            "# %s：AI 分析板块标题已改为「船舶低碳情报双周报」中文序号板块\n"
            "#   一、本期要览 / 二、法规前沿 / 三、产业动态 / 四、能源分类 / 五、研发启示\n"
            "#   配合 config/ai_analysis_prompt.txt（v3.0.0 情报汇编版）使用；重跑本脚本幂等跳过。\n"
            "#   如需改回原版，把 TITLE_MAP 里的替换手动回退即可。\n"
        ) % MARK_D
        if anchor in text:
            text = text.replace(anchor, marker + anchor, 1)
        else:
            text = marker + text
        write(path, text)
        log.append("  ✓ [D] 板块标题已改名（%d 组）：" % len(changed))
        for old, new, n in changed:
            log.append("      %s → %s（%d 处）" % (old, new, n))
    else:
        log.append("  ✗ [D] 板块标题：没有可替换的目标，已跳过")


def patch_md_rendering(root, log):
    """[F] 让 AI 正文的极简 Markdown 真正渲染成 HTML，并补上报告样式"""
    fmt = os.path.join(root, "trendradar", "ai", "formatter.py")
    html = os.path.join(root, "trendradar", "report", "html.py")

    # ---------- ① formatter.py ----------
    if not os.path.exists(fmt):
        log.append("  ✗ 找不到 trendradar/ai/formatter.py，跳过 [F]")
    else:
        text = read(fmt)
        if MARK_F in text:
            log.append("  = [F] 正文渲染：已打过，跳过")
        else:
            # 1) 注入三个渲染函数（放在 _format_list_content 之前）
            anchor_fn = "def _format_list_content(text: str) -> str:"
            text, ok1 = replace_once(text, anchor_fn, MD_HELPERS + anchor_fn,
                                     "[F] formatter.py 注入 Markdown 渲染函数", log)

            # 2) 让推送渠道的 _format_list_content 先做表格降级
            anchor_lc = ('    # 去除首尾空白，防止 AI 返回的内容开头就有换行导致显示空行\n'
                         '    text = text.strip()\n')
            new_lc = anchor_lc + (
                "\n"
                "    # ★补丁F：markdown 表格在推送渠道里降级成一行一条，避免出现一堆竖线\n"
                "    text = _md_tables_to_lines(text)\n"
            )
            text, ok2 = replace_once(text, anchor_lc, new_lc,
                                     "[F] _format_list_content 表格降级", log)

            # 3) HTML 报告改用富渲染
            #
            #    ⚠️ 这里必须**同时**把 HTML 渲染器里的 _format_list_content 去掉。
            #       原链路是： content = _format_list_content(x)  →  _escape_html()
            #       而 _format_list_content 现在会先做表格降级（把它压成 · a ｜ b），
            #       表格还没走到 render_md_block_html 就已经被压平了。
            #       HTML 通道要的是"真表格"，所以这一路改为直接用原文。
            #       步骤 3 与 3b 都只在这个函数内部生效，不会波及企业微信等推送通道。
            n_unwrap = 0
            marker_fn = "def render_ai_analysis_html_rich(result: AIAnalysisResult) -> str:"
            if marker_fn in text:
                head, tail = text.split(marker_fn, 1)
                tail, n_unwrap = re.subn(
                    r"content = _format_list_content\(result\.(\w+)\)",
                    r"content = result.\1",
                    tail,
                )
                text = head + marker_fn + tail
                if n_unwrap:
                    log.append("  ✓ [F] HTML 通道跳过 _format_list_content（%d 处，保住表格）" % n_unwrap)
                else:
                    log.append("  = [F] HTML 通道已无 _format_list_content 包装，跳过")
            else:
                log.append("  ✗ [F] 未找到 render_ai_analysis_html_rich，表格可能被压平")

            old_esc = 'content_html = _escape_html(content).replace("\\n", "<br>")'
            new_esc = "content_html = render_md_block_html(content)"
            n_esc = text.count(old_esc)
            if n_esc:
                text = text.replace(old_esc, new_esc)
                log.append("  ✓ [F] HTML 报告改用富渲染（%d 处板块）" % n_esc)
            else:
                log.append("  ✗ [F] 未找到 _escape_html 渲染锚点（可能程序版本不同，已跳过）")

            # 4) 内容容器加 ai-md 类，取消 pre-wrap 对块级排版的影响
            old_box = '<div class="ai-block-content">{content_html}</div>'
            new_box = '<div class="ai-block-content ai-md">{content_html}</div>'
            n_box = text.count(old_box)
            if n_box:
                text = text.replace(old_box, new_box)
                log.append("  ✓ [F] 内容容器加 ai-md 类（%d 处）" % n_box)
            else:
                log.append("  ✗ [F] 未找到 ai-block-content 容器锚点（已跳过）")

            # 5) 打补丁标记
            if ok1 or ok2 or n_esc or n_box or n_unwrap:
                mark = (
                    "# %s：AI 正文的极简 Markdown 已能渲染成 HTML\n"
                    "#   1. 结论行 / 编号条目 / 圆点条目 / 表格 都会正确排版；\n"
                    "#   2. HTML 通道不再走 _format_list_content，否则表格会被提前压平成文本；\n"
                    "#   3. 推送渠道（企业微信等）里表格自动降级成「· a ｜ b ｜ c」。\n"
                    "#   配套样式在 trendradar/report/html.py 的 .ai-md-* 类里。\n"
                ) % MARK_F
                text = mark + text
                write(fmt, text)
            else:
                log.append("  ✗ [F] 没有任何锚点命中，formatter.py 未修改")

    # ---------- ② report/html.py 样式 ----------
    if not os.path.exists(html):
        log.append("  ✗ 找不到 trendradar/report/html.py，跳过 [F] 样式注入")
        return
    text = read(html)
    if ".ai-md-table" in text:
        log.append("  = [F] 报告样式：已打过，跳过")
        return

    text, ok1 = replace_once(text, CSS_ANCHOR, CSS_BLOCK + CSS_ANCHOR,
                             "[F] html.py 注入 .ai-md-* 样式", log)
    text, ok2 = replace_once(text, CSS_DARK_ANCHOR, CSS_DARK_ANCHOR + "\n" + CSS_DARK_BLOCK,
                             "[F] html.py 注入深色模式样式", log)
    if ok1 or ok2:
        write(html, text)


def patch_smtp_login(root, log):
    """[E] 让 SMTP 登录名可与发件邮箱不同（接入 Brevo / Resend / SendGrid 等中继）

    原版：server.login(from_email, password)  —— 登录名被写死成发件邮箱。
    补丁后：登录名从 EMAIL_SMTP_USER 读取，未设置时回退到 from_email（原行为不变）。
    """
    path = os.path.join(root, "trendradar", "notification", "senders.py")
    if not os.path.exists(path):
        log.append("  ✗ 找不到 trendradar/notification/senders.py，跳过 [E]")
        return
    text = read(path)

    if MARK_E in text:
        log.append("  = [E] SMTP 登录名可配置：已打过，跳过")
        return

    # ① 补 import os（senders.py 原本没有导入 os）
    anchor_imp = "import smtplib\nimport time\n"
    new_imp = "import os\n" + anchor_imp
    text, _ = replace_once(text, anchor_imp, new_imp,
                           "[E] senders.py 补充 import os", log)

    # ② 登录语句改为读取 EMAIL_SMTP_USER
    anchor_login = "            server.login(from_email, password)\n"
    new_login = (
        "            # %s：登录名允许与发件地址不同，从 EMAIL_SMTP_USER 读取\n"
        "            #   Brevo 的登录名形如 7abcde@smtp-brevo.com（不是邮箱）；\n"
        "            #   Resend 固定为 resend，SendGrid 固定为 apikey。\n"
        "            #   未设置 EMAIL_SMTP_USER 时回退到 from_email，行为与原版一致。\n"
        "            _smtp_login = os.environ.get(\"EMAIL_SMTP_USER\", \"\").strip() or from_email\n"
        "            server.login(_smtp_login, password)\n"
    ) % MARK_E
    text, _ = replace_once(text, anchor_login, new_login,
                           "[E] senders.py 登录名可配置", log)

    write(path, text)


# ──────────────────────────────────────────────────────────────────────
# [G] 把 RSS 摘要带到 AI 提示词（两处注入，缺一不可）
# ──────────────────────────────────────────────────────────────────────

# ① core/analyzer.py：count_rss_frequency() 里重建 title_data 时丢掉 summary
G_CORE_ANCHOR = ('                    "source_name": item.get("feed_name", '
                 'item.get("feed_id", "RSS")),\n')
G_CORE_NEW = (
    "                    # ★补丁G：把 summary 留到 AI —— 原版在这里重建字典时\n"
    "                    #   把它丢掉了，下游拿不到。详见本文件头 [G] 说明。\n"
    "                    \"summary\": str(item.get(\"summary\") or \"\")[:400],\n"
    + G_CORE_ANCHOR
)

# ② ai/analyzer.py：拼 RSS 行时只写「[来源] 标题 | 时间」，摘要没进去
G_RSS_ANCHOR = '                        rss_lines.append(line)\n'
G_RSS_NEW = (
    "                        # ★补丁G：把 RSS 摘要带进提示词（原版只传「来源 + 标题 + 时间」）\n"
    "                        #   法规直采源的摘要里带着「文件性质 / 文号 / 生效日期 / 强制性」，\n"
    "                        #   原版把摘要整个丢掉 → AI 建法规表时这三列只能填「—」。\n"
    "                        #   ⚠️ 只对法规直采源追加：给全部条目都加摘要会白吃提示词预算。\n"
    "                        _g_sum = \" \".join(str(t.get(\"summary\") or \"\").split())\n"
    "                        if \"文件性质：\" in _g_sum:\n"
    "                            line += \" | 摘要:\" + _g_sum[:300]\n"
    + G_RSS_ANCHOR
)


# ──────────────────────────────────────────────────────────────────────
# [H] 报告顶部信息卡适配「纯 RSS 运行」
#     本项目把 platforms.sources 清空、只跑 RSS（见 config.yaml 头部说明），
#     于是信息卡里三格热榜口径的指标恒为无意义值：
#         热榜命中  0 / 0        热榜平台  --        新增热点  0
#     另「AI 分析」会拼成 "0 + 111"。
#     本补丁统一改成：只有真的配了热榜（platform_total > 0）时才显示热榜格子。
#     ——不删死，只做条件渲染：日后若重新开启热榜源，格子自动恢复。
# ──────────────────────────────────────────────────────────────────────

# ③ 热榜命中
H_TREND_ANCHOR = (
    '    # 3. 热榜命中\n'
    '    html += f"""\n'
    '                    <div class="info-item">\n'
    '                        <span class="info-label">热榜命中</span>\n'
    '                        <span class="info-value">{hot_news_count} / {hotlist_total}</span>\n'
    '                    </div>"""\n'
)
H_TREND_NEW = (
    '    # 3. 热榜命中（★补丁H：纯 RSS 运行没有热榜，整格隐藏，不再显示无意义的 0 / 0）\n'
    '    if platform_total > 0 or hotlist_total > 0:\n'
    '        html += f"""\n'
    '                        <div class="info-item">\n'
    '                            <span class="info-label">热榜命中</span>\n'
    '                            <span class="info-value">{hot_news_count} / {hotlist_total}</span>\n'
    '                        </div>"""\n'
)

# ④ 热榜平台
H_PLATFORM_ANCHOR = (
    '    # 5. 热榜平台\n'
    '    if platform_total > 0:\n'
    '        platform_value = f"{platform_success}/{platform_total}"\n'
    '    else:\n'
    '        platform_value = "--"\n'
    '    html += f"""\n'
    '                    <div class="info-item">\n'
    '                        <span class="info-label">热榜平台</span>\n'
    '                        <span class="info-value">{platform_value}</span>\n'
    '                    </div>"""\n'
)
H_PLATFORM_NEW = (
    '    # 5. 热榜平台（★补丁H：纯 RSS 运行没有热榜，整格隐藏，不再显示 "--"）\n'
    '    if platform_total > 0:\n'
    '        html += f"""\n'
    '                        <div class="info-item">\n'
    '                            <span class="info-label">热榜平台</span>\n'
    '                            <span class="info-value">{platform_success}/{platform_total}</span>\n'
    '                        </div>"""\n'
)

# ⑤ 新增热点（热榜新增口径；关键词模式下 rss_new_items 恒为 None）
H_NEW_ANCHOR = (
    '    # 7. 新增热点（热榜新增 + RSS 新增）\n'
    '    rss_new_count = sum(len(stat.get("titles", [])) for stat in (rss_new_items or []))\n'
    '    total_new = new_count + rss_new_count\n'
    '    new_value = f"{new_count} + {rss_new_count}" if total_new > 0 else "0"\n'
    '    html += f"""\n'
    '                    <div class="info-item">\n'
    '                        <span class="info-label">新增热点</span>\n'
    '                        <span class="info-value">{new_value}</span>\n'
    '                    </div>"""\n'
)
H_NEW_NEW = (
    '    # 7. 新增热点（★补丁H：这是「热榜新增」口径，纯 RSS 运行恒为 0 → 整格隐藏；\n'
    '    #    关键词匹配模式下 rss_new_items 恒为 None，RSS 侧本就没有新增计数可显示）\n'
    '    if platform_total > 0:\n'
    '        rss_new_count = sum(len(stat.get("titles", [])) for stat in (rss_new_items or []))\n'
    '        total_new = new_count + rss_new_count\n'
    '        new_value = f"{new_count} + {rss_new_count}" if total_new > 0 else "0"\n'
    '        html += f"""\n'
    '                        <div class="info-item">\n'
    '                            <span class="info-label">新增热点</span>\n'
    '                            <span class="info-value">{new_value}</span>\n'
    '                        </div>"""\n'
)

# ⑥ AI 分析格的取值（原版把热榜的 0 也拼进去 → "0 + 111"）
H_AI_ANCHOR = (
    '        ai_parts = [str(hotlist_analyzed)]\n'
    '        if ai_include_rss:\n'
    '            ai_parts.append(str(rss_analyzed))\n'
    '        if ai_include_standalone:\n'
    '            ai_parts.append(str(standalone_analyzed))\n'
    '        ai_value = " + ".join(ai_parts) if sum(int(p) for p in ai_parts) > 0 else "0"\n'
)
H_AI_NEW = (
    '        # ★补丁H：纯 RSS 运行（platform_total == 0）不把热榜的 0 计入，\n'
    '        #   否则 AI 分析格会显示成 "0 + 111" 这种没意义的拼接。\n'
    '        ai_parts = [] if platform_total == 0 else [str(hotlist_analyzed)]\n'
    '        if ai_include_rss:\n'
    '            ai_parts.append(str(rss_analyzed))\n'
    '        if ai_include_standalone:\n'
    '            ai_parts.append(str(standalone_analyzed))\n'
    '        ai_value = " + ".join(ai_parts) if ai_parts and sum(int(p) for p in ai_parts) > 0 else "0"\n'
)


def patch_rss_summary(root, log):
    """★补丁G：让 AI 能看到 RSS 摘要（法规表三列全「—」的根治手段）。

    打两处，缺一不可：
      ① trendradar/core/analyzer.py  count_rss_frequency()
         —— 分组时**重建了一个字典**，只搬 title/source/time/url，
            summary 不在其中，所以到这一步就丢了；
      ② trendradar/ai/analyzer.py    _prepare_news_content()
         —— 拼 RSS 行时只写「[来源] 标题 | 时间」，
            即使摘要还在也不会出现在提示词里。
    """
    # ① 分组时保住 summary
    core_path = os.path.join(root, "trendradar", "core", "analyzer.py")
    if not os.path.exists(core_path):
        log.append("  ✗ 找不到 trendradar/core/analyzer.py，跳过 [G]①")
    else:
        text = read(core_path)
        if MARK_G in text:
            log.append("  = [G]① core/analyzer.py 已有标记，跳过")
        else:
            new_text, _ = replace_once(
                text, G_CORE_ANCHOR, G_CORE_NEW,
                "[G]① core/analyzer.py 分组时保留 summary", log)
            write(core_path, new_text)

    # ② RSS 行尾追加摘要
    ai_path = os.path.join(root, "trendradar", "ai", "analyzer.py")
    if not os.path.exists(ai_path):
        log.append("  ✗ 找不到 trendradar/ai/analyzer.py，跳过 [G]②")
        return
    text = read(ai_path)
    if MARK_G in text:
        log.append("  = [G]② ai/analyzer.py 已有标记，跳过")
        return
    new_text, _ = replace_once(
        text, G_RSS_ANCHOR, G_RSS_NEW,
        "[G]② ai/analyzer.py RSS 行带摘要", log)
    write(ai_path, new_text)


def patch_report_infocard(root, log):
    """★补丁H：报告顶部信息卡适配「纯 RSS 运行」。

    本项目把 platforms.sources 清空、只跑 RSS，信息卡里三格热榜口径的指标
    因此恒为无意义值：热榜命中 0 / 0、热榜平台 --、新增热点 0；
    「AI 分析」还会拼成 "0 + 111"。

    本补丁**不做删除**，只改条件渲染：只有真的配了热榜（platform_total > 0）
    时才输出热榜格子，纯 RSS 运行自动隐藏，并把 AI 分析值里的 0 前缀去掉。
    这样日后重新开启热榜源时格子会自动回来，不会丢信息。

    四处替换必须全部命中才写入，避免出现「半改」的不一致状态。
    """
    path = os.path.join(root, "trendradar", "report", "html.py")
    if not os.path.exists(path):
        log.append("  ✗ 找不到 trendradar/report/html.py，跳过 [H]")
        return
    text = read(path)
    if MARK_H in text:
        log.append("  = [H] 报告信息卡：已打过，跳过")
        return

    pairs = [
        (H_TREND_ANCHOR,    H_TREND_NEW,    "[H]③ 热榜命中 → 纯 RSS 模式整格隐藏"),
        (H_PLATFORM_ANCHOR, H_PLATFORM_NEW, "[H]④ 热榜平台 → 纯 RSS 模式整格隐藏"),
        (H_NEW_ANCHOR,      H_NEW_NEW,      "[H]⑤ 新增热点 → 纯 RSS 模式整格隐藏"),
        (H_AI_ANCHOR,       H_AI_NEW,       "[H]⑥ AI 分析值 → 去掉热榜的 0 前缀"),
    ]
    ok_all = True
    for anchor, new, label in pairs:
        text, ok = replace_once(text, anchor, new, label, log)
        ok_all = ok_all and ok

    if ok_all:
        write(path, text)
    else:
        log.append("  ⚠ [H] 有锚点未命中，为免半改，本次未写入（原文件保持不变）")


# ──────────────────────────────────────────────────────────────────────
# [I] 报告搜索框：加「看得见的反馈」
#     原版 handleSearch() 的全部行为，就是把不匹配的 .news-item / .rss-item
#     设成 display:none，别的一概不做。而本项目报告的主体是 AI 双周报
#     （.ai-section）——它既不参与搜索、又占据页面最上方，真正会被搜索的
#     RSS 条目却在页面最底部（5 屏以外）。于是用户在上方搜索框里打字，
#     眼前这一屏毫无变化，观感就是「搜索没反应」（实测确认：过滤其实生效，
#     15 条法规原文被正确滤到 2 条，只是看不见）。
#
#     本补丁补四样：
#       ① 输入框下方实时显示「命中 N 条」，点「跳到第一条 ↓」可直接定位
#       ② 命中的条目高亮（黄底 + 橙色左边框）
#       ③ 被滤空的分组整组隐藏，分组计数同步改成「命中 N 条」
#       ④ 清空关键词后全部还原（分组、计数、高亮一并复原）
#
#     ⚠️ 仍然只搜索「下方条目」，不搜索 AI 双周报：那是编排好的成稿，
#        按关键词把它拆散反而没法读。故提示文案里明写搜索范围。
# ──────────────────────────────────────────────────────────────────────

I_CSS_ANCHOR = "            .search-input::placeholder { color: #9ca3af; }\n"
I_CSS_BLOCK = """            /* ★补丁I：搜索的可见反馈（命中提示 / 高亮） */
            .search-hint {
                display: none;
                margin-top: 8px;
                font-size: 13px;
                line-height: 1.6;
                color: #6b7280;
            }
            .search-hint.show { display: block; }
            .search-hint b { color: #4f46e5; font-weight: 600; }
            .search-jump {
                margin-left: 8px;
                color: #059669;
                font-weight: 600;
                cursor: pointer;
                text-decoration: underline;
                text-underline-offset: 3px;
            }
            .search-jump:hover { color: #047857; }
            .rss-item.search-hit,
            .news-item.search-hit {
                background: #fffbeb !important;
                border-left-color: #f59e0b !important;
                box-shadow: inset 0 0 0 1px #fde68a;
            }
"""

I_CSS_DARK_ANCHOR = "            body.dark-mode .search-input::placeholder { color: #64748b; }\n"
I_CSS_DARK_BLOCK = """            /* ★补丁I：搜索反馈（深色模式） */
            body.dark-mode .search-hint { color: #94a3b8; }
            body.dark-mode .search-hint b { color: #a5b4fc; }
            body.dark-mode .search-jump { color: #6ee7b7; }
            body.dark-mode .search-jump:hover { color: #34d399; }
            body.dark-mode .rss-item.search-hit,
            body.dark-mode .news-item.search-hit {
                background: #3a3113 !important;
                border-left-color: #fbbf24 !important;
                box-shadow: inset 0 0 0 1px #6b4e08;
            }
"""

# 搜索栏 HTML：补一个「命中提示」容器（并顺手把 placeholder 说准，
# 原版写着「搜索新闻标题...」，本项目报告里同时有法规条目与英文新闻）
I_HTML_ANCHOR = (
    '                <div class="search-bar">\n'
    '                    <input type="text" class="search-input" placeholder="搜索新闻标题..." oninput="handleSearch(this.value)">\n'
    '                </div>'
)
I_HTML_NEW = (
    '                <div class="search-bar">\n'
    '                    <!-- ★补丁I：placeholder 说准搜索范围；下方容器显示命中反馈 -->\n'
    '                    <input type="text" class="search-input" placeholder="搜索下方 RSS 条目标题..." oninput="handleSearch(this.value)">\n'
    '                    <div class="search-hint" id="search-hint"></div>\n'
    '                </div>'
)

I_JS_ANCHOR = (
    '            var handleSearch = (function() {\n'
    '                var timer = null;\n'
    '                return function(query) {\n'
    '                    clearTimeout(timer);\n'
    '                    timer = setTimeout(function() {\n'
    '                        query = query.toLowerCase();\n'
    "                        document.querySelectorAll('.news-item').forEach(function(item) {\n"
    "                            var title = (item.querySelector('.news-title') || {}).textContent || '';\n"
    "                            item.style.display = (!query || title.toLowerCase().indexOf(query) !== -1) ? '' : 'none';\n"
    '                        });\n'
    "                        document.querySelectorAll('.rss-item').forEach(function(item) {\n"
    "                            var title = (item.querySelector('.rss-title') || {}).textContent || '';\n"
    "                            item.style.display = (!query || title.toLowerCase().indexOf(query) !== -1) ? '' : 'none';\n"
    '                        });\n'
    '                    }, 200);\n'
    '                };\n'
    '            })();\n'
)

I_JS_NEW = """            // ★补丁I：搜索加可见反馈 —— 命中计数 / 高亮 / 空分组隐藏 / 一键跳转
            //   原版只做「不匹配就 display:none」；而 AI 双周报不参与搜索又占着
            //   页面最上方，于是打字时眼前毫无变化，观感成了「搜索没反应」。
            var handleSearch = (function() {
                var timer = null;

                function titleText(item, titleSelector) {
                    var el = item.querySelector(titleSelector);
                    return el ? (el.textContent || '') : '';
                }

                function visibleCount(group) {
                    var n = 0;
                    group.querySelectorAll('.rss-item, .news-item').forEach(function(el) {
                        if (el.style.display !== 'none') n++;
                    });
                    return n;
                }

                // 分组计数：过滤时显示「命中 N 条」，清空后还原原文
                function applyGroup(group, countSelector, filtering) {
                    var countEl = group.querySelector(countSelector);
                    if (countEl && countEl.dataset.fullCount === undefined) {
                        countEl.dataset.fullCount = countEl.textContent;
                    }
                    if (!filtering) {
                        group.style.display = '';
                        if (countEl) countEl.textContent = countEl.dataset.fullCount;
                        return;
                    }
                    var n = visibleCount(group);
                    group.style.display = n > 0 ? '' : 'none';
                    if (countEl) countEl.textContent = n > 0 ? ('命中 ' + n + ' 条') : '0 条';
                }

                function applySectionCount(total, filtering) {
                    var el = document.querySelector('.rss-section-count');
                    if (!el) return;
                    if (el.dataset.fullCount === undefined) el.dataset.fullCount = el.textContent;
                    el.textContent = filtering ? ('命中 ' + total + ' 条') : el.dataset.fullCount;
                }

                return function(query) {
                    clearTimeout(timer);
                    timer = setTimeout(function() {
                        var raw = (query || '').trim();
                        var q = raw.toLowerCase();
                        var hits = [];
                        var rssHits = 0;

                        document.querySelectorAll('.news-item').forEach(function(item) {
                            if (!q) {
                                item.style.display = '';
                                item.classList.remove('search-hit');
                                return;
                            }
                            var ok = titleText(item, '.news-title').toLowerCase().indexOf(q) !== -1;
                            item.style.display = ok ? '' : 'none';
                            if (ok) { item.classList.add('search-hit'); hits.push(item); }
                            else { item.classList.remove('search-hit'); }
                        });

                        document.querySelectorAll('.rss-item').forEach(function(item) {
                            if (!q) {
                                item.style.display = '';
                                item.classList.remove('search-hit');
                                return;
                            }
                            var ok = titleText(item, '.rss-title').toLowerCase().indexOf(q) !== -1;
                            item.style.display = ok ? '' : 'none';
                            if (ok) {
                                item.classList.add('search-hit');
                                hits.push(item);
                                rssHits++;
                            } else {
                                item.classList.remove('search-hit');
                            }
                        });

                        document.querySelectorAll('.feed-group').forEach(function(g) {
                            applyGroup(g, '.feed-count', !!q);
                        });
                        document.querySelectorAll('.word-group').forEach(function(g) {
                            applyGroup(g, '.word-count', !!q);
                        });
                        applySectionCount(rssHits, !!q);

                        var hint = document.getElementById('search-hint');
                        if (!hint) return;
                        hint.className = 'search-hint';
                        hint.textContent = '';
                        if (!q) return;

                        hint.className = 'search-hint show';
                        if (hits.length === 0) {
                            hint.appendChild(document.createTextNode('未命中「' + raw + '」 · 搜索范围仅限下方 RSS 条目'));
                            return;
                        }
                        hint.appendChild(document.createTextNode('命中 '));
                        var strong = document.createElement('b');
                        strong.textContent = String(hits.length);
                        hint.appendChild(strong);
                        hint.appendChild(document.createTextNode(' 条（仅下方 RSS 条目）'));
                        var jump = document.createElement('span');
                        jump.className = 'search-jump';
                        jump.textContent = '跳到第一条 ↓';
                        jump.addEventListener('click', function() {
                            hits[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
                        });
                        hint.appendChild(jump);
                    }, 200);
                };
            })();
"""


# ──────────────────────────────────────────────────────────────────────
# [J] 搜索的中英同义词别名表（叠加在 [I] 之上）
#     问题：用户搜「氨动力散货船」0 命中。该词全页 10 处全在 AI 双周报里
#           （AI 把英文新闻译成中文的概括用词），RSS 原标题却是英文
#           （ammonia-powered bulker / dry bulk carrier），纯子串匹配搜不到。
#     解法：一张「同义簇」表，查询词命中任一成员就把整组词一起检索。
#           表放在 html.py 的 handleSearch 里，改动只影响匹配，不动高亮/计数。
#     ⚠️ 本补丁的 5 个锚点全部落在 [I] 重写后的 handleSearch 里，
#        因此必须在 [I] 之后运行（脚本里 patch_search_synonyms 已排在 [I] 之后）。
# ──────────────────────────────────────────────────────────────────────

J_SYN_TABLE = '''                // ★补丁J：中英同义词别名表
                //   报告里的中文词几乎都来自 AI 双周报的概括（如「氨动力散货船」），
                //   而 RSS 原标题是英文（ammonia-powered bulker），纯子串匹配必然 0 命中。
                //   每组是一个「同义簇」：命中任一成员，整组词一起参与检索。
                //   要加词，直接往对应数组里追加即可，中英文词条都行。
                var SEARCH_SYNONYMS = [
                    ["氨燃料", "氨动力", "氨", "ammonia", "nh3", "ammonia-powered", "ammonia-fuelled", "ammonia bunkering"],
                    ["甲醇", "绿色甲醇", "甲醇加注", "methanol", "e-methanol", "bio-methanol", "green methanol"],
                    ["散货船", "干散货船", "bulker", "bulkers", "bulk carrier", "dry bulk", "dry cargo"],
                    ["液化天然气", "lng", "liquefied natural gas", "bio-lng", "lbm", "biomethane", "bio-methane", "生物甲烷"],
                    ["氢", "氢燃料", "氢能", "氢动力", "hydrogen", "h2"],
                    ["加注", "加注作业", "燃料加注", "bunkering", "bunkering operation", "fuel supply"],
                    ["岸电", "shore power", "cold ironing", "onshore power"],
                    ["能效", "能效指数", "eedi", "eexi", "cii", "energy efficiency", "carbon intensity indicator"],
                    ["风助推进", "风力助推", "转子帆", "旋筒风帆", "风帆", "wind-assisted propulsion", "rotor sail", "rotor sails", "flettner"],
                    ["碳捕集", "碳捕集封存", "ccs", "ccus", "carbon capture"],
                    ["脱碳", "温室气体", "净零", "减排", "碳排放", "ghg", "greenhouse gas", "net-zero", "net zero", "decarbonisation", "decarbonization"],
                    ["国际海事组织", "imo", "marpol"],
                    ["欧盟碳市场", "eu ets", "emissions trading system"],
                    ["船用燃料", "燃料油", "marine fuel", "fuel oil", "vlsfo", "iso 8217"],
                    ["核动力", "海上核能", "浮动核电站", "nuclear", "nuclear power", "smr"],
                    ["电池动力", "电池", "纯电动", "混合动力", "燃料电池", "battery", "batteries", "hybrid-electric", "hybrid propulsion", "fuel cell", "fuel cells"],
                    ["乙醇", "燃料乙醇", "生物乙醇", "乙醇燃料", "乙醇加注", "ethanol", "bioethanol", "bio-ethanol", "e-ethanol", "ethyl alcohol"],
                    ["生物燃料", "biofuel", "biofuels", "biodiesel", "fame", "hvo"],
                    ["船级社", "中国船级社", "classification society", "class society", "abs", "dnv", "classnk", "nkk", "bureau veritas", "lloyd's register"],
                    ["碳税", "碳价", "carbon tax", "carbon price", "carbon levy"],
                    ["双燃料", "dual-fuel", "dual fuel"]
                ];

                function _isCJK(s) {
                    return /[\\u4e00-\\u9fa5]/.test(s);
                }

                // ★补丁J-r2：拉丁词「整词」判定。
                //   原来用 indexOf 子串匹配，会踩两个坑：
                //     ① methanol 里含 ethanol 这七个字母 —— 搜 ethanol 会把甲醇新闻全带出来；
                //     ② abs 是船级社，但 absolute / absorb 也会被当成命中。
                //   这里改成扫一遍字符串、要求前后是首尾或非字母数字，
                //   顺带允许尾部一个 s（bunkerings / bioethanols）。
                function _wHits(text, term) {
                    if (!text || !term) { return false; }
                    text = text.toLowerCase();
                    term = term.toLowerCase();
                    var i = text.indexOf(term);
                    while (i !== -1) {
                        var b = i === 0 ? '' : text.charAt(i - 1);
                        var a = i + term.length >= text.length ? '' : text.charAt(i + term.length);
                        var okB = b === '' || !/[a-z0-9]/.test(b);
                        var okA = a === '' || !/[a-z0-9]/.test(a) || a === 's';
                        if (okB && okA) { return true; }
                        i = text.indexOf(term, i + 1);
                    }
                    return false;
                }

                // 单个词条是否「触发」本组：中文双向包含；拉丁文按整词判定
                function _memberHits(m, q) {
                    if (!m || !q) return false;
                    if (m === q) return true;
                    if (_isCJK(m) || _isCJK(q)) return m.indexOf(q) !== -1 || q.indexOf(m) !== -1;
                    return _wHits(m, q) || _wHits(q, m);
                }

                // 由查询词展开出的检索词表；没命中任何同义簇时就只有它自己
                function _qTerms(q) {
                    if (!q) return [];
                    var terms = [q];
                    var seen = {};
                    seen[q] = 1;
                    SEARCH_SYNONYMS.forEach(function(group) {
                        var on = group.some(function(m) { return _memberHits(m, q); });
                        if (!on) return;
                        group.forEach(function(m) {
                            var t = m.toLowerCase();
                            if (!seen[t]) { seen[t] = 1; terms.push(t); }
                        });
                    });
                    return terms;
                }

                // 展开出的、不是原查询词的那部分（用来写提示文案）
                function _extraTerms(terms, q) {
                    var out = [];
                    for (var i = 0; i < terms.length; i++) {
                        if (terms[i] !== q) out.push(terms[i]);
                    }
                    return out;
                }

                // 标题命中哪个检索词：返回命中的那个词，没命中返回空串
                // ★补丁J-r2：拉丁词走整词判定，避免 ethanol 命中 methanol
                function _firstHit(title, terms) {
                    var low = (title || '').toLowerCase();
                    for (var i = 0; i < terms.length; i++) {
                        var t = terms[i];
                        if (_isCJK(t) ? low.indexOf(t) !== -1 : _wHits(low, t)) return t;
                    }
                    return "";
                }

                // 提示文案里的词表缩写：最多列 4 个，多了加「等」
                function _synBrief(list) {
                    var show = list.slice(0, 4);
                    return show.join(' / ') + (list.length > show.length ? ' 等' : '');
                }

'''

J_TABLE_ANCHOR = "                // 分组计数：过滤时显示「命中 N 条」，清空后还原原文\n"

J_TERMS_ANCHOR = (
    "                        var raw = (query || '').trim();\n"
    "                        var q = raw.toLowerCase();\n"
)
J_TERMS_NEW = J_TERMS_ANCHOR + (
    "                        var terms = _qTerms(q);           // ★补丁J：展开中英同义词\n"
    "                        var triedSyn = _extraTerms(terms, q);\n"
    "                        var usedSyn = {};                 // ★补丁J：真的命中的同义词\n"
)

J_NEWS_ANCHOR = (
    "                            var ok = titleText(item, '.news-title').toLowerCase().indexOf(q) !== -1;\n"
)
J_NEWS_NEW = (
    "                            var hitTerm = _firstHit(titleText(item, '.news-title'), terms);\n"
    "                            var ok = hitTerm !== '';\n"
    "                            if (ok && hitTerm !== q) usedSyn[hitTerm] = 1;\n"
)

J_RSS_ANCHOR = (
    "                            var ok = titleText(item, '.rss-title').toLowerCase().indexOf(q) !== -1;\n"
)
J_RSS_NEW = (
    "                            var hitTerm = _firstHit(titleText(item, '.rss-title'), terms);\n"
    "                            var ok = hitTerm !== '';\n"
    "                            if (ok && hitTerm !== q) usedSyn[hitTerm] = 1;\n"
)

J_HINT_ANCHOR = (
    "                        hint.className = 'search-hint show';\n"
    "                        if (hits.length === 0) {\n"
    "                            hint.appendChild(document.createTextNode('未命中「' + raw + '」 · 搜索范围仅限下方 RSS 条目'));\n"
    "                            return;\n"
    "                        }\n"
    "                        hint.appendChild(document.createTextNode('命中 '));\n"
    "                        var strong = document.createElement('b');\n"
    "                        strong.textContent = String(hits.length);\n"
    "                        hint.appendChild(strong);\n"
    "                        hint.appendChild(document.createTextNode(' 条（仅下方 RSS 条目）'));\n"
    "                        var jump = document.createElement('span');\n"
    "                        jump.className = 'search-jump';\n"
    "                        jump.textContent = '跳到第一条 ↓';\n"
)
J_HINT_NEW = (
    "                        // ★补丁J：提示文案把「同义词」也说清楚\n"
    "                        hint.className = 'search-hint show';\n"
    "                        if (hits.length === 0) {\n"
    "                            hint.appendChild(document.createTextNode('未命中「' + raw + '」'));\n"
    "                            if (triedSyn.length) {\n"
    "                                hint.appendChild(document.createTextNode(' · 已试同义词 '));\n"
    "                                var tEl = document.createElement('b');\n"
    "                                tEl.textContent = _synBrief(triedSyn);\n"
    "                                hint.appendChild(tEl);\n"
    "                            }\n"
    "                            hint.appendChild(document.createTextNode(' · 只搜下方 RSS 条目标题，上方 AI 双周报不参与'));\n"
    "                            return;\n"
    "                        }\n"
    "                        hint.appendChild(document.createTextNode('命中 '));\n"
    "                        var strong = document.createElement('b');\n"
    "                        strong.textContent = String(hits.length);\n"
    "                        hint.appendChild(strong);\n"
    "                        hint.appendChild(document.createTextNode(' 条（仅下方 RSS 条目标题）'));\n"
    "                        var syns = Object.keys(usedSyn);\n"
    "                        if (syns.length) {\n"
    "                            hint.appendChild(document.createTextNode(' · 同义词 '));\n"
    "                            var sEl = document.createElement('b');\n"
    "                            sEl.textContent = _synBrief(syns);\n"
    "                            hint.appendChild(sEl);\n"
    "                            hint.appendChild(document.createTextNode(' 一并检索'));\n"
    "                        }\n"
    "                        var jump = document.createElement('span');\n"
    "                        jump.className = 'search-jump';\n"
    "                        jump.textContent = ' · 跳到第一条 ↓';\n"
)


# ──────────────────────────────────────────────────────────────────────
# [K] AI 正文 ↔ RSS 条目「交叉引用」
#
#     目标（用户原话）：像论文的文献交叉引用那样，看 AI 分析时能定位到对应的 RSS。
#
#     原版两头都没有「句柄」，所以谁都指不到谁：
#       · ai/analyzer.py 拼给 AI 的行是「- [来源] 标题 | 时间」，AI 无从指认某一条；
#       · report/html.py 渲染的 <div class="rss-item"> 没有 id，正文也无从跳转。
#
#     补法分四块，缺一不可：
#       ① ai/analyzer.py   每条 RSS 行加行首编号「- [#12] ...」，与报告页一一对应；
#       ② ai/formatter.py  把 AI 正文里的引用标记 (#12) 渲染成可点击徽标（依赖 [F]）；
#       ③ report/html.py   给每个 RSS 条目加 id="rss-12" + 可见编号，并注入样式；
#       ④ report/html.py   注入一段 JS：点徽标跳转 + 闪烁、编号越界标灰划掉并告警、
#                          被引用条目显示「↩ 被引用 N 处」并可跳回正文，
#                          以及「AI 漏标时用专名 + 中英同义词簇保守补引用」。
#
#     ⚠️ 编号口径：AI 与报告读的是同一个 rss_items 列表、同一顺序，
#        故「第 N 条」在两侧天然一致。AI 侧按全量编号后再截断，
#        将来条目数超过 max_news_for_analysis 也不会错位。
#     ⚠️ 编号只加在主区（rss_items）；「新增区」调用传 id_prefix=""，
#        否则同一条目在一页里出现两个编号，引用就有歧义了。
#     ⚠️ 需配合 config/ai_analysis_prompt.txt（v3.3.0 起）里的「引用规范」一起用，
#        否则 AI 不会标引用，只剩自动兜底那一半能力。
# ──────────────────────────────────────────────────────────────────────

K_AI_ANCHOR = "                        rss_lines.append(line)\n"
K_AI_NEW = (
    "                        # ★补丁K：给每条 RSS 编一个与报告页一一对应的稳定编号\n"
    "                        #   行首形如「- [#12] [来源] 标题 | 时间」，AI 据此回引。\n"
    "                        #   编号用全量顺序，先编后截断，超限也不会错位。\n"
    "                        _k_body = line[2:] if line.startswith(\"- \") else line\n"
    "                        rss_lines.append(\"- [#%d] \" % (rss_count + 1) + _k_body)\n"
)

K_FMT_FN_ANCHOR = "def _md_inline_html(text: str) -> str:\n"
K_FMT_CALL_ANCHOR = '    out = re.sub(r"\\*\\*(.+?)\\*\\*", r"<strong>\\1</strong>", out)\n'
K_FMT_CALL_NEW = K_FMT_CALL_ANCHOR + (
    "    out = _md_cite_html(out)   # ★补丁K：把 (#12) 变成可点击的引用徽标\n"
)

K_CITE_FN = r'''def _md_cite_html(html_text: str) -> str:
    # ★补丁K：把 AI 正文里的引用标记渲染成可点击徽标，点击跳转到下方对应的
    #   RSS 条目。能认这些写法（全角 / 半角括号都行，编号前可带「依据」等字样）：
    #       （#12）        [#12]        （依据 #12）
    #       （#3、#7）     （#3 #7）    （#3-7）  （#3、#5-7）
    #   输入已经过 HTML 转义，所以这里可以安全地拼 HTML 片段。
    def _rep(m):
        nums = []
        for part in re.split(r"[,，、;；]\s*", m.group(1)):
            part = part.strip()
            rng = re.match(r"^#?\s*(\d+)\s*[-–~～至]\s*#?\s*(\d+)$", part)
            if rng:
                a, b = int(rng.group(1)), int(rng.group(2))
                if a > b:
                    a, b = b, a
                if 0 < b - a <= 12:
                    nums.extend(range(a, b + 1))
                continue
            for d in re.findall(r"\d+", part):
                nums.append(int(d))
        seen = set()
        out = []
        for n in nums:
            if n <= 0 or n in seen:
                continue
            seen.add(n)
            out.append(
                '<a class="cite-ref" href="#rss-%d" data-target="rss-%d" data-n="%d">#%d</a>'
                % (n, n, n, n)
            )
        return "".join(out) if out else m.group(0)

    return re.sub(
        r"[（(\[]\s*[^#（）()\[\]]{0,8}#\s*([\d#\s\-–~～至,，、;；]+?)\s*[）)\]]",
        _rep, html_text)


'''

K_SIG_ANCHOR = (
    '    def render_rss_stats_html(stats: List[Dict], title: str = "RSS 订阅更新") -> str:\n'
)
K_SIG_NEW = (
    '    # ★补丁K：id_prefix 非空时给每个条目编稳定序号 id="rss-12"，\n'
    '    #   与提示词里给 AI 的 [#12] 一一对应，供 AI 正文回引。\n'
    '    #   「新增区」调用传 id_prefix=""，避免同一页面出现两个编号。\n'
    '    def render_rss_stats_html(stats: List[Dict], title: str = "RSS 订阅更新",\n'
    '                              id_prefix: str = "rss") -> str:\n'
)

K_LOOP_ANCHOR = (
    '        # 按关键词分组渲染（与热榜格式一致）\n'
    '        for stat in stats:\n'
    '            keyword = stat.get("word", "")\n'
)
K_LOOP_NEW = (
    '        # 按关键词分组渲染（与热榜格式一致）\n'
    '        _cite_no = 0  # ★补丁K：跨分组的全局条目序号\n'
    '        for stat in stats:\n'
    '            keyword = stat.get("word", "")\n'
)

K_ITEM_ANCHOR = (
    '                rss_html += """\n'
    '                        <div class="rss-item">\n'
    '                            <div class="rss-meta">"""\n'
)
K_ITEM_NEW = (
    '                _cite_no += 1  # ★补丁K\n'
    '                _cite_attr = (\n'
    '                    \' id="%s-%d" data-cite="%d"\' % (id_prefix, _cite_no, _cite_no)\n'
    '                ) if id_prefix else ""\n'
    '                rss_html += """\n'
    '                        <div class="rss-item"%s>\n'
    '                            <div class="rss-meta">""" % _cite_attr\n'
)

K_META_ANCHOR = (
    '                if is_new:\n'
    '                    rss_html += \'<span class="rss-author" style="color: #dc2626;">NEW</span>\'\n'
)
K_META_NEW = K_META_ANCHOR + (
    '\n'
    '                # ★补丁K：显示条目编号（与 AI 正文里的引用徽标对应）\n'
    '                if id_prefix:\n'
    '                    rss_html += (\'<span class="rss-no" title="AI 正文可引用此编号">#%d</span>\'\n'
    '                                 % _cite_no)\n'
)

K_CALL_ANCHOR = (
    '    rss_new_html = render_rss_stats_html(rss_new_items, "RSS 新增更新") if rss_new_items else ""\n'
)
K_CALL_NEW = (
    '    # ★补丁K：新增区不加编号（同一条目在主区已编号，重复会让引用有歧义）\n'
    '    rss_new_html = render_rss_stats_html(rss_new_items, "RSS 新增更新", "") if rss_new_items else ""\n'
)

K_CSS_ANCHOR = I_CSS_ANCHOR
K_CSS_BLOCK = """            /* ★补丁K：AI 正文 ↔ RSS 条目交叉引用 */
            .cite-ref {
                display: inline-block;
                margin: 0 1px 0 3px;
                padding: 0 5px;
                border-radius: 8px;
                font-size: 11px;
                line-height: 16px;
                font-weight: 600;
                color: #1d4ed8;
                background: #e0e7ff;
                border: 1px solid #c7d2fe;
                text-decoration: none;
                vertical-align: 1px;
                cursor: pointer;
                white-space: nowrap;
                transition: background .15s, color .15s;
            }
            .cite-ref:hover { background: #c7d2fe; color: #1e3a8a; }
            .cite-ref.cite-auto {
                color: #92400e;
                background: #fef3c7;
                border: 1px dashed #fcd34d;
            }
            .cite-ref.cite-auto:hover { background: #fde68a; }
            .cite-ref.cite-dead {
                color: #9ca3af;
                background: #f3f4f6;
                border: 1px solid #e5e7eb;
                text-decoration: line-through;
                cursor: not-allowed;
            }
            .rss-no {
                margin-left: auto;
                padding: 0 6px;
                border-radius: 8px;
                font-size: 11px;
                line-height: 16px;
                font-weight: 600;
                color: #1d4ed8;
                background: #eef2ff;
                border: 1px solid #c7d2fe;
            }
            .rss-cited {
                margin-left: 6px;
                font-size: 12px;
                color: #6b7280;
                cursor: pointer;
                border-bottom: 1px dotted #9ca3af;
            }
            .rss-cited:hover { color: #1d4ed8; border-bottom-color: #1d4ed8; }
            .rss-item.cite-flash { animation: citeFlash 2.4s ease-out 1; }
            @keyframes citeFlash {
                0%   { background: #fef3c7; box-shadow: inset 0 0 0 3px #f59e0b; }
                100% { background: transparent; box-shadow: none; }
            }
"""

K_CSS_DARK_ANCHOR = I_CSS_DARK_ANCHOR
K_CSS_DARK_BLOCK = """            /* ★补丁K：交叉引用（深色模式） */
            body.dark-mode .cite-ref {
                color: #bfdbfe;
                background: #1e3a5f;
                border-color: #1e40af;
            }
            body.dark-mode .cite-ref:hover { background: #1e40af; color: #dbeafe; }
            body.dark-mode .cite-ref.cite-auto {
                color: #fcd34d;
                background: #3a3113;
                border-color: #b45309;
            }
            body.dark-mode .cite-ref.cite-dead {
                color: #64748b;
                background: #1f2937;
                border-color: #374151;
            }
            body.dark-mode .rss-no {
                color: #bfdbfe;
                background: #1e3a5f;
                border-color: #1e40af;
            }
            body.dark-mode .rss-cited { color: #94a3b8; border-bottom-color: #475569; }
            body.dark-mode .rss-cited:hover { color: #bfdbfe; border-bottom-color: #bfdbfe; }
            body.dark-mode .rss-item.cite-flash { animation: citeFlashDark 2.4s ease-out 1; }
            @keyframes citeFlashDark {
                0%   { background: #78350f; box-shadow: inset 0 0 0 3px #fbbf24; }
                100% { background: transparent; box-shadow: none; }
            }
"""

K_JS_ANCHOR = "        </script>\n    </body>\n"
K_JS_CODE = r'''            /* ★补丁K：AI 正文 ↔ RSS 条目「交叉引用」
               ---------------------------------------------------------------
               ① AI 正文里的引用徽标（如 #12）点一下就滚到下方第 12 条 RSS 并闪烁；
               ② 编号在本期报告里不存在的，标灰划掉并在控制台告警（AI 误引）；
               ③ 被引用的条目上显示「↩ 被引用 N 处」，点它跳回正文第一处；
               ④ AI 漏标的，用「英文专名 + 中英同义词簇」保守地自动补引用 ——
                  补上的徽标是虚线样式，悬停会写明是自动匹配、仅供参考。
               ⑤ 本段只在页面加载后加装饰，不改动任何既有 DOM 结构。 */
            (function () {
                var SYN = [
                    ['氨', '氨燃料', '氨动力', 'ammonia'],
                    ['甲醇', '绿色甲醇', 'methanol', 'e-methanol'],
                    ['氢', '氢燃料', '氢能', 'hydrogen'],
                    ['液化天然气', 'lng', 'lbm', '生物甲烷', 'biomethane', 'methane'],
                    ['液化石油气', 'lpg'],
                    ['乙醇', '燃料乙醇', '生物乙醇', 'ethanol', 'bioethanol', 'bio-ethanol', 'e-ethanol'],
                    ['生物燃料', '生物柴油', 'biofuel', 'biodiesel', 'hvo'],
                    ['电池', '纯电动', '混合动力', 'battery', 'hybrid', 'electric'],
                    ['燃料电池', 'fuel cell'],
                    ['岸电', 'shore power', 'cold ironing'],
                    ['风帆', '风助推进', '转子帆', '风能', 'wind-assisted', 'rotor sail', 'flettner', 'wind'],
                    ['碳捕集', 'ccs', 'ccus', 'carbon capture'],
                    ['核动力', '核能', 'nuclear', 'smr'],
                    ['加注', '燃料加注', 'bunkering'],
                    ['双燃料', 'dual-fuel'],
                    ['船级社', 'classnk', 'dnv', 'bureau veritas', 'lloyd', 'abs'],
                    ['国际海事组织', 'imo', 'marpol', 'mepc'],
                    ['欧盟碳市场', 'eu ets', 'ets'],
                    ['能效', 'eedi', 'eexi', 'cii', 'energy efficiency'],
                    ['脱碳', '净零', '减排', '碳排放', 'greenhouse', 'decarbonisation',
                     'decarbonization', 'net-zero', 'net zero'],
                    ['散货船', 'bulker', 'bulkers', 'bulk carrier', 'bulk', 'dry cargo', 'dry bulk'],
                    ['集装箱船', 'container'],
                    ['油轮', 'tanker'],
                    ['滚装船', 'ro-ro', 'roro'],
                    ['邮轮', 'cruise'],
                    ['海上风电', 'offshore wind']
                ];
                var STOP = { the: 1, and: 1, for: 1, with: 1, its: 1, new: 1, first: 1,
                             world: 1, ship: 1, ships: 1, vessel: 1, vessels: 1,
                             marine: 1, maritime: 1, fuel: 1, fuels: 1, energy: 1,
                             power: 1, green: 1, low: 1, carbon: 1, port: 1, ports: 1,
                             sea: 1, says: 1, will: 1, has: 1, have: 1, from: 1,
                             that: 1, this: 1, into: 1, over: 1, more: 1, than: 1,
                             global: 1, market: 1, project: 1, group: 1, ltd: 1,
                             one: 1, two: 1, three: 1, all: 1, can: 1, may: 1,
                             are: 1, was: 1, were: 1, been: 1, not: 1, but: 1,
                             mid: 1, day: 1, week: 1, year: 1, next: 1, last: 1 };

                function low(s) { return (s || '').toLowerCase(); }

                function toks(s) {
                    var out = {}, m;
                    /* 注意：连字符要当分隔符用 —— 标题里大量出现 ammonia-powered /
                       dual-fuel / wind-assisted 这类连字符词，若把整串当一个 token，
                       「ammonia」就永远匹配不到了。 */
                    var re = /[A-Za-z][A-Za-z0-9'’.]*/g;
                    while ((m = re.exec(s || '')) !== null) {
                        var w = m[0].replace(/^[.'’]+|[.'’]+$/g, '').toLowerCase();
                        if (w.length >= 3) { out[w] = 1; }
                    }
                    return out;
                }

                function hasTerm(text, set, term) {
                    if (!term) { return false; }
                    term = term.toLowerCase();
                    if (/^[a-z0-9]+$/.test(term)) { return !!set[term]; }
                    return text.indexOf(term) !== -1;
                }

                function scrollToEl(el) {
                    if (!el) { return; }
                    if (typeof el.scrollIntoView === 'function') {
                        try { el.scrollIntoView({ behavior: 'smooth', block: 'center' }); return; }
                        catch (e) { }
                        try { el.scrollIntoView(true); return; } catch (e) { }
                    }
                    /* 兜底：不支持 scrollIntoView 的环境按坐标滚 */
                    try {
                        var y = el.getBoundingClientRect().top
                              + (window.pageYOffset || document.documentElement.scrollTop || 0) - 120;
                        window.scrollTo(0, y);
                    } catch (e) { }
                }

                function flash(el) {
                    if (!el) { return; }
                    scrollToEl(el);
                    el.classList.remove('cite-flash');
                    void el.offsetWidth;
                    el.classList.add('cite-flash');
                    window.setTimeout(function () { el.classList.remove('cite-flash'); }, 2600);
                }

                function run() {
                    var ai = document.querySelector('.ai-section');
                    var list = [].slice.call(document.querySelectorAll('.rss-item[id^="rss-"]'));
                    if (!ai || !list.length) { return; }

                    /* ---- ① 已有引用：可跳转 / 越界标灰 ---- */
                    var refs = [].slice.call(ai.querySelectorAll('a.cite-ref'));
                    var byTarget = {};
                    refs.forEach(function (a) {
                        var id = a.getAttribute('data-target') || '';
                        var el = id ? document.getElementById(id) : null;
                        if (!el) {
                            a.classList.add('cite-dead');
                            a.setAttribute('title', '本期没有编号 #' + (a.getAttribute('data-n') || '?')
                                                  + ' 的条目（AI 误引或编号已过期）');
                            if (window.console && console.warn) {
                                console.warn('[补丁K] 引用越界：' + (a.textContent || '') + ' → 找不到 #' + id);
                            }
                            return;
                        }
                        a.setAttribute('title', '定位到下方第 '
                            + (el.getAttribute('data-cite') || '?') + ' 条 RSS');
                        (byTarget[id] = byTarget[id] || []).push(a);
                        a.addEventListener('click', function (ev) {
                            ev.preventDefault();
                            flash(el);
                            try { history.replaceState(null, '', '#' + id); } catch (e) {}
                        });
                    });

                    /* ---- ③ 反向索引：被引用 N 处 ---- */
                    Object.keys(byTarget).forEach(function (id) {
                        var el = document.getElementById(id);
                        var meta = el ? el.querySelector('.rss-meta') : null;
                        if (!meta) { return; }
                        var n = byTarget[id].length;
                        var sp = document.createElement('span');
                        sp.className = 'rss-cited';
                        sp.textContent = '↩ 被引用 ' + n + ' 处';
                        sp.setAttribute('title', '点击回到 AI 正文里引用它的位置');
                        sp.addEventListener('click', function () { flash(byTarget[id][0]); });
                        meta.appendChild(sp);
                    });

                    /* ---- ④ 自动兜底：专名 + 同义词保守匹配 ---- */
                    var corpus = list.map(function (el) {
                        var t = el.querySelector('.rss-title');
                        var s = t ? t.textContent : el.textContent;
                        return { el: el, low: low(s), toks: toks(s) };
                    });
                    var N = corpus.length;
                    var df = {};
                    corpus.forEach(function (c) {
                        Object.keys(c.toks).forEach(function (w) { df[w] = (df[w] || 0) + 1; });
                    });
                    function idf(w) { var d = df[w] || 0; return d ? Math.log(1 + N / d) : 0; }

                    /* 同义词簇的「辨别力权重」：命中条目越少、越能区分，权重越高。
                       这样「氨 + 散货船」两条同义线索同时命中时，能准确落到
                       氨动力散货船的条目上，而不是所有含 ammonia 的条目。 */
                    var gw = SYN.map(function (g) {
                        var hit = 0;
                        corpus.forEach(function (c) {
                            for (var i = 0; i < g.length; i++) {
                                if (hasTerm(c.low, c.toks, g[i])) { hit++; return; }
                            }
                        });
                        return hit ? Math.log(1 + N / hit) : 0;
                    });

                    var blocks = [].slice.call(ai.querySelectorAll('.ai-md-text, .ai-md-p'));
                    blocks.forEach(function (b) {
                        if (b.querySelector('a.cite-ref')) { return; }
                        var raw = b.textContent || '';
                        if (raw.replace(/\s/g, '').length < 8) { return; }
                        var btxt = low(raw);
                        var bset = toks(raw);

                        var active = [];
                        SYN.forEach(function (g, gi) {
                            for (var i = 0; i < g.length; i++) {
                                if (hasTerm(btxt, bset, g[i])) { active.push(gi); return; }
                            }
                        });
                        if (!active.length) { return; }

                        var scored = [];
                        corpus.forEach(function (c, idx) {
                            var sc = 0, rare = 0, hit = 0, syn = 0, mx = 0;
                            Object.keys(bset).forEach(function (w) {
                                if (STOP[w] || !c.toks[w]) { return; }
                                sc += idf(w);
                                if ((df[w] || 0) <= 2) { rare++; }
                            });
                            active.forEach(function (gi) {
                                var g = SYN[gi];
                                for (var j = 0; j < g.length; j++) {
                                    if (hasTerm(c.low, c.toks, g[j])) {
                                        hit++;
                                        syn += gw[gi];
                                        if (gw[gi] > mx) { mx = gw[gi]; }
                                        break;
                                    }
                                }
                            });
                            /* 保守口径，宁可漏不可滥：
                               路线 A —— 命中了一个只出现在 ≤2 条里的「专名」
                                         （公司名 / 船型代号 / 项目名），最可靠；
                               路线 B —— 两条以上同义线索同时命中，且其中至少一条是
                                         高辨别力的（如「散货船」只命中 4 条），
                                         总分也要够。两条都不满足就宁可不标。 */
                            var okA = (rare >= 1 && sc >= 1.2);
                            var okB = (hit >= 2 && syn >= 5.0 && mx >= 2.8);
                            if (okA || okB) {
                                scored.push({ i: idx, s: sc + syn });
                            }
                        });
                        if (!scored.length) { return; }
                        scored.sort(function (x, y) { return y.s - x.s; });

                        var keep = [scored[0]];
                        if (scored[1] && scored[0].s >= 3.0 && scored[1].s >= scored[0].s * 0.7) {
                            keep.push(scored[1]);
                        }
                        keep.forEach(function (k) {
                            var el = corpus[k.i].el;
                            var a = document.createElement('a');
                            a.className = 'cite-ref cite-auto';
                            a.setAttribute('href', '#' + el.id);
                            a.setAttribute('data-target', el.id);
                            a.setAttribute('data-n', String(el.getAttribute('data-cite') || ''));
                            a.setAttribute('title', '自动匹配：AI 未标注，按专名 / 同义词推断，仅供参考');
                            a.textContent = '#' + (el.getAttribute('data-cite') || '');
                            a.addEventListener('click', function (ev) { ev.preventDefault(); flash(el); });
                            b.appendChild(a);
                        });
                    });
                }

                if (document.readyState === 'loading') {
                    document.addEventListener('DOMContentLoaded', run);
                } else {
                    run();
                }
            })();
'''

K_JS_NEW = K_JS_CODE + K_JS_ANCHOR


def patch_citation(root, log):
    """★补丁K：AI 正文 ↔ RSS 条目交叉引用（看 AI 分析时能定位到对应 RSS）。

    四块替换，各自独立判定；[F] 未打时自动跳过 ②。
    """
    # ---------- ① 提示词侧：给每条 RSS 行加编号 ----------
    ai_path = os.path.join(root, "trendradar", "ai", "analyzer.py")
    if not os.path.exists(ai_path):
        log.append("  ✗ 找不到 trendradar/ai/analyzer.py，跳过 [K]①")
    else:
        text = read(ai_path)
        if MARK_K in text:
            log.append("  = [K]① ai/analyzer.py 已有标记，跳过")
        else:
            new_text, ok = replace_once(
                text, K_AI_ANCHOR, K_AI_NEW,
                "[K]① RSS 行加行首编号（AI 可回引）", log)
            if ok:
                write(ai_path, new_text)

    # ---------- ② 正文渲染：引用标记 → 可点击徽标 ----------
    fmt_path = os.path.join(root, "trendradar", "ai", "formatter.py")
    if not os.path.exists(fmt_path):
        log.append("  ✗ 找不到 trendradar/ai/formatter.py，跳过 [K]②")
    else:
        text = read(fmt_path)
        if MARK_K in text:
            log.append("  = [K]② ai/formatter.py 已有标记，跳过")
        elif "def _md_inline_html" not in text:
            log.append("  ✗ [K]② 需要先打 [F]（未找到 _md_inline_html），已跳过")
        else:
            t1, ok1 = replace_once(
                text, K_FMT_FN_ANCHOR, K_CITE_FN + K_FMT_FN_ANCHOR,
                "[K]② formatter.py 注入引用徽标渲染函数", log)
            t2, ok2 = replace_once(
                t1, K_FMT_CALL_ANCHOR, K_FMT_CALL_NEW,
                "[K]② 行内渲染接上引用徽标", log)
            if ok1 and ok2:
                write(fmt_path, t2)
            else:
                log.append("  ⚠ [K]② 有锚点未命中，为免半改，formatter.py 未写入")

    # ---------- ③④ report/html.py：条目编号 + 样式 + JS ----------
    path = os.path.join(root, "trendradar", "report", "html.py")
    if not os.path.exists(path):
        log.append("  ✗ 找不到 trendradar/report/html.py，跳过 [K]③④")
        return
    text = read(path)
    if MARK_K in text:
        log.append("  = [K]③④ report/html.py 已有标记，跳过")
        return

    pairs = [
        (K_SIG_ANCHOR,   K_SIG_NEW,     "[K]③ RSS 渲染函数加 id_prefix 参数"),
        (K_LOOP_ANCHOR,  K_LOOP_NEW,    "[K]④ 条目序号计数器（跨分组）"),
        (K_ITEM_ANCHOR,  K_ITEM_NEW,    "[K]⑤ rss-item 加 id / data-cite"),
        (K_META_ANCHOR,  K_META_NEW,    "[K]⑥ 条目显示编号徽标 #N"),
        (K_CALL_ANCHOR,  K_CALL_NEW,    "[K]⑦ 新增区不加编号（避免重复）"),
        (K_CSS_ANCHOR,   K_CSS_ANCHOR + K_CSS_BLOCK,        "[K]⑧ 交叉引用样式（亮色）"),
        (K_CSS_DARK_ANCHOR, K_CSS_DARK_ANCHOR + K_CSS_DARK_BLOCK, "[K]⑨ 交叉引用样式（深色）"),
        (K_JS_ANCHOR,    K_JS_NEW,      "[K]⑩ 跳转 / 越界标灰 / 反向索引 / 自动兜底"),
    ]
    ok_all = True
    for anchor, new, label in pairs:
        text, ok = replace_once(text, anchor, new, label, log)
        ok_all = ok_all and ok

    if ok_all:
        write(path, text)
    else:
        log.append("  ⚠ [K] 有锚点未命中，为免半改，本次未写入（原文件保持不变）")


def patch_search_synonyms(root, log):
    """★补丁J：报告搜索加「中英同义词别名表」。

    用户搜「氨动力散货船」0 命中。实测该词全页出现 10 处，**全部在 AI 双周报**
    （AI 把英文新闻译成中文后的概括用词），而 RSS 原标题是英文
    （ammonia-powered bulker / dry bulk carrier）——搜索是纯子串匹配、不做翻译，
    中文词必然搜不到。

    补法：在 [I] 的 handleSearch 里插一张「同义簇」表（中文词与英文词同组），
    查询词命中任一成员就把整组词一起拿去检索；高亮 / 计数 / 跳转行为一律不变。
    五处替换，必须全部命中才写入，避免出现「半改」的不一致状态。

    ⚠️ 依赖 [I]：锚点全部落在 [I] 重写后的 handleSearch 里，未打 [I] 时自动跳过。
    """
    path = os.path.join(root, "trendradar", "report", "html.py")
    if not os.path.exists(path):
        log.append("  ✗ 找不到 trendradar/report/html.py，跳过 [J]")
        return
    text = read(path)
    if MARK_J in text:
        log.append("  = [J] 搜索同义词：已打过，跳过")
        return
    if MARK_I not in text:
        log.append("  ✗ [J] 需要先打 [I]（未找到 ★补丁I 签名），已跳过")
        return

    pairs = [
        (J_TABLE_ANCHOR, J_TABLE_ANCHOR + J_SYN_TABLE, "[J]⑪ 插入中英同义词别名表 + 匹配函数"),
        (J_TERMS_ANCHOR, J_TERMS_NEW,                  "[J]⑫ 查询词展开成检索词表"),
        (J_NEWS_ANCHOR,  J_NEWS_NEW,                   "[J]⑬ 新闻条目按同义词匹配"),
        (J_RSS_ANCHOR,   J_RSS_NEW,                    "[J]⑭ RSS 条目按同义词匹配"),
        (J_HINT_ANCHOR,  J_HINT_NEW,                   "[J]⑮ 命中提示带上同义词文案"),
    ]
    ok_all = True
    for anchor, new, label in pairs:
        text, ok = replace_once(text, anchor, new, label, log)
        ok_all = ok_all and ok

    if ok_all:
        write(path, text)
    else:
        log.append("  ⚠ [J] 有锚点未命中，为免半改，本次未写入（原文件保持不变）")


def patch_search_feedback(root, log):
    """★补丁I：给报告搜索框加「看得见的反馈」。

    四处替换（亮色 CSS / 深色 CSS / 搜索栏 HTML / handleSearch JS），
    必须全部命中才写入，避免出现「半改」的不一致状态。
    """
    path = os.path.join(root, "trendradar", "report", "html.py")
    if not os.path.exists(path):
        log.append("  ✗ 找不到 trendradar/report/html.py，跳过 [I]")
        return
    text = read(path)
    if MARK_I in text:
        log.append("  = [I] 搜索反馈：已打过，跳过")
        return

    pairs = [
        (I_CSS_ANCHOR,      I_CSS_ANCHOR + I_CSS_BLOCK,  "[I]⑦ 搜索反馈样式（亮色）"),
        (I_CSS_DARK_ANCHOR, I_CSS_DARK_ANCHOR + I_CSS_DARK_BLOCK, "[I]⑧ 搜索反馈样式（深色）"),
        (I_HTML_ANCHOR,     I_HTML_NEW,                   "[I]⑨ 搜索栏加命中提示容器"),
        (I_JS_ANCHOR,       I_JS_NEW,                     "[I]⑩ handleSearch 加反馈逻辑"),
    ]
    ok_all = True
    for anchor, new, label in pairs:
        text, ok = replace_once(text, anchor, new, label, log)
        ok_all = ok_all and ok

    if ok_all:
        write(path, text)
    else:
        log.append("  ⚠ [I] 有锚点未命中，为免半改，本次未写入（原文件保持不变）")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    root = os.path.abspath(root)
    if not os.path.exists(os.path.join(root, "trendradar")):
        print("✗ 目录不像 TrendRadar 项目（缺少 trendradar/ 子目录）: %s" % root)
        print("  用法: python apply_patches.py /path/to/TrendRadar-master")
        return 1

    print("=" * 60)
    print("TrendRadar 补丁  →  项目根目录: %s" % root)
    print("=" * 60)

    log = []
    print("\n[A][B] AI 客户端 (trendradar/ai/client.py)")
    patch_ai_client(root, log)
    print("\n[C] RSS 请求头 (crawler/rss)")
    patch_rss_ua(root, log)
    print("\n[D] AI 分析板块标题 (trendradar/ai/formatter.py)")
    patch_section_titles(root, log)
    print("\n[F] AI 正文 Markdown 渲染 + 报告样式")
    patch_md_rendering(root, log)
    print("\n[E] SMTP 登录名可配置 (trendradar/notification/senders.py)")
    patch_smtp_login(root, log)
    print("\n[G] RSS 摘要带进 AI 提示词 (trendradar/core/analyzer.py + ai/analyzer.py)")
    patch_rss_summary(root, log)
    print("\n[H] 报告信息卡适配纯 RSS (trendradar/report/html.py)")
    patch_report_infocard(root, log)
    print("\n[I] 报告搜索框加可见反馈 (trendradar/report/html.py)")
    patch_search_feedback(root, log)
    print("\n[J] 搜索中英同义词别名表 (trendradar/report/html.py，需先打 [I])")
    patch_search_synonyms(root, log)
    print("\n[K] AI 正文 ↔ RSS 条目交叉引用 (ai/analyzer.py + ai/formatter.py + report/html.py)")
    patch_citation(root, log)

    print()
    for line in log:
        print(line)

    # 语法自检
    print("\n语法检查:")
    ok = True
    for rel in ("trendradar/ai/client.py",
                "trendradar/ai/formatter.py",
                "trendradar/ai/analyzer.py",
                "trendradar/core/analyzer.py",
                "trendradar/report/html.py",
                "trendradar/notification/senders.py",
                "trendradar/crawler/rss/fetcher.py",
                "trendradar/crawler/rss/parser.py"):
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            continue
        try:
            compile(read(p), p, "exec")
            print("  ✓ %s" % rel)
        except SyntaxError as e:
            ok = False
            print("  ✗ %s\n%s" % (rel, e))
    print("\n完成。" if ok else "\n有文件语法异常，请检查。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

