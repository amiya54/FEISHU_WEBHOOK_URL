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

包含六个补丁：

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

    print()
    for line in log:
        print(line)

    # 语法自检
    print("\n语法检查:")
    ok = True
    for rel in ("trendradar/ai/client.py",
                "trendradar/ai/formatter.py",
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

