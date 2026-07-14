from __future__ import annotations

from dataclasses import dataclass
import html
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import re
import socketserver
from urllib.parse import parse_qs, urlencode

from .assurance import AssuranceIssue, build_assurance_report
from .distill import parse_sections
from .llm import chat_completion, llm_settings
from .merge import merge_patches
from .project import ensure_workspace
from .review import (
    ItemDecision,
    latest_patch_dir,
    read_item_decisions,
    record_item_decision,
    review_patches,
    update_item_body,
)
from .review_plan import ReviewPlanEntry, build_review_plan
from .retrieval import load_retrieval_config
from .text_utils import read_text_if_exists
from .translation import cached_translation_markdown, language_label, translate_markdown


TRANSLATION_TARGETS = ["zh", "ja", "ko", "fr", "de", "es", "pt", "ru"]
TRANSLATION_TARGET_LABELS_ZH = {
    "zh": "中文",
    "ja": "日文",
    "ko": "韩文",
    "fr": "法文",
    "de": "德文",
    "es": "西班牙文",
    "pt": "葡萄牙文",
    "ru": "俄文",
}


@dataclass(frozen=True)
class ReviewActionResult:
    message: str
    message_zh: str
    target_language: str = "zh"


def render_review_ui(
    project: Path,
    *,
    patch_dir: Path | None = None,
    target_language: str = "zh",
    message: str = "",
    message_zh: str = "",
    home_url: str = "",
    default_lang: str = "zh",
) -> str:
    root = project.resolve()
    ensure_workspace(root)
    selected_patch_dir = (patch_dir or latest_patch_dir(root)).resolve()
    session_id = selected_patch_dir.name
    decisions = read_item_decisions(root, session_id)
    review_plan = build_review_plan(root, patch_dir=selected_patch_dir)
    assurance = build_assurance_report(root, patch_dir=selected_patch_dir)
    plan_summary = review_plan.payload.get("summary", {})
    if not isinstance(plan_summary, dict):
        plan_summary = {}
    selected_target_language = _normalize_target_language(target_language)
    items = _review_items(
        root,
        selected_patch_dir,
        decisions,
        review_plan.items,
        target_language=selected_target_language,
    )
    session_md = read_text_if_exists(root / ".vibewiki" / "sessions" / session_id / "session.md")
    sections = parse_sections(session_md) if session_md else {}
    goal = sections.get("Goal", "Not provided.").strip()
    outcome = sections.get("Final Outcome", "Not provided.").strip()
    approved = "decision: approved" in read_text_if_exists(
        root / ".vibewiki" / "reviews" / f"{session_id}.yaml"
    )
    default_visible = sum(
        1
        for item in items
        if _plan_group(item) == "review_now"
        and not isinstance(item.get("decision"), ItemDecision)
    )
    clean_default_lang = default_lang if default_lang in {"en", "zh"} else "zh"
    home_link = (
        f'<a class="home-link" href="{_escape(home_url)}">'
        f'{_i18n("Back to Control Center", "返回中控台")}</a>'
        if home_url
        else ""
    )

    return f"""<!doctype html>
<html lang="{_escape(clean_default_lang)}" data-default-lang="{_escape(clean_default_lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VibeWiki Review UI - {_escape(session_id)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8f5;
      --surface: #fff;
      --soft: #eef4f3;
      --ink: #15191d;
      --muted: #60707a;
      --line: #d9ded8;
      --teal: #0f766e;
      --blue: #2563eb;
      --amber: #a16207;
      --rose: #be123c;
      --code: #111827;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
      letter-spacing: 0;
    }}
    main {{ max-width: 1280px; margin: 0 auto; padding: 24px; }}
    header {{
      display: flex;
      gap: 16px;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
      margin-bottom: 18px;
    }}
    h1, h2, h3 {{ margin: 0; line-height: 1.2; letter-spacing: 0; }}
    h1 {{ font-size: clamp(24px, 3vw, 34px); }}
    h2 {{ font-size: 18px; margin-bottom: 10px; }}
    h3 {{ font-size: 16px; }}
    .sub {{ color: var(--muted); margin-top: 6px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }}
    .top-actions {{ display: grid; gap: 10px; justify-items: end; }}
    .home-link {{ color: var(--teal); font-size: 13px; font-weight: 700; text-decoration: none; }}
    .home-link:hover {{ text-decoration: underline; }}
    .language-switch {{
      display: inline-flex;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
    }}
    .language-switch button {{
      border: 0;
      border-radius: 0;
      min-height: 32px;
      padding: 6px 10px;
    }}
    .language-switch button.active {{
      background: var(--ink);
      color: #fff;
    }}
    .layout {{ display: grid; grid-template-columns: 320px 1fr; gap: 16px; align-items: start; }}
    .panel, .card {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .panel {{ margin-bottom: 16px; }}
    .soft {{ background: var(--soft); }}
    .stack {{ display: grid; gap: 12px; }}
    .card-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }}
    .badges {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }}
    .badge {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    .badge.kind {{ color: var(--teal); border-color: #99c8c2; }}
    .badge.decision {{ color: var(--blue); border-color: #a7bdf5; }}
    .badge.skip {{ color: var(--rose); border-color: #e7a7b7; }}
    .badge.plan-review {{ color: var(--teal); border-color: #99c8c2; }}
    .badge.plan-later {{ color: var(--amber); border-color: #dfc27a; }}
    .badge.plan-discard {{ color: var(--rose); border-color: #e7a7b7; }}
    .message {{
      margin-bottom: 16px;
      padding: 12px 14px;
      border: 1px solid #b7d8d2;
      background: #eefbf8;
      border-radius: 8px;
      color: #115e59;
      transition: opacity .25s ease, transform .25s ease;
    }}
    .message.hide {{
      opacity: 0;
      transform: translateY(-4px);
    }}
    .toolbar {{
      display: grid;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .toolbar-row {{
      display: grid;
      grid-template-columns: minmax(180px, 1fr) minmax(140px, 220px) auto auto;
      gap: 8px;
      align-items: center;
    }}
    .bulk-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}
    .queue-tools {{
      display: flex;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
      flex-wrap: wrap;
    }}
    .filter-tools {{
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .triage-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
      margin-top: 10px;
    }}
    .triage-cell {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      background: #fff;
    }}
    .triage-num {{
      display: block;
      font-size: 18px;
      font-weight: 700;
      line-height: 1.1;
    }}
    .triage-label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-top: 2px;
    }}
    .assurance-list {{ display: grid; gap: 8px; margin-top: 12px; }}
    .assurance-item {{ border-left: 3px solid var(--amber); padding: 7px 9px; background: #fff; }}
    .assurance-item.high {{ border-left-color: var(--rose); }}
    .assurance-item strong {{ display: block; font-size: 13px; }}
    .assurance-item p {{ margin: 3px 0 0; color: var(--muted); font-size: 12px; }}
    .assurance-clear {{ margin-top: 12px; padding: 9px; color: var(--teal); background: #fff; border-left: 3px solid var(--teal); }}
    .plan-reason {{
      color: var(--muted);
      font-size: 12px;
      margin: 8px 0 0;
    }}
    .simple-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }}
    .review-lab {{
      border-top: 1px solid var(--line);
      margin-top: 12px;
      padding-top: 12px;
    }}
    .review-lab summary {{
      cursor: pointer;
      color: var(--teal);
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .review-lab textarea[name="body"] {{
      min-height: 300px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
    }}
    .review-lab textarea[name="instruction"] {{
      min-height: 82px;
    }}
    label.inline {{
      display: inline-flex;
      gap: 6px;
      align-items: center;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }}
    .count {{
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }}
    .text {{ color: #202427; font-size: 13px; }}
    .text p {{ margin: 8px 0; }}
    .text ul {{ padding-left: 18px; }}
    .preview {{
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      margin: 12px 0;
      max-height: 340px;
      overflow: auto;
      font-size: 13px;
    }}
    .preview h1, .preview h2, .preview h3, .preview h4 {{
      margin: 10px 0 6px;
      line-height: 1.25;
    }}
    .preview h1 {{ font-size: 18px; }}
    .preview h2 {{ font-size: 16px; }}
    .preview h3, .preview h4 {{ font-size: 14px; }}
    .preview p {{ margin: 8px 0; }}
    .preview ul, .preview ol {{ margin: 8px 0; padding-left: 20px; }}
    .preview blockquote {{
      margin: 8px 0;
      padding-left: 10px;
      border-left: 3px solid var(--line);
      color: var(--muted);
    }}
    .preview code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      background: #edf2f7;
      border-radius: 4px;
      padding: 1px 4px;
    }}
    .preview pre {{
      margin: 10px 0;
      padding: 10px;
      overflow: auto;
      background: #111827;
      color: #f9fafb;
      border-radius: 8px;
    }}
    .preview pre code {{
      background: transparent;
      color: inherit;
      padding: 0;
    }}
    .translation-preview {{
      border: 1px solid #c4d7d3;
      border-radius: 8px;
      padding: 10px;
      margin: 12px 0;
      background: #f2fbf8;
    }}
    .translation-preview summary {{
      cursor: pointer;
      color: var(--teal);
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .translation-note {{
      color: var(--muted);
      font-size: 12px;
      margin: 4px 0 8px;
    }}
    .controls {{ display: grid; gap: 8px; margin-top: 12px; }}
    .fields {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }}
    input, textarea {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      font: inherit;
      font-size: 13px;
      background: #fff;
      color: var(--ink);
    }}
    input[type="checkbox"] {{ width: auto; }}
    textarea {{ min-height: 68px; resize: vertical; }}
    select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      font: inherit;
      font-size: 13px;
      background: #fff;
      color: var(--ink);
    }}
    .select-item {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }}
    .editor {{
      border-top: 1px solid var(--line);
      margin-top: 12px;
      padding-top: 12px;
    }}
    .editor summary {{
      cursor: pointer;
      color: var(--teal);
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .editor textarea {{
      min-height: 300px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
    }}
    .buttons {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    button {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      background: #fff;
      cursor: pointer;
      font: inherit;
      font-size: 13px;
      min-height: 36px;
    }}
    button.primary {{ background: var(--teal); color: #fff; border-color: var(--teal); }}
    button.reject {{ color: var(--rose); }}
    button.defer {{ color: var(--amber); }}
    button.merge {{ color: var(--blue); }}
    button.save {{ color: var(--blue); }}
    .patch-actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    @media (max-width: 900px) {{
      main {{ padding: 16px; }}
      header {{ display: block; }}
      .top-actions {{ justify-items: start; margin-top: 12px; }}
      .layout {{ grid-template-columns: 1fr; }}
      .toolbar-row {{ grid-template-columns: 1fr; }}
      .fields {{ grid-template-columns: 1fr; }}
      .patch-actions {{ margin-top: 12px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        {home_link}
        <h1>{_i18n("VibeWiki Review", "VibeWiki 审核")}</h1>
        <div class="sub">{_escape(session_id)}</div>
      </div>
      <div class="top-actions">
        <div class="language-switch" aria-label="Language">
          <button type="button" data-lang-choice="en" aria-pressed="{_escape(str(clean_default_lang == 'en').lower())}">English</button>
          <button type="button" data-lang-choice="zh" aria-pressed="{_escape(str(clean_default_lang == 'zh').lower())}">中文</button>
        </div>
        <div class="patch-actions">
          <form method="post" action="/approve-and-merge">
            <input type="hidden" name="patch" value="{_escape(session_id)}">
            <button class="primary" type="submit">{_i18n("Approve & Merge", "批准并合并")}</button>
          </form>
        </div>
      </div>
    </header>
    {_message(message, message_zh)}
    <section class="layout">
      <aside>
        <section class="panel soft">
          <h2>{_i18n("Session", "会话")}</h2>
          <div class="text">
            <p><strong>{_i18n("Goal", "目标")}:</strong> {_escape(goal)}</p>
            <p><strong>{_i18n("Outcome", "结果")}:</strong> {_escape(outcome)}</p>
            <p><strong>{_i18n("Patch approved", "整包已批准")}:</strong> {_i18n("yes" if approved else "no", "是" if approved else "否")}</p>
            <p><strong>{_i18n("Items", "候选项")}:</strong> {_escape(str(len(items)))} · <strong>{_i18n("Reviewed", "已审核")}:</strong> {_escape(str(len(decisions)))}</p>
          </div>
        </section>
        <section class="panel">
          <h2>{_i18n("Memory Assurance", "记忆质检")}</h2>
          <div class="text">
            <p>{_i18n("Only exceptions reach you. Raw candidates remain available as evidence.", "只有例外情况需要你处理，原始候选仍作为证据保留。")}</p>
            <div class="triage-grid">
              {_triage_cell("Checked", "已检查", assurance.candidate_count)}
              {_triage_cell("Exceptions", "例外", assurance.attention_count)}
              {_triage_cell("Coverage", "检查状态", assurance.status)}
              {_triage_cell("Duplicates hidden", "已隐藏重复", plan_summary.get("suggested_discard", 0))}
            </div>
            {_assurance_issue_rows(assurance.issues)}
          </div>
        </section>
        <section class="panel">
          <h2>{_i18n("Your decision", "你的决定")}</h2>
          <div class="text">
            <p>{_i18n("Check the flagged skill or conflict, edit it when needed, then approve the pack. Everything else is handled automatically.", "只需检查标出的 Skill 或冲突，必要时直接修改，然后批准整包；其余内容自动处理。")}</p>
            <p>{_i18n("Local assurance checks provenance and structure. It does not claim that every statement is correct.", "本地质检检查来源与结构，但不会声称每条内容都绝对正确。")}</p>
          </div>
        </section>
      </aside>
      <section>
        <div class="queue-tools">
          <div class="filter-tools">
            <label class="inline">
              <input id="hide-reviewed" type="checkbox" checked>
              {_i18n("Hide reviewed", "隐藏已审")}
            </label>
            <label class="inline">
              <input id="show-later" type="checkbox">
              {_i18n("Show lower priority", "显示低优先级")}
            </label>
            <label class="inline">
              <input id="show-discard" type="checkbox">
              {_i18n("Show suggested discard", "显示建议不提交")}
            </label>
          </div>
          <span id="visible-count" class="count">{_escape(str(default_visible))} / {_escape(str(len(items)))}</span>
        </div>
        <section class="stack">
        {''.join(_item_card(item, session_id=session_id) for item in items)}
        </section>
      </section>
    </section>
  </main>
  <script>
    (() => {{
      const defaultLang = document.documentElement.dataset.defaultLang || "zh";
      const languageButtons = Array.from(document.querySelectorAll("[data-lang-choice]"));

      function setLanguage(lang) {{
        document.documentElement.lang = lang;
        document.body.dataset.lang = lang;
        window.localStorage.setItem("vibewiki.review.lang", lang);
        document.querySelectorAll("[data-i18n]").forEach((node) => {{
          node.textContent = lang === "en" ? node.dataset.en : node.dataset.zh;
        }});
        document.querySelectorAll("[data-placeholder-en]").forEach((node) => {{
          node.placeholder = lang === "en" ? node.dataset.placeholderEn : node.dataset.placeholderZh;
        }});
        languageButtons.forEach((button) => {{
          const active = button.dataset.langChoice === lang;
          button.classList.toggle("active", active);
          button.setAttribute("aria-pressed", String(active));
        }});
      }}

      const messages = document.querySelectorAll(".message");
      window.setTimeout(() => {{
        messages.forEach((message) => {{
          message.classList.add("hide");
          window.setTimeout(() => message.remove(), 350);
        }});
      }}, 3200);

      const cards = Array.from(document.querySelectorAll("[data-review-card]"));
      const hideReviewed = document.getElementById("hide-reviewed");
      const showLater = document.getElementById("show-later");
      const showDiscard = document.getElementById("show-discard");
      const visibleCount = document.getElementById("visible-count");

      function applyFilters() {{
        const shouldHideReviewed = hideReviewed.checked;
        const shouldShowLater = showLater.checked;
        const shouldShowDiscard = showDiscard.checked;
        let visible = 0;
        cards.forEach((card) => {{
          const reviewed = card.dataset.decision && card.dataset.decision !== "unreviewed";
          const group = card.dataset.planGroup || "review_now";
          const groupVisible =
            group === "review_now" ||
            (group === "suggested_later" && shouldShowLater) ||
            (group === "suggested_discard" && shouldShowDiscard);
          const reviewVisible = !shouldHideReviewed || !reviewed;
          const show = groupVisible && reviewVisible;
          card.hidden = !show;
          if (show) visible += 1;
        }});
        visibleCount.textContent = `${{visible}} / ${{cards.length}}`;
      }}

      hideReviewed.addEventListener("change", applyFilters);
      showLater.addEventListener("change", applyFilters);
      showDiscard.addEventListener("change", applyFilters);

      languageButtons.forEach((button) => {{
        button.addEventListener("click", () => setLanguage(button.dataset.langChoice || defaultLang));
      }});

      setLanguage(window.localStorage.getItem("vibewiki.review.lang") || defaultLang);
      applyFilters();
    }})();
  </script>
</body>
</html>
"""


