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


def _format_size(size_bytes: int) -> str:
    """Convert a raw byte count to a short human-readable size string."""
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.1f} GB"
    return f"{size_bytes // (1024 ** 2)} MB"


def format_response(text: str) -> str:
    """Convert raw model output into Telegram-safe HTML."""
    cleaned = strip_think_tags(text)
    if not cleaned:
        return "*(no response)*"

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

    return "".join(parts) or "*(no response)*"


_TELEGRAM_MAX_LENGTH = 4096


def split_message(text: str, max_length: int = _TELEGRAM_MAX_LENGTH) -> list[str]:
    """Split a formatted HTML string into chunks that fit within Telegram's limit.

    Splits preferentially on blank lines, then newlines, then spaces so that
    chunks are readable and don't break mid-sentence where possible.
    """
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text

    while len(remaining) > max_length:
        window = remaining[:max_length]

        # Prefer to split on a blank line (paragraph boundary)
        split_at = window.rfind("\n\n")
        if split_at == -1:
            # Fall back to last newline
            split_at = window.rfind("\n")
        if split_at == -1:
            # Fall back to last space
            split_at = window.rfind(" ")
        if split_at <= 0:
            # Hard split — no natural boundary found
            split_at = max_length

        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks
