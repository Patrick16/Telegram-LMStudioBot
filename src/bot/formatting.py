from __future__ import annotations

import html
import re

from src.bot.i18n import tr
from src.bot.markdown import markdown_to_html

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think>.*$", re.DOTALL)


def extract_reasoning(text: str) -> str:
    """Return the text of all ``<think>`` blocks (including an unclosed trailing one)."""
    parts = [m.strip() for m in re.findall(r"<think>(.*?)</think>", text, flags=re.DOTALL)]
    rest = _THINK_BLOCK_RE.sub("", text)
    unclosed = re.search(r"<think>(.*)$", rest, flags=re.DOTALL)
    if unclosed:
        parts.append(unclosed.group(1).strip())
    return "\n\n".join(p for p in parts if p)


def strip_think_tags(text: str) -> str:
    """Remove reasoning blocks from model output."""
    text = _THINK_BLOCK_RE.sub("", text)
    text = _UNCLOSED_THINK_RE.sub("", text)
    return text.strip()


_PREVIEW_LIMIT = 3900
_CURSOR = " ▌"


def format_stream_preview(raw_text: str) -> str:
    """Telegram HTML preview of a reply that is still being generated.

    Rendered like the final reply, so formatting does not "jump" when generation ends.
    Reasoning blocks are hidden; while the model is only "thinking" a short hint is shown.
    Long replies show their tail so the newest text stays visible.
    """
    visible = strip_think_tags(raw_text)
    if not visible:
        return tr("💭 Thinking…") if "<think>" in raw_text else tr("⏳ Thinking...")
    rendered = markdown_to_html(visible)
    chunks = split_message(rendered, _PREVIEW_LIMIT)
    tail = chunks[-1] if len(chunks) == 1 else "… " + chunks[-1]
    return tail + _CURSOR


def html_to_plain(text: str) -> str:
    """Strip Telegram HTML tags and decode entities, yielding readable plain text."""
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def _format_size(size_bytes: int) -> str:
    """Convert a raw byte count to a short human-readable size string."""
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.1f} GB"
    if size_bytes >= 1024 ** 2:
        return f"{size_bytes // (1024 ** 2)} MB"
    if size_bytes >= 1024:
        return f"{size_bytes // 1024} KB"
    return f"{size_bytes} B"


def format_response(text: str, show_reasoning: bool = False) -> str:
    """Convert raw model output into Telegram-safe HTML.

    With *show_reasoning*, the model's ``<think>`` content is prepended as an
    expandable (collapsed) quote.
    """
    cleaned = strip_think_tags(text)
    if not cleaned:
        return tr("<i>(no response)</i>")
    if show_reasoning:
        reasoning = extract_reasoning(text)
        if reasoning:
            quote = f"<blockquote expandable>💭 {html.escape(reasoning, quote=False)}</blockquote>\n"
            return quote + format_response(cleaned)

    return markdown_to_html(cleaned) or tr("<i>(no response)</i>")


_TELEGRAM_MAX_LENGTH = 4096

_HTML_TOKEN_RE = re.compile(r"<[^>]+>|[^<]+")
_HTML_TAG_NAME_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)")
_VISIBLE_TEXT_RE = re.compile(r"<[^>]*>")


def _closing_tags(stack: list[tuple[str, str]]) -> str:
    return "".join(f"</{name}>" for name, _ in reversed(stack))


def _cut_point(piece: str, room: int) -> int:
    """Pick where to cut *piece* so the head is at most *room* chars.

    Prefers the last space and never cuts inside an HTML entity such as ``&amp;``.
    """
    cut = piece.rfind(" ", 1, room + 1)
    if cut <= 0:
        cut = room
    amp = piece.rfind("&", max(0, cut - 10), cut)
    if amp != -1 and ";" not in piece[amp:cut] and amp > 0:
        cut = amp
    return max(cut, 1)


def split_message(text: str, max_length: int = _TELEGRAM_MAX_LENGTH) -> list[str]:
    """Split a formatted HTML string into chunks that fit within Telegram's limit.

    Splits on line boundaries where possible (falling back to spaces, then a hard
    cut). Open tags (``<pre>``, ``<b>``, ...) are closed at the end of a chunk and
    re-opened at the start of the next one, so every chunk is valid HTML.
    """
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    stack: list[tuple[str, str]] = []  # (tag name, full opening tag)
    cur = ""
    prefix_len = 0  # length of re-opened tags at the start of the current chunk

    def flush() -> None:
        nonlocal cur, prefix_len
        body = cur.rstrip() + _closing_tags(stack)
        if _VISIBLE_TEXT_RE.sub("", body).strip():
            chunks.append(body)
        cur = "".join(tag for _, tag in stack)
        prefix_len = len(cur)

    def add_text(piece: str) -> None:
        nonlocal cur
        while piece:
            if len(cur) == prefix_len:
                piece = piece.lstrip()
                if not piece:
                    return
            room = max_length - len(cur) - len(_closing_tags(stack))
            if len(piece) <= room:
                cur += piece
                return
            if len(cur) > prefix_len:
                flush()
                continue
            cut = _cut_point(piece, max(room, 1))
            cur += piece[:cut]
            piece = piece[cut:]
            flush()

    for token in _HTML_TOKEN_RE.findall(text):
        if not token.startswith("<"):
            for line in re.split(r"(?<=\n)", token):
                add_text(line)
            continue

        m = _HTML_TAG_NAME_RE.match(token)
        if m is None:
            add_text(token)
            continue
        closing, name = m.group(1) == "/", m.group(2).lower()
        if closing:
            if stack and stack[-1][0] == name:
                cur += token
                stack.pop()
            continue
        new_stack = stack + [(name, token)]
        needed = len(cur) + len(token) + len(_closing_tags(new_stack))
        if needed > max_length and len(cur) > prefix_len:
            flush()
        cur += token
        stack.append((name, token))

    if len(cur) > prefix_len:
        flush()
    return chunks or [text[:max_length]]
