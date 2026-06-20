from __future__ import annotations

import html
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from .distill import parse_sections
from .project import ensure_workspace
from .review import ItemDecision, latest_patch_dir, read_item_decisions
from .text_utils import read_text_if_exists


@dataclass(frozen=True)
class BoardItem:
    title: str
    path: Path
    item_id: str
    kind: str
    status: str
    confidence: str
    body: str
    decision: ItemDecision | None = None


def generate_review_board(
    project: Path,
    *,
    patch_dir: Path | None = None,
    output: Path | None = None,
) -> Path:
    root = project.resolve()
    ensure_workspace(root)
    selected_patch_dir = (patch_dir or latest_patch_dir(root)).resolve()
    session_id = selected_patch_dir.name
    session_dir = root / ".vibewiki" / "sessions" / session_id
    output_path = (output.resolve() if output else selected_patch_dir / "review_board.html")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session_md = read_text_if_exists(session_dir / "session.md")
    session_sections = parse_sections(session_md) if session_md else {}
    findings_index = read_text_if_exists(selected_patch_dir / "findings" / "index.md")
    composable_index = read_text_if_exists(selected_patch_dir / "composable_units.md")
    questions = read_text_if_exists(selected_patch_dir / "questions.md")
    merge_suggestions = read_text_if_exists(selected_patch_dir / "merge_suggestions.md")
    decisions = read_item_decisions(root, session_id)

    finding_items = _items_from_dir(selected_patch_dir, selected_patch_dir / "findings", "finding", decisions)
    skilllets = _items_from_dir(selected_patch_dir, selected_patch_dir / "skilllets", "skilllet", decisions)
    prompt_patterns = _items_from_dir(
        selected_patch_dir,
        selected_patch_dir / "prompt_patterns",
        "prompt pattern",
        decisions,
    )
    workflows = _items_from_dir(selected_patch_dir, selected_patch_dir / "workflows", "workflow", decisions)

    html_text = _render_board(
        root=root,
        session_id=session_id,
        session_dir=session_dir,
        patch_dir=selected_patch_dir,
        output_path=output_path,
        session_sections=session_sections,
        findings_index=findings_index,
        composable_index=composable_index,
        questions=questions,
        merge_suggestions=merge_suggestions,
        finding_items=finding_items,
        skilllets=skilllets,
        prompt_patterns=prompt_patterns,
        workflows=workflows,
    )
    output_path.write_text(html_text, encoding="utf-8")
    return output_path


def _items_from_dir(
    patch_dir: Path,
    directory: Path,
    fallback_kind: str,
    decisions: dict[str, ItemDecision],
) -> list[BoardItem]:
    if not directory.exists():
        return []
    items: list[BoardItem] = []
    for path in sorted(directory.glob("*.md")):
        if path.name == "index.md":
            continue
        text = path.read_text(encoding="utf-8")
        metadata = _front_matterish_fields(text)
        item_id = path.resolve().relative_to(patch_dir.resolve()).as_posix()
        items.append(
            BoardItem(
                title=_first_heading(text) or path.stem.replace("-", " ").title(),
                path=path,
                item_id=item_id,
                kind=metadata.get("kind") or metadata.get("type") or fallback_kind,
                status=metadata.get("status") or "candidate",
                confidence=metadata.get("confidence") or "",
                body=text,
                decision=decisions.get(item_id),
            )
        )
    return items


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _front_matterish_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines()[:12]:
        match = re.match(r"^([A-Za-z][A-Za-z ]+):\s*(.+)$", line.strip())
        if not match:
            continue
        key = match.group(1).strip().lower().replace(" ", "_")
        fields[key] = match.group(2).strip()
    return fields


