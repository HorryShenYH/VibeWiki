from __future__ import annotations

from dataclasses import dataclass
import html
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import socketserver
from urllib.parse import parse_qs, urlencode, urlparse
import uuid

from .capture import capture_session
from .dashboard import DashboardData, build_dashboard_data
from .distill import distill_session, parse_sections
from .events import append_event, read_events
from .import_markdown import import_markdown_session
from .import_url import import_url_session
from .llm import llm_settings
from .merge import merge_patches
from .project import ensure_workspace
from .project_understanding import build_project_brief, render_project_brief_markdown
from .retrieval import answer_question, build_context_pack, load_retrieval_config
from .review import read_item_decisions
from .review_ui import perform_review_action, render_review_ui
from .text_utils import read_text_if_exists, slugify, utcish_timestamp


REVIEW_ACTIONS = {
    "/item-action",
    "/decision",
    "/bulk-decision",
    "/save-item",
    "/patch-review",
    "/merge",
}


@dataclass(frozen=True)
class ConsoleActionResult:
    message: str
    message_zh: str
    anchor: str = ""
    result_title: str = ""
    result_title_zh: str = ""
    result_text: str = ""


def render_control_center(
    project: Path,
    *,
    message: str = "",
    message_zh: str = "",
    result_title: str = "",
    result_title_zh: str = "",
    result_text: str = "",
) -> str:
    root = project.resolve()
    ensure_workspace(root)
    data = build_dashboard_data(root)
    approved_cards = data.status_counts.get("approved", 0)
    candidate_cards = data.status_counts.get("candidate", 0)
    approved_patches = sum(1 for patch in data.patches if _patch_approved(root, patch.name))
    merged_patches = _merged_patch_ids(root)
    pending_reviews = max(len(data.patches) - len(merged_patches), 0)
    config = load_retrieval_config(root)
    configured_llm = llm_settings(
        base_url_env=config.llm_base_url_env,
        api_key_env=config.llm_api_key_env,
        model_env=config.llm_model_env,
    )
    latest_cards = sorted(data.cards, key=lambda card: card.source.as_posix(), reverse=True)[:6]
    session_rows = _session_rows(data, merged_patches)
    kind_rows = [(kind, count) for kind, count in data.kind_counts.most_common(6) if count]
    max_kind = max((count for _, count in kind_rows), default=1)
    message_html = _message(message, message_zh)
    result_html = _result_panel(result_title, result_title_zh, result_text)

    return f"""<!doctype html>
<html lang="en" data-default-lang="en" data-vibewiki-control-center="1">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VibeWiki - {_escape(data.project_name)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #667085;
      --line: #d9ded8;
      --canvas: #f3f5f2;
      --paper: #ffffff;
      --soft: #eef3ef;
      --teal: #238f84;
      --gold: #d7a62d;
      --coral: #e66a4e;
      --blue: #397da6;
      --green: #6f9f68;
      --danger: #b74252;
      --sidebar: #17202a;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background: var(--canvas);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
      letter-spacing: 0;
    }}
    button, input, textarea, select {{ font: inherit; letter-spacing: 0; }}
    button, .button {{
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px 13px;
      background: var(--paper);
      color: var(--ink);
      cursor: pointer;
      font-size: 13px;
      font-weight: 700;
      text-decoration: none;
      white-space: nowrap;
    }}
    button:hover, .button:hover {{ border-color: #9da8a0; }}
    button.primary, .button.primary {{ background: var(--teal); border-color: var(--teal); color: #fff; }}
    button.secondary, .button.secondary {{ color: var(--blue); }}
    button.quiet, .button.quiet {{ background: transparent; color: var(--muted); }}
    input, textarea, select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--ink);
      padding: 10px 11px;
      font-size: 14px;
    }}
    input:focus, textarea:focus, select:focus {{ outline: 2px solid rgba(35, 143, 132, .22); border-color: var(--teal); }}
    textarea {{ min-height: 142px; resize: vertical; }}
    label {{ display: grid; gap: 6px; color: var(--muted); font-size: 12px; font-weight: 700; }}
    .app {{ min-height: 100vh; display: grid; grid-template-columns: 224px minmax(0, 1fr); }}
    .sidebar {{
      position: sticky;
      top: 0;
      height: 100vh;
      padding: 22px 16px;
      background: var(--sidebar);
      color: #fff;
      display: flex;
      flex-direction: column;
      gap: 24px;
    }}
    .brand {{ display: flex; align-items: center; gap: 10px; color: #fff; text-decoration: none; }}
    .brand-mark {{
      width: 34px;
      height: 34px;
      display: grid;
      place-items: center;
      border: 1px solid rgba(255,255,255,.2);
      border-radius: 6px;
      color: #62c7bb;
      font-size: 21px;
      font-weight: 900;
    }}
    .brand strong {{ display: block; font-size: 16px; }}
    .brand small {{ display: block; color: #9eaaa5; font-size: 11px; }}
    nav {{ display: grid; gap: 5px; }}
    nav a {{
      min-height: 40px;
      display: flex;
      align-items: center;
      padding: 8px 10px;
      border-radius: 6px;
      color: #bac4c0;
      text-decoration: none;
      font-size: 13px;
      font-weight: 650;
    }}
    nav a:hover, nav a.active {{ background: rgba(255,255,255,.09); color: #fff; }}
    .side-status {{ margin-top: auto; padding-top: 16px; border-top: 1px solid rgba(255,255,255,.12); }}
    .side-status span {{ display: block; color: #9eaaa5; font-size: 11px; }}
    .side-status strong {{ display: block; margin-top: 3px; font-size: 13px; overflow-wrap: anywhere; }}
    .main {{ min-width: 0; padding: 24px 28px 48px; }}
    .topbar {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 20px; }}
    .topbar h1 {{ margin: 0; font-size: 26px; line-height: 1.15; }}
    .topbar p {{ margin: 4px 0 0; color: var(--muted); font-size: 13px; }}
    .top-actions {{ display: flex; align-items: center; gap: 8px; }}
    .language {{ display: inline-flex; padding: 3px; border: 1px solid var(--line); border-radius: 6px; background: #fff; }}
    .language button {{ min-width: 42px; min-height: 30px; padding: 4px 8px; border: 0; background: transparent; color: var(--muted); }}
    .language button.active {{ background: var(--ink); color: #fff; }}
    .message {{
      margin-bottom: 16px;
      padding: 11px 13px;
      border: 1px solid #a9d3cd;
      border-left: 4px solid var(--teal);
      border-radius: 6px;
      background: #f0faf8;
      color: #155e57;
      font-size: 13px;
    }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }}
    .metric {{ min-height: 104px; padding: 16px; border: 1px solid var(--line); border-radius: 6px; background: #fff; }}
    .metric b {{ display: block; margin-bottom: 12px; font-size: 30px; line-height: 1; }}
    .metric span {{ color: var(--muted); font-size: 12px; font-weight: 750; }}
    .metric small {{ display: block; margin-top: 4px; color: #8b948f; font-size: 11px; }}
    .flow {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      margin-bottom: 16px;
      overflow: hidden;
    }}
    .flow-step {{ position: relative; min-height: 74px; padding: 13px 14px 13px 48px; border-right: 1px solid var(--line); }}
    .flow-step:last-child {{ border-right: 0; }}
    .step-num {{ position: absolute; left: 14px; top: 17px; width: 24px; height: 24px; display: grid; place-items: center; border-radius: 50%; background: var(--soft); color: var(--muted); font-size: 11px; font-weight: 850; }}
    .flow-step.done .step-num {{ background: var(--green); color: #fff; }}
    .flow-step.current {{ box-shadow: inset 0 -3px var(--gold); }}
    .flow-step strong {{ display: block; font-size: 13px; }}
    .flow-step small {{ color: var(--muted); font-size: 11px; }}
    .columns {{ display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(320px, .85fr); gap: 16px; align-items: start; }}
    .panel {{ min-width: 0; margin-bottom: 16px; border: 1px solid var(--line); border-radius: 6px; background: #fff; }}
    .panel-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 15px 16px; border-bottom: 1px solid var(--line); }}
    .panel-head h2 {{ margin: 0; font-size: 15px; }}
    .panel-head small {{ color: var(--muted); font-size: 11px; }}
    .panel-body {{ padding: 16px; }}
    .tabs {{ display: flex; gap: 4px; padding: 4px; border-radius: 6px; background: var(--soft); margin-bottom: 14px; }}
    .tabs button {{ flex: 1; min-height: 34px; border: 0; background: transparent; color: var(--muted); }}
    .tabs button.active {{ background: #fff; color: var(--ink); box-shadow: 0 1px 3px rgba(23,32,42,.1); }}
    .tab-panel[hidden] {{ display: none; }}
    .form-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
    .form-stack {{ display: grid; gap: 10px; }}
    .form-actions {{ display: flex; gap: 8px; align-items: center; justify-content: space-between; flex-wrap: wrap; }}
    .check {{ display: inline-flex; grid-template-columns: auto 1fr; align-items: center; gap: 7px; color: var(--muted); font-size: 12px; }}
    .check input {{ width: auto; }}
    .ask-form {{ display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }}
    .ask-actions {{ display: flex; gap: 8px; margin-top: 8px; }}
    .result {{ border-top: 1px solid var(--line); padding: 14px 16px; background: #f8faf8; }}
    .result-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }}
    .result h3 {{ margin: 0; font-size: 13px; }}
    pre {{
      max-height: 380px;
      margin: 0;
      padding: 12px;
      overflow: auto;
      border-radius: 6px;
      background: #17202a;
      color: #edf4f1;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font: 12px/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .queue {{ display: grid; }}
    .queue-row {{ display: grid; grid-template-columns: minmax(0, 1.5fr) 120px 125px auto; gap: 12px; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--line); }}
    .queue-row:last-child {{ border-bottom: 0; }}
    .queue-title {{ min-width: 0; }}
    .queue-title strong {{ display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }}
    .queue-title small {{ color: var(--muted); font-size: 11px; }}
    .status {{ display: inline-flex; width: fit-content; padding: 3px 8px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); font-size: 11px; font-weight: 750; }}
    .status.candidate {{ color: #a04c38; border-color: #edbaa9; background: #fff7f4; }}
    .status.approved {{ color: #31734b; border-color: #add0b9; background: #f4fbf6; }}
    .status.merged {{ color: #356e91; border-color: #adc8da; background: #f3f8fb; }}
    .row-actions {{ display: flex; justify-content: flex-end; gap: 7px; }}
    .memory-list {{ display: grid; }}
    .memory-row {{ padding: 12px 16px; border-bottom: 1px solid var(--line); }}
    .memory-row:last-child {{ border-bottom: 0; }}
    .memory-row strong {{ display: block; font-size: 13px; }}
    .memory-meta {{ display: flex; gap: 8px; margin-top: 5px; color: var(--muted); font-size: 11px; }}
    .bars {{ display: grid; gap: 11px; }}
    .bar-row {{ display: grid; grid-template-columns: 110px minmax(0, 1fr) 28px; gap: 8px; align-items: center; font-size: 12px; }}
    .bar-track {{ height: 9px; border-radius: 3px; background: var(--soft); overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 3px; background: var(--blue); }}
    .bar-row:nth-child(2n) .bar-fill {{ background: var(--gold); }}
    .bar-row:nth-child(3n) .bar-fill {{ background: var(--coral); }}
    .empty {{ padding: 24px 16px; color: var(--muted); font-size: 13px; text-align: center; }}
    details.advanced {{ border-top: 1px solid var(--line); }}
    details.advanced summary {{ padding: 13px 16px; cursor: pointer; color: var(--muted); font-size: 12px; font-weight: 750; }}
    .advanced-body {{ display: flex; gap: 8px; padding: 0 16px 16px; flex-wrap: wrap; }}
    @media (max-width: 1050px) {{
      .columns {{ grid-template-columns: 1fr; }}
      .queue-row {{ grid-template-columns: minmax(0, 1fr) 110px auto; }}
      .queue-row .review-count {{ display: none; }}
    }}
    @media (max-width: 760px) {{
      .app {{ grid-template-columns: 1fr; }}
      .sidebar {{ position: static; height: auto; padding: 12px; flex-direction: row; align-items: center; overflow-x: auto; }}
      .brand small, .side-status {{ display: none; }}
      nav {{ display: flex; }}
      nav a {{ white-space: nowrap; }}
      .main {{ padding: 16px 12px 36px; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .flow {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .flow-step:nth-child(2) {{ border-right: 0; }}
      .flow-step:nth-child(-n+2) {{ border-bottom: 1px solid var(--line); }}
      .topbar {{ align-items: flex-start; }}
      .form-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 560px) {{
      .metrics {{ grid-template-columns: 1fr 1fr; }}
      .metric {{ min-height: 90px; padding: 13px; }}
      .metric b {{ font-size: 25px; }}
      .queue-row {{ grid-template-columns: 1fr; }}
      .row-actions {{ justify-content: flex-start; }}
      .ask-form {{ grid-template-columns: 1fr; }}
      .topbar {{ display: block; }}
      .top-actions {{ margin-top: 10px; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <a class="brand" href="#overview">
        <span class="brand-mark">V</span>
        <span><strong>VibeWiki</strong><small>{_i18n("Memory control", "记忆中控")}</small></span>
      </a>
      <nav aria-label="Primary">
        <a class="active" href="#overview">{_i18n("Overview", "概览")}</a>
        <a href="#add">{_i18n("Add", "导入")}</a>
        <a href="#work">{_i18n("Review", "审核")}</a>
        <a href="#reuse">{_i18n("Ask", "提问")}</a>
        <a href="#memory">{_i18n("Memory", "记忆")}</a>
      </nav>
      <div class="side-status">
        <span>{_i18n("Workspace", "工作区")}</span>
        <strong>{_escape(data.project_name)}</strong>
      </div>
    </aside>

    <main class="main">
      <header class="topbar" id="overview">
        <div>
          <h1>{_escape(data.project_name)}</h1>
          <p>{_i18n("Memory Control Center", "记忆中控台")} · {_escape(utcish_timestamp())}</p>
        </div>
        <div class="top-actions">
          <a class="button quiet" href="/">{_i18n("Refresh", "刷新")}</a>
          <div class="language" role="group" aria-label="Language">
            <button type="button" data-lang-choice="en" aria-pressed="true">EN</button>
            <button type="button" data-lang-choice="zh" aria-pressed="false">中文</button>
          </div>
        </div>
      </header>

      {message_html}

      <section class="metrics" aria-label="Memory metrics">
        {_metric(len(data.sessions), "Conversations", "历史对话", "captured", "已记录")}
        {_metric(candidate_cards, "Candidates", "候选记忆", f"{pending_reviews} pending", f"{pending_reviews} 待处理")}
        {_metric(approved_cards, "Trusted memory", "可信记忆", f"{approved_patches} approved batches", f"{approved_patches} 批已批准")}
        {_metric(len(merged_patches), "Merged", "已合并", "ready to reuse", "可直接复用")}
      </section>

      {_flow(data, approved_patches, merged_patches)}

      <section class="columns">
        <div>
          <section class="panel" id="add">
            <div class="panel-head">
              <h2>{_i18n("Add a conversation", "添加一段对话")}</h2>
              <small>{_i18n("Raw evidence stays local", "原始证据保存在本地")}</small>
            </div>
            <div class="panel-body">
              <div class="tabs" role="tablist">
                <button class="active" type="button" data-tab="paste">{_i18n("Paste", "粘贴")}</button>
                <button type="button" data-tab="link">{_i18n("Share link", "分享链接")}</button>
                <button type="button" data-tab="result">{_i18n("Quick result", "快速记录")}</button>
              </div>
              <div class="tab-panel" data-tab-panel="paste">
                <form class="form-stack" method="post" action="/action/import-text">
                  <label>{_i18n("Conversation Markdown", "对话 Markdown")}
                    <textarea required name="body" data-placeholder-en="Paste an exported AI conversation or Markdown notes" data-placeholder-zh="粘贴导出的 AI 对话或 Markdown 笔记" placeholder="Paste an exported AI conversation or Markdown notes"></textarea>
                  </label>
                  <div class="form-grid">
                    <label>{_i18n("Name (optional)", "名称（可选）")}<input name="session_name" data-placeholder-en="e.g. auth-timeout" data-placeholder-zh="例如 auth-timeout" placeholder="e.g. auth-timeout"></label>
                    <label>{_i18n("Recorder note (optional)", "记录备注（可选）")}<input name="notes" data-placeholder-en="What should VibeWiki keep?" data-placeholder-zh="希望 VibeWiki 保留什么？" placeholder="What should VibeWiki keep?"></label>
                  </div>
                  <div class="form-actions">
                    <label class="check"><input type="checkbox" name="auto_distill" value="yes" checked> {_i18n("Generate memory draft now", "立即生成记忆草稿")}</label>
                    <button class="primary" type="submit">{_i18n("Import conversation", "导入对话")}</button>
                  </div>
                </form>
              </div>
              <div class="tab-panel" data-tab-panel="link" hidden>
                <form class="form-stack" method="post" action="/action/import-url">
                  <label>{_i18n("Shared conversation URL", "对话分享链接")}<input required type="url" name="url" placeholder="https://chatgpt.com/share/..."></label>
                  <label>{_i18n("Name (optional)", "名称（可选）")}<input name="session_name" placeholder="shared-conversation"></label>
                  <div class="form-actions">
                    <label class="check"><input type="checkbox" name="auto_distill" value="yes" checked> {_i18n("Generate memory draft now", "立即生成记忆草稿")}</label>
                    <button class="primary" type="submit">{_i18n("Import link", "导入链接")}</button>
                  </div>
                </form>
              </div>
              <div class="tab-panel" data-tab-panel="result" hidden>
                <form class="form-stack" method="post" action="/action/capture">
                  <div class="form-grid">
                    <label>{_i18n("Goal", "目标")}<input required name="goal" data-placeholder-en="What were you trying to do?" data-placeholder-zh="你想完成什么？" placeholder="What were you trying to do?"></label>
                    <label>{_i18n("Outcome", "结果")}<input name="outcome" data-placeholder-en="What finally worked?" data-placeholder-zh="最后什么方法成功了？" placeholder="What finally worked?"></label>
                  </div>
                  <label>{_i18n("Commands, one per line", "关键命令，每行一条")}<textarea name="commands" data-placeholder-en="python3 -m pytest tests/test_feature.py -q" data-placeholder-zh="python3 -m pytest tests/test_feature.py -q" placeholder="python3 -m pytest tests/test_feature.py -q"></textarea></label>
                  <label>{_i18n("Verification", "验证结果")}<input name="tests" data-placeholder-en="All regression tests passed" data-placeholder-zh="所有回归测试通过" placeholder="All regression tests passed"></label>
                  <div class="form-actions">
                    <label class="check"><input type="checkbox" name="auto_distill" value="yes" checked> {_i18n("Generate memory draft now", "立即生成记忆草稿")}</label>
                    <button class="primary" type="submit">{_i18n("Save result", "保存结果")}</button>
                  </div>
                </form>
              </div>
            </div>
          </section>

          <section class="panel" id="work">
            <div class="panel-head">
              <h2>{_i18n("Work queue", "处理队列")}</h2>
              <small>{_escape(str(len(data.sessions)))} {_i18n("conversations", "段对话")}</small>
            </div>
            <div class="queue">{session_rows or _empty("No conversations yet", "还没有对话")}</div>
          </section>
        </div>

        <div>
          <section class="panel" id="reuse">
            <div class="panel-head">
              <h2>{_i18n("Ask your memory", "向记忆提问")}</h2>
              <small>{_i18n("LLM connected" if configured_llm else "Local answer mode", "LLM 已连接" if configured_llm else "本地回答模式")}</small>
            </div>
            <div class="panel-body">
              <form method="post" action="/action/ask">
                <div class="ask-form">
                  <input required name="query" data-placeholder-en="How did we solve this before?" data-placeholder-zh="我们之前是怎么解决这个问题的？" placeholder="How did we solve this before?">
                  <button class="primary" type="submit">{_i18n("Ask", "提问")}</button>
                </div>
              </form>
              <form class="ask-actions" method="post" action="/action/context">
                <input required name="query" data-placeholder-en="Task for the next AI agent" data-placeholder-zh="下一位 AI agent 要完成的任务" placeholder="Task for the next AI agent">
                <button class="secondary" type="submit">{_i18n("Build AI context", "生成 AI 上下文")}</button>
              </form>
            </div>
            {result_html}
          </section>

          <section class="panel" id="memory">
            <div class="panel-head">
              <h2>{_i18n("Recent memory", "最近记忆")}</h2>
              <small>{_escape(str(len(data.cards)))} {_i18n("cards", "张卡片")}</small>
            </div>
            <div class="memory-list">{_memory_rows(latest_cards, root) or _empty("No memory cards yet", "还没有记忆卡片")}</div>
          </section>

          <section class="panel">
            <div class="panel-head"><h2>{_i18n("Memory mix", "记忆构成")}</h2><small>{_i18n("By type", "按类型")}</small></div>
            <div class="panel-body"><div class="bars">{_kind_bars(kind_rows, max_kind) or _empty("No data yet", "暂无数据")}</div></div>
            <details class="advanced">
              <summary>{_i18n("Project tools", "项目工具")}</summary>
              <div class="advanced-body">
                <form method="post" action="/action/understand"><button type="submit">{_i18n("Refresh project brief", "刷新项目简介")}</button></form>
                <a class="button" href="#overview">{_i18n("Back to top", "返回顶部")}</a>
              </div>
            </details>
          </section>
        </div>
      </section>
    </main>
  </div>
  <script>
    (() => {{
      const languageButtons = Array.from(document.querySelectorAll("[data-lang-choice]"));
      function setLanguage(lang) {{
        const next = lang === "zh" ? "zh" : "en";
        document.documentElement.lang = next;
        document.querySelectorAll("[data-i18n]").forEach((node) => {{
          node.textContent = next === "zh" ? node.dataset.zh : node.dataset.en;
        }});
        document.querySelectorAll("[data-placeholder-en]").forEach((node) => {{
          node.placeholder = next === "zh" ? node.dataset.placeholderZh : node.dataset.placeholderEn;
        }});
        languageButtons.forEach((button) => {{
          const active = button.dataset.langChoice === next;
          button.classList.toggle("active", active);
          button.setAttribute("aria-pressed", String(active));
        }});
        try {{ localStorage.setItem("vibewiki.ui.lang", next); }} catch (error) {{}}
      }}
      languageButtons.forEach((button) => button.addEventListener("click", () => setLanguage(button.dataset.langChoice || "en")));
      let savedLanguage = "en";
      try {{ savedLanguage = localStorage.getItem("vibewiki.ui.lang") || "en"; }} catch (error) {{}}
      setLanguage(savedLanguage);

      const tabButtons = Array.from(document.querySelectorAll("[data-tab]"));
      const tabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));
      tabButtons.forEach((button) => button.addEventListener("click", () => {{
        const selected = button.dataset.tab;
        tabButtons.forEach((item) => item.classList.toggle("active", item.dataset.tab === selected));
        tabPanels.forEach((panel) => panel.hidden = panel.dataset.tabPanel !== selected);
      }}));

      document.querySelectorAll("[data-copy-result]").forEach((button) => button.addEventListener("click", async () => {{
        const output = document.querySelector("[data-result-output]");
        if (!output) return;
        await navigator.clipboard.writeText(output.textContent || "");
        button.textContent = document.documentElement.lang === "zh" ? "已复制" : "Copied";
      }}));
    }})();
  </script>
</body>
</html>
"""


