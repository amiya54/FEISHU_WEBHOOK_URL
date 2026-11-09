<div align="center" id="top">

# 船舶低碳情报双周报

**面向船厂技术中心的替代燃料 / 减排规范动态监控** —— 自动抓取 · AI 研判 · 双周推送 · 网页归档

[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-全自动运行-2088FF?style=flat-square&logo=github-actions)](https://github.com/amiya54/FEISHU_WEBHOOK_URL/actions)
[![GitHub Pages](https://img.shields.io/badge/GitHub_Pages-网页版报告-4285F4?style=flat-square&logo=github)](https://amiya54.github.io/FEISHU_WEBHOOK_URL/)
[![RSS](https://img.shields.io/badge/RSS-30%2B订阅源-orange?style=flat-square&logo=rss)](#数据源)
[![AI](https://img.shields.io/badge/AI-双周研判与交叉引用-FF6B6B?style=flat-square&logo=openai)](#核心功能)

</div>

<br>

## 这是什么

一条为**船舶低碳赛道**定制的情报流水线：每期自动从 30+ 个公开 RSS 源抓取与替代燃料（LNG / 甲醇 / 氨 / 氢 / 生物燃料 / 乙醇）、减排规范（IMO / EU / 船级社）相关的新闻，经 AI 分级研判生成中文双周报，推送到企业微信并在 GitHub Pages 归档成网页。

- **双周节奏**：北京时间每周五 08:00 自动发布（隔周一期）
- **零成本运行**：全部跑在 GitHub Actions 免费额度内
- **纯公开信息**：只抓 RSS 公开源，不依赖任何内部数据

## 核心功能

| 功能 | 说明 |
|---|---|
| 中文双周报 | AI 将英文新闻研判、翻译、归纳为按板块组织的中文报告 |
| 交叉引用 | AI 正文中的（#N）可点击跳转到对应原始新闻，被引条目可反向跳回 |
| 跨期跟踪 | 重要事件跨期追踪时间线，连续 2 期无后续自动结案 |
| 数据瘦身 | 同事件多源合并、已刊出的法规旧文自动降重、单源配额上限 |
| 搜索同义词 | 报告内搜索支持中英同义词簇（如「氨动力」↔ ammonia-fueled） |
| 乙醇识别 | 词表用正则卡词边界，甲醇(methanol)不会误判成乙醇(ethanol) |
| 网页归档 | 每期报告存档于 GitHub Pages，支持宽屏 / 深色模式 / 导出 |

## 数据源

覆盖 IMO / EU 官方、五家船级社（CCS / DNV / ABS / LR / BV）、行业媒体（Offshore Energy / Safety4Sea / Manifold Times 等）与中文航运媒体，源清单见 `config/config.yaml` 的 `rss` 段；抓取词表见 `config/frequency_words.txt`。

## 运行机制

```
crawler.yml（爬虫，双周五 00:00 UTC）
  ├─ RSS 抓取 → 词表过滤 → 数据瘦身（补丁L）
  ├─ AI 研判（中文双周报正文 + 交叉引用）
  └─ report/html.py 渲染 → GitHub Pages 发布 + 企业微信推送

clean-crawler.yml（签到，周三/周六 05:00 北京时间）
  └─ 清空运行历史，重置上游试用期计时（防 7 天熔断）
```

仓库根目录的 `apply_patches.py` 是**定制补丁集**（[A]–[M]，共 13 个）：上游升级后重新下载源码，运行 `python apply_patches.py` 一键重打全部补丁（含语法自检与幂等跳过）。

## 网页版

最新一期：<https://amiya54.github.io/FEISHU_WEBHOOK_URL/>

支持：关键词搜索（含中英同义词）、宽屏 / 深色切换、导出 PNG / Markdown、AI 正文 ↔ 原文双向跳转、跨期跟踪时间线。

## 目录结构

```
├── config/
│   ├── config.yaml              # RSS 源、推送通道、运行参数
│   ├── frequency_words.txt      # 抓取词表（含乙醇正则条目）
│   └── ai_analysis_prompt.txt   # AI 研判提示词（v3.3+，含引用规范）
├── patches/
│   └── apply_patches.py         # 定制补丁集 [A]–[M]
├── scripts/
│   └── archive_and_track.py     # 过刊归档 + 跨期跟踪 + 观察池结案
└── .github/workflows/           # crawler.yml（爬虫）/ clean-crawler.yml（签到）
```

## 致谢与许可

本项目基于开源项目 [sansan0/TrendRadar](https://github.com/sansan0/TrendRadar)（GPL-3.0）深度定制：替换了抓取源、词表、AI 提示词与报告渲染，并叠加了十余项针对性补丁。原框架的部署与推送机制功不可没，相关改动同样以 GPL-3.0 开放。
