from __future__ import annotations

from dataclasses import asdict, dataclass
import html
import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import secrets
import socketserver
from urllib.parse import parse_qs, urlencode, urlparse
import uuid

from .assurance import (
    AssuranceReport,
    build_assurance_report,
    load_assurance_policy,
)
from .capture import capture_session
from .conversations import (
    ConversationRecord,
    delete_conversation,
    get_conversation_detail,
    list_conversations,
    plan_conversation_deletion,
    search_conversations,
    update_conversation_flags,
)
from .dashboard import DashboardData, build_dashboard_data
from .distill import distill_session, parse_sections
from .events import append_event, read_events
from .import_markdown import import_markdown_session
from .import_url import import_url_session
from .llm import (
    chat_completion,
    clear_local_llm_settings,
    llm_settings,
    read_local_llm_settings,
    save_local_llm_settings,
)
from .merge import merge_patches
from .project import ensure_workspace
from .project_understanding import build_project_brief, render_project_brief_markdown
from .retrieval import answer_question, build_context_pack, load_retrieval_config
from .review import read_item_decisions, review_patches
from .review_ui import perform_review_action, render_markdown_html, render_review_ui
from .text_utils import read_text_if_exists, slugify, utcish_timestamp


REVIEW_ACTIONS = {
    "/item-action",
    "/decision",
    "/bulk-decision",
    "/save-item",
    "/patch-review",
    "/approve-and-merge",
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


@dataclass(frozen=True)
class DistillAutomationResult:
    generated: bool
    auto_promoted: bool = False
    attention_count: int = 0


def render_control_center(
    project: Path,
    *,
    message: str = "",
    message_zh: str = "",
    result_title: str = "",
    result_title_zh: str = "",
    result_text: str = "",
    csrf_token: str = "",
) -> str:
    root = project.resolve()
    ensure_workspace(root)
    data = build_dashboard_data(root)
    approved_cards = data.status_counts.get("approved", 0)
    merged_patches = _merged_patch_ids(root)
    assurance_policy = load_assurance_policy(root)
    manual_review = assurance_policy.mode != "exceptions"
    assurance_reports = {
        patch.name: build_assurance_report(root, patch_dir=patch)
        for patch in data.patches
        if patch.name not in merged_patches
    }
    pending_reviews = (
        len(assurance_reports)
        if manual_review
        else sum(
            report.attention_count
            for report in assurance_reports.values()
            if report.needs_attention
        )
    ) + sum(
        1
        for session in data.sessions
        if not (root / ".vibewiki" / "patches" / session.name).exists()
    )
    config = load_retrieval_config(root)
    configured_llm = llm_settings(
        base_url_env=config.llm_base_url_env,
        api_key_env=config.llm_api_key_env,
        model_env=config.llm_model_env,
        project=root,
    )
    local_llm = read_local_llm_settings(root)
    form_llm = local_llm or configured_llm
    form_provider = form_llm.provider if form_llm else "minimax"
    form_base_url = form_llm.base_url if form_llm else "https://api.minimaxi.com/v1"
    form_model = form_llm.model if form_llm else "MiniMax-M2.7"
    llm_status_en = f"{configured_llm.model} configured" if configured_llm else "Local mode"
    llm_status_zh = f"已配置 {configured_llm.model}" if configured_llm else "本地模式"
    llm_source_en = (
        "Managed by environment variables"
        if configured_llm and configured_llm.source == "environment"
        else "Stored only in this project"
        if local_llm
        else "No model API configured"
    )
    llm_source_zh = (
        "由环境变量管理"
        if configured_llm and configured_llm.source == "environment"
        else "仅保存在当前项目"
        if local_llm
        else "尚未配置模型 API"
    )
    api_key_placeholder_en = (
        "Saved; leave blank to keep it"
        if local_llm and local_llm.api_key
        else "API key (optional for local models)"
    )
    api_key_placeholder_zh = (
        "已保存；留空则保留"
        if local_llm and local_llm.api_key
        else "API Key（本地模型可留空）"
    )
    disconnect_button = (
        f'<button class="disconnect" type="submit" name="settings_action" value="disconnect" formnovalidate>'
        f'{_i18n("Disconnect", "断开连接")}</button>'
        if local_llm
        else ""
    )
    latest_cards = sorted(data.cards, key=lambda card: card.source.as_posix(), reverse=True)[:6]
    session_rows = _session_rows(
        data,
        merged_patches,
        assurance_reports,
        manual_review=manual_review,
    )
    conversations = list_conversations(root)
    conversation_rows = _conversation_rows(root, conversations)
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
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%2317232D'/%3E%3Cpath d='M12 16c7-1 14 1 18 4l2 29c-6-5-13-7-20-7V16Z' fill='%23F5F8F5'/%3E%3Cpath d='M52 16c-7-1-14 1-18 4l-2 29c6-5 13-7 20-7V16Z' fill='%232AA397'/%3E%3C/svg%3E">
  <style>
    :root {{
      color-scheme: light;
      --ink: #1d1d1f;
      --muted: #6e6e73;
      --subtle: #86868b;
      --line: rgba(29, 29, 31, .10);
      --line-strong: rgba(29, 29, 31, .16);
      --canvas: #f5f5f7;
      --paper: #ffffff;
      --soft: #f0f0f2;
      --teal: #137f77;
      --teal-soft: #edf8f6;
      --gold: #d99a1b;
      --coral: #d96b52;
      --blue: #0071e3;
      --green: #2f7d4c;
      --danger: #c43f4f;
      --sidebar: rgba(249, 249, 251, .86);
      --shadow: 0 1px 2px rgba(0, 0, 0, .035), 0 12px 36px rgba(0, 0, 0, .045);
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      background: var(--canvas);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", Inter, system-ui, sans-serif;
      line-height: 1.45;
      letter-spacing: 0;
      -webkit-font-smoothing: antialiased;
    }}
    button, input, textarea, select {{ font: inherit; letter-spacing: 0; }}
    button, .button {{
      min-height: 36px;
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      padding: 7px 13px;
      background: var(--paper);
      color: var(--ink);
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
      text-decoration: none;
      white-space: nowrap;
      transition: background-color .16s ease, border-color .16s ease, box-shadow .16s ease;
    }}
    button:hover, .button:hover {{ border-color: rgba(29, 29, 31, .28); background: #fbfbfd; }}
    button.primary, .button.primary {{ background: var(--teal); border-color: var(--teal); color: #fff; box-shadow: 0 1px 2px rgba(19, 127, 119, .22); }}
    button.primary:hover, .button.primary:hover {{ background: #0f716a; border-color: #0f716a; }}
    button.secondary, .button.secondary {{ color: var(--blue); }}
    button.quiet, .button.quiet {{ background: rgba(255,255,255,.58); color: var(--muted); }}
    input, textarea, select {{
      width: 100%;
      border: 1px solid var(--line-strong);
      border-radius: 8px;
      background: rgba(255, 255, 255, .92);
      color: var(--ink);
      padding: 10px 12px;
      font-size: 14px;
      box-shadow: inset 0 1px 1px rgba(0, 0, 0, .02);
      transition: border-color .16s ease, box-shadow .16s ease;
    }}
    input:focus, textarea:focus, select:focus {{ outline: 0; border-color: rgba(0, 113, 227, .58); box-shadow: 0 0 0 3px rgba(0, 113, 227, .12); }}
    textarea {{ min-height: 128px; resize: vertical; }}
    label {{ display: grid; gap: 6px; color: var(--muted); font-size: 12px; font-weight: 600; }}
    .app {{ min-height: 100vh; display: grid; grid-template-columns: 236px minmax(0, 1fr); }}
    .sidebar {{
      position: sticky;
      top: 0;
      height: 100vh;
      padding: 24px 16px 18px;
      background: var(--sidebar);
      border-right: 1px solid var(--line);
      color: var(--ink);
      display: flex;
      flex-direction: column;
      gap: 28px;
      -webkit-backdrop-filter: saturate(180%) blur(24px);
      backdrop-filter: saturate(180%) blur(24px);
    }}
    .brand {{ display: flex; align-items: center; gap: 11px; padding: 0 5px; color: var(--ink); text-decoration: none; }}
    .brand-mark {{
      width: 40px;
      height: 40px;
      display: block;
      flex: 0 0 auto;
      filter: drop-shadow(0 3px 7px rgba(23, 35, 45, .14));
    }}
    .brand-mark svg {{ display: block; width: 100%; height: 100%; }}
    .brand strong {{ display: block; font-size: 16px; line-height: 1.2; font-weight: 680; }}
    .brand small {{ display: block; margin-top: 3px; color: var(--subtle); font-size: 11px; }}
    nav {{ display: grid; gap: 3px; }}
    nav a {{
      position: relative;
      min-height: 38px;
      display: flex;
      align-items: center;
      padding: 8px 12px 8px 29px;
      border-radius: 8px;
      color: var(--muted);
      text-decoration: none;
      font-size: 13px;
      font-weight: 590;
    }}
    nav a::before {{ content: ""; position: absolute; left: 13px; width: 6px; height: 6px; border-radius: 50%; background: #c7c7cc; }}
    nav a:hover {{ background: rgba(0, 0, 0, .035); color: var(--ink); }}
    nav a.active {{ background: rgba(0, 0, 0, .055); color: var(--ink); font-weight: 650; }}
    nav a.active::before {{ background: var(--teal); box-shadow: 0 0 0 3px rgba(19,127,119,.12); }}
    .side-status {{ margin-top: auto; padding: 15px 11px 2px; border-top: 1px solid var(--line); }}
    .side-status span {{ display: block; color: var(--subtle); font-size: 10px; text-transform: uppercase; }}
    .side-status strong {{ display: block; margin-top: 4px; font-size: 12px; font-weight: 600; overflow-wrap: anywhere; }}
    .main {{ width: 100%; max-width: 1480px; min-width: 0; margin: 0 auto; padding: 30px 34px 56px; }}
    .topbar {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 22px; }}
    .topbar h1 {{ margin: 0; font-size: 32px; line-height: 1.08; font-weight: 720; }}
    .topbar p {{ margin: 7px 0 0; color: var(--muted); font-size: 12px; }}
    .top-actions {{ display: flex; align-items: center; gap: 8px; }}
    .language {{ display: inline-flex; padding: 3px; border: 1px solid var(--line); border-radius: 8px; background: rgba(255,255,255,.72); box-shadow: 0 1px 2px rgba(0,0,0,.03); }}
    .language button {{ min-width: 41px; min-height: 28px; padding: 3px 8px; border: 0; border-radius: 6px; background: transparent; color: var(--muted); box-shadow: none; }}
    .language button.active {{ background: var(--ink); color: #fff; }}
    .message {{
      margin-bottom: 16px;
      padding: 11px 14px;
      border: 1px solid rgba(19, 127, 119, .20);
      border-radius: 8px;
      background: var(--teal-soft);
      color: #135f59;
      font-size: 13px;
    }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-bottom: 12px; border: 1px solid var(--line); border-radius: 8px; background: rgba(255,255,255,.82); box-shadow: var(--shadow); overflow: hidden; }}
    .metric {{ min-height: 91px; padding: 15px 18px; border-right: 1px solid var(--line); }}
    .metric:last-child {{ border-right: 0; }}
    .metric b {{ display: block; margin-bottom: 9px; font-size: 27px; line-height: 1; font-weight: 680; font-variant-numeric: tabular-nums; }}
    .metric span {{ color: var(--ink); font-size: 11px; font-weight: 650; }}
    .metric small {{ display: block; margin-top: 2px; color: var(--subtle); font-size: 10px; }}
    .flow {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255,255,255,.62);
      margin-bottom: 18px;
      overflow: hidden;
    }}
    .flow-step {{ position: relative; min-height: 63px; padding: 11px 13px 10px 46px; border-right: 1px solid var(--line); }}
    .flow-step:last-child {{ border-right: 0; }}
    .step-num {{ position: absolute; left: 14px; top: 17px; width: 23px; height: 23px; display: grid; place-items: center; border-radius: 50%; background: #e8e8ed; color: var(--muted); font-size: 10px; font-weight: 700; }}
    .flow-step.done .step-num {{ background: var(--green); color: #fff; }}
    .flow-step.current {{ box-shadow: inset 0 -2px var(--gold); }}
    .flow-step strong {{ display: block; font-size: 12px; font-weight: 650; }}
    .flow-step small {{ color: var(--subtle); font-size: 10px; }}
    .columns {{ display: grid; grid-template-columns: minmax(0, 1.16fr) minmax(340px, .84fr); gap: 16px; align-items: start; }}
    .panel {{ min-width: 0; margin-bottom: 16px; border: 1px solid var(--line); border-radius: 8px; background: rgba(255,255,255,.88); box-shadow: var(--shadow); overflow: hidden; }}
    .panel-head {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--line); }}
    .panel-head h2 {{ margin: 0; font-size: 15px; font-weight: 670; }}
    .panel-head small {{ color: var(--subtle); font-size: 10px; }}
    .panel-body {{ padding: 15px 16px 16px; }}
    .command-center {{ margin-bottom: 16px; }}
    .command-head {{ padding: 16px 18px 14px; }}
    .command-title {{ display: flex; align-items: center; gap: 10px; }}
    .command-icon {{ width: 23px; height: 23px; display: block; flex: 0 0 auto; color: var(--teal); }}
    .command-icon svg {{ display: block; width: 100%; height: 100%; }}
    .command-head h2 {{ font-size: 16px; }}
    .connection {{ display: inline-flex; align-items: center; gap: 6px; color: var(--subtle); font-size: 10px; }}
    .connection::before {{ content: ""; width: 7px; height: 7px; border-radius: 50%; background: #34c759; box-shadow: 0 0 0 3px rgba(52,199,89,.10); }}
    .command-body {{ display: grid; grid-template-columns: minmax(0, 1.12fr) minmax(320px, .88fr); gap: 12px; padding: 15px 16px 16px; }}
    .command-body form {{ min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }}
    .command-body input {{ min-width: 0; height: 40px; }}
    .command-body button {{ min-height: 40px; }}
    .tabs {{ display: flex; gap: 3px; padding: 3px; border-radius: 8px; background: var(--soft); margin-bottom: 14px; }}
    .tabs button {{ flex: 1; min-height: 34px; border: 0; background: transparent; color: var(--muted); }}
    .tabs button.active {{ background: #fff; color: var(--ink); box-shadow: 0 1px 4px rgba(0,0,0,.10); }}
    .tab-panel[hidden] {{ display: none; }}
    .form-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
    .form-stack {{ display: grid; gap: 10px; }}
    .form-actions {{ display: flex; gap: 8px; align-items: center; justify-content: space-between; flex-wrap: wrap; }}
    .check {{ display: inline-flex; grid-template-columns: auto 1fr; align-items: center; gap: 7px; color: var(--muted); font-size: 12px; }}
    .check input {{ width: auto; }}
    .result {{ border-top: 1px solid var(--line); padding: 14px 16px; background: #f8faf8; }}
    .result-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }}
    .result h3 {{ margin: 0; font-size: 13px; }}
    pre {{
      max-height: 380px;
      margin: 0;
      padding: 12px;
      overflow: auto;
      border-radius: 8px;
      background: #1d1d1f;
      color: #edf4f1;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font: 12px/1.55 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .queue {{ display: grid; }}
    .queue-row {{ display: grid; grid-template-columns: minmax(0, 1.5fr) 112px 114px auto; gap: 12px; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--line); }}
    .queue-row:last-child {{ border-bottom: 0; }}
    .queue-title {{ min-width: 0; }}
    .queue-title strong {{ display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }}
    .queue-title small {{ color: var(--muted); font-size: 11px; }}
    .status {{ display: inline-flex; width: fit-content; padding: 3px 8px; border: 1px solid var(--line); border-radius: 999px; color: var(--muted); font-size: 10px; font-weight: 650; }}
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
    .bar-track {{ height: 7px; border-radius: 4px; background: var(--soft); overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 3px; background: var(--blue); }}
    .bar-row:nth-child(2n) .bar-fill {{ background: var(--gold); }}
    .bar-row:nth-child(3n) .bar-fill {{ background: var(--coral); }}
    .empty {{ padding: 24px 16px; color: var(--muted); font-size: 13px; text-align: center; }}
    details.advanced {{ border-top: 1px solid var(--line); }}
    details.advanced summary {{ padding: 13px 16px; cursor: pointer; color: var(--muted); font-size: 12px; font-weight: 650; }}
    .advanced-body {{ display: flex; gap: 8px; padding: 0 16px 16px; flex-wrap: wrap; }}
    .button-icon {{ display: inline-flex; align-items: center; gap: 6px; }}
    .button-icon svg {{ width: 14px; height: 14px; }}
    .visually-hidden {{ position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }}
    @media (max-width: 1050px) {{
      .command-body {{ grid-template-columns: 1fr; }}
      .columns {{ grid-template-columns: 1fr; }}
      .queue-row {{ grid-template-columns: minmax(0, 1fr) 110px auto; }}
      .queue-row .review-count {{ display: none; }}
    }}
    @media (max-width: 820px) {{
      .app {{ grid-template-columns: 1fr; }}
      .sidebar {{ position: sticky; z-index: 20; height: auto; padding: 10px 12px 8px; display: grid; grid-template-columns: 1fr; gap: 8px; overflow: visible; border-right: 0; border-bottom: 1px solid var(--line); }}
      .brand {{ padding: 0; }}
      .brand-mark {{ width: 34px; height: 34px; }}
      .brand small, .side-status {{ display: none; }}
      nav {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); width: 100%; }}
      nav a {{ min-height: 33px; justify-content: center; padding: 6px 4px; white-space: nowrap; }}
      nav a::before {{ display: none; }}
      .main {{ padding: 22px 16px 40px; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .metric:nth-child(2) {{ border-right: 0; }}
      .metric:nth-child(-n+2) {{ border-bottom: 1px solid var(--line); }}
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
      .command-body form {{ grid-template-columns: 1fr; }}
      .queue-row {{ grid-template-columns: 1fr; }}
      .row-actions {{ justify-content: flex-start; }}
      .topbar {{ display: block; }}
      .top-actions {{ margin-top: 10px; }}
    }}

    /* Focused workspace layout */
    :root {{
      --canvas: #f6f7f9;
      --paper: #ffffff;
      --soft: #eef1f4;
      --ink: #161719;
      --muted: #65686d;
      --subtle: #92959a;
      --line: rgba(22, 23, 25, .09);
      --line-strong: rgba(22, 23, 25, .15);
      --teal: #087f75;
      --blue: #0a71d8;
      --shadow: 0 18px 60px rgba(28, 37, 44, .07), 0 2px 8px rgba(28, 37, 44, .04);
    }}
    body {{ min-width: 320px; background: var(--canvas); }}
    .app {{ display: block; min-height: 100vh; }}
    .sidebar {{
      position: sticky;
      z-index: 30;
      top: 0;
      width: 100%;
      height: 68px;
      padding: 10px max(24px, calc((100vw - 1180px) / 2));
      display: grid;
      grid-template-columns: auto minmax(360px, 1fr) auto;
      align-items: center;
      gap: 22px;
      border: 0;
      border-bottom: 1px solid var(--line);
      background: rgba(249, 250, 251, .84);
      -webkit-backdrop-filter: saturate(180%) blur(26px);
      backdrop-filter: saturate(180%) blur(26px);
    }}
    .brand {{ gap: 10px; padding: 0; }}
    .brand-mark {{ width: 36px; height: 36px; filter: drop-shadow(0 4px 8px rgba(20, 35, 45, .13)); }}
    .brand strong {{ font-size: 15px; font-weight: 700; }}
    .brand small {{ margin-top: 1px; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; }}
    nav {{ display: flex; justify-content: center; gap: 4px; }}
    nav a {{
      min-height: 38px;
      padding: 8px 11px;
      display: inline-flex;
      justify-content: center;
      gap: 7px;
      border: 1px solid transparent;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 620;
      white-space: nowrap;
    }}
    nav a::before {{ display: none; }}
    nav a svg {{ width: 16px; height: 16px; flex: 0 0 auto; }}
    nav a:hover {{ background: rgba(255, 255, 255, .7); }}
    nav a.active {{ border-color: var(--line); background: #fff; box-shadow: 0 1px 4px rgba(24, 31, 37, .07); }}
    .nav-badge {{
      min-width: 18px;
      height: 18px;
      padding: 0 5px;
      display: inline-grid;
      place-items: center;
      border-radius: 9px;
      background: #e7edf1;
      color: #5e646a;
      font-size: 9px;
      font-variant-numeric: tabular-nums;
    }}
    nav a.active .nav-badge {{ background: #dff3ef; color: #176e66; }}
    .top-actions {{ display: flex; align-items: center; justify-content: flex-end; gap: 8px; margin: 0; }}
    .memory-state {{ display: inline-flex; align-items: center; gap: 6px; color: var(--muted); font-size: 10px; white-space: nowrap; }}
    .memory-state i, .bridge-state i {{ width: 6px; height: 6px; border-radius: 50%; background: #24a06f; box-shadow: 0 0 0 3px rgba(36, 160, 111, .10); }}
    .language {{ background: rgba(237, 239, 242, .78); box-shadow: none; }}
    .language button {{ min-width: 34px; min-height: 26px; font-size: 10px; }}
    .icon-button {{ width: 34px; min-width: 34px; min-height: 34px; padding: 0; display: grid; place-items: center; }}
    .icon-button svg {{ width: 15px; height: 15px; }}
    .settings-trigger {{ border-color: transparent; background: transparent; }}
    .settings-trigger:hover {{ border-color: var(--line); background: #fff; }}
    .main {{ width: 100%; max-width: 1420px; margin: 0 auto; padding: 40px 30px 72px; }}
    .message {{ max-width: 980px; margin: 0 auto 22px; }}
    [data-view-panel] {{ display: none; }}
    .app[data-active-view="ask"] [data-view-panel="ask"],
    .app[data-active-view="add"] [data-view-panel="add"],
    .app[data-active-view="attention"] [data-view-panel="attention"],
    .app[data-active-view="memory"] [data-view-panel="memory"] {{ display: block; }}
    .command-center {{ max-width: 980px; margin: 54px auto 0; }}
    .ask-hero {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; margin-bottom: 30px; }}
    .eyebrow {{ color: var(--teal); font: 700 10px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace; text-transform: uppercase; }}
    .ask-hero h1 {{ margin: 12px 0 0; font-size: 44px; line-height: 1.06; font-weight: 720; }}
    .ask-hero p {{ margin: 9px 0 0; color: var(--muted); font-size: 13px; }}
    .connection {{ margin-top: 3px; padding: 7px 10px; border: 1px solid var(--line); border-radius: 8px; background: rgba(255,255,255,.58); }}
    .query-switch {{ width: fit-content; display: inline-flex; gap: 3px; margin-bottom: 10px; padding: 3px; border-radius: 8px; background: #e9ecef; }}
    .query-switch button {{ min-height: 31px; padding: 5px 10px; display: inline-flex; align-items: center; gap: 6px; border: 0; background: transparent; color: var(--muted); font-size: 11px; box-shadow: none; }}
    .query-switch button svg {{ width: 14px; height: 14px; }}
    .query-switch button.active {{ background: #fff; color: var(--ink); box-shadow: 0 1px 4px rgba(24,31,37,.10); }}
    .query-panel[hidden] {{ display: none; }}
    .ask-form {{
      min-height: 70px;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: center;
      gap: 10px;
      padding: 8px 9px 8px 20px;
      border: 1px solid rgba(18, 24, 28, .13);
      border-radius: 8px;
      background: #fff;
      box-shadow: var(--shadow);
    }}
    .ask-form:focus-within {{ border-color: rgba(10, 113, 216, .45); box-shadow: 0 0 0 4px rgba(10,113,216,.08), var(--shadow); }}
    .ask-form input {{ height: 52px; padding: 0; border: 0; background: transparent; box-shadow: none; font-size: 17px; }}
    .ask-form input:focus {{ box-shadow: none; }}
    .send-button {{ width: 48px; min-width: 48px; height: 48px; padding: 0; display: grid; place-items: center; }}
    .send-button svg {{ width: 19px; height: 19px; }}
    .system-strip {{
      margin-top: 34px;
      padding: 17px 2px;
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 18px;
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      color: var(--muted);
      font-size: 10px;
    }}
    .system-strip span {{ min-width: 0; display: flex; align-items: center; gap: 8px; white-space: nowrap; }}
    .system-strip b {{ color: var(--ink); font-size: 16px; font-weight: 660; font-variant-numeric: tabular-nums; }}
    .bridge-state {{ justify-content: flex-end; color: #28775d; }}
    .result {{ margin-top: 18px; border: 1px solid var(--line); border-radius: 8px; background: #fff; overflow: hidden; }}
    .result-head {{ margin: 0; padding: 10px 12px; border-bottom: 1px solid var(--line); }}
    .result pre {{ max-height: 430px; border-radius: 0; }}
    .columns {{ display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(300px, .75fr); gap: 16px; align-items: start; }}
    .columns > div {{ display: contents; }}
    .panel {{ margin: 28px 0 0; border-color: var(--line); background: rgba(255,255,255,.88); box-shadow: 0 8px 32px rgba(27, 36, 43, .045); }}
    .focus-panel {{ grid-column: 1 / -1; max-width: 940px; width: 100%; margin: 28px auto 0; }}
    .memory-panel {{ grid-column: 1; }}
    .memory-insights {{ grid-column: 2; }}
    .panel-head {{ min-height: 62px; padding: 17px 20px; }}
    .panel-head h2 {{ font-size: 18px; font-weight: 680; }}
    .section-count {{ min-width: 26px; height: 24px; padding: 0 7px; display: inline-grid; place-items: center; border-radius: 8px; background: #eef1f3; color: var(--muted); font-size: 10px; font-weight: 700; }}
    .attention-count {{ background: #fff0eb; color: #a65540; }}
    .panel-body {{ padding: 19px 20px 21px; }}
    .tabs {{ margin-bottom: 18px; }}
    .form-stack {{ gap: 14px; }}
    .form-stack textarea {{ min-height: 210px; }}
    .conversation-workspace {{
      grid-column: 1 / -1;
      width: 100%;
      grid-template-columns: minmax(280px, .78fr) minmax(380px, 1.24fr) minmax(300px, .86fr);
      gap: 14px;
      align-items: start;
    }}
    .app[data-active-view="add"] .conversation-workspace {{ display: grid; }}
    .conversation-workspace .panel {{ margin-top: 28px; }}
    .import-panel .form-grid {{ grid-template-columns: 1fr; }}
    .import-panel textarea {{ min-height: 216px; }}
    .conversation-reader, .conversation-library {{ min-width: 0; }}
    .conversation-reader {{ min-height: 650px; }}
    .reader-heading {{ min-width: 0; }}
    .reader-heading h2 {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .reader-heading small {{ display: block; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .reader-empty {{ min-height: 585px; display: grid; place-items: center; padding: 28px; color: var(--muted); text-align: center; }}
    .reader-empty[hidden], .reader-body[hidden] {{ display: none; }}
    .reader-meta {{
      min-height: 43px;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 10px 16px;
      border-bottom: 1px solid var(--line);
      color: var(--subtle);
      font-size: 10px;
      overflow: hidden;
    }}
    .reader-meta span {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .reader-transcript {{
      height: 470px;
      padding: 22px 24px 32px;
      overflow: auto;
      overscroll-behavior: contain;
      background: #fff;
    }}
    .reader-transcript h1 {{ margin: 0 0 18px; font-size: 24px; line-height: 1.18; }}
    .reader-transcript h2 {{ margin: 28px 0 10px; font-size: 18px; }}
    .reader-transcript h3, .reader-transcript h4 {{ margin: 22px 0 8px; font-size: 15px; }}
    .reader-transcript p, .reader-transcript li, .reader-transcript blockquote {{ color: #34373a; font-size: 13px; line-height: 1.68; }}
    .reader-transcript p {{ margin: 0 0 12px; }}
    .reader-transcript ul, .reader-transcript ol {{ margin: 8px 0 16px; padding-left: 22px; }}
    .reader-transcript blockquote {{ margin: 14px 0; padding: 2px 0 2px 14px; border-left: 2px solid var(--teal); color: var(--muted); }}
    .reader-transcript code {{ padding: 2px 5px; border-radius: 5px; background: #eef1f3; font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .reader-transcript pre {{ max-height: none; margin: 14px 0; }}
    .reader-transcript pre code {{ padding: 0; background: transparent; color: inherit; }}
    .reader-impact {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
      background: #f8f9fa;
    }}
    .reader-impact span {{ padding: 10px 13px; border-right: 1px solid var(--line); color: var(--subtle); font-size: 9px; }}
    .reader-impact span:last-child {{ border-right: 0; }}
    .reader-impact b {{ display: block; margin-bottom: 2px; color: var(--ink); font-size: 15px; }}
    .conversation-curation summary {{ padding: 12px 16px; cursor: pointer; color: var(--muted); font-size: 11px; font-weight: 650; }}
    .curation-form {{ display: grid; gap: 10px; padding: 0 16px 16px; }}
    .curation-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 9px; }}
    .curation-form textarea {{ min-height: 74px; }}
    .curation-actions {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
    .curation-actions .check {{ color: var(--ink); }}
    .conversation-tools {{ padding: 12px 16px; border-bottom: 1px solid var(--line); }}
    .conversation-search {{ position: relative; display: block; }}
    .conversation-search svg {{ position: absolute; left: 11px; top: 50%; width: 15px; height: 15px; color: var(--subtle); transform: translateY(-50%); pointer-events: none; }}
    .conversation-search input {{ height: 36px; padding: 7px 10px 7px 34px; background: #f5f6f7; font-size: 12px; }}
    .conversation-list {{ max-height: 590px; overflow: auto; overscroll-behavior: contain; }}
    .conversation-row {{
      min-width: 0;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 38px;
      border-bottom: 1px solid var(--line);
      transition: background-color .14s ease, box-shadow .14s ease;
    }}
    .conversation-row:last-child {{ border-bottom: 0; }}
    .conversation-row[hidden] {{ display: none; }}
    .conversation-row.selected {{ background: #f1f7f6; box-shadow: inset 2px 0 var(--teal); }}
    .conversation-open {{
      min-width: 0;
      min-height: 104px;
      padding: 14px 8px 14px 16px;
      border: 0;
      border-radius: 0;
      background: transparent;
      text-align: left;
      white-space: normal;
      box-shadow: none;
    }}
    .conversation-open:hover {{ border: 0; background: rgba(19,127,119,.04); }}
    .conversation-copy {{ min-width: 0; }}
    .conversation-title-line {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }}
    .conversation-title-line strong {{ min-width: 0; overflow: hidden; color: var(--ink); font-size: 13px; font-weight: 660; text-overflow: ellipsis; white-space: nowrap; }}
    .conversation-title-line time {{ flex: 0 0 auto; color: var(--subtle); font-size: 9px; font-variant-numeric: tabular-nums; }}
    .conversation-preview {{
      margin: 6px 0 8px;
      display: -webkit-box;
      overflow: hidden;
      color: var(--muted);
      font-size: 11px;
      line-height: 1.45;
      -webkit-box-orient: vertical;
      -webkit-line-clamp: 2;
    }}
    .conversation-meta {{ display: flex; align-items: center; gap: 7px; flex-wrap: wrap; color: var(--subtle); font-size: 9px; }}
    .conversation-meta .status {{ padding: 2px 6px; font-size: 9px; }}
    .pin-mark {{ display: inline-flex; align-items: center; gap: 3px; color: #9a6d12; }}
    .pin-mark svg {{ width: 11px; height: 11px; fill: currentColor; }}
    .delete-trigger {{
      width: 32px;
      min-width: 32px;
      min-height: 32px;
      align-self: center;
      padding: 0;
      display: grid;
      place-items: center;
      border-color: transparent;
      background: transparent;
      color: var(--subtle);
    }}
    .delete-trigger svg {{ width: 15px; height: 15px; }}
    .delete-trigger:hover {{ border-color: rgba(196,63,79,.18); background: #fff3f4; color: var(--danger); }}
    .delete-trigger:disabled {{ cursor: not-allowed; color: #b28325; opacity: .72; }}
    .delete-trigger:disabled:hover {{ border-color: transparent; background: transparent; }}
    .conversation-empty {{ display: none; }}
    .conversation-empty.visible {{ display: block; }}
    .queue-row {{ min-height: 68px; grid-template-columns: minmax(0, 1fr) auto auto; padding: 13px 20px; }}
    .queue-row .review-count {{ display: none; }}
    .queue-title strong {{ font-size: 13px; }}
    .queue-title small {{ display: block; margin-top: 3px; }}
    .memory-row {{ padding: 14px 20px; }}
    .memory-meta {{ flex-wrap: wrap; }}
    .bar-row {{ grid-template-columns: 90px minmax(0,1fr) 24px; }}
    details.advanced summary {{ padding: 14px 20px; }}
    .model-dialog {{
      width: min(560px, calc(100vw - 32px));
      max-height: calc(100vh - 40px);
      padding: 0;
      border: 1px solid rgba(22, 23, 25, .12);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      box-shadow: 0 28px 90px rgba(15, 23, 29, .20), 0 3px 12px rgba(15, 23, 29, .10);
      overflow: auto;
    }}
    .model-dialog::backdrop {{ background: rgba(22, 25, 29, .34); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); }}
    .settings-head {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 22px 24px 18px; border-bottom: 1px solid var(--line); }}
    .settings-head h2 {{ margin: 0; font-size: 20px; font-weight: 700; }}
    .settings-head p {{ margin: 5px 0 0; color: var(--muted); font-size: 11px; }}
    .settings-close {{ width: 32px; min-width: 32px; min-height: 32px; padding: 0; display: grid; place-items: center; border-color: transparent; background: transparent; }}
    .settings-close svg {{ width: 16px; height: 16px; }}
    .settings-body {{ display: grid; gap: 15px; padding: 20px 24px 24px; }}
    .api-state {{ display: flex; align-items: center; gap: 9px; padding-bottom: 2px; color: var(--muted); font-size: 11px; }}
    .api-state i {{ width: 7px; height: 7px; flex: 0 0 auto; border-radius: 50%; background: #a6a8ab; }}
    .api-state.configured i {{ background: #24a06f; box-shadow: 0 0 0 3px rgba(36,160,111,.10); }}
    .settings-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .settings-grid .wide {{ grid-column: 1 / -1; }}
    .secret-hint {{ margin: -8px 0 0; color: var(--subtle); font-size: 10px; }}
    .privacy-note {{ padding: 11px 12px; border-left: 2px solid #38a58d; background: #f4f8f7; color: #52615e; font-size: 10px; }}
    .settings-actions {{ display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding-top: 2px; }}
    .settings-actions .disconnect {{ margin-right: auto; color: var(--danger); }}
    .delete-dialog {{ width: min(500px, calc(100vw - 32px)); }}
    .delete-summary {{ padding: 13px 14px; border: 1px solid var(--line); border-radius: 8px; background: #f7f8f9; }}
    .delete-summary strong {{ display: block; overflow-wrap: anywhere; font-size: 13px; }}
    .delete-summary p {{ margin: 6px 0 0; color: var(--muted); font-size: 11px; }}
    .delete-impact {{ display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    .delete-impact span {{ padding: 12px; border-right: 1px solid var(--line); color: var(--muted); font-size: 9px; }}
    .delete-impact span:last-child {{ border-right: 0; }}
    .delete-impact b {{ display: block; margin-bottom: 4px; color: var(--ink); font-size: 20px; font-weight: 680; }}
    button.danger {{ border-color: var(--danger); background: var(--danger); color: #fff; }}
    button.danger:hover {{ border-color: #ad3342; background: #ad3342; }}

    @media (max-width: 1180px) {{
      .conversation-workspace {{ grid-template-columns: minmax(0, 1.15fr) minmax(300px, .85fr); }}
      .import-panel {{ grid-column: 1 / -1; }}
      .import-panel .form-grid {{ grid-template-columns: 1fr 1fr; }}
    }}
    @media (max-width: 900px) {{
      .sidebar {{ height: auto; min-height: 64px; grid-template-columns: auto 1fr auto; gap: 12px; padding: 9px 16px; }}
      nav a {{ padding: 8px; }}
      nav a svg {{ display: none; }}
      .memory-state {{ display: none; }}
      .columns {{ grid-template-columns: 1fr; }}
      .conversation-workspace {{ grid-template-columns: 1fr; }}
      .import-panel {{ order: 1; }}
      .conversation-library {{ order: 2; margin-top: 0 !important; }}
      .conversation-reader {{ order: 3; margin-top: 0 !important; }}
      .memory-panel, .memory-insights {{ grid-column: 1; }}
      .memory-insights {{ margin-top: 0; }}
    }}
    @media (max-width: 680px) {{
      .sidebar {{ grid-template-columns: 1fr auto; }}
      .brand-mark {{ width: 34px; height: 34px; }}
      .brand small {{ max-width: 120px; }}
      nav {{ grid-column: 1 / -1; grid-row: 2; display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); width: 100%; }}
      nav a {{ min-width: 0; padding: 7px 4px; font-size: 10px; }}
      nav a svg {{ display: block; width: 14px; height: 14px; }}
      .top-actions {{ grid-column: 2; grid-row: 1; }}
      .sidebar {{ padding-bottom: 8px; }}
      .main {{ padding: 26px 16px 48px; }}
      .command-center {{ margin-top: 28px; }}
      .ask-hero {{ margin-bottom: 24px; }}
      .ask-hero h1 {{ font-size: 36px; }}
      .connection {{ font-size: 9px; }}
      .system-strip {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}
      .bridge-state {{ justify-content: flex-start; }}
      .form-grid, .import-panel .form-grid, .curation-grid {{ grid-template-columns: 1fr; }}
      .import-panel .tabs button {{ min-width: 0; padding: 5px 4px; font-size: 10px; white-space: normal; }}
      .reader-transcript {{ padding: 19px 18px 28px; }}
      .queue-row {{ grid-template-columns: 1fr auto; }}
      .queue-row .status {{ display: none; }}
      .model-dialog {{ width: min(560px, calc(100vw - 24px)); }}
    }}
    @media (max-width: 430px) {{
      .brand small, .language {{ display: none; }}
      nav a {{ gap: 4px; }}
      .ask-hero {{ display: block; }}
      .connection {{ width: fit-content; margin-top: 15px; }}
      .ask-form {{ min-height: 62px; padding-left: 14px; }}
      .ask-form input {{ height: 46px; font-size: 15px; }}
      .send-button {{ width: 44px; min-width: 44px; height: 44px; }}
      .system-strip {{ gap: 12px; }}
      .system-strip span {{ white-space: normal; }}
      .panel-head, .panel-body {{ padding-left: 15px; padding-right: 15px; }}
      .queue-row {{ grid-template-columns: 1fr; }}
      .row-actions {{ justify-content: flex-start; }}
      .settings-head, .settings-body {{ padding-left: 17px; padding-right: 17px; }}
      .settings-grid {{ grid-template-columns: 1fr; }}
      .settings-grid .wide {{ grid-column: 1; }}
      .settings-actions {{ flex-wrap: wrap; }}
      .delete-impact {{ grid-template-columns: 1fr; }}
      .delete-impact span {{ border-right: 0; border-bottom: 1px solid var(--line); }}
      .delete-impact span:last-child {{ border-bottom: 0; }}
      .settings-actions .disconnect {{ width: 100%; margin-right: 0; order: 3; }}
    }}
  </style>
</head>
<body>
  <div class="app" data-active-view="ask">
    <aside class="sidebar">
      <a class="brand" href="#ask" data-view-choice="ask">
        <span class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 64 64">
            <rect width="64" height="64" rx="12" fill="#24333F"/>
            <path d="M12 16C19 15 26 17 30 20L32 49C26 44 19 42 12 42V16Z" fill="#F5F8F5"/>
            <path d="M52 16C45 15 38 17 34 20L32 49C38 44 45 42 52 42V16Z" fill="#2AA397"/>
            <path d="M28 54H36" stroke="#F0B84B" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </span>
        <span><strong>VibeWiki</strong><small>{_escape(data.project_name)}</small></span>
      </a>
      <nav aria-label="Primary">
        <a class="active" href="#ask" data-view-choice="ask" aria-selected="true">{_icon("sparkles")}{_i18n("Ask", "提问")}</a>
        <a href="#add" data-view-choice="add" aria-selected="false">{_icon("messages")}{_i18n("Chats", "对话")}</a>
        <a href="#attention" data-view-choice="attention" aria-selected="false">{_icon("bell")}{_i18n("Attention", "待处理")}<b class="nav-badge">{pending_reviews}</b></a>
        <a href="#memory" data-view-choice="memory" aria-selected="false">{_icon("book")}{_i18n("Memory", "记忆")}</a>
      </nav>
      <div class="top-actions">
        <span class="memory-state"><i></i>{approved_cards} {_i18n("trusted", "可信")}</span>
        <div class="language" role="group" aria-label="Language">
          <button type="button" data-lang-choice="en" aria-pressed="true">EN</button>
          <button type="button" data-lang-choice="zh" aria-pressed="false">中文</button>
        </div>
        <button class="quiet icon-button settings-trigger" type="button" data-settings-open title="Model settings" aria-label="Model settings">{_icon("settings")}</button>
      </div>
    </aside>

    <main class="main">
      {message_html}

      <section class="command-center" id="ask" data-view-panel="ask">
        <div class="ask-hero">
          <div>
            <span class="eyebrow">{_i18n("PROJECT MEMORY", "项目记忆")}</span>
            <h1>{_i18n("Ask VibeWiki", "问问 VibeWiki")}</h1>
            <p>{_escape(data.project_name)}</p>
          </div>
          <button class="connection" type="button" data-settings-open>{_i18n(llm_status_en, llm_status_zh)}</button>
        </div>
        <div class="query-switch" role="tablist">
          <button class="active" type="button" data-query-mode="answer" aria-selected="true">{_icon("message")}{_i18n("Answer", "回答")}</button>
          <button type="button" data-query-mode="context" aria-selected="false">{_icon("cpu")}{_i18n("Agent context", "Agent 上下文")}</button>
        </div>
        <div class="query-panel" data-query-panel="answer">
          <form class="ask-form" method="post" action="/action/ask">
            <label class="visually-hidden" for="memory-query">{_i18n("Question", "问题")}</label>
            <input id="memory-query" autofocus required name="query" data-placeholder-en="What should I know?" data-placeholder-zh="我应该知道什么？" placeholder="What should I know?">
            <button class="primary send-button" type="submit" title="Ask" aria-label="Ask">{_icon("arrow")}</button>
          </form>
        </div>
        <div class="query-panel" data-query-panel="context" hidden>
          <form class="ask-form" method="post" action="/action/context">
            <label class="visually-hidden" for="agent-task">{_i18n("Agent task", "Agent 任务")}</label>
            <input id="agent-task" required name="query" data-placeholder-en="Describe the task for your agent" data-placeholder-zh="描述要交给 Agent 的任务" placeholder="Describe the task for your agent">
            <button class="primary send-button" type="submit" title="Build context" aria-label="Build context">{_icon("arrow")}</button>
          </form>
        </div>
        {result_html}
        <div class="system-strip">
          <span><b>{approved_cards}</b>{_i18n("Trusted memories", "可信记忆")}</span>
          <span><b>{pending_reviews}</b>{_i18n("Need attention", "需要处理")}</span>
          <span><b>{len(data.sessions)}</b>{_i18n("Conversations", "历史对话")}</span>
          <span class="bridge-state"><i></i>{_i18n("Agent bridge ready", "Agent 已连接")}</span>
        </div>
      </section>

      <section class="columns">
        <div>
          <section class="conversation-workspace" id="add" data-view-panel="add">
            <section class="panel import-panel">
              <div class="panel-head">
                <h2>{_i18n("Import conversation", "导入对话")}</h2>
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
                      <button class="primary" type="submit">{_i18n("Import", "导入")}</button>
                    </div>
                  </form>
                </div>
                <div class="tab-panel" data-tab-panel="link" hidden>
                  <form class="form-stack" method="post" action="/action/import-url">
                    <label>{_i18n("Shared conversation URL", "对话分享链接")}<input required type="url" name="url" placeholder="https://chatgpt.com/share/..."></label>
                    <label>{_i18n("Name (optional)", "名称（可选）")}<input name="session_name" placeholder="shared-conversation"></label>
                    <div class="form-actions">
                      <label class="check"><input type="checkbox" name="auto_distill" value="yes" checked> {_i18n("Generate memory draft now", "立即生成记忆草稿")}</label>
                      <button class="primary" type="submit">{_i18n("Import", "导入")}</button>
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
                      <button class="primary" type="submit">{_i18n("Save", "保存")}</button>
                    </div>
                  </form>
                </div>
              </div>
            </section>

            <section class="panel conversation-reader" data-conversation-reader aria-live="polite">
              <div class="panel-head">
                <div class="reader-heading">
                  <h2 data-reader-title>{_i18n("Select a conversation", "选择一段对话")}</h2>
                  <small data-reader-subtitle>{_i18n("Read the source before trusting the memory.", "在信任记忆前先查看原始内容。")}</small>
                </div>
              </div>
              <div class="reader-empty" data-reader-empty>
                <span>{_i18n("Choose a conversation from the library.", "从对话库中选择一段对话。")}</span>
              </div>
              <div class="reader-body" data-reader-body hidden>
                <div class="reader-meta">
                  <span data-reader-source></span>
                  <span>·</span>
                  <span data-reader-actor></span>
                  <span>·</span>
                  <span data-reader-file></span>
                </div>
                <div class="reader-transcript" data-reader-transcript></div>
                <div class="reader-impact">
                  <span><b data-reader-memories>0</b>{_i18n("Memory blocks", "记忆块")}</span>
                  <span><b data-reader-files>0</b>{_i18n("Memory files", "记忆文件")}</span>
                  <span><b data-reader-shared>0</b>{_i18n("Shared files", "共同来源文件")}</span>
                </div>
                <details class="conversation-curation">
                  <summary>{_i18n("Pin, rename, tag or note", "置顶、重命名、标签或备注")}</summary>
                  <form class="curation-form" method="post" action="/action/conversation-flags">
                    <input type="hidden" name="csrf_token" value="{_escape(csrf_token)}">
                    <input type="hidden" name="session" value="" data-curation-session>
                    <div class="curation-grid">
                      <label>{_i18n("Display title", "显示标题")}<input name="custom_title" maxlength="160" data-curation-title></label>
                      <label>{_i18n("Tags", "标签")}<input name="tags" data-curation-tags data-placeholder-en="debug, architecture" data-placeholder-zh="调试, 架构" placeholder="debug, architecture"></label>
                    </div>
                    <label>{_i18n("Private note", "私人备注")}<textarea name="note" maxlength="2000" data-curation-note></textarea></label>
                    <div class="curation-actions">
                      <label class="check"><input type="checkbox" name="pinned" value="yes" data-curation-pinned> {_i18n("Keep at top", "置顶保留")}</label>
                      <button class="primary" type="submit">{_i18n("Save", "保存")}</button>
                    </div>
                  </form>
                </details>
              </div>
            </section>

            <aside class="panel conversation-library">
              <div class="panel-head">
                <h2>{_i18n("Conversation library", "对话库")}</h2>
                <span class="section-count">{len(conversations)}</span>
              </div>
              <div class="conversation-tools">
                <label class="conversation-search">
                  <span class="visually-hidden">{_i18n("Search conversations", "搜索对话")}</span>
                  {_icon("search")}
                  <input type="search" data-conversation-search data-placeholder-en="Search conversations" data-placeholder-zh="搜索对话" placeholder="Search conversations">
                </label>
              </div>
              <div class="conversation-list" data-conversation-list>
                {conversation_rows or _empty("No conversations yet", "还没有对话")}
                <div class="empty conversation-empty" data-conversation-empty>{_i18n("No matching conversations", "没有匹配的对话")}</div>
              </div>
            </aside>
          </section>

          <section class="panel focus-panel" id="attention" data-view-panel="attention">
            <div class="panel-head">
              <h2>{_i18n("Needs attention", "需要处理")}</h2>
              <span class="section-count attention-count">{pending_reviews}</span>
            </div>
            <div class="queue">{session_rows or _empty("No exceptions. Memory is up to date.", "没有例外，记忆已是最新状态。")}</div>
          </section>
        </div>

        <div>
          <section class="panel memory-panel" id="memory" data-view-panel="memory">
            <div class="panel-head">
              <h2>{_i18n("Project memory", "项目记忆")}</h2>
              <span class="section-count">{len(data.cards)}</span>
            </div>
            <div class="memory-list">{_memory_rows(latest_cards, root) or _empty("No memory cards yet", "还没有记忆卡片")}</div>
          </section>

          <section class="panel memory-insights" id="memory-insights" data-view-panel="memory">
            <div class="panel-head"><h2>{_i18n("Memory mix", "记忆构成")}</h2></div>
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
  <dialog class="model-dialog" data-model-dialog aria-labelledby="model-settings-title">
    <div class="settings-head">
      <div>
        <h2 id="model-settings-title">{_i18n("Model API", "模型 API")}</h2>
        <p>{_i18n("Use a small model to turn project memory into concise answers.", "使用小模型把项目记忆整理成简洁回答。")}</p>
      </div>
      <button class="settings-close" type="button" data-settings-close title="Close" aria-label="Close">{_icon("x")}</button>
    </div>
    <form class="settings-body" method="post" action="/action/model-settings">
      <input type="hidden" name="csrf_token" value="{_escape(csrf_token)}">
      <div class="api-state {'configured' if configured_llm else ''}"><i></i>{_i18n(llm_source_en, llm_source_zh)}</div>
      <div class="settings-grid">
        <label>{_i18n("Provider", "服务商")}
          <select name="provider" data-provider-select>
            <option value="minimax"{' selected' if form_provider == 'minimax' else ''}>MiniMax</option>
            <option value="openai"{' selected' if form_provider == 'openai' else ''}>OpenAI</option>
            <option value="compatible"{' selected' if form_provider == 'compatible' else ''}>{_escape("OpenAI-compatible / Local")}</option>
          </select>
        </label>
        <label>{_i18n("Model", "模型")}
          <input required name="model" value="{_escape(form_model)}" data-model-input placeholder="MiniMax-M2.7" autocomplete="off">
        </label>
        <label class="wide">{_i18n("Base URL", "Base URL")}
          <input required type="url" name="base_url" value="{_escape(form_base_url)}" data-base-url-input placeholder="https://api.example.com/v1" autocomplete="url">
        </label>
        <label class="wide">{_i18n("API Key", "API Key")}
          <input type="password" name="api_key" data-placeholder-en="{_escape(api_key_placeholder_en)}" data-placeholder-zh="{_escape(api_key_placeholder_zh)}" placeholder="{_escape(api_key_placeholder_en)}" autocomplete="new-password" spellcheck="false">
        </label>
      </div>
      <p class="secret-hint">{_i18n("The key is never shown again. A blank field keeps the saved key.", "密钥不会再次显示；留空会保留已保存的密钥。")}</p>
      <div class="privacy-note">{_i18n("Stored locally with 0600 permissions under .vibewiki/private/ and excluded from Git.", "配置以 0600 权限保存在 .vibewiki/private/，并已排除在 Git 之外。")}</div>
      <div class="settings-actions">
        {disconnect_button}
        <button type="submit" name="settings_action" value="save">{_i18n("Save", "保存")}</button>
        <button class="primary" type="submit" name="settings_action" value="test">{_i18n("Save & test", "保存并测试")}</button>
      </div>
    </form>
  </dialog>
  <dialog class="model-dialog delete-dialog" data-delete-dialog aria-labelledby="delete-conversation-title">
    <div class="settings-head">
      <div>
        <h2 id="delete-conversation-title">{_i18n("Remove conversation", "删除对话")}</h2>
        <p>{_i18n("Review the exact Wiki impact before continuing.", "继续前先确认会影响哪些 Wiki 内容。")}</p>
      </div>
      <button class="settings-close" type="button" data-delete-close title="Close" aria-label="Close">{_icon("x")}</button>
    </div>
    <form class="settings-body" method="post" action="/action/delete-session">
      <input type="hidden" name="csrf_token" value="{_escape(csrf_token)}">
      <input type="hidden" name="session" value="" data-delete-session>
      <div class="delete-summary">
        <strong data-delete-title></strong>
        <p data-delete-note></p>
      </div>
      <div class="delete-impact">
        <span><b data-delete-blocks>0</b>{_i18n("Wiki blocks removed", "撤回的 Wiki 内容块")}</span>
        <span><b data-delete-files>0</b>{_i18n("Wiki files changed", "会修改的 Wiki 文件")}</span>
        <span><b data-delete-shared>0</b>{_i18n("Shared files preserved", "保留共同内容的文件")}</span>
      </div>
      <div class="privacy-note">{_i18n("The raw conversation, drafts, and review records move to .vibewiki/trash/. Content supported by other conversations stays in place.", "原始对话、草稿和审核记录会移入 .vibewiki/trash/；由其他对话共同支持的内容会保留。")}</div>
      <div class="settings-actions">
        <button type="button" data-delete-close>{_i18n("Cancel", "取消")}</button>
        <button class="danger" type="submit">{_i18n("Move to Trash", "移到回收站")}</button>
      </div>
    </form>
  </dialog>
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

      const app = document.querySelector(".app");
      const viewChoices = Array.from(document.querySelectorAll("[data-view-choice]"));
      const viewAliases = {{ overview: "ask", reuse: "ask", work: "attention" }};
      const validViews = new Set(["ask", "add", "attention", "memory"]);
      function setView(requested, updateHash = false) {{
        const aliased = viewAliases[requested] || requested;
        const selected = validViews.has(aliased) ? aliased : "ask";
        if (app) app.dataset.activeView = selected;
        viewChoices.forEach((choice) => {{
          const active = choice.dataset.viewChoice === selected;
          choice.classList.toggle("active", active);
          choice.setAttribute("aria-selected", String(active));
        }});
        if (updateHash) history.replaceState(null, "", `#${{selected}}`);
      }}
      viewChoices.forEach((choice) => choice.addEventListener("click", (event) => {{
        event.preventDefault();
        setView(choice.dataset.viewChoice || "ask", true);
      }}));
      window.addEventListener("hashchange", () => setView(location.hash.slice(1)));
      setView(location.hash.slice(1));

      const settingsDialog = document.querySelector("[data-model-dialog]");
      document.querySelectorAll("[data-settings-open]").forEach((button) => button.addEventListener("click", () => {{
        if (settingsDialog && typeof settingsDialog.showModal === "function") settingsDialog.showModal();
      }}));
      document.querySelectorAll("[data-settings-close]").forEach((button) => button.addEventListener("click", () => settingsDialog?.close()));
      settingsDialog?.addEventListener("click", (event) => {{
        if (event.target === settingsDialog) settingsDialog.close();
      }});

      const providerSelect = document.querySelector("[data-provider-select]");
      const baseUrlInput = document.querySelector("[data-base-url-input]");
      const modelInput = document.querySelector("[data-model-input]");
      const providerPresets = {{
        minimax: {{ baseUrl: "https://api.minimaxi.com/v1", model: "MiniMax-M2.7" }},
        openai: {{ baseUrl: "https://api.openai.com/v1", model: "gpt-4.1-mini" }},
      }};
      providerSelect?.addEventListener("change", () => {{
        const preset = providerPresets[providerSelect.value];
        if (!preset) return;
        if (baseUrlInput) baseUrlInput.value = preset.baseUrl;
        if (modelInput) modelInput.value = preset.model;
      }});

      const queryModeButtons = Array.from(document.querySelectorAll("[data-query-mode]"));
      const queryPanels = Array.from(document.querySelectorAll("[data-query-panel]"));
      queryModeButtons.forEach((button) => button.addEventListener("click", () => {{
        const selected = button.dataset.queryMode;
        queryModeButtons.forEach((item) => {{
          const active = item.dataset.queryMode === selected;
          item.classList.toggle("active", active);
          item.setAttribute("aria-selected", String(active));
        }});
        queryPanels.forEach((panel) => panel.hidden = panel.dataset.queryPanel !== selected);
        const input = document.querySelector(`[data-query-panel="${{selected}}"] input`);
        if (input) input.focus();
      }}));

      const tabButtons = Array.from(document.querySelectorAll("[data-tab]"));
      const tabPanels = Array.from(document.querySelectorAll("[data-tab-panel]"));
      tabButtons.forEach((button) => button.addEventListener("click", () => {{
        const selected = button.dataset.tab;
        tabButtons.forEach((item) => item.classList.toggle("active", item.dataset.tab === selected));
        tabPanels.forEach((panel) => panel.hidden = panel.dataset.tabPanel !== selected);
      }}));

      const conversationSearch = document.querySelector("[data-conversation-search]");
      const conversationRows = Array.from(document.querySelectorAll("[data-conversation-row]"));
      const conversationButtons = Array.from(document.querySelectorAll("[data-conversation-open]"));
      const conversationEmpty = document.querySelector("[data-conversation-empty]");
      const originalPreviews = new Map(
        conversationRows.map((row) => [row.dataset.session || "", row.querySelector("[data-conversation-preview]")?.textContent || ""])
      );
      const readerEmpty = document.querySelector("[data-reader-empty]");
      const readerBody = document.querySelector("[data-reader-body]");
      const readerTitle = document.querySelector("[data-reader-title]");
      const readerSubtitle = document.querySelector("[data-reader-subtitle]");
      const readerSource = document.querySelector("[data-reader-source]");
      const readerActor = document.querySelector("[data-reader-actor]");
      const readerFile = document.querySelector("[data-reader-file]");
      const readerTranscript = document.querySelector("[data-reader-transcript]");
      const readerMemories = document.querySelector("[data-reader-memories]");
      const readerFiles = document.querySelector("[data-reader-files]");
      const readerShared = document.querySelector("[data-reader-shared]");
      const curationSession = document.querySelector("[data-curation-session]");
      const curationTitle = document.querySelector("[data-curation-title]");
      const curationTags = document.querySelector("[data-curation-tags]");
      const curationNote = document.querySelector("[data-curation-note]");
      const curationPinned = document.querySelector("[data-curation-pinned]");

      let conversationRequest = 0;
      async function openConversation(button) {{
        const session = button.dataset.session || "";
        if (!session) return;
        const request = ++conversationRequest;
        conversationRows.forEach((row) => {{
          const selected = row.dataset.session === session;
          row.classList.toggle("selected", selected);
          row.querySelector("[data-conversation-open]")?.setAttribute("aria-pressed", String(selected));
        }});
        if (readerTitle) readerTitle.textContent = button.querySelector("strong")?.textContent || session;
        if (readerSubtitle) readerSubtitle.textContent = document.documentElement.lang === "zh" ? "正在读取原始对话..." : "Loading source conversation...";
        if (readerEmpty) readerEmpty.hidden = true;
        if (readerBody) readerBody.hidden = true;
        try {{
          const response = await fetch("/api/conversation?session=" + encodeURIComponent(session));
          if (!response.ok) throw new Error("HTTP " + response.status);
          const data = await response.json();
          if (request !== conversationRequest) return;
          const conversation = data.conversation || {{}};
          const impact = data.impact || {{}};
          if (readerTitle) readerTitle.textContent = conversation.title || session;
          if (readerSubtitle) readerSubtitle.textContent = conversation.created_at || session;
          if (readerSource) readerSource.textContent = conversation.source || "";
          if (readerActor) readerActor.textContent = "@" + (conversation.recorded_by || "unknown");
          if (readerFile) readerFile.textContent = data.transcript_file || "session.md";
          if (readerTranscript) readerTranscript.innerHTML = data.transcript_html || "<p>No transcript content.</p>";
          if (readerMemories) readerMemories.textContent = String(impact.memory_blocks || 0);
          if (readerFiles) readerFiles.textContent = String((impact.memory_files || []).length);
          if (readerShared) readerShared.textContent = String((impact.shared_files || []).length);
          if (curationSession) curationSession.value = session;
          if (curationTitle) curationTitle.value = conversation.custom_title || "";
          if (curationTags) curationTags.value = (conversation.tags || []).join(", ");
          if (curationNote) curationNote.value = conversation.note || "";
          if (curationPinned) curationPinned.checked = Boolean(conversation.pinned);
          if (readerBody) readerBody.hidden = false;
        }} catch (error) {{
          if (request !== conversationRequest) return;
          if (readerEmpty) {{
            readerEmpty.hidden = false;
            readerEmpty.textContent = document.documentElement.lang === "zh" ? "无法读取这段对话。" : "Could not load this conversation.";
          }}
          if (readerSubtitle) readerSubtitle.textContent = String(error);
        }}
      }}

      conversationButtons.forEach((button) => button.addEventListener("click", () => void openConversation(button)));
      if (conversationButtons.length) void openConversation(conversationButtons[0]);

      let conversationSearchTimer = 0;
      let conversationSearchRequest = 0;
      conversationSearch?.addEventListener("input", () => {{
        const request = ++conversationSearchRequest;
        globalThis.clearTimeout(conversationSearchTimer);
        conversationSearchTimer = globalThis.setTimeout(async () => {{
          const query = (conversationSearch.value || "").trim();
          if (!query) {{
            conversationRows.forEach((row) => {{
              row.hidden = false;
              const preview = row.querySelector("[data-conversation-preview]");
              if (preview) preview.textContent = originalPreviews.get(row.dataset.session || "") || "";
            }});
            conversationEmpty?.classList.remove("visible");
            return;
          }}
          try {{
            const response = await fetch("/api/conversations/search?q=" + encodeURIComponent(query));
            if (!response.ok) throw new Error("HTTP " + response.status);
            const hits = await response.json();
            if (request !== conversationSearchRequest) return;
            const bySession = new Map(hits.map((hit) => [hit.session_id, hit]));
            let visible = 0;
            conversationRows.forEach((row) => {{
              const hit = bySession.get(row.dataset.session || "");
              row.hidden = !hit;
              if (hit) {{
                visible += 1;
                const preview = row.querySelector("[data-conversation-preview]");
                if (preview) preview.textContent = hit.snippet || originalPreviews.get(row.dataset.session || "") || "";
              }}
            }});
            conversationEmpty?.classList.toggle("visible", conversationRows.length > 0 && visible === 0);
          }} catch {{
            if (request !== conversationSearchRequest) return;
            const localQuery = query.toLocaleLowerCase();
            let visible = 0;
            conversationRows.forEach((row) => {{
              const matches = (row.dataset.search || "").toLocaleLowerCase().includes(localQuery);
              row.hidden = !matches;
              if (matches) visible += 1;
            }});
            conversationEmpty?.classList.toggle("visible", conversationRows.length > 0 && visible === 0);
          }}
        }}, 180);
      }});

      const deleteDialog = document.querySelector("[data-delete-dialog]");
      const deleteSession = document.querySelector("[data-delete-session]");
      const deleteTitle = document.querySelector("[data-delete-title]");
      const deleteNote = document.querySelector("[data-delete-note]");
      const deleteBlocks = document.querySelector("[data-delete-blocks]");
      const deleteFiles = document.querySelector("[data-delete-files]");
      const deleteShared = document.querySelector("[data-delete-shared]");
      document.querySelectorAll("[data-delete-trigger]").forEach((button) => button.addEventListener("click", () => {{
        if (deleteSession) deleteSession.value = button.dataset.session || "";
        if (deleteTitle) deleteTitle.textContent = button.dataset.title || button.dataset.session || "";
        if (deleteBlocks) deleteBlocks.textContent = button.dataset.blocks || "0";
        if (deleteFiles) deleteFiles.textContent = button.dataset.files || "0";
        if (deleteShared) deleteShared.textContent = button.dataset.shared || "0";
        if (deleteNote) {{
          const draftCount = button.dataset.drafts || "0";
          deleteNote.textContent = document.documentElement.lang === "zh"
            ? `这段对话及其 ${{draftCount}} 个已保存草稿文件将从当前项目移出。`
            : `This conversation and its ${{draftCount}} stored draft files will leave the active project.`;
        }}
        if (deleteDialog && typeof deleteDialog.showModal === "function") deleteDialog.showModal();
      }}));
      document.querySelectorAll("[data-delete-close]").forEach((button) => button.addEventListener("click", () => deleteDialog?.close()));
      deleteDialog?.addEventListener("click", (event) => {{
        if (event.target === deleteDialog) deleteDialog.close();
      }});

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
    model_settings_token = secrets.token_urlsafe(32)

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
                        csrf_token=model_settings_token,
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
            if parsed.path == "/api/conversation":
                session_id = _value(query, "session")
                try:
                    detail = get_conversation_detail(root, session_id)
                except FileNotFoundError:
                    self.send_error(404, "Conversation not found")
                    return
                payload = asdict(detail)
                payload["transcript_html"] = render_markdown_html(detail.transcript)
                self._send_json(payload)
                return
            if parsed.path == "/api/conversations/search":
                query_text = _value(query, "q")
                hits = search_conversations(root, query_text, limit=80)
                self._send_json([asdict(hit) for hit in hits])
                return
            if parsed.path == "/health":
                self._send_text("ok\n")
                return
            self.send_error(404, "Not found")

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                data = self._read_form()
                if parsed.path in {
                    "/action/model-settings",
                    "/action/delete-session",
                    "/action/conversation-flags",
                } and not secrets.compare_digest(
                    _value(data, "csrf_token"), model_settings_token
                ):
                    self.send_error(403, "Invalid control-center form token")
                    return
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
                            csrf_token=model_settings_token,
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
                        csrf_token=model_settings_token,
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

        def _send_json(self, payload: object, *, status: int = 200) -> None:
            encoded = (
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + chr(10)
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
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
        if generated.generated:
            message, message_zh = _append_distill_message(
                message,
                message_zh,
                generated,
            )
        return ConsoleActionResult(message, message_zh, anchor="add")

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
        if generated.generated:
            message, message_zh = _append_distill_message(
                message,
                message_zh,
                generated,
            )
        return ConsoleActionResult(message, message_zh, anchor="add")

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
        if generated.generated:
            message, message_zh = _append_distill_message(
                message,
                message_zh,
                generated,
            )
        return ConsoleActionResult(message, message_zh, anchor="add")

    if path == "/action/distill":
        session_dir = _session_dir(root, _value(data, "session"))
        patches = distill_session(root, session_dir=session_dir)
        append_event(root, "distill", subject=patches.session_id, data={"patch_dir": str(patches.patch_dir)})
        generated = finalize_distill(root, patches.patch_dir, source="ui")
        message, message_zh = _append_distill_message(
            "Memory draft generated",
            "记忆草稿已生成",
            generated,
            include_generated=False,
        )
        return ConsoleActionResult(message, message_zh, anchor="work")

    if path == "/action/conversation-flags":
        session_id = _value(data, "session")
        tags = [
            item.strip()
            for item in _value(data, "tags").replace("，", ",").split(",")
            if item.strip()
        ]
        updated = update_conversation_flags(
            root,
            session_id,
            pinned=_value(data, "pinned") == "yes",
            tags=tags,
            custom_title=_value(data, "custom_title"),
            note=_text(data, "note"),
        )
        append_event(
            root,
            "conversation-curation",
            subject=session_id,
            data={
                "pinned": updated.pinned,
                "tag_count": len(updated.tags),
                "renamed": bool(updated.custom_title),
            },
        )
        return ConsoleActionResult(
            "Conversation details saved",
            "对话信息已保存",
            anchor="add",
        )

    if path == "/action/delete-session":
        session_id = _value(data, "session")
        result = delete_conversation(root, session_id)
        impact = result.impact
        return ConsoleActionResult(
            f"Conversation moved to Trash; {impact.memory_blocks} source-owned Wiki blocks removed, with shared memory preserved in {len(impact.shared_files)} files",
            f"对话已移到回收站；撤回 {impact.memory_blocks} 个仅属于它的 Wiki 内容块，并在 {len(impact.shared_files)} 个文件中保留了共同记忆",
            anchor="add",
        )

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

    if path == "/action/model-settings":
        action = _value(data, "settings_action") or "save"
        if action == "disconnect":
            removed = clear_local_llm_settings(root)
            config = load_retrieval_config(root)
            active = llm_settings(
                base_url_env=config.llm_base_url_env,
                api_key_env=config.llm_api_key_env,
                model_env=config.llm_model_env,
                project=root,
            )
            append_event(root, "llm-settings", subject="disconnect", data={"source": "ui"})
            if active:
                return ConsoleActionResult(
                    "Local model settings removed; environment settings are still active",
                    "本地模型配置已移除，环境变量配置仍然生效",
                    anchor="ask",
                )
            return ConsoleActionResult(
                "Model API disconnected" if removed else "No local model API was configured",
                "模型 API 已断开" if removed else "当前没有本地模型 API 配置",
                anchor="ask",
            )

        settings = save_local_llm_settings(
            root,
            provider=_value(data, "provider"),
            base_url=_value(data, "base_url"),
            model=_value(data, "model"),
            api_key=_value(data, "api_key"),
        )
        append_event(
            root,
            "llm-settings",
            subject=action,
            data={"source": "ui", "provider": settings.provider, "model": settings.model},
        )
        if action == "test":
            try:
                response = chat_completion(
                    settings,
                    system="This is an API connection check. Reply with only OK.",
                    user="Reply with OK.",
                    timeout=30,
                )
            except RuntimeError as exc:
                return ConsoleActionResult(
                    f"Settings saved, but the connection test failed: {exc}",
                    f"配置已保存，但连接测试失败：{exc}",
                    anchor="ask",
                )
            if not response.strip():
                return ConsoleActionResult(
                    "Settings saved, but the model returned an empty response",
                    "配置已保存，但模型返回了空响应",
                    anchor="ask",
                )
            return ConsoleActionResult(
                f"Model connected: {settings.model}",
                f"模型连接成功：{settings.model}",
                anchor="ask",
            )
        return ConsoleActionResult(
            f"Model settings saved: {settings.model}",
            f"模型配置已保存：{settings.model}",
            anchor="ask",
        )

    if path == "/action/understand":
        brief = build_project_brief(root)
        output = root / "docs" / "wiki" / "project_brief.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_project_brief_markdown(brief), encoding="utf-8")
        append_event(root, "understand", subject=root.name, data={"output": str(output)})
        return ConsoleActionResult("Project brief refreshed", "项目简介已刷新", anchor="memory")

    raise ValueError(f"Unknown control-center action: {path}")


def _auto_distill(
    project: Path,
    session_dir: Path,
    data: dict[str, list[str]],
) -> DistillAutomationResult:
    if _value(data, "auto_distill") != "yes":
        return DistillAutomationResult(generated=False)
    patches = distill_session(project, session_dir=session_dir)
    append_event(
        project,
        "distill",
        subject=patches.session_id,
        data={"patch_dir": str(patches.patch_dir), "source": "ui"},
    )
    return finalize_distill(project, patches.patch_dir, source="ui")


def finalize_distill(
    project: Path,
    patch_dir: Path,
    *,
    source: str,
) -> DistillAutomationResult:
    report = build_assurance_report(project, patch_dir=patch_dir)
    append_event(
        project,
        "assurance",
        subject=patch_dir.name,
        data={
            "status": report.status,
            "attention": report.attention_count,
            "path": str(report.path),
            "source": source,
        },
    )
    policy = load_assurance_policy(project)
    should_promote = (
        policy.mode == "exceptions"
        and policy.auto_promote_clear_knowledge
        and not report.needs_attention
    )
    if not should_promote:
        return DistillAutomationResult(
            generated=True,
            attention_count=report.attention_count,
        )

    review = review_patches(
        project,
        patch_dir=patch_dir,
        approve=True,
        reviewer="vibewiki",
        method="local_assurance",
        notes=(
            "Automatically promoted source-linked knowledge after local assurance found no "
            "skill, conflict, incomplete provenance, or over-distillation exception."
        ),
    )
    append_event(
        project,
        "review",
        subject=patch_dir.name,
        data={
            "decision": "approved",
            "method": "local_assurance",
            "review_file": str(review.review_file),
        },
    )
    changed = merge_patches(project, patch_dir=patch_dir, safe_only=True)
    append_event(
        project,
        "merge",
        subject=patch_dir.name,
        data={
            "patch_dir": str(patch_dir),
            "changed": [str(item) for item in changed],
            "mode": "knowledge_only",
            "source": source,
        },
    )
    return DistillAutomationResult(generated=True, auto_promoted=True)


def _append_distill_message(
    message: str,
    message_zh: str,
    result: DistillAutomationResult,
    *,
    include_generated: bool = True,
) -> tuple[str, str]:
    if include_generated:
        message += "; memory draft generated"
        message_zh += "，并已生成记忆草稿"
    if result.auto_promoted:
        return (
            message + "; safe knowledge added automatically",
            message_zh + "，低风险知识已自动入库",
        )
    if result.attention_count:
        return (
            message + f"; {result.attention_count} exception(s) need attention",
            message_zh + f"，有 {result.attention_count} 个例外需要处理",
        )
    return message, message_zh


def _session_rows(
    data: DashboardData,
    merged_patches: set[str],
    assurance_reports: dict[str, AssuranceReport],
    *,
    manual_review: bool,
) -> str:
    rows: list[str] = []
    for session in reversed(data.sessions[-8:]):
        patch = data.root / ".vibewiki" / "patches" / session.name
        sections = parse_sections(read_text_if_exists(session / "session.md"))
        goal = sections.get("Goal", session.name).strip().splitlines()[0]
        outcome = sections.get("Final Outcome", "").strip().splitlines()
        detail = outcome[0] if outcome and outcome[0] != "Not provided." else session.name
        if session.name in merged_patches:
            continue
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
            assurance = assurance_reports.get(session.name)
            if (
                assurance
                and not assurance.needs_attention
                and not manual_review
                and not _patch_approved(data.root, session.name)
            ):
                continue
            decisions = read_item_decisions(data.root, session.name)
            reviewed = str(assurance.attention_count if assurance else len(decisions))
            approved = _patch_approved(data.root, session.name)
            if approved:
                state, state_zh, status_class = "approved", "已批准", "approved"
            else:
                state, state_zh, status_class = "attention", "需处理", "candidate"
            if assurance and assurance.needs_attention:
                titles = [issue.title for issue in assurance.issues if issue.requires_human]
                detail = "; ".join(titles[:2])
            elif manual_review and not approved:
                detail = "Manual approval is enabled for this workspace."
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
            f'<span class="review-count">{_escape(reviewed)} {_i18n("exceptions", "个例外")}</span>'
            f'<div class="row-actions">{action}</div></div>'
        )
    return "".join(rows)


def _conversation_rows(root: Path, conversations: list[ConversationRecord]) -> str:
    rows: list[str] = []
    status_labels = {
        "captured": ("captured", "已记录"),
        "candidate": ("candidate", "候选"),
        "approved": ("approved", "已批准"),
        "merged": ("merged", "已合并"),
    }
    for conversation in conversations:
        impact = plan_conversation_deletion(root, conversation.session_id)
        state, state_zh = status_labels.get(
            conversation.status,
            (conversation.status, conversation.status),
        )
        status_class = conversation.status if conversation.status in {"candidate", "approved", "merged"} else ""
        search = " ".join(
            (
                conversation.title,
                conversation.preview,
                conversation.recorded_by,
                conversation.source,
                conversation.session_id,
                " ".join(conversation.tags),
                conversation.note,
            )
        )
        pin = (
            f'<span class="pin-mark">{_icon("star")}{_i18n("Pinned", "已置顶")}</span>'
            if conversation.pinned
            else ""
        )
        tags = "".join(
            f'<span>#{_escape(tag)}</span>' for tag in conversation.tags[:2]
        )
        disabled = ' disabled aria-disabled="true"' if conversation.pinned else ""
        delete_title = (
            "Unpin this conversation before removing it"
            if conversation.pinned
            else "Remove conversation"
        )
        rows.append(
            f'<article class="conversation-row" data-conversation-row '
            f'data-session="{_escape(conversation.session_id)}" data-search="{_escape(search)}">'
            f'<button class="conversation-open" type="button" data-conversation-open '
            f'data-session="{_escape(conversation.session_id)}" aria-pressed="false">'
            f'<div class="conversation-copy"><div class="conversation-title-line"><strong>{_escape(conversation.title)}</strong>'
            f'<time datetime="{_escape(conversation.created_at)}">{_escape(_conversation_date(conversation.created_at))}</time></div>'
            f'<p class="conversation-preview" data-conversation-preview>{_escape(conversation.preview)}</p><div class="conversation-meta">'
            f'<span class="status {status_class}">{_i18n(state, state_zh)}</span>'
            f'<span>{_conversation_source(conversation.source)}</span><span>@{_escape(conversation.recorded_by)}</span>'
            f'{pin}{tags}</div></div></button>'
            f'<button class="delete-trigger" type="button" data-delete-trigger '
            f'data-session="{_escape(conversation.session_id)}" data-title="{_escape(conversation.title)}" '
            f'data-blocks="{impact.memory_blocks}" data-files="{len(impact.memory_files)}" '
            f'data-shared="{len(impact.shared_files)}" data-drafts="{impact.candidate_files}" '
            f'title="{_escape(delete_title)}" aria-label="{_escape(delete_title)}"{disabled}>{_icon("trash")}'
            f'<span class="visually-hidden">{_i18n("Remove conversation", "删除对话")}</span></button></article>'
        )
    return "".join(rows)


def _conversation_date(value: str) -> str:
    if not value:
        return "-"
    return value.replace("T", " ")[:16]


def _conversation_source(value: str) -> str:
    translations = {
        "Quick result": "快速记录",
        "Pasted Markdown": "粘贴的 Markdown",
        "ChatGPT share": "ChatGPT 分享",
        "Claude share": "Claude 分享",
        "Shared link": "分享链接",
        "Markdown file": "Markdown 文件",
    }
    translated = translations.get(value)
    return _i18n(value, translated) if translated else _escape(value)


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


def _icon(name: str) -> str:
    paths = {
        "sparkles": '<path d="m12 3 1.1 3.2a4 4 0 0 0 2.5 2.5L19 10l-3.4 1.3a4 4 0 0 0-2.5 2.5L12 17l-1.1-3.2a4 4 0 0 0-2.5-2.5L5 10l3.4-1.3a4 4 0 0 0 2.5-2.5L12 3Z"/><path d="m5 3 .4 1.1a2 2 0 0 0 1.2 1.2L8 6l-1.4.7a2 2 0 0 0-1.2 1.2L5 9l-.4-1.1a2 2 0 0 0-1.2-1.2L2 6l1.4-.7a2 2 0 0 0 1.2-1.2L5 3Z"/><path d="m19 15 .5 1.4a2 2 0 0 0 1.1 1.1L22 18l-1.4.5a2 2 0 0 0-1.1 1.1L19 21l-.5-1.4a2 2 0 0 0-1.1-1.1L16 18l1.4-.5a2 2 0 0 0 1.1-1.1L19 15Z"/>',
        "plus": '<path d="M12 5v14M5 12h14"/>',
        "bell": '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Z"/><path d="M10 21h4"/>',
        "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/>',
        "refresh": '<path d="M20 6v5h-5"/><path d="M4 18v-5h5"/><path d="M18.2 9A7 7 0 0 0 6.1 6.6L4 11M20 13l-2.1 4.4A7 7 0 0 1 5.8 15"/>',
        "message": '<path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z"/>',
        "messages": '<path d="M21 15a4 4 0 0 1-4 4H9l-5 3v-5a4 4 0 0 1-1-2V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4v8Z"/><path d="M8 8h8M8 12h5"/>',
        "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>',
        "trash": '<path d="M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 11v5M14 11v5"/>',
        "star": '<path d="m12 2.8 2.8 5.7 6.3.9-4.6 4.4 1.1 6.3-5.6-3-5.6 3 1.1-6.3-4.6-4.4 6.3-.9L12 2.8Z"/>',
        "cpu": '<rect width="14" height="14" x="5" y="5" rx="2"/><path d="M9 9h6v6H9zM9 1v4M15 1v4M9 19v4M15 19v4M19 9h4M19 14h4M1 9h4M1 14h4"/>',
        "arrow": '<path d="m5 12 14-7-4 14-3-6-7-1Z"/><path d="m12 13 7-8"/>',
        "settings": '<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6 1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/>',
        "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    }
    body = paths.get(name, paths["sparkles"])
    return (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{body}</svg>'
    )


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)
