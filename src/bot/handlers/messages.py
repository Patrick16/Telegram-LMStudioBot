import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.ephemeral import reply_ephemeral
from src.bot.handlers.menu import handle_pending_input
from src.bot.handlers.menu.pending import expire_pending_if_stale
from src.bot.services import inference
from src.bot.services.generation import get_generations

logger = logging.getLogger(__name__)


@require_owner
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if expire_pending_if_stale(context):
        await reply_ephemeral(
            update.effective_message,
            "⌛ The earlier input request expired, so this was sent to the model.",
        )

    # Intercept pending input from menu buttons
    if context.chat_data.get("pending_input"):
        await handle_pending_input(update, context)
        return

    message = update.effective_message
    await inference.run_text_turn(message, context, message.text)


@require_owner
async def regenerate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await inference.run_regenerate(update.effective_message, context)


@require_owner
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if get_generations(context).stop(message.chat_id):
        logger.info("Generation stopped by user")
    else:
        await message.reply_text("Nothing is being generated right now.")
