from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import html
import json
import math
from pathlib import Path
import re

from .doctor import build_doctor_report
from .events import read_events
from .memory_cards import MemoryCard, collect_memory_cards
from .text_utils import utcish_timestamp


PALETTE = [
    "#2a9d8f",
    "#e9c46a",
    "#e76f51",
    "#457b9d",
    "#8ab17d",
    "#6d597a",
    "#f4a261",
    "#264653",
]

LABELS = {
    "en": {
        "title": "VibeWiki Dashboard",
        "eyebrow": "reviewed memory system",
        "subtitle": "A compact view of sessions, candidate memory, review progress, and reusable project knowledge.",
        "sessions": "Sessions",
        "patches": "Patches",
        "cards": "Memory Cards",
        "reviews": "Review Records",
        "next": "Next Step",
        "status": "Memory Status",
        "types": "Card Types",
        "funnel": "Review Funnel",
        "activity": "Recent Activity",
        "recent_cards": "Recent Memory Cards",
        "workspace": "Workspace",
        "approved": "approved",
        "candidate": "candidate",
        "missing": "missing",
        "generated": "Generated",
        "no_data": "No data yet",
        "open_items": "open items",
        "reviewed_items": "reviewed items",
        "approved_items": "approved items",
        "events": "events",
        "source": "source",
        "actor": "actor",
    },
    "zh": {
        "title": "VibeWiki 仪表盘",
        "eyebrow": "可审查记忆系统",
        "subtitle": "用一页看清会话、候选记忆、审核进度和可复用项目知识。",
        "sessions": "会话",
        "patches": "补丁",
        "cards": "记忆卡片",
        "reviews": "审核记录",
        "next": "下一步",
        "status": "记忆状态",
        "types": "卡片类型",
        "funnel": "审核漏斗",
        "activity": "最近活动",
        "recent_cards": "最近记忆卡片",
        "workspace": "工作区",
        "approved": "已审核",
        "candidate": "候选",
        "missing": "缺失",
        "generated": "生成时间",
        "no_data": "暂无数据",
        "open_items": "待审核",
        "reviewed_items": "已处理",
        "approved_items": "已批准",
        "events": "事件",
        "source": "来源",
        "actor": "记录人",
    },
}


@dataclass(frozen=True)
class DashboardData:
    root: Path
    project_name: str
    generated_at: str
    workspace_exists: bool
    sessions: list[Path]
    patches: list[Path]
    review_files: list[Path]
    cards: list[MemoryCard]
    status_counts: Counter[str]
    kind_counts: Counter[str]
    decision_counts: Counter[str]
    event_counts: Counter[str]
    recent_events: list[dict[str, object]]
    next_steps: list[str]


def generate_dashboard(project: Path, *, output: Path | None = None, lang: str = "zh") -> Path:
    root = project.expanduser().resolve()
    data = build_dashboard_data(root)
    output_path = output.expanduser().resolve() if output else root / ".vibewiki" / "dashboard.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_dashboard_html(data, lang=lang), encoding="utf-8")
    return output_path


def build_dashboard_data(project: Path) -> DashboardData:
    root = project.expanduser().resolve()
    workspace = root / ".vibewiki"
    workspace_exists = workspace.exists()
    sessions = _directories(workspace / "sessions")
    patches = _directories(workspace / "patches")
    review_files = _review_files(workspace / "reviews")
    cards = collect_memory_cards(root, scope="all", ensure=False) if workspace_exists else []
    status_counts = Counter(card.status for card in cards)
    kind_counts = Counter(_kind_label(card.kind) for card in cards)
    decision_counts = _decision_counts(review_files)
    events = read_events(root, limit=None)
    event_counts = Counter(str(event.get("type", "") or "unknown") for event in events)
    doctor = build_doctor_report(root)
    return DashboardData(
        root=root,
        project_name=_project_name(root),
        generated_at=utcish_timestamp(),
        workspace_exists=workspace_exists,
        sessions=sessions,
        patches=patches,
        review_files=review_files,
        cards=cards,
        status_counts=status_counts,
        kind_counts=kind_counts,
        decision_counts=decision_counts,
        event_counts=event_counts,
        recent_events=events[-8:],
        next_steps=doctor.next_steps,
    )


