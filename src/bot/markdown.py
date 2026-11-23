"""Markdown (as LLMs write it) → Telegram HTML.

Telegram's HTML subset has no lists, headings, tables or rules, so those are rendered with
typography instead: headings become bold, ``- item`` becomes ``• item``, tables become an
aligned monospace block, ``---`` becomes a thin line. The goal is that no Markdown syntax
characters reach the user while the structure and emphasis survive.

Works on partial text too (live streaming): an unclosed code fence is rendered as code,
unclosed ``**`` simply stays literal until its pair arrives.
"""

from __future__ import annotations

import html
import re

_SAFE_LINK_SCHEMES = ("http://", "https://", "tg://", "mailto:")

# --- blocks ---------------------------------------------------------------------------------

# A fence may start mid-line ("and ```"), may carry a language and may be unclosed (streaming).
_FENCE_RE = re.compile(
    r"(?P<fence>`{3,}|~{3,})(?P<lang>[^\n`]*)\n?(?P<body>.*?)(?:(?P=fence)|\Z)", re.DOTALL
)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_RULE_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_BULLET_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_ORDERED_RE = re.compile(r"^(\s*)(\d{1,9})[.)]\s+(.*)$")
_TASK_RE = re.compile(r"^\[([ xX])\]\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?\s*$")

_BULLETS = ("•", "◦", "▪")
_RULE = "──────────"
_INDENT = "    "

# --- inline ---------------------------------------------------------------------------------