def perform_review_action(
    project: Path,
    *,
    patch_dir: Path,
    path: str,
    data: dict[str, list[str]],
) -> ReviewActionResult:
    root = project.resolve()
    selected_patch_dir = patch_dir.resolve()

    if path == "/item-action":
        item = _form_value(data, "item")
        action = _form_value(data, "action")
        body = _form_text(data, "body")
        instruction = _form_value(data, "instruction")
        target_language = _normalize_target_language(
            _form_value(data, "target_language") or "zh"
        )
        if action == "save":
            update_item_body(root, patch_dir=selected_patch_dir, item=item, body=body)
            return ReviewActionResult(f"Saved Markdown for {item}", f"已保存 {item} 的 Markdown")
        if action == "approve":
            update_item_body(root, patch_dir=selected_patch_dir, item=item, body=body)
            record_item_decision(
                root,
                patch_dir=selected_patch_dir,
                item=item,
                decision="approve",
                note="Submitted from simplified review UI.",
            )
            return ReviewActionResult(f"Submitted {item}", f"已提交 {item}")
        if action == "reject":
            record_item_decision(
                root,
                patch_dir=selected_patch_dir,
                item=item,
                decision="reject",
                note=instruction or "Rejected from simplified review UI.",
            )
            return ReviewActionResult(f"Discarded {item}", f"已标记不提交 {item}")
        if action == "revise":
            if not instruction:
                raise ValueError("Revision instruction is required.")
            revised = revise_candidate_markdown(root, body=body, instruction=instruction)
            update_item_body(root, patch_dir=selected_patch_dir, item=item, body=revised)
            return ReviewActionResult(f"Revised {item} with LLM", f"LLM 已修订 {item}")
        if action == "translate":
            translate_candidate_markdown(
                root,
                body=body,
                target_language=target_language,
            )
            return ReviewActionResult(
                f"Generated {language_label(target_language)} preview for {item}",
                f"已生成 {item} 的 {_language_label_zh(target_language)} 预览",
                target_language=target_language,
            )
        raise ValueError(f"Unknown item action: {action}")

    if path == "/decision":
        item = _form_value(data, "item")
        decision = _form_value(data, "decision")
        record_item_decision(
            root,
            patch_dir=selected_patch_dir,
            item=item,
            decision=decision,
            target=_form_value(data, "target"),
            title=_form_value(data, "title"),
            summary=_form_value(data, "summary"),
            tags=_form_value(data, "tags"),
            note=_form_value(data, "note"),
        )
        return ReviewActionResult(
            f"Recorded {decision} for {item}",
            f"已记录 {item}：{decision}",
        )

    if path == "/bulk-decision":
        items = _form_values(data, "item")
        decision = _form_value(data, "decision")
        if not items:
            raise ValueError("No items selected.")
        for item in items:
            record_item_decision(
                root,
                patch_dir=selected_patch_dir,
                item=item,
                decision=decision,
                note=_form_value(data, "note"),
            )
        return ReviewActionResult(
            f"Recorded {decision} for {len(items)} items",
            f"已为 {len(items)} 项记录：{decision}",
        )

    if path == "/save-item":
        item = _form_value(data, "item")
        update_item_body(
            root,
            patch_dir=selected_patch_dir,
            item=item,
            body=_form_text(data, "body"),
        )
        return ReviewActionResult(f"Saved Markdown for {item}", f"已保存 {item} 的 Markdown")

    if path == "/patch-review":
        review_patches(root, patch_dir=selected_patch_dir, approve=True)
        return ReviewActionResult("Patch approved", "整包已批准")

    if path == "/approve-and-merge":
        review_patches(root, patch_dir=selected_patch_dir, approve=True)
        changed = merge_patches(root, patch_dir=selected_patch_dir)
        return ReviewActionResult(
            f"Approved and merged {len(changed)} files",
            f"已批准并合并 {len(changed)} 个文件",
        )

    if path == "/merge":
        changed = merge_patches(root, patch_dir=selected_patch_dir)
        return ReviewActionResult(
            f"Merged {len(changed)} files",
            f"已合并 {len(changed)} 个文件",
        )

    raise ValueError(f"Unknown review action: {path}")


