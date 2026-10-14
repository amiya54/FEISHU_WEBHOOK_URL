#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TrendRadar 船舶低碳推送 —— 源码补丁脚本（幂等，可重复执行）

用法（在 TrendRadar 项目根目录执行）：
    python apply_patches.py                # 自动定位当前目录
    python apply_patches.py /path/to/TrendRadar-master

包含四个补丁：

  [D] AI 分析板块标题改为「船舶低碳技术研发」场景措辞
      板块标题（核心热点态势 / 舆论风向争议 / 异动与弱信号 / RSS 深度洞察 /
      研判策略建议）是**硬编码在 trendradar/ai/formatter.py 里的**，
      config.yaml 没有任何字段可以覆盖。不改代码，推送里就一直是
      「舆论风向争议」这种对技术研发没有意义的标题。
      本补丁把 5 个渲染器（企业微信/飞书共用 markdown、钉钉、纯文本、
      Telegram、HTML 报告）里的标题一并替换为：
          核心热点态势   → 今日技术主线
          舆论风向争议   → 技术路线与分歧
          异动与弱信号   → 弱信号与风向标
          RSS 深度洞察   → 关键参数与硬数据
          研判策略建议   → 研发启示
          头部 AI 热点分析 → AI 低碳技术情报
      需配合 config/ai_analysis_prompt.txt（v2.0.0-c）一起使用。

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

注意：程序自带版本检查只对 config/ 下的配置文件做「只读」比对，不覆盖源码；
但**升级程序（重新下载 master）会覆盖以上改动**，届时重跑本脚本即可。
"""

import io
import os
import sys

UA_OLD_1 = '"User-Agent": "TrendRadar/2.0 RSS Reader (https://github.com/trendradar)"'
UA_OLD_2 = '"User-Agent": "TrendRadar/2.0 RSS Reader"'
UA_NEW = ('"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
          'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"')

MARK_A = "★补丁A"
MARK_B = "★补丁B"
MARK_D = "★补丁D"

# [D] 板块标题映射：原词 -> 新词
#     这些字符串在 formatter.py 中只作为板块标题出现（各 5 处，分别对应
#     markdown / 钉钉 / 纯文本 / Telegram / HTML 五个渲染器），可安全全量替换。
TITLE_MAP = [
    ("✨ AI 热点分析", "✨ AI 低碳技术情报"),
    ("核心热点态势", "今日技术主线"),
    ("舆论风向争议", "技术路线与分歧"),
    ("异动与弱信号", "弱信号与风向标"),
    ("RSS 深度洞察", "关键参数与硬数据"),
    ("研判策略建议", "研发启示"),
]


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
    """[D] 把 AI 分析板块标题改为船舶低碳技术研发场景措辞"""
    path = os.path.join(root, "trendradar", "ai", "formatter.py")
    if not os.path.exists(path):
        log.append("  ✗ 找不到 trendradar/ai/formatter.py，跳过 [D]")
        return
    text = read(path)

    if MARK_D in text:
        log.append("  = [D] 板块标题改名：已打过，跳过")
        return

    # 先检查是否已经是新标题（防止用户手工改过或补丁标记被清）
    if "今日技术主线" in text and "研发启示" in text:
        log.append("  = [D] 板块标题改名：已是新标题，跳过")
        return

    changed = []
    for old, new in TITLE_MAP:
        n = text.count(old)
        if n == 0:
            log.append("    · 「%s」未找到（可能程序版本不同）" % old)
            continue
        if new in text:
            log.append("    · 「%s」→「%s」：目标词已存在，跳过以免重复替换" % (old, new))
            continue
        text = text.replace(old, new)
        changed.append((old, new, n))

    if changed:
        # 插入补丁标记，便于幂等判断
        anchor = "def _escape_html(text: str) -> str:"
        marker = (
            "# %s：AI 分析板块标题已改为「船舶低碳技术研发」场景措辞\n"
            "#   配合 config/ai_analysis_prompt.txt 使用；重跑本脚本可幂等跳过。\n"
            "#   如需改回原版，删除本行并将其下方 TITLE_MAP 中的替换手动回退即可。\n"
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

    print()
    for line in log:
        print(line)

    # 语法自检
    print("\n语法检查:")
    ok = True
    for rel in ("trendradar/ai/client.py",
                "trendradar/ai/formatter.py",
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
