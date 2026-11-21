"""Keyboard builders, help texts and settings rendering for the inline menu."""

import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ---------------------------------------------------------------------------
# Help text constants
# ---------------------------------------------------------------------------

HELP_MODELS = (
    "📦 <b>Model Management Help</b>\n\n"
    "• <b>List Models</b> — Shows all models available on disk in LM Studio.\n"
    "• <b>Loaded Models</b> — Shows models currently loaded into memory.\n"
    "• <b>Load Model</b> — Loads a model by its identifier (e.g. <code>qwen/qwen3-4b</code>).\n"
    "• <b>Unload Model</b> — Unloads a model by its identifier to free memory."
)

HELP_SESSIONS = (
    "🧠 <b>Sessions Help</b>\n\n"
    "• <b>New Chat</b> — Creates a new chat session (auto-named if no name given).\n"
    "• <b>List Chats</b> — Shows all sessions; tap one to switch to it.\n"
    "• <b>Remove Chat</b> — Shows all sessions; tap one to delete it."
)

HELP_SETTINGS = (
    "⚙️ <b>Settings Help</b>\n\n"
    "• <b>Current Settings</b> — View both model and session settings at a glance.\n"
    "• <b>Model Settings</b> — Adjust model-scoped runtime settings "
    "(GPU, context length, identifier).\n"
    "• <b>Session Settings</b> — Adjust session-scoped generation "
    "settings (temperature, max tokens, etc.).\n"
    "• <b>Model Presets</b> — Browse and apply saved model setting presets.\n"
    "• <b>Session Presets</b> — Browse and apply saved session setting presets.\n"
    "• <b>History Reuse Policy</b> — Control how chat history is assembled for inference."
)

# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------


def build_main_menu() -> InlineKeyboardMarkup:
    """Build the top-level menu keyboard (no Inference section, Regenerate at top)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Model Management", callback_data="menu:models"),
            InlineKeyboardButton("🧠 Chat Sessions", callback_data="menu:sessions"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="menu:settings"),
            InlineKeyboardButton("🔄 Regenerate", callback_data="menu:regenerate"),
        ],
        [InlineKeyboardButton("❓ Help", callback_data="menu:help")],
    ])


def build_back_button(target: str) -> InlineKeyboardMarkup:
    """Build a single-row keyboard with a Back button pointing to *target*."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back", callback_data=target)],
    ])


def build_models_menu() -> InlineKeyboardMarkup:
    """Model Management sub-menu."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 List Models", callback_data="models:list"),
            InlineKeyboardButton("🧠 Loaded Models", callback_data="models:loaded"),
        ],
        [
            InlineKeyboardButton("⬆ Load Model", callback_data="models:load"),
            InlineKeyboardButton("⬇ Unload Model", callback_data="models:unload"),
        ],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:main")],
    ])


def build_sessions_menu() -> InlineKeyboardMarkup:
    """Chat Sessions sub-menu."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ New Chat", callback_data="sessions:new"),
            InlineKeyboardButton("🗂 List Chats", callback_data="sessions:list"),
        ],
        [InlineKeyboardButton("🗑 Remove Chat", callback_data="sessions:remove")],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:main")],
    ])


def build_settings_menu() -> InlineKeyboardMarkup:
    """Settings sub-menu with split scopes, presets, and history policy."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Current Settings", callback_data="settings:current")],
        [
            InlineKeyboardButton("🖥 Model Settings", callback_data="settings:model_menu"),
            InlineKeyboardButton("💬 Session Settings", callback_data="settings:session_menu"),
        ],
        [
            InlineKeyboardButton("📦 Model Presets", callback_data="settings:model_presets"),
            InlineKeyboardButton("💾 Session Presets", callback_data="settings:session_presets"),
        ],
        [InlineKeyboardButton("📜 History Reuse Policy", callback_data="settings:history_policy")],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:main")],
    ])


def build_model_settings_menu() -> InlineKeyboardMarkup:
    """Model-scoped runtime settings menu."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🖥 GPU", callback_data="settings:model:gpu"),
            InlineKeyboardButton("📏 Context Length", callback_data="settings:model:context_length"),
        ],
        [InlineKeyboardButton("🏷 Identifier", callback_data="settings:model:identifier")],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:settings")],
    ])


