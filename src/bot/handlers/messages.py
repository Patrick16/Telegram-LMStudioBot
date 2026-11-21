import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.handlers.menu import handle_pending_input
from src.bot.responses import history_content, send_response
from src.lms import sdk
from src.storage.models import ChatMessage

logger = logging.getLogger(__name__)

STREAM_UPDATE_INTERVAL = 50


@require_owner
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Intercept pending input from menu buttons
    if context.chat_data.get("pending_input"):
        await handle_pending_input(update, context)
        return

    store = context.bot_data["store"]
    config = context.bot_data["config"]
    session = store.get_active_session()

    if session is None:
        await update.effective_message.reply_text("❌ No active chat. Use /newchat first.")
        return

    user_text = update.effective_message.text
    user_msg = ChatMessage(role="user", content=user_text)
    store.append_message(session.id, user_msg)

    # Load history and trim by policy for inference
    history = store.load_history(session.id)
    trimmed = sdk.trim_history(history, session.settings.history_policy)

    sent_message = await update.effective_message.reply_text("⏳ Thinking...")
    full_response = ""

    try:
        async for chunk in sdk.chat_stream(
            session, host=config.LMS_HOST, port=config.LMS_PORT,
            history_messages=trimmed,
        ):
            full_response += chunk

        if full_response:
            await send_response(sent_message, full_response)
            stored = history_content(full_response)
            if stored:
                store.append_message(
                    session.id,
                    ChatMessage(role="assistant", content=stored),
                )
        else:
            await sent_message.edit_text("❌ No response from model.")
    except Exception as e:
        logger.error("Inference error: %s", e)
        await sent_message.edit_text("❌ LM Studio is unreachable.")


@require_owner
async def regenerate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    config = context.bot_data["config"]
    session = store.get_active_session()

    if session is None:
        await update.effective_message.reply_text("❌ No active chat. Use /newchat first.")
        return

    history = store.load_history(session.id)

    if not history:
        await update.effective_message.reply_text(
            "❌ Nothing to regenerate (no messages in this chat)."
        )
        return

    # Remove last assistant message if present
    if history[-1].role == "assistant":
        store.pop_last_assistant(session.id)
        history = history[:-1]

    if not history or history[-1].role != "user":
        await update.effective_message.reply_text(
            "❌ Nothing to regenerate (no messages in this chat)."
        )
        return

    trimmed = sdk.trim_history(history, session.settings.history_policy)

    sent_message = await update.effective_message.reply_text("⏳ Regenerating...")
    full_response = ""

    try:
        async for chunk in sdk.chat_stream(
            session, host=config.LMS_HOST, port=config.LMS_PORT,
            history_messages=trimmed,
        ):
            full_response += chunk

        if full_response:
            await send_response(sent_message, full_response)
            stored = history_content(full_response)
            if stored:
                store.append_message(
                    session.id,
                    ChatMessage(role="assistant", content=stored),
                )
        else:
            await sent_message.edit_text("❌ No response from model.")
    except Exception as e:
        logger.error("Regeneration error: %s", e)
        await sent_message.edit_text("❌ LM Studio is unreachable.")
