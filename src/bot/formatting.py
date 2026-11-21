from __future__ import annotations

import html
import re

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_UNCLOSED_THINK_RE = re.compile(r"<think>.*$", re.DOTALL)
_CODE_RE = re.compile(r"```(?:[^\n`]*)\n?(.*?)```|`([^`\n]+)`", re.DOTALL)

# Markdown inline formatting — applied to HTML-escaped plain text sections
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
_MD_BOLD_ITALIC_RE = re.compile(r"\*\*\*(.+?)\*\*\*")
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_ITALIC_RE = re.compile(r"\*([^*\n]+?)\*")
_MD_STRIKE_RE = re.compile(r"~~(.+?)~~")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def strip_think_tags(text: str) -> str:
    """Remove reasoning blocks from model output."""
    text = _THINK_BLOCK_RE.sub("", text)
    text = _UNCLOSED_THINK_RE.sub("", text)
    return text.strip()


def _markdown_to_html(text: str) -> str:
    """Convert common Markdown formatting to Telegram HTML tags.

    Must be called on already-HTML-escaped text so that HTML special chars
    in the original content are safe before we inject tag characters.
    Order matters: *** before ** before * to avoid partial matches.
    """
    text = _MD_HEADING_RE.sub(r"<b>\1</b>", text)
    text = _MD_BOLD_ITALIC_RE.sub(r"<b><i>\1</i></b>", text)
    text = _MD_BOLD_RE.sub(r"<b>\1</b>", text)
    text = _MD_ITALIC_RE.sub(r"<i>\1</i>", text)
    text = _MD_STRIKE_RE.sub(r"<s>\1</s>", text)
    text = _MD_LINK_RE.sub(r'<a href="\2">\1</a>', text)
    return text


def html_to_plain(text: str) -> str:
    """Strip Telegram HTML tags and decode entities, yielding readable plain text."""
    return html.unescape(re.sub(r"<[^>]+>", "", text))


def _format_size(size_bytes: int) -> str:
    """Convert a raw byte count to a short human-readable size string."""
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.1f} GB"
    return f"{size_bytes // (1024 ** 2)} MB"


def format_response(text: str) -> str:
    """Convert raw model output into Telegram-safe HTML."""
    cleaned = strip_think_tags(text)
    if not cleaned:
        return "<i>(no response)</i>"

    parts: list[str] = []
    last_index = 0

    for match in _CODE_RE.finditer(cleaned):
        plain_text = cleaned[last_index:match.start()]
        if plain_text:
            parts.append(_markdown_to_html(html.escape(plain_text, quote=False)))

        fenced_code, inline_code = match.groups()
        if fenced_code is not None:
            escaped = html.escape(fenced_code, quote=False)
            parts.append(f"<pre><code>{escaped}</code></pre>")
        else:
            escaped = html.escape(inline_code, quote=False)
            parts.append(f"<code>{escaped}</code>")

        last_index = match.end()

    tail = cleaned[last_index:]
    if tail:
        parts.append(_markdown_to_html(html.escape(tail, quote=False)))

    return "".join(parts) or "<i>(no response)</i>"


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