def _render_board(
    *,
    root: Path,
    session_id: str,
    session_dir: Path,
    patch_dir: Path,
    output_path: Path,
    session_sections: dict[str, str],
    findings_index: str,
    composable_index: str,
    questions: str,
    merge_suggestions: str,
    finding_items: list[BoardItem],
    skilllets: list[BoardItem],
    prompt_patterns: list[BoardItem],
    workflows: list[BoardItem],
) -> str:
    goal = session_sections.get("Goal", "Not provided.").strip()
    outcome = session_sections.get("Final Outcome", "Not provided.").strip()
    commands = session_sections.get("Key Commands", "Not provided.").strip()
    tests = session_sections.get("Tests / Verification", "Not provided.").strip()
    units_count = len(skilllets) + len(prompt_patterns) + len(workflows)
    approve_command = (
        f"vibewiki --project {_shell_quote(root)} review --patch-dir {_shell_quote(patch_dir)} --approve"
    )
    merge_command = f"vibewiki --project {_shell_quote(root)} merge --patch-dir {_shell_quote(patch_dir)}"
    review_command = f"vibewiki --project {_shell_quote(root)} review --patch-dir {_shell_quote(patch_dir)}"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VibeWiki Review Board - {_escape(session_id)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f5;
      --surface: #ffffff;
      --surface-soft: #eef4f3;
      --ink: #171a1c;
      --muted: #5d666f;
      --line: #d9ded8;
      --teal: #0f766e;
      --blue: #2563eb;
      --amber: #b45309;
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
    a {{ color: var(--blue); text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    .shell {{ max-width: 1440px; margin: 0 auto; padding: 24px; }}
    .topbar {{
      display: flex;
      gap: 16px;
      align-items: flex-start;
      justify-content: space-between;
      padding: 18px 0 20px;
      border-bottom: 1px solid var(--line);
    }}
    h1, h2, h3 {{ margin: 0; line-height: 1.2; letter-spacing: 0; }}
    h1 {{ font-size: clamp(24px, 3vw, 36px); }}
    h2 {{ font-size: 18px; margin-bottom: 12px; }}
    h3 {{ font-size: 15px; }}
    .muted {{ color: var(--muted); }}
    .session-id {{ margin-top: 6px; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }}
    .action {{
      display: inline-flex;
      align-items: center;
      min-height: 36px;
      padding: 7px 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      color: var(--ink);
      font-size: 13px;
      text-decoration: none;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 20px 0;
    }}
    .metric {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-height: 82px;
    }}
    .metric strong {{ display: block; font-size: 24px; }}
    .metric span {{ color: var(--muted); font-size: 13px; }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(280px, 0.9fr) minmax(360px, 1.35fr) minmax(320px, 1.05fr);
      gap: 16px;
      align-items: start;
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 16px;
    }}
    .panel.soft {{ background: var(--surface-soft); }}
    .stack {{ display: grid; gap: 12px; }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }}
    .card-head {{
      display: flex;
      gap: 10px;
      align-items: flex-start;
      justify-content: space-between;
      margin-bottom: 10px;
    }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 22px;
      padding: 2px 7px;
      border-radius: 999px;
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    .badge.kind {{ border-color: #99c8c2; color: var(--teal); }}
    .badge.warn {{ border-color: #e5c38b; color: var(--amber); }}
    .badge.status {{ border-color: #e5a3b2; color: var(--rose); }}
    .md {{ font-size: 13px; color: #202427; }}
    .md h1, .md h2, .md h3 {{ font-size: 14px; margin: 13px 0 7px; }}
    .md p {{ margin: 8px 0; }}
    .md ul {{ margin: 8px 0; padding-left: 18px; }}
    .md li {{ margin: 4px 0; }}
    .md pre, .command {{
      overflow-x: auto;
      border-radius: 8px;
      background: var(--code);
      color: #f8fafc;
      padding: 10px;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    .review-commands {{
      margin-top: 12px;
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .review-commands summary {{
      cursor: pointer;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }}
    .summary-row {{ display: grid; gap: 10px; }}
    .summary-row dt {{ color: var(--muted); font-size: 12px; margin-bottom: 2px; }}
    .summary-row dd {{ margin: 0; }}
    .empty {{ color: var(--muted); font-size: 13px; padding: 8px 0; }}
    @media (max-width: 1120px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .actions {{ justify-content: flex-start; }}
    }}
    @media (max-width: 760px) {{
      .shell {{ padding: 16px; }}
      .topbar {{ display: block; }}
      .actions {{ margin-top: 14px; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div>
        <h1>Review Board</h1>
        <div class="session-id">{_escape(session_id)}</div>
      </div>
      <nav class="actions" aria-label="Artifacts">
        {_artifact_link("Session", session_dir / "session.md", output_path)}
        {_artifact_link("Raw", session_dir / "raw_session.md", output_path)}
        {_artifact_link("Patch", patch_dir, output_path)}
      </nav>
    </header>

    <section class="metrics" aria-label="Patch Counts">
      {_metric("Findings", len(finding_items), "candidate notes")}
      {_metric("Skilllets", len(skilllets), "small capabilities")}
      {_metric("Patterns", len(prompt_patterns), "prompt shapes")}
      {_metric("Workflows", len(workflows), "larger procedures")}
    </section>

    <section class="layout">
      <div>
        <section class="panel soft">
          <h2>Session</h2>
          <dl class="summary-row">
            <div><dt>Goal</dt><dd>{_inline_markdown(goal)}</dd></div>
            <div><dt>Outcome</dt><dd>{_inline_markdown(outcome)}</dd></div>
            <div><dt>Commands</dt><dd>{_markdown_block(commands)}</dd></div>
            <div><dt>Verification</dt><dd>{_markdown_block(tests)}</dd></div>
          </dl>
        </section>
        <section class="panel">
          <h2>Commands</h2>
          <div class="command">{_escape(review_command)}

{_escape(approve_command)}

{_escape(merge_command)}</div>
        </section>
        <section class="panel">
          <h2>Questions</h2>
          {_markdown_block(questions)}
        </section>
      </div>

      <div>
        <section class="panel">
          <h2>Findings</h2>
          {_markdown_block(findings_index)}
        </section>
        <div class="stack">
          {_cards(finding_items, root, patch_dir, output_path)}
        </div>
      </div>

      <div>
        <section class="panel">
          <h2>Composable Units</h2>
          {_markdown_block(composable_index)}
        </section>
        <section class="panel">
          <h2>Merge Suggestions</h2>
          {_markdown_block(merge_suggestions)}
        </section>
        <div class="stack">
          {_cards([*skilllets, *prompt_patterns, *workflows], root, patch_dir, output_path)}
          {_empty(units_count, "No candidate reusable units.")}
        </div>
      </div>
    </section>
  </main>
</body>
</html>
"""


def _metric(label: str, value: int, caption: str) -> str:
    return f"""<div class="metric"><strong>{value}</strong><span>{_escape(label)} - {_escape(caption)}</span></div>"""


def _cards(items: list[BoardItem], root: Path, patch_dir: Path, output_path: Path) -> str:
    return "\n".join(_card(item, root, patch_dir, output_path) for item in items)


def _card(item: BoardItem, root: Path, patch_dir: Path, output_path: Path) -> str:
    badges = [
        f'<span class="badge kind">{_escape(item.kind)}</span>',
        f'<span class="badge status">{_escape(item.status)}</span>',
    ]
    if item.confidence:
        badges.append(f'<span class="badge warn">confidence: {_escape(item.confidence)}</span>')
    if item.decision:
        badges.append(f'<span class="badge kind">decision: {_escape(item.decision.decision)}</span>')
        if item.decision.target:
            badges.append(f'<span class="badge">target: {_escape(item.decision.target)}</span>')
    return f"""<article class="card">
  <div class="card-head">
    <div>
      <h3>{_escape(item.title)}</h3>
      <div class="badges">{"".join(badges)}</div>
    </div>
    {_artifact_link("Open", item.path, output_path)}
  </div>
  {_markdown_block(_important_sections(item.body))}
  {_review_command_block(item, root, patch_dir)}
</article>"""


def _review_command_block(item: BoardItem, root: Path, patch_dir: Path) -> str:
    base = (
        f"vibewiki --project {_shell_quote(root)} review-item "
        f"--patch-dir {_shell_quote(patch_dir)} --item {_shell_quote(Path(item.item_id))}"
    )
    commands = [
        f"{base} --decision approve",
        f"{base} --decision reject --note {_shell_quote('reason')}",
        f"{base} --decision defer --note {_shell_quote('why later')}",
        f"{base} --decision edit --title {_shell_quote('New title')} --summary {_shell_quote('Reviewed summary')}",
        f"{base} --decision downgrade --target knowledge",
    ]
    if not item.item_id.startswith("findings/"):
        commands.append(f"{base} --decision merge --target {_shell_quote('existing-unit-slug')}")
    current = []
    if item.decision:
        current = [
            f"current decision: {item.decision.decision}",
            f"target: {item.decision.target or 'not set'}",
            f"note: {item.decision.note or 'none'}",
            "",
        ]
    return f"""<details class="review-commands">
  <summary>Item review commands</summary>
  <div class="command">{_escape(chr(10).join([*current, *commands]))}</div>
</details>"""


def _important_sections(markdown: str) -> str:
    sections = parse_sections(markdown)
    preferred = [
        "Summary",
        "Purpose",
        "When To Use",
        "Inputs",
        "Outputs",
        "Steps",
        "Verification",
        "Evidence From Session",
        "Follow Up",
        "Related Units",
    ]
    blocks: list[str] = []
    for name in preferred:
        text = sections.get(name, "").strip()
        if text and text != "Not provided.":
            blocks.append(f"### {name}\n\n{text}")
    if blocks:
        return "\n\n".join(blocks)
    return markdown


def _artifact_link(label: str, path: Path, output_path: Path) -> str:
    if not path.exists():
        return ""
    href = os.path.relpath(path, output_path.parent)
    return f'<a class="action" href="{_escape(href)}">{_escape(label)}</a>'


def _empty(count: int, message: str) -> str:
    if count:
        return ""
    return f'<div class="empty">{_escape(message)}</div>'


def _markdown_block(markdown: str) -> str:
    clean = markdown.strip()
    if not clean or clean == "Not provided.":
        return '<div class="empty">Not provided.</div>'
    return f'<div class="md">{_render_markdown(clean)}</div>'


def _render_markdown(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    bullets: list[str] = []
    table: list[str] = []
    code: list[str] = []
    in_code = False

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{_inline_markdown(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_bullets() -> None:
        if bullets:
            output.append("<ul>" + "".join(f"<li>{_inline_markdown(item)}</li>" for item in bullets) + "</ul>")
            bullets.clear()

    def flush_table() -> None:
        if table:
            output.append(f"<pre>{_escape(chr(10).join(table))}</pre>")
            table.clear()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                output.append(f"<pre>{_escape(chr(10).join(code))}</pre>")
                code.clear()
                in_code = False
            else:
                flush_paragraph()
                flush_bullets()
                flush_table()
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        if not stripped:
            flush_paragraph()
            flush_bullets()
            flush_table()
            continue
        if stripped.startswith("#"):
            flush_paragraph()
            flush_bullets()
            flush_table()
            level = min(len(stripped) - len(stripped.lstrip("#")), 3)
            text = stripped[level:].strip()
            output.append(f"<h{level}>{_inline_markdown(text)}</h{level}>")
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            flush_table()
            bullets.append(stripped[2:].strip())
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            flush_bullets()
            table.append(stripped)
            continue
        flush_bullets()
        flush_table()
        paragraph.append(stripped)
    flush_paragraph()
    flush_bullets()
    flush_table()
    if in_code:
        output.append(f"<pre>{_escape(chr(10).join(code))}</pre>")
    return "\n".join(output)


def _inline_markdown(text: str) -> str:
    escaped = _escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _shell_quote(path: Path) -> str:
    return shlex.quote(str(path))