def serve_control_center(
    project: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    root = project.resolve()
    ensure_workspace(root)

    class ControlCenterHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/":
                self._send_html(
                    render_control_center(
                        root,
                        message=_value(query, "message"),
                        message_zh=_value(query, "message_zh"),
                    )
                )
                return
            if parsed.path == "/review":
                patch_dir = _patch_dir(root, _value(query, "patch"))
                self._send_html(
                    render_review_ui(
                        root,
                        patch_dir=patch_dir,
                        message=_value(query, "message"),
                        message_zh=_value(query, "message_zh"),
                        target_language=_value(query, "target_language") or "zh",
                        home_url="/",
                        default_lang="en",
                    )
                )
                return
            if parsed.path == "/health":
                self._send_text("ok\n")
                return
            self.send_error(404, "Not found")

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                data = self._read_form()
                if parsed.path in REVIEW_ACTIONS:
                    patch_dir = _patch_dir(root, _value(data, "patch"))
                    result = perform_review_action(
                        root,
                        patch_dir=patch_dir,
                        path=parsed.path,
                        data=data,
                    )
                    append_event(
                        root,
                        "ui-review",
                        subject=patch_dir.name,
                        data={"action": parsed.path},
                    )
                    self._redirect_review(
                        patch_dir.name,
                        result.message,
                        result.message_zh,
                        target_language=result.target_language,
                    )
                    return

                result = perform_console_action(root, path=parsed.path, data=data)
                if result.result_text:
                    self._send_html(
                        render_control_center(
                            root,
                            message=result.message,
                            message_zh=result.message_zh,
                            result_title=result.result_title,
                            result_title_zh=result.result_title_zh,
                            result_text=result.result_text,
                        )
                    )
                    return
                self._redirect_home(result.message, result.message_zh, result.anchor)
            except Exception as exc:
                self._send_html(
                    render_control_center(
                        root,
                        message=f"Error: {exc}",
                        message_zh=f"错误：{exc}",
                    ),
                    status=400,
                )

        def _read_form(self) -> dict[str, list[str]]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > 8 * 1024 * 1024:
                raise ValueError("Request is larger than 8 MB.")
            return parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)

        def _send_html(self, body: str, *, status: int = 200) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_text(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _redirect_home(self, message: str, message_zh: str, anchor: str = "") -> None:
            target = "/?" + urlencode({"message": message, "message_zh": message_zh})
            if anchor:
                target += f"#{anchor}"
            self.send_response(303)
            self.send_header("Location", target)
            self.end_headers()

        def _redirect_review(
            self,
            patch: str,
            message: str,
            message_zh: str,
            *,
            target_language: str = "zh",
        ) -> None:
            target = "/review?" + urlencode(
                {
                    "patch": patch,
                    "message": message,
                    "message_zh": message_zh,
                    "target_language": target_language,
                }
            )
            self.send_response(303)
            self.send_header("Location", target)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    class ReusableThreadingServer(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with ReusableThreadingServer((host, port), ControlCenterHandler) as server:
        print(f"VibeWiki Control Center: http://{host}:{port}/")
        print(f"Workspace: {root}")
        print("For VS Code Remote SSH, forward this port and open the same URL locally.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nVibeWiki Control Center stopped.")


def perform_console_action(
    project: Path,
    *,
    path: str,
    data: dict[str, list[str]],
) -> ConsoleActionResult:
    root = project.resolve()
    ensure_workspace(root)

    if path == "/action/import-text":
        body = _text(data, "body").strip()
        if not body:
            raise ValueError("Conversation Markdown is required.")
        session_name = _value(data, "session_name")
        inbox = root / ".vibewiki" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        source_name = f"{utcish_timestamp().replace(':', '')}-{uuid.uuid4().hex[:6]}-{slugify(session_name or 'conversation')}.md"
        source = inbox / source_name
        source.write_text(body.rstrip() + "\n", encoding="utf-8")
        session = import_markdown_session(
            root,
            source,
            notes=_value(data, "notes"),
            session_name=session_name or None,
        )
        append_event(root, "import-markdown", subject=session.session_id, data={"source": str(source)})
        generated = _auto_distill(root, session.session_dir, data)
        message = "Conversation imported"
        message_zh = "对话已导入"
        if generated:
            message += "; memory draft generated"
            message_zh += "，并已生成记忆草稿"
        return ConsoleActionResult(message, message_zh, anchor="work")

    if path == "/action/import-url":
        url = _value(data, "url")
        if not url:
            raise ValueError("Shared conversation URL is required.")
        session = import_url_session(
            root,
            url,
            session_name=_value(data, "session_name") or None,
        )
        append_event(root, "import-url", subject=session.session_id, data={"url": url})
        generated = _auto_distill(root, session.session_dir, data)
        message = "Conversation link imported"
        message_zh = "对话链接已导入"
        if generated:
            message += "; memory draft generated"
            message_zh += "，并已生成记忆草稿"
        return ConsoleActionResult(message, message_zh, anchor="work")

    if path == "/action/capture":
        goal = _value(data, "goal")
        if not goal:
            raise ValueError("Goal is required.")
        commands = [line.strip() for line in _text(data, "commands").splitlines() if line.strip()]
        session = capture_session(
            root,
            goal=goal,
            outcome=_value(data, "outcome"),
            commands=commands,
            tests=_value(data, "tests"),
        )
        append_event(root, "capture", subject=session.session_id, data={"goal": goal})
        generated = _auto_distill(root, session.session_dir, data)
        message = "Result captured"
        message_zh = "结果已记录"
        if generated:
            message += "; memory draft generated"
            message_zh += "，并已生成记忆草稿"
        return ConsoleActionResult(message, message_zh, anchor="work")

    if path == "/action/distill":
        session_dir = _session_dir(root, _value(data, "session"))
        patches = distill_session(root, session_dir=session_dir)
        append_event(root, "distill", subject=patches.session_id, data={"patch_dir": str(patches.patch_dir)})
        return ConsoleActionResult("Memory draft generated", "记忆草稿已生成", anchor="work")

    if path == "/action/merge":
        patch_dir = _patch_dir(root, _value(data, "patch"))
        changed = merge_patches(root, patch_dir=patch_dir)
        append_event(
            root,
            "merge",
            subject=patch_dir.name,
            data={"patch_dir": str(patch_dir), "changed": [str(item) for item in changed]},
        )
        return ConsoleActionResult(
            f"Merged {len(changed)} files into trusted memory",
            f"已将 {len(changed)} 个文件合并到可信记忆",
            anchor="work",
        )

    if path == "/action/ask":
        query = _value(data, "query")
        if not query:
            raise ValueError("Question is required.")
        answer = answer_question(root, query)
        append_event(root, "ask", subject=query, data={"source": "ui"})
        return ConsoleActionResult(
            "Answer ready",
            "回答已生成",
            anchor="reuse",
            result_title="Answer",
            result_title_zh="回答",
            result_text=answer,
        )

    if path == "/action/context":
        query = _value(data, "query")
        if not query:
            raise ValueError("Agent task is required.")
        context = build_context_pack(root, query, output_format="json")
        append_event(root, "context", subject=query, data={"source": "ui", "format": "json"})
        return ConsoleActionResult(
            "AI context ready",
            "AI 上下文已生成",
            anchor="reuse",
            result_title="AI context pack",
            result_title_zh="AI 上下文包",
            result_text=context,
        )

    if path == "/action/understand":
        brief = build_project_brief(root)
        output = root / "docs" / "wiki" / "project_brief.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_project_brief_markdown(brief), encoding="utf-8")
        append_event(root, "understand", subject=root.name, data={"output": str(output)})
        return ConsoleActionResult("Project brief refreshed", "项目简介已刷新", anchor="memory")

    raise ValueError(f"Unknown control-center action: {path}")


def _auto_distill(project: Path, session_dir: Path, data: dict[str, list[str]]) -> bool:
    if _value(data, "auto_distill") != "yes":
        return False
    patches = distill_session(project, session_dir=session_dir)
    append_event(
        project,
        "distill",
        subject=patches.session_id,
        data={"patch_dir": str(patches.patch_dir), "source": "ui"},
    )
    return True


def _flow(data: DashboardData, approved_patches: int, merged_patches: set[str]) -> str:
    values = [len(data.sessions), len(data.patches), approved_patches, len(merged_patches)]
    labels = [
        ("Capture", "记录"),
        ("Distill", "提炼"),
        ("Review", "审核"),
        ("Reuse", "复用"),
    ]
    current = next((index for index, value in enumerate(values) if value == 0), 3)
    steps: list[str] = []
    for index, ((en, zh), value) in enumerate(zip(labels, values), 1):
        classes = ["flow-step"]
        if value > 0:
            classes.append("done")
        if index - 1 == current:
            classes.append("current")
        steps.append(
            f'<div class="{" ".join(classes)}"><span class="step-num">{index}</span>'
            f'<strong>{_i18n(en, zh)}</strong><small>{value} {_i18n("ready", "已完成")}</small></div>'
        )
    return f'<section class="flow" aria-label="Memory workflow">{"".join(steps)}</section>'


def _session_rows(data: DashboardData, merged_patches: set[str]) -> str:
    rows: list[str] = []
    for session in reversed(data.sessions[-8:]):
        patch = data.root / ".vibewiki" / "patches" / session.name
        sections = parse_sections(read_text_if_exists(session / "session.md"))
        goal = sections.get("Goal", session.name).strip().splitlines()[0]
        outcome = sections.get("Final Outcome", "").strip().splitlines()
        detail = outcome[0] if outcome and outcome[0] != "Not provided." else session.name
        if not patch.exists():
            state = "captured"
            state_zh = "已记录"
            status_class = ""
            action = (
                f'<form method="post" action="/action/distill"><input type="hidden" name="session" value="{_escape(session.name)}">'
                f'<button class="primary" type="submit">{_i18n("Distill", "生成记忆")}</button></form>'
            )
            reviewed = "-"
        else:
            decisions = read_item_decisions(data.root, session.name)
            reviewed = str(len(decisions))
            approved = _patch_approved(data.root, session.name)
            if session.name in merged_patches:
                state, state_zh, status_class = "merged", "已合并", "merged"
            elif approved:
                state, state_zh, status_class = "approved", "已批准", "approved"
            else:
                state, state_zh, status_class = "candidate", "待审核", "candidate"
            actions = [
                f'<a class="button secondary" href="/review?patch={_escape(session.name)}">{_i18n("Review", "审核")}</a>'
            ]
            if approved and session.name not in merged_patches:
                actions.append(
                    f'<form method="post" action="/action/merge"><input type="hidden" name="patch" value="{_escape(session.name)}">'
                    f'<button class="primary" type="submit">{_i18n("Merge", "合并")}</button></form>'
                )
            action = "".join(actions)
        rows.append(
            f'<div class="queue-row"><div class="queue-title"><strong>{_escape(goal)}</strong><small>{_escape(detail)}</small></div>'
            f'<span class="status {status_class}">{_i18n(state, state_zh)}</span>'
            f'<span class="review-count">{_escape(reviewed)} {_i18n("decisions", "项已审")}</span>'
            f'<div class="row-actions">{action}</div></div>'
        )
    return "".join(rows)


def _memory_rows(cards: list[object], root: Path) -> str:
    rows: list[str] = []
    for card in cards:
        title = getattr(card, "subject", "") or getattr(card, "title", "")
        kind = getattr(card, "kind", "memory")
        status = getattr(card, "status", "candidate")
        confidence = getattr(card, "confidence", "")
        actor = getattr(card, "actor", "unknown")
        rows.append(
            f'<div class="memory-row"><strong>{_escape(title)}</strong><div class="memory-meta">'
            f'<span class="status {"approved" if status == "approved" else "candidate"}">{_escape(status)}</span>'
            f'<span>{_escape(kind)}</span><span>{_escape(confidence)}</span><span>@{_escape(actor)}</span></div></div>'
        )
    return "".join(rows)


def _kind_bars(rows: list[tuple[str, int]], max_value: int) -> str:
    rendered: list[str] = []
    for kind, count in rows:
        width = max(4.0, count / max_value * 100)
        rendered.append(
            f'<div class="bar-row"><span>{_escape(kind)}</span><div class="bar-track">'
            f'<div class="bar-fill" style="width:{width:.1f}%"></div></div><strong>{count}</strong></div>'
        )
    return "".join(rendered)


def _metric(value: int, en: str, zh: str, detail_en: str, detail_zh: str) -> str:
    return (
        f'<article class="metric"><b>{value}</b><span>{_i18n(en, zh)}</span>'
        f'<small>{_i18n(detail_en, detail_zh)}</small></article>'
    )


def _message(en: str, zh: str) -> str:
    if not en and not zh:
        return ""
    return f'<div class="message">{_i18n(en or zh, zh or en)}</div>'


def _result_panel(title: str, title_zh: str, text: str) -> str:
    if not text:
        return ""
    return f"""<div class="result">
  <div class="result-head"><h3>{_i18n(title or "Result", title_zh or "结果")}</h3><button type="button" data-copy-result>{_i18n("Copy", "复制")}</button></div>
  <pre data-result-output>{_escape(text)}</pre>
</div>"""


def _empty(en: str, zh: str) -> str:
    return f'<div class="empty">{_i18n(en, zh)}</div>'


def _patch_approved(root: Path, session_id: str) -> bool:
    review = root / ".vibewiki" / "reviews" / f"{session_id}.yaml"
    return "decision: approved" in read_text_if_exists(review)


def _merged_patch_ids(root: Path) -> set[str]:
    merged: set[str] = set()
    for event in read_events(root, event_type="merge", limit=None):
        subject = str(event.get("subject", "")).strip()
        data = event.get("data", {})
        if subject:
            merged.add(subject)
        if isinstance(data, dict):
            patch_dir = str(data.get("patch_dir", "")).strip()
            if patch_dir:
                merged.add(Path(patch_dir).name)
    return merged


def _session_dir(root: Path, session_id: str) -> Path:
    if not session_id:
        raise ValueError("Session is required.")
    base = (root / ".vibewiki" / "sessions").resolve()
    selected = (base / session_id).resolve()
    if selected.parent != base or not selected.is_dir():
        raise FileNotFoundError(f"Session not found: {session_id}")
    return selected


def _patch_dir(root: Path, patch_id: str) -> Path:
    if not patch_id:
        patches = sorted(path for path in (root / ".vibewiki" / "patches").glob("*") if path.is_dir())
        if not patches:
            raise FileNotFoundError("No candidate memory exists yet.")
        return patches[-1].resolve()
    base = (root / ".vibewiki" / "patches").resolve()
    selected = (base / patch_id).resolve()
    if selected.parent != base or not selected.is_dir():
        raise FileNotFoundError(f"Candidate memory not found: {patch_id}")
    return selected


def _value(data: dict[str, list[str]], key: str) -> str:
    return data.get(key, [""])[0].strip()


def _text(data: dict[str, list[str]], key: str) -> str:
    return data.get(key, [""])[0]


def _i18n(en: str, zh: str) -> str:
    return f'<span data-i18n data-en="{_escape(en)}" data-zh="{_escape(zh)}">{_escape(en)}</span>'


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)
