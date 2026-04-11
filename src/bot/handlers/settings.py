import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner

logger = logging.getLogger(__name__)

VALID_SETTINGS = {
    "temperature": {"type": float, "min": 0.0, "max": 2.0},
    "max_tokens": {"type": int, "min": -1, "max": None},
    "top_p": {"type": float, "min": 0.0, "max": 1.0},
}


@require_owner
async def setprompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await update.effective_message.reply_text("❌ No active chat. Use /newchat first.")
        return

    prompt_text = " ".join(context.args) if context.args else ""
    session.system_prompt = prompt_text
    store.update_session(session)

    if prompt_text:
        await update.effective_message.reply_text("✅ System prompt updated.")
    else:
        await update.effective_message.reply_text("✅ System prompt cleared.")


@require_owner
async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await update.effective_message.reply_text("❌ No active chat. Use /newchat first.")
        return

    args = context.args
    if not args or len(args) < 2:
        await update.effective_message.reply_text(
            "❌ Usage: /set <setting> <value>\nValid settings: temperature, max_tokens, top_p"
        )
        return

    setting_name = args[0].lower()
    value_str = args[1]

    if setting_name not in VALID_SETTINGS:
        valid_names = ", ".join(VALID_SETTINGS.keys())
        await update.effective_message.reply_text(
            f"❌ Unknown setting: {setting_name}. Valid: {valid_names}"
        )
        return

    spec = VALID_SETTINGS[setting_name]
    try:
        value = spec["type"](value_str)
    except (ValueError, TypeError):
        await update.effective_message.reply_text(
            f"❌ Invalid value for {setting_name}: must be a {spec['type'].__name__}"
        )
        return

    if spec["min"] is not None and value < spec["min"]:
        await update.effective_message.reply_text(
            f"❌ Invalid value for {setting_name}: must be >= {spec['min']}"
        )
        return
    if spec["max"] is not None and value > spec["max"]:
        await update.effective_message.reply_text(
            f"❌ Invalid value for {setting_name}: must be <= {spec['max']}"
        )
        return

    setattr(session.settings, setting_name, value)
    store.update_session(session)
    await update.effective_message.reply_text(f"✅ {setting_name} set to {value}")
