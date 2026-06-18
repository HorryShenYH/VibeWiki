from __future__ import annotations

import html
import json
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .import_markdown import import_markdown_session
from .models import SessionPaths
from .text_utils import slugify


def fetch_url_text(url: str, timeout: int = 30) -> tuple[str, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "VibeWiki/0.1 (+https://github.com/HorryShenYH/VibeWiki)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
        content_type = response.headers.get("content-type", "")
    charset = _charset_from_content_type(content_type) or "utf-8"
    return raw.decode(charset, errors="replace"), content_type


def _charset_from_content_type(content_type: str) -> str:
    match = re.search(r"charset=([^;\s]+)", content_type, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def html_to_markdown(source_url: str, html_text: str) -> str:
    if _looks_like_chatgpt_share(source_url, html_text):
        chatgpt = chatgpt_share_to_markdown(source_url, html_text)
        if chatgpt:
            return chatgpt
        title = _html_title(html_text) or "ChatGPT Shared Conversation"
        return f"""# {title}

Imported from: {source_url}

No readable ChatGPT conversation text was found. The original HTML is preserved in `raw_source.html` for parser upgrades.
"""

    title = _html_title(html_text) or source_url
    body = _html_body_text(html_text)
    return f"""# {title}

Imported from: {source_url}

{body or "No readable page text was found. The raw HTML is preserved in `raw_session.md`."}
"""


def _looks_like_chatgpt_share(source_url: str, html_text: str) -> bool:
    host = urlparse(source_url).netloc.lower()
    return "chatgpt.com" in host or "ChatGPT" in html_text or "__NEXT_DATA__" in html_text


def chatgpt_share_to_markdown(source_url: str, html_text: str) -> str:
    data = _next_data(html_text)
    title = _html_title(html_text) or "ChatGPT Shared Conversation"
    messages = _chatgpt_messages_from_json(data) if data else []
    if not messages:
        messages = _chatgpt_messages_from_react_router(html_text)
    if not messages:
        messages = _chatgpt_messages_from_text(_html_body_text(html_text))
    if not messages:
        return ""

    lines = [f"# {title}", "", f"Imported from: {source_url}", ""]
    for role, content in messages:
        role_title = role.strip().title() or "Message"
        lines.extend([f"## {role_title}", "", content.strip(), ""])
    return "\n".join(lines).strip() + "\n"


def _next_data(html_text: str) -> object | None:
    patterns = [
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        payload = html.unescape(match.group(1)).strip()
        if not payload:
            continue
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            continue
    return None


def _chatgpt_messages_from_react_router(html_text: str) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = []
    for payload in _react_router_payloads(html_text):
        decoded = _decode_devalue_table(payload)
        candidates = _chatgpt_messages_from_json(decoded)
        if candidates:
            messages.extend(candidates)
    return _dedupe_messages(messages)


def _react_router_payloads(html_text: str) -> list[object]:
    payloads: list[object] = []
    for script in re.findall(
        r"<script[^>]*>(.*?)</script>",
        html_text,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        if "streamController.enqueue" not in script:
            continue
        chunks: list[str] = []
        for match in re.finditer(r"\.streamController\.enqueue\((\"(?:\\.|[^\"\\])*\")\)", script):
            try:
                chunks.append(json.loads(match.group(1)))
            except json.JSONDecodeError:
                continue
        payload_text = "".join(chunks).strip()
        if not payload_text or not payload_text.startswith(("[", "{")):
            continue
        try:
            payloads.append(json.loads(payload_text))
        except json.JSONDecodeError:
            continue
    return payloads


def _decode_devalue_table(value: object) -> object:
    if not _looks_like_devalue_table(value):
        return value

    table = value
    memo: dict[int, object] = {}
    active: set[int] = set()

    def resolve_ref(ref: int) -> object:
        if ref < 0 or ref >= len(table):
            return None
        if ref in memo:
            return memo[ref]
        if ref in active:
            return None
        active.add(ref)
        resolved = resolve_value(table[ref])
        active.remove(ref)
        memo[ref] = resolved
        return resolved

    def resolve_key(key: object) -> object:
        if isinstance(key, str):
            match = re.fullmatch(r"_(\d+)", key)
            if match:
                resolved = resolve_ref(int(match.group(1)))
                if isinstance(resolved, str):
                    return resolved
                return str(resolved)
        return key

    def resolve_value(item: object) -> object:
        if isinstance(item, dict):
            resolved_dict: dict[object, object] = {}
            for key, child in item.items():
                resolved_key = resolve_key(key)
                if isinstance(child, int):
                    resolved_dict[resolved_key] = resolve_ref(child)
                else:
                    resolved_dict[resolved_key] = resolve_value(child)
            return resolved_dict
        if isinstance(item, list):
            return [
                resolve_ref(child) if isinstance(child, int) else resolve_value(child)
                for child in item
            ]
        return item

    return resolve_ref(0)


def _looks_like_devalue_table(value: object) -> bool:
    if not isinstance(value, list) or not value:
        return False
    first = value[0]
    return isinstance(first, dict) and any(
        isinstance(key, str) and re.fullmatch(r"_\d+", key) for key in first
    )


def _chatgpt_messages_from_json(data: object) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = []
    seen: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            role = _role_from_dict(value)
            content = _content_from_dict(value)
            if content and _should_keep_chatgpt_message(value, role):
                key = f"{role}:{content}"
                if key not in seen:
                    seen.add(key)
                    messages.append((role or "message", content))
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(data)
    return messages


def _dedupe_messages(messages: list[tuple[str, str]]) -> list[tuple[str, str]]:
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for role, content in messages:
        key = f"{role}:{content}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append((role, content))
    return deduped


def _should_keep_chatgpt_message(value: dict[object, object], role: str) -> bool:
    role_name = role.lower()
    if role_name not in {"user", "assistant"}:
        return False
    content_type = _content_type_from_dict(value).lower()
    if content_type and content_type not in {"text", "multimodal_text"}:
        return False
    return True


def _content_type_from_dict(value: dict[object, object]) -> str:
    content = value.get("content")
    if isinstance(content, dict):
        content_type = content.get("content_type")
        if isinstance(content_type, str):
            return content_type
    message = value.get("message")
    if isinstance(message, dict):
        return _content_type_from_dict(message)
    return ""


def _role_from_dict(value: dict[object, object]) -> str:
    author = value.get("author")
    if isinstance(author, dict):
        role = author.get("role") or author.get("name")
        if isinstance(role, str):
            return role
    role = value.get("role")
    if isinstance(role, str):
        return role
    message = value.get("message")
    if isinstance(message, dict):
        return _role_from_dict(message)
    return ""


def _content_from_dict(value: dict[object, object]) -> str:
    content = value.get("content")
    if isinstance(content, dict):
        parts = content.get("parts")
        if isinstance(parts, list):
            return _join_content_parts(parts)
        text = content.get("text")
        if isinstance(text, str):
            return text
    if isinstance(content, str):
        return content
    parts = value.get("parts")
    if isinstance(parts, list):
        return _join_content_parts(parts)
    text = value.get("text")
    if isinstance(text, str):
        return text
    message = value.get("message")
    if isinstance(message, dict):
        return _content_from_dict(message)
    return ""


def _join_content_parts(parts: list[object]) -> str:
    values: list[str] = []
    for part in parts:
        if isinstance(part, str):
            values.append(part)
        elif isinstance(part, dict):
            text = part.get("text") or part.get("content")
            if isinstance(text, str):
                values.append(text)
    return "\n\n".join(value.strip() for value in values if value and value.strip())


def _chatgpt_messages_from_text(text: str) -> list[tuple[str, str]]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    messages: list[tuple[str, str]] = []
    current_role = ""
    current: list[str] = []
    saw_role = False
    role_markers = {
        "you": "user",
        "user": "user",
        "chatgpt": "assistant",
        "assistant": "assistant",
    }
    for line in lines:
        role = role_markers.get(line.lower().rstrip(":"))
        if role:
            saw_role = True
            if current:
                messages.append((current_role or "message", "\n".join(current).strip()))
            current_role = role
            current = []
            continue
        current.append(line)
    if current:
        messages.append((current_role or "message", "\n".join(current).strip()))
    return messages if saw_role else []


def _html_title(html_text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html_text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return _collapse_text(html.unescape(_strip_tags(match.group(1))))


def _html_body_text(html_text: str) -> str:
    match = re.search(r"<body[^>]*>(.*?)</body>", html_text, flags=re.IGNORECASE | re.DOTALL)
    text = match.group(1) if match else html_text
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</(p|div|section|article|li|h[1-6]|br)>", "\n", text, flags=re.IGNORECASE)
    return _collapse_text(html.unescape(_strip_tags(text)))


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text)


def _collapse_text(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def import_url_session(
    project: Path,
    url: str,
    *,
    goal: str = "",
    outcome: str = "",
    commands: list[str] | None = None,
    tests: str = "",
    benchmark: str = "",
    notes: str = "",
    things_not_to_record: str = "",
    session_name: str | None = None,
) -> SessionPaths:
    html_text, content_type = fetch_url_text(url)
    markdown = html_to_markdown(url, html_text)
    parsed = urlparse(url)
    fallback_slug = slugify(parsed.netloc + "-" + parsed.path, fallback="shared-conversation")
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / f"{fallback_slug}.md"
        source.write_text(markdown, encoding="utf-8")
        paths = import_markdown_session(
            project,
            source,
            goal=goal,
            outcome=outcome,
            commands=commands,
            tests=tests,
            benchmark=benchmark,
            notes=notes,
            things_not_to_record=things_not_to_record,
            session_name=session_name,
        )

    raw_html = paths.session_dir / "raw_source.html"
    raw_html.write_text(html_text, encoding="utf-8")
    metadata = paths.metadata_yaml.read_text(encoding="utf-8")
    metadata += f"imported_url: {url}\ncontent_type: {content_type}\nraw_source_html: {raw_html}\n"
    paths.metadata_yaml.write_text(metadata, encoding="utf-8")
    return paths