def render_dashboard_html(data: DashboardData, *, lang: str = "zh") -> str:
    clean_lang = lang if lang in LABELS else "zh"
    labels = LABELS[clean_lang]
    approved_cards = data.status_counts.get("approved", 0)
    candidate_cards = data.status_counts.get("candidate", 0)
    reviewed_items = sum(data.decision_counts.values())
    approved_items = data.decision_counts.get("approve", 0)
    candidate_items = candidate_cards
    open_items = max(candidate_items - reviewed_items, 0)
    funnel = [
        (labels["sessions"], len(data.sessions)),
        (labels["patches"], len(data.patches)),
        (labels["candidate"], candidate_items),
        (labels["reviewed_items"], reviewed_items),
        (labels["approved_items"], approved_items),
    ]
    status_segments = [
        (labels["approved"], approved_cards, PALETTE[0]),
        (labels["candidate"], candidate_cards, PALETTE[2]),
    ]
    kind_rows = _top_counts(data.kind_counts, limit=7)
    event_rows = _top_counts(data.event_counts, limit=7)
    event_total = sum(data.event_counts.values())
    recent_cards = _recent_cards(data.cards, limit=6)
    next_steps = data.next_steps or ["vibewiki init"]

    return f"""<!doctype html>
<html lang="{_escape(clean_lang)}" data-vibewiki-dashboard="1">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(labels["title"])} - {_escape(data.project_name)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #667085;
      --line: #d9ded8;
      --paper: #fbfcfa;
      --field: #f2f5f1;
      --teal: #2a9d8f;
      --gold: #e9c46a;
      --coral: #e76f51;
      --blue: #457b9d;
      --green: #8ab17d;
      --shadow: 0 16px 36px rgba(23, 32, 42, 0.09);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        linear-gradient(135deg, rgba(42, 157, 143, 0.12), transparent 34%),
        linear-gradient(315deg, rgba(233, 196, 106, 0.16), transparent 38%),
        var(--field);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.5;
    }}
    .shell {{
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 42px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 20px;
      align-items: end;
      padding: 28px;
      border: 1px solid rgba(23, 32, 42, 0.1);
      background: rgba(251, 252, 250, 0.86);
      box-shadow: var(--shadow);
      border-radius: 8px;
    }}
    .eyebrow {{
      color: var(--teal);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 6px 0 8px;
      font-size: 54px;
      line-height: 1;
      letter-spacing: 0;
    }}
    .subtitle {{
      max-width: 760px;
      margin: 0;
      color: var(--muted);
      font-size: 17px;
    }}
    .stamp {{
      min-width: 220px;
      padding: 16px;
      border-left: 4px solid var(--gold);
      background: #fff;
      border-radius: 8px;
      font-size: 13px;
      color: var(--muted);
    }}
    .stamp strong {{
      display: block;
      color: var(--ink);
      font-size: 15px;
      margin-bottom: 4px;
      overflow-wrap: anywhere;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin: 18px 0;
    }}
    .metric, .panel, .next {{
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.86);
      border-radius: 8px;
    }}
    .metric {{
      padding: 18px;
      min-height: 118px;
    }}
    .metric b {{
      display: block;
      font-size: 34px;
      line-height: 1;
      margin-bottom: 12px;
    }}
    .metric span {{
      color: var(--muted);
      font-size: 14px;
      font-weight: 650;
    }}
    .metric small {{
      display: block;
      color: var(--muted);
      margin-top: 8px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(0, .85fr);
      gap: 18px;
      align-items: start;
    }}
    .panel {{
      padding: 20px;
      min-width: 0;
      overflow: hidden;
    }}
    .panel h2, .next h2 {{
      margin: 0 0 16px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .chart-grid {{
      display: grid;
      grid-template-columns: minmax(220px, .8fr) minmax(0, 1.2fr);
      gap: 18px;
      align-items: center;
    }}
    svg {{
      display: block;
      width: 100%;
      height: auto;
    }}
    .legend {{
      display: grid;
      gap: 9px;
      color: var(--muted);
      font-size: 14px;
    }}
    .legend-row, .event-row, .card-row {{
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
    }}
    .swatch {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
    }}
    .count {{
      color: var(--ink);
      font-weight: 800;
    }}
    .next {{
      padding: 18px 20px;
      margin: 18px 0;
      border-left: 4px solid var(--teal);
    }}
    .next code {{
      display: block;
      width: 100%;
      padding: 12px;
      margin-top: 10px;
      background: #16202a;
      color: #f8faf7;
      border-radius: 6px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
    }}
    .events, .cards {{
      display: grid;
      gap: 10px;
    }}
    .event-row, .card-row {{
      grid-template-columns: 96px minmax(0, 1fr) auto;
      padding: 11px 0;
      border-bottom: 1px solid var(--line);
      font-size: 14px;
    }}
    .event-row:last-child, .card-row:last-child {{
      border-bottom: 0;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      width: fit-content;
      min-height: 24px;
      padding: 2px 9px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--paper);
      color: var(--muted);
      font-size: 12px;
      font-weight: 750;
      white-space: nowrap;
    }}
    .card-title, .event-subject {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .card-title strong {{
      display: block;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}
    .card-title small {{
      color: var(--muted);
    }}
    .muted {{
      color: var(--muted);
    }}
    .footer {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
      text-align: center;
    }}
    @media (max-width: 900px) {{
      .hero, .grid, .chart-grid {{
        grid-template-columns: 1fr;
      }}
      .metrics {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 560px) {{
      .shell {{
        width: min(100vw - 20px, 1180px);
        padding-top: 10px;
      }}
      .hero, .panel, .next {{
        padding: 16px;
      }}
      .metrics {{
        grid-template-columns: 1fr;
      }}
      .event-row, .card-row {{
        grid-template-columns: 1fr;
      }}
      .stamp {{
        min-width: 0;
      }}
      h1 {{
        font-size: 34px;
      }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <div class="eyebrow">{_escape(labels["eyebrow"])}</div>
        <h1>{_escape(data.project_name)}</h1>
        <p class="subtitle">{_escape(labels["subtitle"])}</p>
      </div>
      <aside class="stamp">
        <strong>{_escape(labels["workspace"])}: {_escape(_workspace_state(data, labels))}</strong>
        {_escape(labels["generated"])}: {_escape(data.generated_at)}
      </aside>
    </section>

    <section class="metrics" aria-label="VibeWiki metrics">
      {_metric(labels["sessions"], len(data.sessions), f'{event_total} {labels["events"]}')}
      {_metric(labels["patches"], len(data.patches), f'{open_items} {labels["open_items"]}')}
      {_metric(labels["cards"], len(data.cards), f'{approved_cards} {labels["approved"]} / {candidate_cards} {labels["candidate"]}')}
      {_metric(labels["reviews"], len(data.review_files), f'{reviewed_items} {labels["reviewed_items"]}')}
    </section>

    <section class="next">
      <h2>{_escape(labels["next"])}</h2>
      <code>{_escape(next_steps[0])}</code>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>{_escape(labels["status"])}</h2>
        <div class="chart-grid">
          {_donut_svg(status_segments)}
          <div class="legend">
            {_legend(status_segments)}
          </div>
        </div>
      </div>

      <div class="panel">
        <h2>{_escape(labels["funnel"])}</h2>
        {_funnel_svg(funnel)}
      </div>

      <div class="panel">
        <h2>{_escape(labels["types"])}</h2>
        {_bar_svg(kind_rows, empty_label=labels["no_data"])}
      </div>

      <div class="panel">
        <h2>{_escape(labels["activity"])}</h2>
        {_event_list(data.recent_events, labels)}
      </div>

      <div class="panel">
        <h2>{_escape(labels["recent_cards"])}</h2>
        {_card_list(recent_cards, data.root, labels)}
      </div>

      <div class="panel">
        <h2>{_escape(labels["events"])}</h2>
        {_bar_svg(event_rows, empty_label=labels["no_data"])}
      </div>
    </section>

    <p class="footer">VibeWiki keeps the storage boring and the memory reviewable.</p>
  </main>
</body>
</html>
"""


