import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.handlers.menu import handle_pending_input
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
    session.history.append(ChatMessage(role="user", content=user_text))

    sent_message = await update.effective_message.reply_text("⏳ Thinking...")
    full_response = ""
    token_count = 0

    try:
        async for chunk in sdk.chat_stream(session, host=config.LMS_HOST, port=config.LMS_PORT):
            full_response += chunk
            token_count += 1
            if token_count % STREAM_UPDATE_INTERVAL == 0:
                try:
                    await sent_message.edit_text(full_response)
                except Exception:
                    pass

        if full_response:
            try:
                await sent_message.edit_text(full_response)
            except Exception:
                pass
            session.history.append(ChatMessage(role="assistant", content=full_response))
            store.update_session(session)
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

    if not session.history:
        await update.effective_message.reply_text(
            "❌ Nothing to regenerate (no messages in this chat)."
        )
        return

    # Remove last assistant message if present
    if session.history[-1].role == "assistant":
        session.history.pop()

    if not session.history or session.history[-1].role != "user":
        await update.effective_message.reply_text(
            "❌ Nothing to regenerate (no messages in this chat)."
        )
        return

    sent_message = await update.effective_message.reply_text("⏳ Regenerating...")
    full_response = ""
    token_count = 0

    try:
        async for chunk in sdk.chat_stream(session, host=config.LMS_HOST, port=config.LMS_PORT):
            full_response += chunk
            token_count += 1
            if token_count % STREAM_UPDATE_INTERVAL == 0:
                try:
                    await sent_message.edit_text(full_response)
                except Exception:
                    pass

        if full_response:
            try:
                await sent_message.edit_text(full_response)
            except Exception:
                pass
            session.history.append(ChatMessage(role="assistant", content=full_response))
            store.update_session(session)
        else:
            await sent_message.edit_text("❌ No response from model.")
    except Exception as e:
        logger.error("Regeneration error: %s", e)
        await sent_message.edit_text("❌ LM Studio is unreachable.")
