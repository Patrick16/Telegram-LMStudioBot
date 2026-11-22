"""Keyboard builders, help texts and settings rendering for the inline menu."""

import html
from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.handlers.menu.params import (
    HISTORY_POLICIES,
    build_modes_row,
    summarize_session_settings,
)
from src.bot.pagination import nav_row, paginate
from src.bot.services.inference import CB_STOP

# ---------------------------------------------------------------------------
# Help text constants
# ---------------------------------------------------------------------------

HELP_MODELS = (
    "📦 <b>Model Management Help</b>\n\n"
    "Every model on disk is one button: ▶ used by this chat, 🟢 loaded, ⚪ not loaded.\n"
    "Tap a model to open its card:\n"
    "• <b>Load</b> — loads it and uses it in this chat.\n"
    "• <b>Unload</b> — frees memory.\n"
    "• <b>Use in chat</b> — binds an already loaded model to this chat."
)

HELP_SESSIONS = (
    "🧠 <b>Sessions Help</b>\n\n"
    "• <b>Chats</b> — all chats with message count and last activity; tap one for its card.\n"
    "• <b>Open / Rename / Delete</b> — actions on a chat card.\n"
    "• <b>New Chat</b> — creates a chat (auto-named if no name given)."
)

HELP_SETTINGS = (
    "⚙️ <b>Settings Help</b>\n\n"
    "• <b>Current Settings</b> — a readable overview of this chat's settings.\n"
    "• <b>Session Settings</b> — pick a mode (🎯 Precise / ⚖️ Balanced / 🎨 Creative) or "
    "tap a setting: quick values, ➖/➕ steps, or type your own.\n"
    "• <b>Model Settings</b> — GPU, context length and identifier, applied on the next load.\n"
    "• <b>Model / Session Presets</b> — preview a preset before applying it; "
    "session presets can be saved from the current settings.\n"
    "• <b>History Reuse Policy</b> — how much of the chat the model sees each turn."
)

# ---------------------------------------------------------------------------
# Keyboard builders
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LmsState:
    """LM Studio reachability snapshot shown in the main menu header."""

    online: bool
    loaded: tuple[str, ...] = ()


def render_main_menu_text(store, lms: LmsState | None = None) -> str:
    """Header of the main menu: LM Studio, active chat and model at a glance (Telegram HTML)."""
    lines = ["🏠 <b>Main Menu</b>"]
    if lms is not None:
        if lms.online:
            lines.append(f"🟢 LM Studio · {len(lms.loaded)} loaded")
        else:
            lines.append("🔴 LM Studio · offline")
    session = store.get_active_session()
    if session is None:
        lines.append("💬 No chat yet — tap ➕ New Chat")
    else:
        count = len(store.load_history(session.id))
        name = html.escape(session.name, quote=False)
        lines.append(f"💬 Chat: <b>{name}</b> · {count} message(s)")
        if session.model_identifier:
            model = html.escape(session.model_identifier, quote=False)
            lines.append(f"🧠 Model: <code>{model}</code>")
        else:
            lines.append("🧠 Model: <i>not loaded</i>")
        temperature = session.settings.temperature
        lines.append(f"🌡 Temperature: <code>{temperature}</code>")
    return "\n".join(lines)


def render_delete_confirmation(session, message_count: int) -> str:
    name = html.escape(session.name, quote=False)
    return (
        f"🗑 Delete chat <b>{name}</b> and its {message_count} message(s)?\n"
        "This cannot be undone."
    )


def build_delete_confirmation_keyboard(
    session_id: str, cancel: str | None = None
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Delete", callback_data=f"sessions:confirm_remove:{session_id}")],
        [InlineKeyboardButton("⬅ Cancel", callback_data=cancel or "sessions:remove")],
    ])


def build_main_menu() -> InlineKeyboardMarkup:
    """Top-level control panel: the everyday actions are one tap away."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ New Chat", callback_data="sessions:new"),
            InlineKeyboardButton("🗂 Chats", callback_data="sessions:list"),
        ],
        [
            InlineKeyboardButton("📦 Models", callback_data="menu:models"),
            InlineKeyboardButton("⚙️ Settings", callback_data="menu:settings"),
        ],
        [
            InlineKeyboardButton("🔄 Regenerate", callback_data="menu:regenerate"),
            InlineKeyboardButton("⏹ Stop", callback_data=CB_STOP),
        ],
        [
            InlineKeyboardButton("📊 Status", callback_data="menu:status"),
            InlineKeyboardButton("❓ Help", callback_data="menu:help"),
        ],
    ])


def build_back_button(target: str) -> InlineKeyboardMarkup:
    """Build a single-row keyboard with a Back button pointing to *target*."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅ Back", callback_data=target)],
    ])