def _metric(label: str, value: int, detail: str) -> str:
    return f"""<article class="metric">
  <b>{value}</b>
  <span>{_escape(label)}</span>
  <small>{_escape(detail)}</small>
</article>"""


def _donut_svg(segments: list[tuple[str, int, str]]) -> str:
    total = sum(value for _, value, _ in segments)
    if total <= 0:
        return """<svg viewBox="0 0 120 120" role="img" aria-label="No memory cards">
  <circle cx="60" cy="60" r="42" fill="none" stroke="#d9ded8" stroke-width="16"/>
  <text x="60" y="57" text-anchor="middle" font-size="18" font-weight="800" fill="#17202a">0</text>
  <text x="60" y="74" text-anchor="middle" font-size="10" fill="#667085">cards</text>
</svg>"""
    circumference = 2 * math.pi * 42
    offset = 0.0
    circles: list[str] = [
        '<circle cx="60" cy="60" r="42" fill="none" stroke="#d9ded8" stroke-width="16"/>'
    ]
    for _, value, color in segments:
        if value <= 0:
            continue
        length = circumference * (value / total)
        gap = circumference - length
        circles.append(
            '<circle cx="60" cy="60" r="42" fill="none" '
            f'stroke="{_escape(color)}" stroke-width="16" stroke-linecap="round" '
            f'stroke-dasharray="{length:.3f} {gap:.3f}" stroke-dashoffset="{-offset:.3f}" '
            'transform="rotate(-90 60 60)"/>'
        )
        offset += length
    return f"""<svg viewBox="0 0 120 120" role="img" aria-label="Memory status">
  {"".join(circles)}
  <text x="60" y="58" text-anchor="middle" font-size="20" font-weight="800" fill="#17202a">{total}</text>
  <text x="60" y="75" text-anchor="middle" font-size="10" fill="#667085">cards</text>
</svg>"""


