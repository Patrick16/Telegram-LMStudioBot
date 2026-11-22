"""Keyboard builders, help texts and settings rendering for the inline menu."""

import html
from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.handlers.menu.params import (
    HISTORY_POLICIES,
    build_modes_row,
    summarize_session_settings,
)
from src.bot.i18n import tr
from src.bot.pagination import nav_row, paginate
from src.bot.services.inference import CB_STOP

# ---------------------------------------------------------------------------
# Help texts
# ---------------------------------------------------------------------------


def help_models_text() -> str:
    return tr(
        "📦 <b>Model Management Help</b>\n\n"
        "Every model on disk is one button: ▶ used by this chat, 🟢 loaded, ⚪ not loaded.\n"
        "Tap a model to open its card:\n"
        "• <b>Load</b> — loads it and uses it in this chat.\n"
        "• <b>Unload</b> — frees memory.\n"
        "• <b>Use in chat</b> — binds an already loaded model to this chat."
    )


def help_sessions_text() -> str:
    return tr(
        "🧠 <b>Sessions Help</b>\n\n"
        "• <b>Chats</b> — all chats with message count and last activity; tap one for its card.\n"
        "• <b>Open / Rename / Delete</b> — actions on a chat card.\n"
        "• <b>New Chat</b> — creates a chat (auto-named if no name given)."
    )


def help_settings_text() -> str:
    return tr(
        "⚙️ <b>Settings Help</b>\n\n"
        "• <b>Current Settings</b> — a readable overview of this chat's settings.\n"
        "• <b>Session Settings</b> — pick a mode (🎯 Precise / ⚖️ Balanced / 🎨 Creative) or "
        "tap a setting: quick values, ➖/➕ steps, or type your own.\n"
        "• <b>Model Settings</b> — GPU, context length and identifier, applied on the next load.\n"
        "• <b>Model / Session Presets</b> — preview a preset before applying it; "
        "session presets can be saved from the current settings.\n"
        "• <b>History Reuse Policy</b> — how much of the chat the model sees each turn.\n"
        "• <b>Language</b> — switch the interface language."
    )


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LmsState:
    """LM Studio reachability snapshot shown in the main menu header."""

    online: bool
    loaded: tuple[str, ...] = ()


def render_main_menu_text(store, lms: LmsState | None = None) -> str:
    """Header of the main menu: LM Studio, active chat and model at a glance (Telegram HTML)."""
    lines = [tr("🏠 <b>Main Menu</b>")]
    if lms is not None:
        if lms.online:
            lines.append(tr("🟢 LM Studio · {count} loaded", count=len(lms.loaded)))
        else:
            lines.append(tr("🔴 LM Studio · offline"))
    session = store.get_active_session()
    if session is None:
        lines.append(tr("💬 No chat yet — tap ➕ New Chat"))
    else:
        count = len(store.load_history(session.id))
        name = html.escape(session.name, quote=False)
        lines.append(tr("💬 Chat: <b>{name}</b> · {count} message(s)", name=name, count=count))
        if session.model_identifier:
            model = html.escape(session.model_identifier, quote=False)
            lines.append(tr("🧠 Model: <code>{model}</code>", model=model))
        else:
            lines.append(tr("🧠 Model: <i>not loaded</i>"))
        lines.append(tr("🌡 Temperature: <code>{value}</code>", value=session.settings.temperature))
    return "\n".join(lines)


def render_delete_confirmation(session, message_count: int) -> str:
    name = html.escape(session.name, quote=False)
    return tr(
        "🗑 Delete chat <b>{name}</b> and its {count} message(s)?\nThis cannot be undone.",
        name=name, count=message_count,
    )


def build_delete_confirmation_keyboard(
    session_id: str, cancel: str | None = None
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            tr("🗑 Delete"), callback_data=f"sessions:confirm_remove:{session_id}"
        )],
        [InlineKeyboardButton(tr("⬅ Cancel"), callback_data=cancel or "sessions:remove")],
    ])


def build_main_menu() -> InlineKeyboardMarkup:
    """Top-level control panel: the everyday actions are one tap away."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(tr("➕ New Chat"), callback_data="sessions:new"),
            InlineKeyboardButton(tr("🗂 Chats"), callback_data="sessions:list"),
        ],
        [
            InlineKeyboardButton(tr("📦 Models"), callback_data="menu:models"),
            InlineKeyboardButton(tr("⚙️ Settings"), callback_data="menu:settings"),
        ],
        [
            InlineKeyboardButton(tr("🔄 Regenerate"), callback_data="menu:regenerate"),
            InlineKeyboardButton(tr("⏹ Stop"), callback_data=CB_STOP),
        ],
        [
            InlineKeyboardButton(tr("📊 Status"), callback_data="menu:status"),
            InlineKeyboardButton(tr("❓ Help"), callback_data="menu:help"),
        ],
    ])


def build_back_button(target: str) -> InlineKeyboardMarkup:
    """Build a single-row keyboard with a Back button pointing to *target*."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr("⬅ Back"), callback_data=target)],
    ])