def build_sessions_menu() -> InlineKeyboardMarkup:
    """Chat Sessions sub-menu."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ New Chat", callback_data="sessions:new"),
            InlineKeyboardButton("🗂 List Chats", callback_data="sessions:list"),
        ],
        [
            InlineKeyboardButton("✏️ Rename Chat", callback_data="sessions:rename"),
            InlineKeyboardButton("🗑 Remove Chat", callback_data="sessions:remove"),
        ],
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


def _value_label(settings, attr: str) -> str:
    """Short current-value text for a settings button."""
    value = getattr(settings, attr)
    if attr == "system_prompt":
        return "set" if value else "empty"
    if attr == "stop_strings":
        return f"{len(value)} set" if value else "none"
    if value is None:
        return "default"
    return str(value)


def build_session_settings_menu(settings=None) -> InlineKeyboardMarkup:
    """Session-scoped generation settings menu.

    When *settings* is given, each button shows the current value (``🌡 Temperature · 0.7``).
    """
    def label(icon_name: str, attr: str) -> str:
        if settings is None:
            return icon_name
        return f"{icon_name} · {_value_label(settings, attr)}"

    rows = []
    if settings is not None:
        rows.append(build_modes_row(settings))
    rows += [
        [InlineKeyboardButton(label("📝 System Prompt", "system_prompt"),
                              callback_data="settings:session:prompt")],
        [
            InlineKeyboardButton(label("🌡 Temperature", "temperature"),
                                 callback_data="settings:session:temperature"),
            InlineKeyboardButton(label("🔢 Max Tokens", "max_tokens"),
                                 callback_data="settings:session:max_tokens"),
        ],
        [
            InlineKeyboardButton(label("📊 Top-P", "top_p"),
                                 callback_data="settings:session:top_p"),
            InlineKeyboardButton(label("🔝 Top-K", "top_k"),
                                 callback_data="settings:session:top_k"),
        ],
        [
            InlineKeyboardButton(label("🔁 Repeat Penalty", "repeat_penalty"),
                                 callback_data="settings:session:repeat_penalty"),
            InlineKeyboardButton(label("🛑 Stop Strings", "stop_strings"),
                                 callback_data="settings:session:stop_strings"),
        ],
        [InlineKeyboardButton(label("🎲 Seed", "seed"), callback_data="settings:session:seed")],
    ]
    if settings is not None:
        state = "on" if settings.show_reasoning else "off"
        rows.append([
            InlineKeyboardButton(
                f"💭 Show reasoning: {state}", callback_data="settings:session:toggle_reasoning"
            ),
            InlineKeyboardButton("↺ Reset", callback_data="settings:session:reset"),
        ])
    rows.append([InlineKeyboardButton("⬅ Back", callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


def build_history_policy_menu(current: str | None = None) -> InlineKeyboardMarkup:
    """History reuse policy selection menu; the active policy is marked with ✅."""
    rows = [
        [InlineKeyboardButton(
            ("✅ " if mode == current else "") + title,
            callback_data=f"settings:history_policy:{mode}",
        )]
        for mode, (title, _) in HISTORY_POLICIES.items()
    ]
    rows.append([InlineKeyboardButton("⬅ Back", callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


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


def build_sessions_list_keyboard(
    sessions, action: str, page: int = 0, active_id: str | None = None
) -> InlineKeyboardMarkup:
    """One button per session (paginated); the active chat is marked with ▶."""
    shown, page, pages = paginate(sessions, page)
    rows = []
    for s in shown:
        label = f"▶ {s.name}" if s.id == active_id else s.name
        rows.append([InlineKeyboardButton(label, callback_data=f"sessions:{action}:{s.id}")])
    navigation = nav_row(f"sessions:page:{action}:", page, pages)
    if navigation:
        rows.append(navigation)
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
    """Readable overview of the active chat's settings (Telegram HTML)."""
    lines = ["📋 <b>Current Settings</b>", ""]
    lines.extend(summarize_session_settings(session.settings))
    lines.append("")
    lines.append("<b>Model</b>")
    if model_info:
        lines.append(f"🧠 {_code(model_info)}")
    else:
        lines.append("<i>(No model loaded)</i>")
    return "\n".join(lines)
