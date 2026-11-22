import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.i18n import tr
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
        name = tr("Chat {n}", n=count)

    session = store.create_session(name)
    await _cmd_reply(
        update.effective_message,
        tr('💬 New chat "{name}" created and activated.', name=session.name),
    )


@require_owner
async def chats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    sessions = store.list_sessions()
    if not sessions:
        await _cmd_reply(
            update.effective_message, tr("💬 No chats yet. Use /newchat to create one.")
        )
        return

    lines = [tr("💬 Your chats:")]
    for i, s in enumerate(sessions, 1):
        active = "▶ " if s.id == store.store.active_session_id else "  "
        model_info = f" ({s.model_identifier})" if s.model_identifier else ""
        msg_count = len(store.load_history(s.id))
        lines.append(
            tr("[{i}] {active}{name}{model} — {count} messages",
               i=i, active=active, name=s.name, model=model_info, count=msg_count)
        )

    await _cmd_reply(update.effective_message, "\n".join(lines))


@require_owner
async def switchchat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    args = context.args
    if not args:
        await _cmd_reply(update.effective_message, tr("❌ Usage: /switchchat <id_or_number>"))
        return

    session_id = store.resolve_session_id(args[0])
    if session_id is None:
        await _cmd_reply(update.effective_message, tr("❌ Chat not found: {arg}", arg=args[0]))
        return

    session = store.switch_session(session_id)
    await _cmd_reply(update.effective_message, tr('✅ Switched to "{name}".', name=session.name))


@require_owner
async def removechat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    args = context.args
    if not args:
        await _cmd_reply(update.effective_message, tr("❌ Usage: /removechat <id_or_number>"))
        return

    session_id = store.resolve_session_id(args[0])
    if session_id is None:
        await _cmd_reply(update.effective_message, tr("❌ Chat not found: {arg}", arg=args[0]))
        return

    session = store.store.sessions[session_id]
    name = session.name
    store.delete_session(session_id)
    await _cmd_reply(update.effective_message, tr('🗑 Chat "{name}" removed.', name=name))


@require_owner
async def renamechat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await _cmd_reply(update.effective_message, tr("❌ No active chat. Use /newchat first."))
        return
    name = " ".join(context.args).strip() if context.args else ""
    if not name:
        await _cmd_reply(update.effective_message, tr("❌ Usage: /renamechat <new name>"))
        return
    if len(name) > 64:
        await _cmd_reply(update.effective_message, tr("❌ The name must be 64 characters or fewer."))
        return
    session.name = name
    store.update_session(session)
    await _cmd_reply(update.effective_message, tr('✅ Chat renamed to "{name}".', name=name))