def build_sessions_menu() -> InlineKeyboardMarkup:
    """Chat Sessions sub-menu."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(tr("➕ New Chat"), callback_data="sessions:new"),
            InlineKeyboardButton(tr("🗂 List Chats"), callback_data="sessions:list"),
        ],
        [
            InlineKeyboardButton(tr("✏️ Rename Chat"), callback_data="sessions:rename"),
            InlineKeyboardButton(tr("🗑 Remove Chat"), callback_data="sessions:remove"),
        ],
        [InlineKeyboardButton(tr("⬅ Back"), callback_data="menu:main")],
    ])


def build_settings_menu() -> InlineKeyboardMarkup:
    """Settings sub-menu with split scopes, presets, history policy and language."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(tr("📋 Current Settings"), callback_data="settings:current")],
        [
            InlineKeyboardButton(tr("🖥 Model Settings"), callback_data="settings:model_menu"),
            InlineKeyboardButton(
                tr("💬 Session Settings"), callback_data="settings:session_menu"
            ),
        ],
        [
            InlineKeyboardButton(tr("📦 Model Presets"), callback_data="settings:model_presets"),
            InlineKeyboardButton(
                tr("💾 Session Presets"), callback_data="settings:session_presets"
            ),
        ],
        [InlineKeyboardButton(
            tr("📜 History Reuse Policy"), callback_data="settings:history_policy"
        )],
        [InlineKeyboardButton(tr("🌐 Language"), callback_data="settings:language")],
        [InlineKeyboardButton(tr("⬅ Back"), callback_data="menu:main")],
    ])


def build_model_settings_menu() -> InlineKeyboardMarkup:
    """Model-scoped runtime settings menu."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(tr("🖥 GPU"), callback_data="settings:model:gpu"),
            InlineKeyboardButton(
                tr("📏 Context Length"), callback_data="settings:model:context_length"
            ),
        ],
        [InlineKeyboardButton(tr("🏷 Identifier"), callback_data="settings:model:identifier")],
        [InlineKeyboardButton(tr("⬅ Back"), callback_data="menu:settings")],
    ])


def _value_label(settings, attr: str) -> str:
    """Short current-value text for a settings button."""
    value = getattr(settings, attr)
    if attr == "system_prompt":
        return tr("set") if value else tr("empty")
    if attr == "stop_strings":
        return tr("{count} set", count=len(value)) if value else tr("none")
    if value is None:
        return tr("default")
    return str(value)


def build_session_settings_menu(settings=None) -> InlineKeyboardMarkup:
    """Session-scoped generation settings menu.

    When *settings* is given, each button shows the current value (``🌡 Temperature · 0.7``).
    """
    def label(icon_name: str, attr: str) -> str:
        if settings is None:
            return icon_name
        return f"{icon_name} · {_value_label(settings, attr)}"

    def button(text: str, attr: str, key: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(label(text, attr), callback_data=f"settings:session:{key}")

    rows = []
    if settings is not None:
        rows.append(build_modes_row(settings))
    rows += [
        [button(tr("📝 System Prompt"), "system_prompt", "prompt")],
        [
            button(tr("🌡 Temperature"), "temperature", "temperature"),
            button(tr("🔢 Max Tokens"), "max_tokens", "max_tokens"),
        ],
        [
            button(tr("📊 Top-P"), "top_p", "top_p"),
            button(tr("🔝 Top-K"), "top_k", "top_k"),
        ],
        [
            button(tr("🔁 Repeat Penalty"), "repeat_penalty", "repeat_penalty"),
            button(tr("🛑 Stop Strings"), "stop_strings", "stop_strings"),
        ],
        [button(tr("🎲 Seed"), "seed", "seed")],
    ]
    if settings is not None:
        state = tr("on") if settings.show_reasoning else tr("off")
        rows.append([
            InlineKeyboardButton(
                tr("💭 Show reasoning: {state}", state=state),
                callback_data="settings:session:toggle_reasoning",
            ),
            InlineKeyboardButton(tr("↺ Reset"), callback_data="settings:session:reset"),
        ])
    rows.append([InlineKeyboardButton(tr("⬅ Back"), callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


def build_history_policy_menu(current: str | None = None) -> InlineKeyboardMarkup:
    """History reuse policy selection menu; the active policy is marked with ✅."""
    rows = [
        [InlineKeyboardButton(
            ("✅ " if mode == current else "") + tr(title),
            callback_data=f"settings:history_policy:{mode}",
        )]
        for mode, (title, _) in HISTORY_POLICIES.items()
    ]
    rows.append([InlineKeyboardButton(tr("⬅ Back"), callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


def build_help_menu() -> InlineKeyboardMarkup:
    """Help sub-menu with topic buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(tr("📦 Model Help"), callback_data="menu:help:models"),
            InlineKeyboardButton(tr("🧠 Sessions Help"), callback_data="menu:help:sessions"),
        ],
        [
            InlineKeyboardButton(tr("⚙️ Settings Help"), callback_data="menu:help:settings"),
            InlineKeyboardButton(tr("⌨️ Commands"), callback_data="menu:help:commands"),
        ],
        [InlineKeyboardButton(tr("⬅ Back"), callback_data="menu:main")],
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
    rows.append([InlineKeyboardButton(tr("⬅ Back"), callback_data="menu:sessions")])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Help topic builders
# ---------------------------------------------------------------------------

def build_help_models() -> tuple[str, InlineKeyboardMarkup]:
    return help_models_text(), build_back_button("menu:help")


def build_help_sessions() -> tuple[str, InlineKeyboardMarkup]:
    return help_sessions_text(), build_back_button("menu:help")


def build_help_settings() -> tuple[str, InlineKeyboardMarkup]:
    return help_settings_text(), build_back_button("menu:help")


# ---------------------------------------------------------------------------
# Current settings renderer
# ---------------------------------------------------------------------------

def _code(value) -> str:
    return f"<code>{html.escape(str(value), quote=False)}</code>"


def render_current_settings(session, model_info: str | None = None) -> str:
    """Readable overview of the active chat's settings (Telegram HTML)."""
    lines = [tr("📋 <b>Current Settings</b>"), ""]
    lines.extend(summarize_session_settings(session.settings))
    lines.append("")
    lines.append(tr("<b>Model</b>"))
    if model_info:
        lines.append(f"🧠 {_code(model_info)}")
    else:
        lines.append(tr("<i>(No model loaded)</i>"))
    return "\n".join(lines)
