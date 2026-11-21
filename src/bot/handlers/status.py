from telegram import Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.services.status import build_status_text


@require_owner
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = await build_status_text(context)
    await update.effective_message.reply_text(text, parse_mode="HTML")
