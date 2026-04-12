import logging

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.auth import require_owner
from src.bot.ephemeral import reply_ephemeral

logger = logging.getLogger(__name__)

VALID_SETTINGS = {
    "temperature": {"type": float, "min": 0.0, "max": 2.0},
    "max_tokens": {"type": int, "min": -1, "max": None},
    "top_p": {"type": float, "min": 0.0, "max": 1.0},
    "top_k": {"type": int, "min": 1, "max": None},
    "repeat_penalty": {"type": float, "min": 0.01, "max": None},
    "seed": {"type": int, "min": 0, "max": None},
}

# Settings that are stored under a different attribute name
_ATTR_MAP = {
    "stop_strings": "stop_strings",
}


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
    session.settings.system_prompt = prompt_text
    store.update_session(session)

    if prompt_text:
        await _cmd_reply(update.effective_message, "✅ System prompt updated.")
    else:
        await _cmd_reply(update.effective_message, "✅ System prompt cleared.")


@require_owner
async def set_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    store = context.bot_data["store"]
    session = store.get_active_session()
    if session is None:
        await _cmd_reply(update.effective_message, "❌ No active chat. Use /newchat first.")
        return

    args = context.args
    if not args or len(args) < 2:
        valid_names = ", ".join(list(VALID_SETTINGS.keys()) + ["stop_strings"])
        await _cmd_reply(
            update.effective_message,
            f"❌ Usage: /set <setting> <value>\nValid settings: {valid_names}",
        )
        return

    setting_name = args[0].lower()
    value_str = args[1]

    # Handle stop_strings specially (comma-separated list)
    if setting_name == "stop_strings":
        raw = " ".join(args[1:])
        if raw.lower() in ("none", "clear", "[]"):
            session.settings.stop_strings = []
        else:
            session.settings.stop_strings = [s.strip() for s in raw.split(",") if s.strip()]
        store.update_session(session)
        await _cmd_reply(
            update.effective_message,
            f"✅ stop_strings set to {session.settings.stop_strings}",
        )
        return

    if setting_name not in VALID_SETTINGS:
        valid_names = ", ".join(list(VALID_SETTINGS.keys()) + ["stop_strings"])
        await _cmd_reply(
            update.effective_message,
            f"❌ Unknown setting: {setting_name}. Valid: {valid_names}",
        )
        return

    spec = VALID_SETTINGS[setting_name]

    # Allow clearing nullable settings
    if value_str.lower() in ("none", "null") and setting_name in (
        "top_k", "repeat_penalty", "seed",
    ):
        setattr(session.settings, setting_name, None)
        store.update_session(session)
        await _cmd_reply(update.effective_message, f"✅ {setting_name} cleared")
        return

    try:
        value = spec["type"](value_str)
    except (ValueError, TypeError):
        await _cmd_reply(
            update.effective_message,
            f"❌ Invalid value for {setting_name}: must be a {spec['type'].__name__}",
        )
        return

    if spec["min"] is not None and value < spec["min"]:
        await _cmd_reply(
            update.effective_message,
            f"❌ Invalid value for {setting_name}: must be >= {spec['min']}",
        )
        return
    if spec["max"] is not None and value > spec["max"]:
        await _cmd_reply(
            update.effective_message,
            f"❌ Invalid value for {setting_name}: must be <= {spec['max']}",
        )
        return

    setattr(session.settings, setting_name, value)
    store.update_session(session)
    await _cmd_reply(update.effective_message, f"✅ {setting_name} set to {value}")