def build_session_settings_menu() -> InlineKeyboardMarkup:
    """Session-scoped generation settings menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 System Prompt", callback_data="settings:session:prompt")],
        [
            InlineKeyboardButton("🌡 Temperature", callback_data="settings:session:temperature"),
            InlineKeyboardButton("🔢 Max Tokens", callback_data="settings:session:max_tokens"),
        ],
        [
            InlineKeyboardButton("📊 Top-P", callback_data="settings:session:top_p"),
            InlineKeyboardButton("🔝 Top-K", callback_data="settings:session:top_k"),
        ],
        [
            InlineKeyboardButton(
                "🔁 Repeat Penalty",
                callback_data="settings:session:repeat_penalty",
            ),
            InlineKeyboardButton(
                "🛑 Stop Strings",
                callback_data="settings:session:stop_strings",
            ),
        ],
        [InlineKeyboardButton("🎲 Seed", callback_data="settings:session:seed")],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:settings")],
    ])


def build_history_policy_menu() -> InlineKeyboardMarkup:
    """History reuse policy selection menu."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Off", callback_data="settings:history_policy:off")],
        [InlineKeyboardButton(
            "📐 Fit Budget (Recent)",
            callback_data="settings:history_policy:fit_budget_recent",
        )],
        [InlineKeyboardButton(
            "🔢 Last N Pairs",
            callback_data="settings:history_policy:last_n_pairs",
        )],
        [InlineKeyboardButton(
            "📋 Full If Possible",
            callback_data="settings:history_policy:full_if_possible",
        )],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:settings")],
    ])


def build_help_menu() -> InlineKeyboardMarkup:
    """Help sub-menu with topic buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📦 Model Help", callback_data="menu:help:models"),
            InlineKeyboardButton("🧠 Sessions Help", callback_data="menu:help:sessions"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings Help", callback_data="menu:help:settings"),
        ],
        [InlineKeyboardButton("⬅ Back", callback_data="menu:main")],
    ])


def build_sessions_list_keyboard(sessions, action: str) -> InlineKeyboardMarkup:
    """Build dynamic keyboard with one button per session."""
    rows = []
    for s in sessions:
        cb = f"sessions:{action}:{s.id}"
        rows.append([InlineKeyboardButton(s.name, callback_data=cb)])
    rows.append([InlineKeyboardButton("⬅ Back", callback_data="menu:sessions")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Help topic builders
# ---------------------------------------------------------------------------

def build_help_models() -> tuple[str, InlineKeyboardMarkup]:
    return HELP_MODELS, build_back_button("menu:help")


def build_help_sessions() -> tuple[str, InlineKeyboardMarkup]:
    return HELP_SESSIONS, build_back_button("menu:help")


def build_help_settings() -> tuple[str, InlineKeyboardMarkup]:
    return HELP_SETTINGS, build_back_button("menu:help")


# ---------------------------------------------------------------------------
# Current settings renderer
# ---------------------------------------------------------------------------

def _code(value) -> str:
    return f"<code>{html.escape(str(value), quote=False)}</code>"


def render_current_settings(session, model_info: str | None = None) -> str:
    """Build a combined current-settings text (Telegram HTML) for both scopes."""
    s = session.settings
    lines = ["📋 <b>Current Settings</b>\n"]

    lines.append("<b>Session Settings</b>")
    prompt_display = (
        s.system_prompt[:60] + '…'
        if len(s.system_prompt) > 60
        else s.system_prompt or '(none)'
    )
    lines.append(f"  System Prompt: {_code(prompt_display)}")
    lines.append(f"  Temperature: {_code(s.temperature)}")
    lines.append(f"  Max Tokens: {_code(s.max_tokens)}")
    lines.append(f"  Top-P: {_code(s.top_p)}")
    lines.append(f"  Top-K: {_code(s.top_k if s.top_k is not None else '(default)')}")
    lines.append(
        "  Repeat Penalty: "
        + _code(s.repeat_penalty if s.repeat_penalty is not None else "(default)")
    )
    lines.append(f"  Stop Strings: {_code(s.stop_strings or '(none)')}")
    lines.append(f"  Seed: {_code(s.seed if s.seed is not None else '(random)')}")
    lines.append(f"  History Policy: {_code(s.history_policy.mode)}")
    if s.history_policy.mode == "last_n_pairs" and s.history_policy.message_pair_limit is not None:
        lines.append(f"    Pair Limit: {_code(s.history_policy.message_pair_limit)}")

    lines.append("")
    lines.append("<b>Model Runtime</b>")
    if model_info:
        lines.append(f"  Loaded: {_code(model_info)}")
    else:
        lines.append("  <i>(No model loaded)</i>")

    return "\n".join(lines)
