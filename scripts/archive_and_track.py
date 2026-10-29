#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨期跟踪 + 过刊归档（TrendRadar 报告后处理）

解决两个结构性问题：
  1. 每期报告覆盖上一期，没有过刊库 —— 编号每期重排，跨期无法互引。
  2. 双周报只会说「这两周发生了什么」，不会说「上期提的那件事现在怎么样了」。

做法（不改 TrendRadar 源码，只在生成好的 index.html 上做后处理）：
  · 解析报告里的 rss-N 条目，聚成「事件」（同一新闻多源分发会被并成一条）
  · 与上一期的事件做跨期匹配，判断状态变化：已落地 / 规则落地 / 有新进展 / 仍在观察
  · 在 AI 正文之前插入一块「跨期跟踪」表（默认展开，可折叠）
  · 把本期报告另存为 archive/issues/<日期>.html，并生成 archive/index.html 过刊目录
  · 台账 archive/ledger.json 只存「每期事件」，观察池由台账现算
    —— 这样同一天重跑会覆盖而非累积，脚本天然幂等

用法：
    python scripts/archive_and_track.py --report index.html --archive archive
    python scripts/archive_and_track.py --report index.html --archive archive --date 2026-10-30
    python scripts/archive_and_track.py --report index.html --dry-run   # 只打印，不落盘

退出码永远是 0：归档失败不应该阻断报告发布。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from html import escape as esc
from html import unescape
from pathlib import Path

MARK_S = "<!--TRACK:START-->"
MARK_E = "<!--TRACK:END-->"
CSS_S = "<!--TRACK:CSS:START-->"
CSS_E = "<!--TRACK:CSS:END-->"

CST = timezone(timedelta(hours=8))

# ── 词法 ─────────────────────────────────────────────────────────────
STOP = set(
    """the a an and or of for to in on at by with from as is are was were be been
    new first world global its it this that these those has have had will would can
    could after before over under into out up down more most less least than then
    about says said amid via per amid among across""".split()
)

CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
WORD_RE = re.compile(r"[a-z][a-z0-9'’.]*")
# 只认「高辨识度」实体：全大写缩写、含数字/点/& 的写法、书名号里的文件号
ENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9&.\-]*[0-9&.\-][A-Za-z0-9&.\-]*|[A-Z]{3,}[0-9]*")
Q_RE = re.compile(r"[《【]([^》】]{2,40})[》】]")
CN_ORGS = ("中国船级社", "海事局", "交通运输部", "国际海事组织", "欧盟", "工信部", "国务院")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def tokens(text: str) -> set:
    """英文按词（连字符已由正则当分隔符）；中文按二元组。"""
    t = norm(text).lower()
    out = set()
    for run in CJK_RE.findall(t):
        if len(run) == 1:
            out.add(run)
        for i in range(len(run) - 1):
            out.add(run[i : i + 2])
    for w in WORD_RE.findall(t):
        w = w.strip(".'’")
        if len(w) >= 3 and w not in STOP:
            out.add(w)
    return out


def entities(text: str) -> set:
    t = norm(text)
    out = set()
    for m in ENT_RE.findall(t):
        m = m.strip(".-")
        if len(m) >= 2 and m.lower() not in STOP:
            out.add(m.lower())
    for m in Q_RE.findall(t):
        out.add(m.strip().lower())
    for kw in CN_ORGS:
        if kw in t:
            out.add(kw)
    return out