def serve_review_ui(
    project: Path,
    *,
    patch_dir: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    root = project.resolve()
    ensure_workspace(root)
    selected_patch_dir = (patch_dir or latest_patch_dir(root)).resolve()

    class ReviewHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            message = ""
            message_zh = ""
            if "?" in self.path:
                query = self.path.split("?", 1)[1]
                parsed = parse_qs(query)
                message = parsed.get("message", [""])[0]
                message_zh = parsed.get("message_zh", [""])[0]
                target_language = parsed.get("target_language", ["zh"])[0]
            else:
                target_language = "zh"
            self._send_html(
                render_review_ui(
                    root,
                    patch_dir=selected_patch_dir,
                    target_language=target_language,
                    message=message,
                    message_zh=message_zh,
                )
            )

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0") or 0)
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            try:
                result = perform_review_action(
                    root,
                    patch_dir=selected_patch_dir,
                    path=self.path,
                    data=data,
                )
                self._redirect(
                    result.message,
                    result.message_zh,
                    target_language=result.target_language,
                )
            except Exception as exc:
                self._redirect(f"Error: {exc}", f"错误：{exc}")

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_html(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _redirect(
            self,
            message: str,
            message_zh: str = "",
            target_language: str = "zh",
        ) -> None:
            target = "/?" + urlencode(
                {
                    "message": message,
                    "message_zh": message_zh or message,
                    "target_language": _normalize_target_language(target_language),
                }
            )
            self.send_response(303)
            self.send_header("Location", target)
            self.end_headers()

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer((host, port), ReviewHandler) as server:
        print(f"VibeWiki review UI: http://{host}:{port}/")
        print(f"Patch: {selected_patch_dir}")
        server.serve_forever()


def _review_items(
    project: Path,
    patch_dir: Path,
    decisions: dict[str, ItemDecision],
    review_plan: dict[str, ReviewPlanEntry] | None = None,
    target_language: str = "zh",
) -> list[dict[str, object]]:
    plan_items = review_plan or {}
    items: list[dict[str, object]] = []
    for folder, fallback_kind in [
        ("findings", "finding"),
        ("skilllets", "skilllet"),
        ("prompt_patterns", "prompt pattern"),
        ("workflows", "workflow"),
    ]:
        directory = patch_dir / folder
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            if path.name == "index.md":
                continue
            text = path.read_text(encoding="utf-8")
            item_id = path.resolve().relative_to(patch_dir.resolve()).as_posix()
            items.append(
                {
                    "id": item_id,
                    "path": path,
                    "title": _first_heading(text) or path.stem.replace("-", " ").title(),
                    "kind": _field(text, "Kind") or _field(text, "Type") or fallback_kind,
                    "status": _field(text, "Status") or "candidate",
                    "decision": decisions.get(item_id),
                    "plan": plan_items.get(item_id),
                    "snippet": _snippet(text),
                    "body": text,
                    "translation": cached_translation_markdown(
                        project,
                        markdown=text,
                        target_language=target_language,
                    ),
                    "target_language": target_language,
                }
            )
    return items


def _triage_cell(en: str, zh: str, value: object) -> str:
    return (
        '<div class="triage-cell">'
        f'<span class="triage-num">{_escape(value)}</span>'
        f'<span class="triage-label">{_i18n(en, zh)}</span>'
        "</div>"
    )


def _assurance_issue_rows(issues: tuple[AssuranceIssue, ...]) -> str:
    translations = {
        "source-missing": ("源对话缺失", "记忆草稿无法追溯到导入或记录的原始对话。"),
        "source-link-mismatch": ("候选项来源不一致", "一个或多个候选项指向了不同的来源会话。"),
        "reusable-guidance": ("可复用流程需要审核", "它可能影响未来的 AI Agent，可信前需要人工确认。"),
        "memory-conflict": ("可能需要更新已有记忆", "请决定合并、替换，还是保留两个版本。"),
        "incomplete-evidence": ("关键证据仍不完整", "本次检查明确标为部分完成，不会假装已经全部验证。"),
        "candidate-volume": ("候选记忆过多", "请把它当作一个过度提取问题处理，无需逐条审核全部候选。"),
    }
    human_issues = [issue for issue in issues if issue.requires_human]
    if not human_issues:
        return (
            '<div class="assurance-clear">'
            f'{_i18n("No exception needs human review.", "没有需要人工处理的例外。")}'
            "</div>"
        )
    rows: list[str] = []
    for issue in human_issues:
        title_zh, message_zh = translations.get(issue.code, (issue.title, issue.message))
        rows.append(
            f'<div class="assurance-item {_escape(issue.severity)}">'
            f'<strong>{_i18n(issue.title, title_zh)}</strong>'
            f'<p>{_i18n(issue.message, message_zh)}</p></div>'
        )
    return f'<div class="assurance-list">{"".join(rows)}</div>'


def _plan_group(item: dict[str, object]) -> str:
    plan = item.get("plan")
    if isinstance(plan, ReviewPlanEntry):
        return plan.group or "suggested_later"
    return "review_now"


def _plan_group_label(group: str) -> str:
    labels = {
        "review_now": ("Review now", "优先审核"),
        "suggested_later": ("Lower priority", "低优先级"),
        "suggested_discard": ("Suggested discard", "建议不提交"),
    }
    en, zh = labels.get(group, ("Pre-review", "预审"))
    return _i18n(en, zh)


def _item_card(item: dict[str, object], *, session_id: str = "") -> str:
    decision = item.get("decision")
    decision_text = decision.decision if isinstance(decision, ItemDecision) else "unreviewed"
    decision_class = "skip" if decision_text in {"reject", "defer"} else "decision"
    plan = item.get("plan")
    plan_group = _plan_group(item)
    plan_reason = plan.reason if isinstance(plan, ReviewPlanEntry) else "No pre-review note."
    plan_badge_class = {
        "review_now": "plan-review",
        "suggested_later": "plan-later",
        "suggested_discard": "plan-discard",
    }.get(plan_group, "plan-later")
    item_id = str(item["id"])
    item_title = str(item["title"])
    item_kind = str(item["kind"])
    item_status = str(item["status"])
    item_snippet = str(item["snippet"])
    item_body = str(item["body"])
    item_translation = str(item.get("translation") or "")
    target_language = _normalize_target_language(str(item.get("target_language") or "zh"))
    preview_html = _markdown_to_html(item_body)
    translation_html = _translation_preview(item_translation, target_language=target_language)
    search_text = " ".join(
        str(value)
        for value in [
            item_title,
            item_kind,
            item_status,
            decision_text,
            item_snippet,
        ]
    )
    search_text = " ".join(search_text.split()).lower()
    return f"""<article class="card" data-review-card data-kind="{_escape(item_kind)}" data-decision="{_escape(decision_text)}" data-plan-group="{_escape(plan_group)}" data-search="{_escape(search_text)}">
  <div class="card-head">
    <div>
      <h3>{_escape(item_title)}</h3>
      <div class="badges">
        <span class="badge kind">{_escape(item_kind)}</span>
        <span class="badge">{_escape(item_status)}</span>
        <span class="badge {decision_class}">{_escape(decision_text)}</span>
        <span class="badge {plan_badge_class}">{_plan_group_label(plan_group)}</span>
      </div>
      <p class="plan-reason"><strong>{_i18n("Pre-review", "预审")}:</strong> {_escape(plan_reason)}</p>
    </div>
  </div>
  <div class="preview">{preview_html}</div>
  {translation_html}
  <form class="controls" method="post" action="/item-action">
    <input type="hidden" name="patch" value="{_escape(session_id)}">
    <input type="hidden" name="item" value="{_escape(item_id)}">
    <div class="simple-actions">
      <button class="primary" type="submit" name="action" value="approve">{_i18n("Submit", "提交")}</button>
      <button class="reject" type="submit" name="action" value="reject">{_i18n("Do Not Submit", "不提交")}</button>
      <label class="select-item">
        {_i18n("Translate to", "翻译为")}
        <select name="target_language">
          {_translation_options(target_language)}
        </select>
      </label>
      <button class="save" type="submit" name="action" value="translate">{_i18n("Translate Preview", "生成翻译预览")}</button>
    </div>
    <details class="review-lab">
      <summary>{_i18n("Edit Markdown or Ask LLM to Revise", "编辑 Markdown 或让 LLM 修改")}</summary>
      <textarea name="body" spellcheck="false">{_escape(item_body)}</textarea>
      <textarea name="instruction" placeholder="写一句修改意见，例如：压缩成一条 issue，删掉重复内容，保留证据" data-placeholder-en="Revision instruction, e.g. shorten this into one issue, remove duplicated claims, keep evidence" data-placeholder-zh="写一句修改意见，例如：压缩成一条 issue，删掉重复内容，保留证据"></textarea>
      <div class="simple-actions">
        <button class="save" type="submit" name="action" value="save">{_i18n("Save Manual Edit", "保存手动修改")}</button>
        <button class="merge" type="submit" name="action" value="revise">{_i18n("Generate Revision with LLM", "让 LLM 生成修订稿")}</button>
      </div>
    </details>
  </form>
</article>"""


def _translation_preview(markdown: str, *, target_language: str) -> str:
    if not markdown.strip():
        return ""
    label_en = language_label(target_language)
    label_zh = _language_label_zh(target_language)
    return f"""<details class="translation-preview" open>
  <summary>{_i18n(f"{label_en} Markdown Preview", f"{label_zh} Markdown 预览")}</summary>
  <p class="translation-note">{_i18n("Display only. The stored Markdown remains English.", "仅用于显示。实际存储的 Markdown 仍然是英文。")}</p>
  <div class="preview">{_markdown_to_html(markdown)}</div>
</details>"""


def revise_candidate_markdown(project: Path, *, body: str, instruction: str) -> str:
    root = project.resolve()
    config = load_retrieval_config(root)
    settings = llm_settings(
        base_url_env=config.llm_base_url_env,
        api_key_env=config.llm_api_key_env,
        model_env=config.llm_model_env,
        project=root,
    )
    if not settings:
        raise RuntimeError(
            "No LLM API is configured. Open Model API in the VibeWiki control "
            "center, or set VIBEWIKI_LLM_BASE_URL, VIBEWIKI_LLM_API_KEY, and "
            "VIBEWIKI_LLM_MODEL."
        )
    system = (
        "You revise VibeWiki candidate memory Markdown for human review. "
        "Return only the full revised Markdown document. Keep the document in English. "
        "Preserve factual evidence, status/kind/type/session metadata, and source claims. "
        "Do not invent facts. If the reviewer asks for deletion or rejection, produce a "
        "short candidate note explaining why it should not be submitted."
    )
    user = f"""Reviewer instruction:
{instruction}

Current candidate Markdown:
{body}
"""
    revised = chat_completion(settings, system=system, user=user)
    return _strip_markdown_fence(revised).strip() + "\n"


def translate_candidate_markdown(
    project: Path,
    *,
    body: str,
    target_language: str = "zh",
) -> str:
    return translate_markdown(
        project.resolve(),
        markdown=body,
        target_language=_normalize_target_language(target_language),
    )


def _translation_options(selected: str) -> str:
    options: list[str] = []
    selected_target = _normalize_target_language(selected)
    for language in TRANSLATION_TARGETS:
        is_selected = " selected" if language == selected_target else ""
        label = f"{language_label(language)} / {_language_label_zh(language)}"
        options.append(
            f'<option value="{_escape(language)}"{is_selected}>{_escape(label)}</option>'
        )
    return "\n".join(options)


def _language_label_zh(language: str) -> str:
    return TRANSLATION_TARGET_LABELS_ZH.get(language, language)


def _normalize_target_language(value: str) -> str:
    language = value.strip()
    return language if language in TRANSLATION_TARGETS else "zh"


def _strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    match = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```$", stripped, re.DOTALL)
    if match:
        return match.group(1)
    return stripped


def _i18n(en: str, zh: str) -> str:
    return f'<span data-i18n data-en="{_escape(en)}" data-zh="{_escape(zh)}">{_escape(zh)}</span>'


def render_markdown_html(text: str) -> str:
    """Render the safe Markdown subset shared by review and conversation views."""
    return _markdown_to_html(text)


def _markdown_to_html(text: str) -> str:
    lines = text.splitlines()
    html_lines: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    ordered_items: list[str] = []
    code_lines: list[str] = []
    in_code = False

    def flush_paragraph() -> None:
        if not paragraph:
            return
        html_lines.append(f"<p>{_inline_markdown(' '.join(paragraph))}</p>")
        paragraph.clear()

    def flush_lists() -> None:
        if list_items:
            rendered = "".join(f"<li>{_inline_markdown(item)}</li>" for item in list_items)
            html_lines.append(f"<ul>{rendered}</ul>")
            list_items.clear()
        if ordered_items:
            rendered = "".join(f"<li>{_inline_markdown(item)}</li>" for item in ordered_items)
            html_lines.append(f"<ol>{rendered}</ol>")
            ordered_items.clear()

    def flush_code() -> None:
        if not code_lines:
            return
        code = "\n".join(code_lines)
        html_lines.append(f"<pre><code>{_escape(code)}</code></pre>")
        code_lines.clear()

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if in_code:
            if stripped.startswith("```"):
                flush_code()
                in_code = False
            else:
                code_lines.append(raw_line)
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            flush_lists()
            in_code = True
            continue
        if not stripped:
            flush_paragraph()
            flush_lists()
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            flush_lists()
            level = min(len(heading.group(1)), 4)
            html_lines.append(f"<h{level}>{_inline_markdown(heading.group(2).strip())}</h{level}>")
            continue

        unordered = re.match(r"^[-*]\s+(.+)$", stripped)
        if unordered:
            flush_paragraph()
            if ordered_items:
                flush_lists()
            list_items.append(unordered.group(1).strip())
            continue

        ordered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if ordered:
            flush_paragraph()
            if list_items:
                flush_lists()
            ordered_items.append(ordered.group(1).strip())
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            flush_lists()
            quote = stripped.lstrip("> ").strip()
            html_lines.append(f"<blockquote><p>{_inline_markdown(quote)}</p></blockquote>")
            continue

        paragraph.append(stripped)

    flush_paragraph()
    flush_lists()
    if in_code:
        flush_code()
    return "\n".join(html_lines)


def _inline_markdown(text: str) -> str:
    rendered = _escape(text)
    rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
    rendered = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", rendered)
    return rendered


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _field(text: str, name: str) -> str:
    prefix = f"{name}:"
    for line in text.splitlines()[:12]:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def _snippet(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        lines.append(clean)
        if len("\n".join(lines)) > 900:
            break
    snippet = "\n".join(lines)
    if len(snippet) > 1100:
        return snippet[:1097] + "..."
    return snippet


def _form_value(data: dict[str, list[str]], key: str) -> str:
    return data.get(key, [""])[0].strip()


def _form_text(data: dict[str, list[str]], key: str) -> str:
    return data.get(key, [""])[0]


def _form_values(data: dict[str, list[str]], key: str) -> list[str]:
    return [value.strip() for value in data.get(key, []) if value.strip()]


def _review_value(decision: object, field: str) -> str:
    if not isinstance(decision, ItemDecision):
        return ""
    return str(getattr(decision, field, "")).strip()


def _message(message: str, message_zh: str = "") -> str:
    if not message and not message_zh:
        return ""
    return (
        '<div class="message" data-i18n '
        f'data-en="{_escape(message or message_zh)}" '
        f'data-zh="{_escape(message_zh or message)}">'
        f"{_escape(message_zh or message)}</div>"
    )


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)