_CODE_SPAN_RE = re.compile(r"(`+)(.+?)\1")
_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!|~>])")
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(\s*([^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
_AUTOLINK_RE = re.compile(r"<((?:https?|tg)://[^\s>]+|mailto:[^\s>]+)>")
_BARE_URL_RE = re.compile(r"https?://[^\s<>()\[\]]+[^\s<>()\[\].,;:!?'\"]")

_BOLD_ITALIC_RE = re.compile(r"\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*")
_BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_BOLD_UNDERSCORE_RE = re.compile(r"(?<![\w_])__(?=\S)(.+?)(?<=\S)__(?![\w_])")
# Emphasis only when the markers hug the text: "2 * 3 * 4" and snake_case stay untouched.
_ITALIC_RE = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
_ITALIC_UNDERSCORE_RE = re.compile(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])")
_STRIKE_RE = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~")
_SPOILER_RE = re.compile(r"\|\|(?=\S)(.+?)(?<=\S)\|\|")

_SLOT = "\x00{}\x00"
_SLOT_RE = re.compile(r"\x00(\d+)\x00")


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


def _anchor(url: str, label_html: str) -> str:
    return f'<a href="{html.escape(url, quote=True)}">{label_html}</a>'


def render_inline(text: str) -> str:
    """Render one piece of prose: emphasis, code spans, links; everything else is escaped."""
    slots: list[str] = []

    def keep(fragment: str) -> str:
        slots.append(fragment)
        return _SLOT.format(len(slots) - 1)

    text = _CODE_SPAN_RE.sub(lambda m: keep(f"<code>{_escape(m.group(2).strip())}</code>"), text)
    text = _ESCAPE_RE.sub(lambda m: keep(_escape(m.group(1))), text)

    def link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        if not url.lower().startswith(_SAFE_LINK_SCHEMES):
            return m.group(0)
        return keep(_anchor(url, _emphasis(_escape(label))))

    text = _LINK_RE.sub(link, text)
    text = _AUTOLINK_RE.sub(lambda m: keep(_anchor(m.group(1), _escape(m.group(1)))), text)
    # Bare URLs are linked by Telegram itself; they are only shielded from emphasis rules.
    text = _BARE_URL_RE.sub(lambda m: keep(_escape(m.group(0))), text)

    text = _emphasis(_escape(text))
    while _SLOT_RE.search(text):
        text = _SLOT_RE.sub(lambda m: slots[int(m.group(1))], text)
    return text


def _emphasis(text: str) -> str:
    text = _BOLD_ITALIC_RE.sub(r"<b><i>\1</i></b>", text)
    text = _BOLD_RE.sub(r"<b>\1</b>", text)
    text = _BOLD_UNDERSCORE_RE.sub(r"<b>\1</b>", text)
    text = _ITALIC_RE.sub(r"<i>\1</i>", text)
    text = _ITALIC_UNDERSCORE_RE.sub(r"<i>\1</i>", text)
    text = _STRIKE_RE.sub(r"<s>\1</s>", text)
    text = _SPOILER_RE.sub(r"<tg-spoiler>\1</tg-spoiler>", text)
    return text


def _plain_cell(cell: str) -> str:
    """Table cells go into a monospace block, so emphasis markers are just dropped."""
    cell = _CODE_SPAN_RE.sub(lambda m: m.group(2), cell.strip())
    cell = _LINK_RE.sub(lambda m: m.group(1), cell)
    cell = re.sub(r"(\*\*\*|\*\*|__|~~)(?=\S)(.+?)(?<=\S)\1", r"\2", cell)
    cell = re.sub(r"(?<![\w*])\*(?=\S)([^*]+?)(?<=\S)\*(?![\w*])", r"\1", cell)
    return _ESCAPE_RE.sub(r"\1", cell).replace("<br>", " ")


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    return [_plain_cell(c) for c in re.split(r"(?<!\\)\|", line)]


def _render_table(lines: list[str]) -> str:
    rows = [_split_row(line) for line in lines if not _TABLE_SEP_RE.match(line)]
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    sizes = [max(len(r[i]) for r in rows) for i in range(width)]

    def fmt(row: list[str]) -> str:
        return " │ ".join(cell.ljust(sizes[i]) for i, cell in enumerate(row)).rstrip()

    out = [fmt(rows[0]), "─┼─".join("─" * s for s in sizes)] + [fmt(r) for r in rows[1:]]
    return "<pre>" + _escape("\n".join(out)) + "</pre>"


def _list_level(indent: str) -> int:
    return len(indent.replace("\t", "  ")) // 2


def _render_item(indent: str, marker: str, body: str) -> str:
    task = _TASK_RE.match(body)
    if task:
        marker = "☑" if task.group(1).lower() == "x" else "☐"
        body = task.group(2)
    return _INDENT * min(_list_level(indent), 4) + marker + " " + render_inline(body)


def _render_prose(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if (
            _TABLE_ROW_RE.match(line)
            and i + 1 < len(lines)
            and _TABLE_SEP_RE.match(lines[i + 1])
        ):
            j = i + 2
            while j < len(lines) and _TABLE_ROW_RE.match(lines[j]):
                j += 1
            out.append(_render_table(lines[i:j]))
            i = j
            continue

        if _QUOTE_RE.match(line):
            j = i
            quoted = []
            while j < len(lines) and _QUOTE_RE.match(lines[j]):
                quoted.append(_QUOTE_RE.match(lines[j]).group(1))
                j += 1
            out.append("<blockquote>" + _render_prose("\n".join(quoted)) + "</blockquote>")
            i = j
            continue

        heading = _HEADING_RE.match(line)
        bullet = _BULLET_RE.match(line)
        ordered = _ORDERED_RE.match(line)
        if heading:
            out.append("<b>" + render_inline(heading.group(1)) + "</b>")
        elif _RULE_RE.match(line):
            out.append(_RULE)
        elif bullet:
            level = min(_list_level(bullet.group(1)), len(_BULLETS) - 1)
            out.append(_render_item(bullet.group(1), _BULLETS[level], bullet.group(2)))
        elif ordered:
            out.append(_render_item(ordered.group(1), ordered.group(2) + ".", ordered.group(3)))
        else:
            out.append(render_inline(line))
        i += 1
    return "\n".join(out)


def _render_code(lang: str, body: str) -> str:
    lang = lang.strip().split()[0] if lang.strip() else ""
    lang = re.sub(r"[^\w+#.-]", "", lang)
    attr = f' class="language-{lang}"' if lang else ""
    return f"<pre><code{attr}>{_escape(body)}</code></pre>"


def markdown_to_html(text: str) -> str:
    """Convert Markdown to Telegram-compatible HTML."""
    parts: list[str] = []
    last = 0
    for match in _FENCE_RE.finditer(text):
        if match.start() > last:
            parts.append(_render_prose(text[last:match.start()]))
        parts.append(_render_code(match.group("lang"), match.group("body")))
        last = match.end()
    if last < len(text):
        parts.append(_render_prose(text[last:]))
    return "".join(parts)