def jac(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / float(len(a | b))


# ── 阶段判定（顺序有意义：越靠前越"成熟"） ────────────────────────
STAGE_RULES = [
    (
        "testing",
        ["trial", "test", "pilot", "demonstrat", "prototype", "试航", "试验",
         "示范", "海试"],
    ),
    (
        "operating",
        ["deliver", "in service", "into service", "enters service", "commercial service",
         "in operation", "commission", "maiden", "operat", "complet", "sails", "voyage",
         "launch", "handover", "start", "begins", "commence",
         "交付", "投运", "首航", "营运", "运营", "完成", "加注",
         "下水", "接船", "首艘", "投产", "开工"],
    ),
    (
        "policy",
        ["into force", "amend", "regulation", "rule", "requir", "approv",
         "mandat", "guideline", "standard", "circular", "生效", "规则", "修正案",
         "规范", "强制", "指南", "标准", "公告", "通知"],
    ),
    (
        "planned",
        ["plan", "order", "contract", "sign", "agree", "propos", "draft",
         "consult", "intend", "will ", "to be ", "mou", "partnership", "study",
         "select", "拟", "计划", "征求意见", "签署", "订单", "协议", "备忘录",
         "合作", "探索", "研究", "选型", "立项"],
    ),
]

STAGE_CN = {
    "planned": "计划/订单",
    "testing": "试验/试航",
    "policy": "规则/政策",
    "operating": "交付/营运",
}
STATUS_CN = {
    "done": "已落地",
    "policy": "规则落地",
    "progress": "有新进展",
    "watching": "未见后续",
    "new": "新增观察",
}
STATUS_ORDER = {"done": 0, "policy": 1, "progress": 2, "watching": 3, "new": 4}


ROUNDUP_WORDS = ("roundup", "round-up", "week in review", "weekly", "this week",
                 "盘点", "一览", "周报", "汇总", "速览")


def is_roundup(title: str) -> bool:
    t = norm(title).lower()
    return any(w in t for w in ROUNDUP_WORDS)


def stage_of(title: str) -> str:
    t = norm(title).lower()
    for name, kws in STAGE_RULES:
        for kw in kws:
            if kw.isascii():
                # 词首边界：避免 latest 命中 test、operating 之外的误伤
                if re.search(r"(?<![a-z])" + re.escape(kw), t):
                    return name
            elif kw in t:
                return name
    return "other"


def transition(prev_stage: str, cur_stage: str) -> str:
    """返回 done / policy / progress。规则保守：只在明确的阶段跃迁时升级。"""
    if cur_stage == "operating" and prev_stage in ("planned", "testing"):
        return "done"
    if prev_stage in ("planned", "testing") and cur_stage == "policy":
        return "policy"
    if cur_stage == "operating" and prev_stage != "operating":
        return "done"
    return "progress"


# ── 解析报告 ────────────────────────────────────────────────────────
def parse_items(doc: str):
    """抽出主区编号条目（id="rss-N"）。新增区没有编号，不参与跟踪。"""
    marks = list(re.finditer(r'<div class="rss-item"[^>]*\bid="rss-(\d+)"', doc))
    items = []
    for idx, m in enumerate(marks):
        end = marks[idx + 1].start() if idx + 1 < len(marks) else min(len(doc), m.start() + 8000)
        seg = doc[m.start() : end]

        title, url = "", ""
        tm = re.search(r'<div class="rss-title"[^>]*>(.*?)</div>', seg, re.S)
        if tm:
            inner = tm.group(1)
            um = re.search(r'href="([^"]+)"', inner)
            if um:
                url = unescape(um.group(1))
            title = norm(re.sub(r"<[^>]+>", "", inner))

        src = ""
        for sm in re.finditer(r'<span class="rss-author"[^>]*>(.*?)</span>', seg, re.S):
            val = norm(re.sub(r"<[^>]+>", "", sm.group(1)))
            if val and val.upper() != "NEW":
                src = val
                break

        if title:
            items.append(
                {"cite": int(m.group(1)), "title": title, "url": url, "src": src}
            )
    return items


def cluster(items, thr: float = 0.62):
    """把同一事件的多源报道并成一条（并查集）。"""
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    toks = [tokens(i["title"]) for i in items]
    for a in range(n):
        for b in range(a + 1, n):
            if items[a]["url"] and items[a]["url"] == items[b]["url"]:
                union(a, b)
                continue
            if jac(toks[a], toks[b]) >= thr:
                union(a, b)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)

    events = []
    for root in sorted(groups):
        members = [items[i] for i in groups[root]]
        rep = max(members, key=lambda x: len(tokens(x["title"])))
        events.append(
            {
                "cite": rep["cite"],
                "cites": [x["cite"] for x in members],
                "title": rep["title"],
                "url": rep["url"] or next((x["url"] for x in members if x["url"]), ""),
                "src": rep["src"],
                "srcs": sorted({x["src"] for x in members if x["src"]}),
                "stage": stage_of(rep["title"]),
            }
        )
    return events


# ── 台账 ────────────────────────────────────────────────────────────
def load_ledger(path: Path):
    if not path.exists():
        return {"version": 1, "issues": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "issues" not in data:
            raise ValueError("结构不符")
        return data
    except Exception as e:
        print("[track] ⚠ 台账读取失败，按首期处理：%s" % e)
        return {"version": 1, "issues": []}


def match_score(a_title: str, a_url: str, b_title: str, b_url: str):
    """返回 (score, tier)。tier: 'strong' 可直接判定阶段跃迁；'weak' 只算「有新进展」。"""
    if a_url and a_url == b_url:
        return 1.0, "strong"
    ta, tb = tokens(a_title), tokens(b_title)
    inter = len(ta & tb)
    if not inter:
        return 0.0, ""
    jt = inter / float(len(ta | tb))
    je = jac(entities(a_title), entities(b_title))
    score = 0.6 * jt + 0.2 * (inter / float(min(len(ta), len(tb)))) + 0.2 * je
    if jt >= 0.36 or (jt >= 0.24 and je >= 0.30):
        return score, "strong"
    if inter >= 3 and inter / float(min(len(ta), len(tb))) >= 0.42:
        return score, "weak"
    return score, ""


# 连续多少期「没有相关报道」后停止跟踪（结案）。
# 不结案的话观察池只进不出：每期新增 3~6 项、永不退出，
# 半年后跟踪表会长到没人看。结案只是不再展示，台账里记录还在。
MISS_LIMIT = 2


def consecutive_misses(ev, from_date: str, issues) -> int:
    """事件在 from_date 期之后，连续有多少期没出现相关报道。

    「出现」的判定刻意宽松（标题 jaccard >= 0.5）——
    误判成「有消息」的代价是晚 1 期结案，误判成「没消息」的代价是漏掉真进展。
    中间只要有一期匹配上就清零重计。
    """
    key = tokens(ev.get("title", ""))
    if not key:
        return 0
    miss = 0
    for issue in issues:
        if issue.get("date", "") <= from_date:
            continue
        hit = any(
            jac(key, tokens(x.get("title", ""))) >= 0.5
            for x in issue.get("events", [])
        )
        miss = 0 if hit else miss + 1
    return miss


def build_tracking(cur_events, prev_issues, today, max_new=3, max_rows=8):
    """返回 (rows, stats)。rows 每项：dict(status, cur, prev, prev_date, tracked)。"""
    # 候选：往期处于 planned / testing 的事件（这些才「值得期待后续」）
    closed = 0
    candidates = []
    seen_titles = set()
    for issue in reversed(prev_issues[-3:]):
        for ev in issue.get("events", []):
            if ev.get("stage") not in ("planned", "testing"):
                continue
            if is_roundup(ev.get("title", "")):
                continue
            # 连续 2 期无相关报道 → 结案，不再进跟踪表（台账里仍保留）
            if consecutive_misses(ev, issue.get("date", ""), prev_issues) >= MISS_LIMIT:
                closed += 1
                continue
            key = norm(ev.get("title", "")).lower()
            if not key or key in seen_titles:
                continue
            seen_titles.add(key)
            candidates.append({"ev": ev, "date": issue.get("date", "")})

    # 先算全部候选对，再按分数从高到低做一对一分配 ——
    # 避免两条上期事项抢同一条本期报道（会把无关的两件事都标成「有进展」）
    pairs = []
    for ci, cand in enumerate(candidates):
        ev = cand["ev"]
        for cur in cur_events:
            sc, tier = match_score(ev.get("title", ""), ev.get("url", ""),
                                   cur["title"], cur.get("url", ""))
            if tier:
                pairs.append((sc, tier, ci, cur))
    pairs.sort(key=lambda x: -x[0])

    assigned, used_cur = {}, set()
    for sc, tier, ci, cur in pairs:
        if ci in assigned or cur["cite"] in used_cur:
            continue
        assigned[ci] = (cur, tier)
        used_cur.add(cur["cite"])

    rows = []
    for ci, cand in enumerate(candidates):
        ev = cand["ev"]
        if ci in assigned:
            best, best_tier = assigned[ci]
            st = transition(ev.get("stage", ""), best["stage"])
            # 证据只到「弱相关」时，不下「已落地 / 规则落地」这种强结论
            if best_tier == "weak" and st in ("done", "policy"):
                st = "progress"
            rows.append(
                {
                    "status": st,
                    "cur": best,
                    "prev": ev,
                    "prev_date": cand["date"],
                    "tracked": 1,
                }
            )
        else:
            rows.append(
                {
                    "status": "watching",
                    "cur": None,
                    "prev": ev,
                    "prev_date": cand["date"],
                    "tracked": 1,
                }
            )

    # 「仍在观察」按时间排序并带上跟踪期数（同一事件在往期也出现过则累加）
    for row in rows:
        if row["status"] != "watching":
            continue
        key_t = tokens(row["prev"].get("title", ""))
        n = 0
        for issue in prev_issues[-4:]:
            for ev in issue.get("events", []):
                if ev.get("stage") in ("planned", "testing") and jac(
                    key_t, tokens(ev.get("title", ""))
                ) >= 0.55:
                    n += 1
                    break
        row["tracked"] = max(1, n)

    rows.sort(
        key=lambda r: (
            STATUS_ORDER[r["status"]],
            -r["tracked"],
            -(r["cur"]["cite"] if r["cur"] else r["prev"].get("cite", 0)),
        )
    )

    # 本期新出现的「计划/试验」类事件 —— 下期起就是它们被跟踪
    used = set()
    for r in rows:
        if r["cur"]:
            used.update(r["cur"].get("cites") or [r["cur"]["cite"]])
        used.add(r["prev"].get("cite"))
    fresh = [
        {
            "status": "new",
            "cur": ev,
            "prev": ev,
            "prev_date": today,
            "tracked": 0,
        }
        for ev in cur_events
        if ev["stage"] in ("planned", "testing")
        and ev["cite"] not in used
        and not is_roundup(ev["title"])
    ]
    fresh.sort(key=lambda r: -len(tokens(r["prev"]["title"])))

    # 统计按「全部候选」算，展示再按状态配额截断 ——
    # 否则「已落地」一多就把「未见后续」全挤掉，摘要数字也会跟着缩水
    stats = {k: sum(1 for r in rows if r["status"] == k) for k in STATUS_ORDER}
    stats["pool"] = sum(1 for ev in cur_events if ev["stage"] in ("planned", "testing"))
    stats["closed"] = closed

    caps = {"done": 4, "policy": 2, "progress": 2, "watching": 2}
    shown, used_n = [], {}
    for r in rows:
        st = r["status"]
        if used_n.get(st, 0) >= caps.get(st, 2):
            continue
        shown.append(r)
        used_n[st] = used_n.get(st, 0) + 1
        if len(shown) >= max_rows:
            break
    take = max(0, min(len(fresh), max_new, max_rows - len(shown)))
    shown = shown + fresh[:take]
    stats["new"] = take
    return shown, stats


# ── 渲染 ────────────────────────────────────────────────────────────
CSS_BLOCK = CSS_S + """
<style id="track-style">
/* ── 跨期跟踪（附录样式 · 2026-10-21 重做）────────────────────────
   旧版是 4 列硬表格（事项 / 上期 / 本期 / 依据），要塞进 8 行，
   读者看到的是「一堆短词 + 几个彩色小块」，说不出这件事到底怎么了。
   新版改成「一行一件事」的时间线卡片：
     左圆点 = 状态，标题占一行，下面一句「上期阶段 → 本期结果」，
     依据缩到右侧。扫一眼先看到彩色圆点分布，再逐条读变化。 */
.track-wrap{max-width:1120px;margin:0 auto;padding:6px 16px 46px}
.track-box{border:1px solid #e2e8f0;border-radius:14px;background:#fff;overflow:hidden;
box-shadow:0 1px 2px rgba(15,23,42,.04)}
.track-box>summary{list-style:none;cursor:pointer;display:flex;align-items:baseline;
flex-wrap:wrap;gap:4px 12px;padding:16px 20px 13px;border-bottom:1px solid #f1f5f9}
.track-box>summary::-webkit-details-marker{display:none}
.track-box>summary::before{content:"▸";color:#94a3b8;font-size:11px;margin-right:2px;
transition:transform .15s;display:inline-block}
.track-box[open]>summary::before{transform:rotate(90deg)}
.tk-eyebrow{font-size:11px;letter-spacing:.14em;color:#94a3b8;text-transform:uppercase}
.tk-h{font-size:15.5px;font-weight:600;color:#0f172a;letter-spacing:-.01em}
.tk-sub{font-size:12.5px;color:#64748b}
.tk-arch{margin-left:auto;font-size:12px;color:#2563eb;text-decoration:none;
border-bottom:1px dashed #bfdbfe;white-space:nowrap;align-self:center}
.tk-arch:hover{border-bottom-color:#2563eb}

/* 摘要计数条：先给「结果分布」，再给明细 */
.tk-chips{display:flex;flex-wrap:wrap;gap:8px;padding:13px 20px;background:#fafbfc;
border-bottom:1px solid #f1f5f9}
.tk-chip{display:inline-flex;align-items:center;gap:6px;padding:5px 11px;border-radius:999px;
font-size:12px;color:#475569;background:#fff;border:1px solid #e2e8f0;white-space:nowrap}
.tk-chip b{font-size:14px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1}
.tk-chip i{width:7px;height:7px;border-radius:50%;display:inline-block}
.c-done b{color:#059669}
.c-done i{background:#059669}
.c-policy b{color:#2563eb}.c-policy i{background:#2563eb}
.c-progress b{color:#d97706}.c-progress i{background:#d97706}
.c-watching b{color:#94a3b8}.c-watching i{background:#cbd5e1}
.c-closed b{color:#94a3b8}.c-closed i{background:#64748b}
.c-new b{color:#7c3aed}.c-new i{background:#a78bfa}

/* 明细：一行一件事 */
.tk-list{list-style:none;margin:0;padding:4px 0 6px}
.tk-row{display:flex;gap:12px;padding:13px 20px;border-top:1px solid #f5f7fa}
.tk-row:first-child{border-top:0}
.tk-row:hover{background:#fbfdff}
.tk-rail{flex:0 0 10px;display:flex;justify-content:center;padding-top:5px}
.tk-dot{width:9px;height:9px;border-radius:50%;display:block;box-shadow:0 0 0 3px rgba(148,163,184,.14)}
.d-done{background:#059669}
.d-policy{background:#2563eb}
.d-progress{background:#d97706}
.d-watching{background:#cbd5e1}
.d-new{background:#a78bfa}
.tk-body{flex:1;min-width:0}
.tk-line1{display:block;overflow:hidden}
.tk-tag{float:left;margin:2px 9px 0 0;font-size:11px;padding:1px 8px;border-radius:5px;line-height:1.7;
border:1px solid transparent;white-space:nowrap}
.t-done{background:#ecfdf5;color:#047857;border-color:#a7f3d0}
.t-policy{background:#eff6ff;color:#1d4ed8;border-color:#bfdbfe}
.t-progress{background:#fffbeb;color:#b45309;border-color:#fde68a}
.t-watching{background:#f8fafc;color:#64748b;border-color:#e2e8f0}
.t-new{background:#f5f3ff;color:#6d28d9;border-color:#ddd6fe}
.tk-name{display:block;color:#0f172a;font-size:13.5px;line-height:1.65;text-decoration:none;
display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
a.tk-name:hover{color:#1d4ed8;text-decoration:underline;text-underline-offset:2px}
.tk-line2{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-top:5px;
font-size:12px;color:#94a3b8}
.tk-from{color:#64748b}
.tk-ar{color:#cbd5e1;font-size:11px}
.tk-to{color:#334155;font-weight:500}
.tk-to.dim{color:#94a3b8;font-weight:400}
.tk-meta{margin-left:auto;display:inline-flex;align-items:center;gap:5px;white-space:nowrap}
.tk-ref{display:inline-block;padding:0 5px;border-radius:4px;background:#f1f5f9;color:#475569;
font-size:11px;text-decoration:none;border:1px solid #e2e8f0;line-height:1.5}
.tk-ref:hover{background:#e0e7ff;color:#3730a3;border-color:#c7d2fe}
.tk-note{padding:10px 20px 14px;font-size:11.5px;color:#94a3b8;line-height:1.75;
border-top:1px solid #f5f7fa}
@media(max-width:640px){
  .track-wrap{padding:4px 10px 34px}
  .tk-row{padding:12px 14px;gap:8px}
  .track-box>summary{padding:14px 14px 11px}
  .tk-chips{padding:11px 14px;gap:6px}
  .tk-meta{margin-left:0;width:100%}
  .tk-note{padding:9px 14px 12px}
}
.rss-item:target{background:#fff7ed;box-shadow:inset 3px 0 0 #f59e0b}
body.dark-mode .track-box{background:#1e293b;border-color:#334155}
body.dark-mode .track-box>summary{border-bottom-color:#334155}
body.dark-mode .tk-h,body.dark-mode .tk-name{color:#e2e8f0}
body.dark-mode .tk-eyebrow,body.dark-mode .tk-sub,body.dark-mode .tk-from,
body.dark-mode .tk-line2{color:#94a3b8}
body.dark-mode .tk-chips{background:#182234;border-bottom-color:#334155}
body.dark-mode .tk-chip{background:#1e293b;border-color:#334155;color:#cbd5e1}
body.dark-mode .tk-row{border-top-color:#334155}
body.dark-mode .tk-row:hover{background:#243244}
body.dark-mode .tk-to{color:#e2e8f0}
body.dark-mode .tk-to.dim{color:#94a3b8}
body.dark-mode .tk-ref{background:#334155;color:#cbd5e1;border-color:#475569}
body.dark-mode .tk-arch{color:#93c5fd;border-bottom-color:#1e40af}
body.dark-mode .t-done{background:#14532d;color:#bbf7d0;border-color:#166534}
body.dark-mode .t-policy{background:#1e3a8a;color:#dbeafe;border-color:#1e40af}
body.dark-mode .t-progress{background:#78350f;color:#fde68a;border-color:#92400e}
body.dark-mode .t-watching{background:#334155;color:#cbd5e1;border-color:#475569}
body.dark-mode .t-new{background:#3b0764;color:#ddd6fe;border-color:#6d28d9}
body.dark-mode .tk-note{color:#64748b;border-top-color:#334155}
body.dark-mode .d-watching{background:#475569}
body.dark-mode .rss-item:target{background:#422006;box-shadow:inset 3px 0 0 #f59e0b}
</style>
""" + CSS_E


def short(text: str, n: int = 62) -> str:
    text = norm(text)
    return text if len(text) <= n else text[: n - 1] + "…"


def render_box(rows, stats, prev_date, archive_href: str):
    """渲染「附录 · 跨期跟踪」。

    旧版是 4 列表格，信息密度高但没有叙事：读者看到「上期 10-16 / 计划/订单」
    这种碎片，得自己在脑子里拼「所以这件事到底怎么样了」。
    新版：顶部一句话结论 + 状态计数条 + 一行一件事（圆点=状态，
    标题一行，第二行写「上期阶段 → 本期结果」，依据缩到右侧）。
    """
    total = stats["done"] + stats["policy"] + stats["progress"] + stats["watching"]
    if prev_date is None:
        sub = "本期首次建立基线：%d 项计划 / 试验类事项进入观察池，下期起显示进展" % stats.get(
            "pool", stats["new"]
        )
    else:
        has_next = stats["done"] + stats["policy"] + stats["progress"]
        sub = "对照上期（%s）的 %d 项：%d 项有下文，%d 项本期未见后续" % (
            prev_date[5:], total, has_next, stats["watching"]
        )

    def chip(cls, n, label):
        if not n:
            return ""
        return '<span class="tk-chip %s"><i></i><b>%d</b>%s</span>' % (cls, n, label)

    chips = "".join(
        [
            chip("c-done", stats["done"], "已落地"),
            chip("c-policy", stats["policy"], "规则落地"),
            chip("c-progress", stats["progress"], "有新进展"),
            chip("c-watching", stats["watching"], "未见后续"),
            chip("c-closed", stats.get("closed", 0), "停止跟踪"),
            chip("c-new", stats["new"], "本期新增"),
        ]
    )

    items = []
    for r in rows:
        ev = r["prev"]
        cur = r["cur"]
        st = r["status"]

        title = esc(short(ev.get("title", ""), 78))
        if ev.get("url"):
            title = (
                '<a class="tk-name" href="%s" target="_blank" rel="noopener">%s</a>'
                % (esc(ev["url"]), title)
            )
        else:
            title = '<span class="tk-name">%s</span>' % title
        tag = '<span class="tk-tag t-%s">%s</span>' % (st, STATUS_CN[st])

        frm = STAGE_CN.get(ev.get("stage"), "其它")
        # 行首用具体日期（10-16）而不是笼统的「上期」：回溯多期时才分得清哪条来自哪期
        frm_label = "本期" if st == "new" else (r["prev_date"][5:] if r["prev_date"] else "往期")

        if st == "watching":
            arrow = '<span class="tk-ar">—</span>'
            to = '<span class="tk-to dim">本期没有相关报道</span>'
            # 上期编号只在上期那份文档里有效，不能拿本期 #N 顶替
            href = "archive/issues/%s.html#rss-%d" % (r["prev_date"], ev["cite"])
            meta = (
                '<span class="tk-meta">已跟踪 %d 期 · '
                '<a class="tk-ref" href="%s" title="跳到过刊里那一条">过刊 #%d</a></span>'
                % (r["tracked"], esc(href), ev["cite"])
            )
        elif st == "new":
            arrow = '<span class="tk-ar">—</span>'
            to = '<span class="tk-to dim">进入观察池</span>'
            meta = '<span class="tk-meta"><a class="tk-ref" href="#rss-%d">#%d</a></span>' % (
                ev["cite"], ev["cite"]
            )
        else:
            arrow = '<span class="tk-ar">→</span>'
            to_stage = STAGE_CN.get(cur.get("stage"), "其它")
            if to_stage == "其它":
                # 本期那条的措辞不属于四个阶段，硬写「其它」反而像漏填；
                # 说清「这条线动了，具体看依据」比一个占位词有用
                to_txt = "阶段有更新"
            elif to_stage != frm:
                to_txt = to_stage
            else:
                to_txt = "仍在%s阶段" % frm
            to = '<span class="tk-to">%s</span>' % esc(to_txt)
            refs = (cur.get("cites") or [cur["cite"]])[:4]
            meta = '<span class="tk-meta">依据 ' + "".join(
                '<a class="tk-ref" href="#rss-%d">#%d</a>' % (c, c) for c in refs
            ) + "</span>"

        items.append(
            '<li class="tk-row"><span class="tk-rail"><i class="tk-dot d-%s"></i></span>'
            '<div class="tk-body">'
            '<div class="tk-line1">%s%s</div>'
            '<div class="tk-line2"><span class="tk-from">%s · %s</span>%s%s%s</div>'
            "</div></li>" % (st, tag, title, frm_label, esc(frm), arrow, to, meta)
        )

    if items:
        body = '<ul class="tk-list">\n%s\n</ul>' % "\n".join(items)
    else:
        body = '<div class="tk-note">本期没有需要跟踪的后续事项。</div>'

    note = (
        '<div class="tk-note">「未见后续」只表示本期没抓到相关报道，不等于事情没进展。'
        "状态按条目措辞判定：计划 / 订单 → 试验 / 试航 → 交付 / 营运，法规类走「规则落地」。"
        "连续 2 期没有相关报道的事项会自动停止跟踪（只停展示，记录仍在台账）。"
        "点编号可跳到下方对应 RSS 原文。</div>"
    )

    return (
        MARK_S
        + '\n<div class="track-wrap">\n<details class="track-box" open>\n'
        '<summary><span class="tk-eyebrow">附录</span>'
        '<span class="tk-h">跨期跟踪</span>'
        '<span class="tk-sub">%s</span>'
        '<a class="tk-arch" href="%s">过刊库 ↗</a></summary>\n'
        '%s\n%s\n%s\n</details>\n</div>\n'
        % (sub, esc(archive_href), ('<div class="tk-chips">%s</div>' % chips) if chips else "", body, note)
        + MARK_E
    )


# ── 归档页 ──────────────────────────────────────────────────────────
ARCHIVE_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;color:#0f172a}
.wrap{max-width:780px;margin:0 auto;padding:40px 20px 60px}
h1{font-size:20px;font-weight:500;margin:0 0 6px}
.sub{color:#64748b;font-size:13px;margin-bottom:26px;line-height:1.7}
.card{display:block;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px 18px;margin-bottom:10px;text-decoration:none;color:inherit;transition:border-color .15s,transform .15s}
.card:hover{border-color:#93c5fd;transform:translateY(-1px)}
.date{font-size:15px;font-weight:500}
.meta{color:#64748b;font-size:12.5px;margin-top:6px;line-height:1.7}
.pill{display:inline-block;margin-right:8px;padding:1px 8px;border-radius:9px;font-size:11.5px;background:#eef2ff;color:#3730a3;border:1px solid #c7d2fe}
.pill.g{background:#dcfce7;color:#166534;border-color:#bbf7d0}
.empty{color:#94a3b8;font-size:13px}
</style>"""


def build_archive_index(issues, out_path: Path):
    rows = []
    for it in sorted(issues, key=lambda x: x.get("date", ""), reverse=True):
        s = it.get("summary") or {}
        pills = ['<span class="pill">%d 条</span>' % it.get("items", 0)]
        if s.get("done"):
            pills.append('<span class="pill g">已落地 %d</span>' % s["done"])
        if s.get("policy"):
            pills.append('<span class="pill">规则落地 %d</span>' % s["policy"])
        rows.append(
            '<a class="card" href="issues/%s.html"><div class="date">%s</div>'
            '<div class="meta">%s</div></a>'
            % (esc(it.get("date", "")), esc(it.get("date", "")), "".join(pills))
        )
    body = "\n".join(rows) if rows else '<div class="empty">还没有归档。</div>'
    page = (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="robots" content="noindex,nofollow">'
        "<title>过刊库 · 船舶低碳情报双周报</title><style>%s</head><body>"
        '<div class="wrap"><h1>过刊库</h1>'
        '<div class="sub">船舶低碳情报双周报的历史各期。每期独立自包含，可直接打开；'
        '正文里的 #编号 只在本期有效。</div>%s</div></body></html>'
        % (ARCHIVE_CSS, body)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")


# ── 主流程 ──────────────────────────────────────────────────────────
def strip_previous(doc: str) -> str:
    doc = re.sub(re.escape(MARK_S) + r".*?" + re.escape(MARK_E) + r"\n?", "", doc, flags=re.S)
    doc = re.sub(re.escape(CSS_S) + r".*?" + re.escape(CSS_E) + r"\n?", "", doc, flags=re.S)
    return doc


def inject(doc: str, block: str) -> str:
    """把附录插到**整页最末**（2026-10-21 起）。

    旧版插在 `.ai-section` 前面 —— 报告一打开先看到一张跨期跟踪表，
    读者还没看本期内容就被上期的事拦住，顺序是反的。
    现在改为排在页面可见内容之后、末尾脚本之前：
    先在末尾脚本锚点上找，找不到退到 </body>，都找不到就追加到文档尾。
    """
    if "</head>" in doc:
        doc = doc.replace("</head>", CSS_BLOCK + "\n</head>", 1)
    # 用正则找**最后一个** </body>，不依赖具体缩进：
    # 报告模板换行/缩进在历史上变过好几版，写死字符串会静默落不到页面里。
    for pat in (r"</body\s*>", r"</html\s*>"):
        hits = list(re.finditer(pat, doc, re.I))
        if hits:
            pos = hits[-1].start()
            return doc[:pos] + block + "\n" + doc[pos:]
    return doc + "\n" + block


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", default="index.html")
    ap.add_argument("--archive", default="archive")
    ap.add_argument("--date", default="")
    ap.add_argument("--prev-issues", type=int, default=3, help="回溯几期做匹配")
    ap.add_argument("--max-rows", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    report = Path(args.report)
    if not report.exists():
        print("[track] 未找到 %s，跳过归档与跟踪" % report)
        return 0

    today = args.date or datetime.now(CST).strftime("%Y-%m-%d")
    doc = report.read_text(encoding="utf-8", errors="replace")
    doc = strip_previous(doc)

    items = parse_items(doc)
    if not items:
        print("[track] 报告里没有编号条目，跳过（可能 [K] 未生效）")
        return 0
    events = cluster(items)

    arch_dir = Path(args.archive)
    ledger_path = arch_dir / "ledger.json"
    ledger = load_ledger(ledger_path)
    issues = [i for i in ledger.get("issues", []) if i.get("date") != today]
    issues.sort(key=lambda x: x.get("date", ""))

    prev = issues[-args.prev_issues :]
    rows, stats = build_tracking(events, prev, today, max_new=3, max_rows=args.max_rows)

    prev_date = prev[-1]["date"] if prev else None
    in_archive = (arch_dir / "issues").exists()
    archive_href = "archive/index.html"
    block = render_box(rows, stats, prev_date, archive_href)
    out = inject(doc, block)

    dup = len(items) - len(events)
    print(
        "[track] 条目 %d → 事件 %d（合并同一事件 %d 条）｜上期 %s ｜"
        "已落地 %d · 规则落地 %d · 有新进展 %d · 仍在观察 %d · 结案 %d"
        % (len(items), len(events), dup, prev_date or "无",
           stats["done"], stats["policy"], stats["progress"], stats["watching"],
           stats.get("closed", 0))
    )

    if args.dry_run:
        return 0

    report.write_text(out, encoding="utf-8")

    # 归档本期（自包含单文件）
    issues_dir = arch_dir / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    arch_doc = out.replace('href="archive/index.html"', 'href="../index.html"')
    arch_doc = arch_doc.replace('href="archive/issues/', 'href="')
    (issues_dir / ("%s.html" % today)).write_text(arch_doc, encoding="utf-8")

    # 台账：只存每期事件，观察池由它现算 —— 同日重跑天然幂等
    issues.append(
        {
            "date": today,
            "items": len(items),
            "events": [
                {
                    "cite": e["cite"],
                    "title": e["title"],
                    "url": e.get("url", ""),
                    "src": e.get("src", ""),
                    "stage": e["stage"],
                }
                for e in events
            ],
            "summary": stats,
        }
    )
    issues.sort(key=lambda x: x.get("date", ""))
    # 只保留最近 12 期的明细，更早的留下元信息即可
    for it in issues[:-12]:
        it["events"] = []

    ledger = {"version": 1, "updated": today, "issues": issues[-26:]}
    arch_dir.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    build_archive_index(ledger["issues"], arch_dir / "index.html")
    n_arch = len(list(issues_dir.glob("*.html")))
    print("[track] 已归档：%s ｜ 过刊库共 %d 期 ｜ %s"
          % (issues_dir / ("%s.html" % today), n_arch, arch_dir / "index.html"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        import traceback

        traceback.print_exc()
        print("[track] ⚠ 归档/跟踪失败（不影响报告本身）：%s" % e)
        sys.exit(0)
