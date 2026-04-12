import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.ephemeral import reply_ephemeral

logger = logging.getLogger(__name__)


async def _cmd_reply(message, text: str) -> None:
    """Send an ephemeral reply for command results."""
    await reply_ephemeral(message, text)


@require_owner
async def newchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    name = " ".join(context.args) if context.args else None
    if not name:
        count = len(store.list_sessions()) + 1
        name = f"Chat {count}"

    session = store.create_session(name)
    await _cmd_reply(
        update.effective_message,
        f'💬 New chat "{session.name}" created and activated.',
    )


@require_owner
async def chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    sessions = store.list_sessions()
    if not sessions:
        await _cmd_reply(update.effective_message, "💬 No chats yet. Use /newchat to create one.")
        return

    lines = ["💬 Your chats:"]
    for i, s in enumerate(sessions, 1):
        active = "▶ " if s.id == store.store.active_session_id else "  "
        model_info = f" ({s.model_identifier})" if s.model_identifier else ""
        msg_count = len(store.load_history(s.id))
        lines.append(f"[{i}] {active}{s.name}{model_info} — {msg_count} messages")

    await _cmd_reply(update.effective_message, "\n".join(lines))


@require_owner
async def switchchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    args = context.args
    if not args:
        await _cmd_reply(update.effective_message, "❌ Usage: /switchchat <id_or_number>")
        return

    session_id = store.resolve_session_id(args[0])
    if session_id is None:
        await _cmd_reply(update.effective_message, f"❌ Chat not found: {args[0]}")
        return

    session = store.switch_session(session_id)
    await _cmd_reply(update.effective_message, f'✅ Switched to "{session.name}".')


@require_owner
async def removechat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    args = context.args
    if not args:
        await _cmd_reply(update.effective_message, "❌ Usage: /removechat <id_or_number>")
        return

    session_id = store.resolve_session_id(args[0])
    if session_id is None:
        await _cmd_reply(update.effective_message, f"❌ Chat not found: {args[0]}")
        return

    session = store.store.sessions[session_id]
    name = session.name
    store.delete_session(session_id)
    await _cmd_reply(update.effective_message, f'🗑 Chat "{name}" removed.')
