from telegram import Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.commands import render_help
from src.bot.handlers.menu import menu_command_handler
from src.bot.handlers.menu.screens import probe_lms
from src.bot.handlers.quickbar import quickbar_keyboard
from src.bot.i18n import tr
from src.bot.services.inference import ensure_session
from src.bot.services.status import build_status_text


def render_welcome(status: str, no_model_loaded: bool) -> str:
    """First-run message: what to do next, then the current status (Telegram HTML)."""
    text = tr(
        "👋 <b>Welcome to LMStudioBot</b>\n"
        "Quick start:\n"
        "1️⃣ Open 📦 Models and load a model\n"
        "2️⃣ Just send a message to chat\n"
        "3️⃣ Tune the replies in ⚙️ Settings\n\n"
    )
    text += status
    if no_model_loaded:
        text += "\n\n" + tr("👉 No model is loaded yet — open 📦 Models and tap one to load it.")
    return text


@require_owner
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    ensure_session(context.bot_data["store"])
    status = await build_status_text(context)
    lms = await probe_lms(context)
    await update.effective_message.reply_text(
        render_welcome(status, no_model_loaded=lms.online and not lms.loaded),
        reply_markup=quickbar_keyboard(),
        parse_mode="HTML",
    )
    await menu_command_handler.__wrapped__(update, context)


@require_owner
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(render_help(), parse_mode="HTML")