def _legend(segments: list[tuple[str, int, str]]) -> str:
    if not any(value for _, value, _ in segments):
        return '<div class="muted">No memory cards yet.</div>'
    rows = []
    for label, value, color in segments:
        rows.append(
            f"""<div class="legend-row">
  <span class="swatch" style="background:{_escape(color)}"></span>
  <span>{_escape(label)}</span>
  <span class="count">{value}</span>
</div>"""
        )
    return "\n".join(rows)


def _bar_svg(rows: list[tuple[str, int]], *, empty_label: str) -> str:
    if not rows:
        return f'<p class="muted">{_escape(empty_label)}</p>'
    width = 640
    row_height = 42
    left = 150
    chart_width = 420
    height = max(92, 28 + row_height * len(rows))
    max_value = max(value for _, value in rows) or 1
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Bar chart">'
    ]
    for index, (label, value) in enumerate(rows):
        y = 24 + index * row_height
        bar_width = max(3, chart_width * value / max_value)
        color = PALETTE[index % len(PALETTE)]
        parts.append(
            f'<text x="0" y="{y + 16}" font-size="15" fill="#17202a">{_escape(_shorten(label, 18))}</text>'
        )
        parts.append(
            f'<rect x="{left}" y="{y}" width="{chart_width}" height="20" rx="4" fill="#edf1ec"/>'
        )
        parts.append(
            f'<rect x="{left}" y="{y}" width="{bar_width:.2f}" height="20" rx="4" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{left + chart_width + 18}" y="{y + 16}" font-size="15" font-weight="800" fill="#17202a">{value}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _funnel_svg(rows: list[tuple[str, int]]) -> str:
    width = 640
    height = 260
    max_value = max((value for _, value in rows), default=0) or 1
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Review funnel">']
    for index, (label, value) in enumerate(rows):
        y = 20 + index * 46
        bar_width = max(4, 420 * value / max_value) if value else 4
        color = PALETTE[index % len(PALETTE)]
        parts.append(
            f'<text x="0" y="{y + 18}" font-size="15" fill="#17202a">{_escape(_shorten(label, 16))}</text>'
        )
        parts.append(f'<rect x="142" y="{y}" width="420" height="24" rx="5" fill="#edf1ec"/>')
        parts.append(f'<rect x="142" y="{y}" width="{bar_width:.2f}" height="24" rx="5" fill="{color}"/>')
        parts.append(
            f'<text x="584" y="{y + 18}" font-size="15" font-weight="800" fill="#17202a">{value}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _event_list(events: list[dict[str, object]], labels: dict[str, str]) -> str:
    if not events:
        return f'<p class="muted">{_escape(labels["no_data"])}</p>'
    rows = ['<div class="events">']
    for event in reversed(events):
        event_type = str(event.get("type", "") or "event")
        subject = str(event.get("subject", "") or "")
        at = str(event.get("at", "") or "")
        actor = str(event.get("actor", "") or "")
        rows.append(
            f"""<div class="event-row">
  <span class="pill">{_escape(event_type)}</span>
  <span class="event-subject">{_escape(subject or "-")}</span>
  <span class="muted">{_escape(_compact_date(at) or actor)}</span>
</div>"""
        )
    rows.append("</div>")
    return "\n".join(rows)


def _card_list(cards: list[MemoryCard], root: Path, labels: dict[str, str]) -> str:
    if not cards:
        return f'<p class="muted">{_escape(labels["no_data"])}</p>'
    rows = ['<div class="cards">']
    for card in cards:
        source = _relative(card.source, root)
        rows.append(
            f"""<div class="card-row">
  <span class="pill">{_escape(card.status)}</span>
  <span class="card-title"><strong>{_escape(card.subject or card.title)}</strong><small>{_escape(card.kind)} · {_escape(card.actor)}</small></span>
  <span class="muted">{_escape(source)}</span>
</div>"""
        )
    rows.append("</div>")
    return "\n".join(rows)


def _directories(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.iterdir() if item.is_dir())


def _review_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted([*path.glob("*.yaml"), *path.glob("*.json")])


def _decision_counts(paths: list[Path]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in paths:
        if path.suffix == ".json":
            data = _read_json(path)
            items = data.get("items") if isinstance(data, dict) else None
            if isinstance(items, dict):
                for item in items.values():
                    if isinstance(item, dict):
                        decision = str(item.get("decision", "")).strip()
                        if decision:
                            counts[decision] += 1
            continue
        text = _read_text(path)
        for match in re.findall(r"^\s*decision:\s*([A-Za-z_-]+)\s*$", text, flags=re.MULTILINE):
            counts[match.strip()] += 1
    return counts


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _project_name(root: Path) -> str:
    config = root / ".vibewiki" / "config.yaml"
    text = _read_text(config)
    match = re.search(r"^project_name:\s*(.+)\s*$", text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip().strip('"\'') or root.name
    return root.name


def _kind_label(kind: str) -> str:
    clean = kind.strip().lower().replace("_", " ")
    return clean or "memory"


def _top_counts(counts: Counter[str], *, limit: int) -> list[tuple[str, int]]:
    rows = [(key, value) for key, value in counts.most_common(limit) if value > 0]
    return rows


def _recent_cards(cards: list[MemoryCard], *, limit: int) -> list[MemoryCard]:
    def key(card: MemoryCard) -> tuple[int, str]:
        status_rank = 0 if card.status == "candidate" else 1
        return (status_rank, card.source.as_posix())

    return sorted(cards, key=key)[:limit]


def _workspace_state(data: DashboardData, labels: dict[str, str]) -> str:
    return data.root.name if data.workspace_exists else labels["missing"]


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _compact_date(value: str) -> str:
    if not value:
        return ""
    return value.replace("T", " ")[:16]


def _shorten(value: str, limit: int) -> str:
    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    return clean[: max(0, limit - 1)].rstrip() + "…"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)
