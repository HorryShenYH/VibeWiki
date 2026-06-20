from __future__ import annotations

import html
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import socketserver
from urllib.parse import parse_qs, urlencode

from .distill import parse_sections
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
from .text_utils import read_text_if_exists


def render_review_ui(project: Path, *, patch_dir: Path | None = None, message: str = "") -> str:
    root = project.resolve()
    ensure_workspace(root)
    selected_patch_dir = (patch_dir or latest_patch_dir(root)).resolve()
    session_id = selected_patch_dir.name
    decisions = read_item_decisions(root, session_id)
    items = _review_items(selected_patch_dir, decisions)
    kinds = sorted({str(item["kind"]) for item in items})
    kind_options = "".join(
        f'<option value="{_escape(kind)}">{_escape(kind)}</option>' for kind in kinds
    )
    session_md = read_text_if_exists(root / ".vibewiki" / "sessions" / session_id / "session.md")
    sections = parse_sections(session_md) if session_md else {}
    goal = sections.get("Goal", "Not provided.").strip()
    outcome = sections.get("Final Outcome", "Not provided.").strip()
    approved = "decision: approved" in read_text_if_exists(
        root / ".vibewiki" / "reviews" / f"{session_id}.yaml"
    )

    return f"""<!doctype html>
<html lang="en">
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
    .snippet {{
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      margin: 12px 0;
      max-height: 210px;
      overflow: auto;
      font-size: 13px;
      white-space: pre-wrap;
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
    .patch-actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    @media (max-width: 900px) {{
      main {{ padding: 16px; }}
      header {{ display: block; }}
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
        <h1>VibeWiki Review / 审核</h1>
        <div class="sub">{_escape(session_id)}</div>
      </div>
      <div class="patch-actions">
        <form method="post" action="/patch-review">
          <button class="primary" type="submit">Approve Patch / 批准整包</button>
        </form>
        <form method="post" action="/merge">
          <button class="merge" type="submit">Merge / 合并</button>
        </form>
      </div>
    </header>
    {_message(message)}
    <section class="layout">
      <aside>
        <section class="panel soft">
          <h2>Session / 会话</h2>
          <div class="text">
            <p><strong>Goal:</strong> {_escape(goal)}</p>
            <p><strong>Outcome:</strong> {_escape(outcome)}</p>
            <p><strong>Patch approved:</strong> {_escape('yes' if approved else 'no')}</p>
            <p><strong>Items:</strong> {_escape(str(len(items)))} / <strong>Reviewed:</strong> {_escape(str(len(decisions)))}</p>
          </div>
        </section>
        <section class="panel">
          <h2>How it works / 怎么用</h2>
          <div class="text">
            <p>Reviewed cards are hidden by default. Turn off hide reviewed if you want to inspect previous decisions.</p>
            <p>已审核卡片默认隐藏。需要回看时取消隐藏已审即可。</p>
            <p>Open Markdown edit on any card to revise the candidate before approving it.</p>
            <p>每张卡片都能展开 Markdown 正文，直接修改候选记忆。</p>
          </div>
        </section>
      </aside>
      <section>
        <section class="panel toolbar" aria-label="Review tools">
          <div class="toolbar-row">
            <input id="filter-text" type="search" placeholder="Search candidates / 搜索候选">
            <select id="filter-kind" aria-label="Kind filter">
              <option value="">All kinds / 全部类型</option>
              {kind_options}
            </select>
            <label class="inline">
              <input id="hide-reviewed" type="checkbox" checked>
              Hide reviewed / 隐藏已审
            </label>
            <span id="visible-count" class="count">{_escape(str(len(items)))} / {_escape(str(len(items)))}</span>
          </div>
          <form id="bulk-form" class="bulk-row" method="post" action="/bulk-decision">
            <select name="decision" aria-label="Bulk decision">
              <option value="approve">Approve selected / 批准所选</option>
              <option value="reject">Reject selected / 拒绝所选</option>
              <option value="defer">Defer selected / 稍后处理</option>
            </select>
            <input name="note" placeholder="Bulk note / 批量备注">
            <button class="primary" type="submit">Apply / 应用</button>
          </form>
        </section>
        <section class="stack">
        {''.join(_item_card(item) for item in items)}
        </section>
      </section>
    </section>
  </main>
  <script>
    (() => {{
      const messages = document.querySelectorAll(".message");
      window.setTimeout(() => {{
        messages.forEach((message) => {{
          message.classList.add("hide");
          window.setTimeout(() => message.remove(), 350);
        }});
      }}, 3200);

      const cards = Array.from(document.querySelectorAll("[data-review-card]"));
      const textFilter = document.getElementById("filter-text");
      const kindFilter = document.getElementById("filter-kind");
      const hideReviewed = document.getElementById("hide-reviewed");
      const visibleCount = document.getElementById("visible-count");

      function applyFilters() {{
        const query = (textFilter.value || "").trim().toLowerCase();
        const kind = kindFilter.value;
        const shouldHideReviewed = hideReviewed.checked;
        let visible = 0;
        cards.forEach((card) => {{
          const matchesText = !query || (card.dataset.search || "").includes(query);
          const matchesKind = !kind || card.dataset.kind === kind;
          const reviewed = card.dataset.decision && card.dataset.decision !== "unreviewed";
          const matchesReviewState = !shouldHideReviewed || !reviewed;
          const show = matchesText && matchesKind && matchesReviewState;
          card.hidden = !show;
          if (show) visible += 1;
        }});
        visibleCount.textContent = `${{visible}} / ${{cards.length}}`;
      }}

      [textFilter, kindFilter, hideReviewed].forEach((control) => {{
        control.addEventListener("input", applyFilters);
        control.addEventListener("change", applyFilters);
      }});

      const bulkForm = document.getElementById("bulk-form");
      bulkForm.addEventListener("submit", (event) => {{
        const checked = document.querySelectorAll('input[name="item"][form="bulk-form"]:checked');
        if (!checked.length) {{
          event.preventDefault();
          window.alert("Select at least one item / 请至少选择一项");
        }}
      }});

      applyFilters();
    }})();
  </script>
</body>
</html>
"""


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
            if "?" in self.path:
                query = self.path.split("?", 1)[1]
                message = parse_qs(query).get("message", [""])[0]
            self._send_html(render_review_ui(root, patch_dir=selected_patch_dir, message=message))

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0") or 0)
            data = parse_qs(self.rfile.read(length).decode("utf-8"))
            try:
                if self.path == "/decision":
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
                    self._redirect(f"Recorded {decision} for {item}")
                    return
                if self.path == "/bulk-decision":
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
                    self._redirect(f"Recorded {decision} for {len(items)} items")
                    return
                if self.path == "/save-item":
                    item = _form_value(data, "item")
                    update_item_body(
                        root,
                        patch_dir=selected_patch_dir,
                        item=item,
                        body=_form_text(data, "body"),
                    )
                    self._redirect(f"Saved Markdown for {item}")
                    return
                if self.path == "/patch-review":
                    review_patches(root, patch_dir=selected_patch_dir, approve=True)
                    self._redirect("Patch approved")
                    return
                if self.path == "/merge":
                    changed = merge_patches(root, patch_dir=selected_patch_dir)
                    self._redirect(f"Merged {len(changed)} files")
                    return
                self.send_error(404, "Unknown action")
            except Exception as exc:
                self._redirect(f"Error: {exc}")

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_html(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _redirect(self, message: str) -> None:
            target = "/?" + urlencode({"message": message})
            self.send_response(303)
            self.send_header("Location", target)
            self.end_headers()

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer((host, port), ReviewHandler) as server:
        print(f"VibeWiki review UI: http://{host}:{port}/")
        print(f"Patch: {selected_patch_dir}")
        server.serve_forever()


def _review_items(patch_dir: Path, decisions: dict[str, ItemDecision]) -> list[dict[str, object]]:
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
                    "snippet": _snippet(text),
                    "body": text,
                }
            )
    return items


def _item_card(item: dict[str, object]) -> str:
    decision = item.get("decision")
    decision_text = decision.decision if isinstance(decision, ItemDecision) else "unreviewed"
    decision_class = "skip" if decision_text in {"reject", "defer"} else "decision"
    item_id = str(item["id"])
    item_title = str(item["title"])
    item_kind = str(item["kind"])
    item_status = str(item["status"])
    item_snippet = str(item["snippet"])
    item_body = str(item["body"])
    title = _review_value(decision, "title")
    target = _review_value(decision, "target")
    tags = _review_value(decision, "tags")
    summary = _review_value(decision, "summary")
    note = _review_value(decision, "note")
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
    return f"""<article class="card" data-review-card data-kind="{_escape(item_kind)}" data-decision="{_escape(decision_text)}" data-search="{_escape(search_text)}">
  <div class="card-head">
    <div>
      <h3>{_escape(item_title)}</h3>
      <div class="badges">
        <span class="badge kind">{_escape(item_kind)}</span>
        <span class="badge">{_escape(item_status)}</span>
        <span class="badge {decision_class}">{_escape(decision_text)}</span>
      </div>
    </div>
    <label class="select-item">
      <input type="checkbox" name="item" value="{_escape(item_id)}" form="bulk-form">
      Select / 选择
    </label>
  </div>
  <div class="snippet">{_escape(item_snippet)}</div>
  <form class="controls" method="post" action="/decision">
    <input type="hidden" name="item" value="{_escape(item_id)}">
    <div class="fields">
      <input name="title" value="{_escape(title)}" placeholder="Title / 标题">
      <input name="target" value="{_escape(target)}" placeholder="Target: knowledge or existing-slug / 目标">
      <input name="tags" value="{_escape(tags)}" placeholder="Tags / 标签">
      <textarea name="summary" placeholder="Summary / 摘要">{_escape(summary)}</textarea>
    </div>
    <textarea name="note" placeholder="Note / 备注">{_escape(note)}</textarea>
    <div class="buttons">
      <button class="primary" type="submit" name="decision" value="approve">Approve / 批准</button>
      <button class="reject" type="submit" name="decision" value="reject">Reject / 拒绝</button>
      <button class="defer" type="submit" name="decision" value="defer">Defer / 稍后</button>
      <button type="submit" name="decision" value="downgrade">Downgrade / 降为知识</button>
      <button class="merge" type="submit" name="decision" value="merge">Merge / 合入已有</button>
      <button type="submit" name="decision" value="edit">Edit / 编辑后批准</button>
    </div>
  </form>
  <details class="editor">
    <summary>Edit Markdown / 修改正文</summary>
    <form class="controls" method="post" action="/save-item">
      <input type="hidden" name="item" value="{_escape(item_id)}">
      <textarea name="body" spellcheck="false">{_escape(item_body)}</textarea>
      <div class="buttons">
        <button class="primary" type="submit">Save Markdown / 保存正文</button>
      </div>
    </form>
  </details>
</article>"""


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


def _message(message: str) -> str:
    if not message:
        return ""
    return f'<div class="message">{_escape(message)}</div>'


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)
