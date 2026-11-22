"""Text and keyboard builders for the model and chat screens (list + detail card)."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.formatting import _format_size
from src.bot.pagination import nav_row, paginate

MAX_LABEL = 64  # Telegram button text limit


def _truncate(label: str) -> str:
    return label if len(label) <= MAX_LABEL else label[: MAX_LABEL - 1] + "…"


def _code(value) -> str:
    return f"<code>{html.escape(str(value), quote=False)}</code>"


def format_ago(iso_timestamp: str, now: datetime | None = None) -> str:
    """Short relative time ("5 min ago") for an ISO timestamp; empty if unparseable."""
    try:
        moment = datetime.fromisoformat(iso_timestamp)
    except (TypeError, ValueError):
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    seconds = int(((now or datetime.now(timezone.utc)) - moment).total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    if seconds < 7 * 86400:
        return f"{seconds // 86400} d ago"
    return moment.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModelEntry:
    key: str
    size_bytes: int = 0
    loaded: bool = False


def _model_mark(entry: ModelEntry, bound: str | None) -> str:
    if entry.loaded and entry.key == bound:
        return "▶"
    return "🟢" if entry.loaded else "⚪"


def render_models_text(entries: list[ModelEntry], bound: str | None, page: int, pages: int) -> str:
    loaded = sum(1 for e in entries if e.loaded)
    lines = ["📦 <b>Models</b>", f"🟢 LM Studio · {loaded} loaded of {len(entries)}"]
    if bound:
        lines.append(f"🔗 This chat: {_code(bound)}")
    lines.append("▶ used by this chat · 🟢 loaded · ⚪ on disk")
    lines.append("Tap a model to load, unload or use it.")
    if pages > 1:
        lines.append(f"Page {page + 1}/{pages}")
    return "\n".join(lines)


def build_models_keyboard(
    entries: list[ModelEntry], page: int, bound: str | None
) -> tuple[InlineKeyboardMarkup, int, int]:
    """Paginated model buttons; returns ``(markup, clamped_page, pages)``."""
    shown, page, pages = paginate(entries, page)
    rows = []
    for entry in shown:
        label = _truncate(
            f"{_model_mark(entry, bound)} {entry.key} · {_format_size(entry.size_bytes)}"
        )
        index = entries.index(entry)
        rows.append([InlineKeyboardButton(label, callback_data=f"models:card:{index}")])
    navigation = nav_row("models:page:", page, pages)
    if navigation:
        rows.append(navigation)
    rows.append([
        InlineKeyboardButton("🔄 Refresh", callback_data="menu:models"),
        InlineKeyboardButton("⬅ Back", callback_data="menu:main"),
    ])
    return InlineKeyboardMarkup(rows), page, pages


def build_models_unreachable() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "📦 <b>Models</b>\n🔴 LM Studio is unreachable.\n"
        "Start LM Studio and enable its local server, then retry."
    )
    return text, InlineKeyboardMarkup([[
        InlineKeyboardButton("🔄 Retry", callback_data="menu:models"),
        InlineKeyboardButton("⬅ Back", callback_data="menu:main"),
    ]])


def render_model_card(entry: ModelEntry, bound: str | None, staged: dict | None) -> str:
    lines = [f"📦 <b>{html.escape(entry.key, quote=False)}</b>"]
    lines.append(f"💾 Size: {_format_size(entry.size_bytes)}")
    lines.append("🟢 Loaded" if entry.loaded else "⚪ Not loaded")
    if entry.loaded:
        lines.append("🔗 Used by this chat: " + ("yes" if entry.key == bound else "no"))
    elif staged:
        shown = ", ".join(f"{k}={v}" for k, v in staged.items() if v is not None)
        if shown:
            lines.append(f"⚙️ Staged load settings: {_code(shown)}")
    return "\n".join(lines)


def build_model_card_keyboard(
    entry: ModelEntry, bound: str | None, has_chat: bool
) -> InlineKeyboardMarkup:
    rows = []
    if entry.loaded:
        row = [InlineKeyboardButton("⬇ Unload", callback_data="models:do:unload")]
        if has_chat and entry.key != bound:
            row.insert(0, InlineKeyboardButton("🔗 Use in chat", callback_data="models:do:bind"))
        rows.append(row)
    else:
        rows.append([InlineKeyboardButton("⬆ Load", callback_data="models:do:load")])
    rows.append([InlineKeyboardButton("⬅ Back", callback_data="menu:models")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Chats
# ---------------------------------------------------------------------------

def chat_row_label(session, message_count: int, active: bool) -> str:
    parts = [f"{'▶ ' if active else ''}{session.name}", f"{message_count} msg"]
    ago = format_ago(session.updated_at)
    if ago:
        parts.append(ago)
    return _truncate(" · ".join(parts))


def render_chat_card(session, message_count: int, active: bool) -> str:
    title = html.escape(session.name, quote=False) + ("  ▶ active" if active else "")
    lines = [f"💬 <b>{title}</b>"]
    lines.append(f"✉️ {message_count} message(s)")
    if session.model_identifier:
        lines.append(f"🧠 Model: {_code(session.model_identifier)}")
    else:
        lines.append("🧠 Model: <i>any loaded model</i>")
    ago = format_ago(session.updated_at)
    if ago:
        lines.append(f"🕒 Last activity: {ago}")
    created = format_ago(session.created_at)
    if created:
        lines.append(f"📅 Created: {created}")
    return "\n".join(lines)


def build_chat_card_keyboard(session_id: str, active: bool) -> InlineKeyboardMarkup:
    rows = []
    if not active:
        rows.append([InlineKeyboardButton("✅ Open", callback_data=f"sessions:switch:{session_id}")])
    rows.append([
        InlineKeyboardButton("✏️ Rename", callback_data=f"sessions:rename:{session_id}"),
        InlineKeyboardButton("🗑 Delete", callback_data=f"sessions:del_card:{session_id}"),
    ])
    rows.append([InlineKeyboardButton("⬅ Back", callback_data="sessions:list")])
    return InlineKeyboardMarkup(rows)
