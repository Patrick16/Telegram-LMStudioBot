import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.ephemeral import reply_ephemeral
from src.bot.handlers.settings_spec import SETTING_SPECS, apply_text

logger = logging.getLogger(__name__)

# ``/set`` accepts every menu setting except the system prompt (that is /setprompt).
SET_COMMAND_NAMES = tuple(name for name in SETTING_SPECS if name != "prompt")


async def _cmd_reply(message, text: str) -> None:
    """Send an ephemeral reply for command results."""
    await reply_ephemeral(message, text)


@require_owner
async def setprompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await _cmd_reply(update.effective_message, "❌ No active chat. Use /newchat first.")
        return

    prompt_text = " ".join(context.args) if context.args else ""
    value, message = apply_text(SETTING_SPECS["prompt"], prompt_text)
    session.settings.system_prompt = value
    store.update_session(session)
    await _cmd_reply(update.effective_message, message)


@require_owner
async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """``/set <setting> <value>`` — same parsing and validation as the menu."""
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await _cmd_reply(update.effective_message, "❌ No active chat. Use /newchat first.")
        return

    valid_names = ", ".join(SET_COMMAND_NAMES)
    args = context.args
    if not args or len(args) < 2:
        await _cmd_reply(
            update.effective_message,
            f"❌ Usage: /set <setting> <value>\nValid settings: {valid_names}",
        )
        return

    name = args[0].lower()
    spec = SETTING_SPECS.get(name) if name in SET_COMMAND_NAMES else None
    if spec is None:
        await _cmd_reply(
            update.effective_message, f"❌ Unknown setting: {name}. Valid: {valid_names}"
        )
        return

    try:
        value, message = apply_text(spec, " ".join(args[1:]))
    except ValueError as err:
        await _cmd_reply(update.effective_message, str(err))
        return

    setattr(session.settings, spec.attr, value)
    store.update_session(session)
    await _cmd_reply(update.effective_message, message)
