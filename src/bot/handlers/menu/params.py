"""Settings presentation: parameter screens, creativity modes, history policy, presets."""

from __future__ import annotations

import html
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.handlers.settings_spec import SETTING_SPECS, SettingSpec
from src.bot.i18n import mark, tr
from src.storage.models import SessionGenerationSettings

CB_BACK_SESSION_SETTINGS = "settings:session_menu"


def _code(value) -> str:
    return f"<code>{html.escape(str(value), quote=False)}</code>"


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

def display_value(attr: str, value: Any) -> str:
    """Human wording for a setting value."""
    if attr == "max_tokens":
        return tr("unlimited") if value == -1 else str(value)
    if attr == "seed":
        return tr("random") if value is None else str(value)
    if attr == "system_prompt":
        return value if value else tr("none")
    if attr == "stop_strings":
        return ", ".join(value) if value else tr("none")
    if value is None:
        return tr("default")
    return str(value)


def _short(text: str, limit: int = 60) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


# ---------------------------------------------------------------------------
# Creativity modes
# ---------------------------------------------------------------------------

CREATIVITY_MODES: dict[str, tuple[str, dict[str, float]]] = {
    "precise": (mark("🎯 Precise"), {"temperature": 0.2, "top_p": 0.9}),
    "balanced": (mark("⚖️ Balanced"), {"temperature": 0.7, "top_p": 1.0}),
    "creative": (mark("🎨 Creative"), {"temperature": 1.1, "top_p": 0.95}),
}


def current_mode(settings: SessionGenerationSettings) -> str | None:
    for key, (_, values) in CREATIVITY_MODES.items():
        if all(getattr(settings, attr) == value for attr, value in values.items()):
            return key
    return None


def mode_title(settings: SessionGenerationSettings) -> str:
    key = current_mode(settings)
    return tr(CREATIVITY_MODES[key][0]) if key else tr("🛠 Custom")


def build_modes_row(settings: SessionGenerationSettings | None) -> list[InlineKeyboardButton]:
    active = current_mode(settings) if settings is not None else None
    return [
        InlineKeyboardButton(
            ("✅ " if key == active else "") + tr(title), callback_data=f"settings:mode:{key}"
        )
        for key, (title, _) in CREATIVITY_MODES.items()
    ]


# ---------------------------------------------------------------------------
# History policy
# ---------------------------------------------------------------------------

HISTORY_POLICIES: dict[str, tuple[str, str]] = {
    "off": (
        mark("🚫 No history"),
        mark("Every message stands alone; the model remembers nothing."),
    ),
    "fit_budget_recent": (
        mark("📐 Fit to context"),
        mark("As many of the newest messages as fit the model's context window."),
    ),
    "last_n_pairs": (
        mark("🔢 Last N exchanges"),
        mark("Only the last N question–answer pairs."),
    ),
    "full_if_possible": (
        mark("📋 Full history"),
        mark("Everything, as long as it fits the context window."),
    ),
}


def history_policy_title(mode: str) -> str:
    return tr(HISTORY_POLICIES.get(mode, (mode, ""))[0])


def render_history_policy_text(settings: SessionGenerationSettings | None) -> str:
    lines = [
        tr("📜 <b>History Reuse Policy</b>"),
        tr("How much of the chat the model sees each turn."),
    ]
    if settings is not None:
        policy = settings.history_policy
        title, description = HISTORY_POLICIES.get(policy.mode, (policy.mode, ""))
        lines.append(tr("Current: <b>{title}</b>", title=tr(title)))
        if description:
            lines.append(f"<i>{tr(description)}</i>")
        if policy.mode == "last_n_pairs" and policy.message_pair_limit is not None:
            lines.append(
                tr("Keeping the last {count} exchange(s).", count=policy.message_pair_limit)
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parameter screen
# ---------------------------------------------------------------------------

def _is_chosen(current: Any, value: Any) -> bool:
    if value is None or current is None:
        return value is None and current is None
    return current == value


def render_param_text(key: str, settings: SessionGenerationSettings) -> str:
    spec = SETTING_SPECS[key]
    current = getattr(settings, spec.attr)
    default = getattr(SessionGenerationSettings(), spec.attr)
    lines = [f"{spec.icon} <b>{tr(spec.title)}</b>", f"<i>{tr(spec.description)}</i>", ""]
    shown = _short(display_value(spec.attr, current), 300 if key == "prompt" else 60)
    lines.append(tr("Current: {value}", value=_code(shown)))
    if default != current:
        lines.append(
            tr("Default: {value}", value=_code(_short(display_value(spec.attr, default))))
        )
    if spec.hint:
        lines.append(tr("Allowed: {hint}", hint=tr(spec.hint)))
    return "\n".join(lines)


def build_param_keyboard(key: str, settings: SessionGenerationSettings) -> InlineKeyboardMarkup:
    spec: SettingSpec = SETTING_SPECS[key]
    current = getattr(settings, spec.attr)
    rows: list[list[InlineKeyboardButton]] = []

    per_row = 2 if key == "prompt" else 3
    picks = [
        InlineKeyboardButton(
            ("✅ " if _is_chosen(current, value) else "") + tr(label),
            callback_data=f"settings:param:pick:{index}",
        )
        for index, (label, value) in enumerate(spec.choices)
    ]
    for start in range(0, len(picks), per_row):
        rows.append(picks[start:start + per_row])

    if spec.step is not None:
        rows.append([
            InlineKeyboardButton(f"➖ {spec.step:g}", callback_data="settings:param:step:-1"),
            InlineKeyboardButton(f"➕ {spec.step:g}", callback_data="settings:param:step:1"),
        ])
    rows.append([
        InlineKeyboardButton(tr("✏️ Enter value"), callback_data="settings:param:input"),
        InlineKeyboardButton(tr("↺ Default"), callback_data="settings:param:reset"),
    ])
    rows.append([InlineKeyboardButton(tr("⬅ Back"), callback_data=CB_BACK_SESSION_SETTINGS)])
    return InlineKeyboardMarkup(rows)


# ---------------------------------------------------------------------------
# Readable summary of the session settings
# ---------------------------------------------------------------------------

def summarize_session_settings(settings: SessionGenerationSettings) -> list[str]:
    """One readable line per setting (Telegram HTML)."""
    lines = [tr("🎭 Mode: {mode}", mode=mode_title(settings))]
    for key, spec in SETTING_SPECS.items():
        value = getattr(settings, spec.attr)
        limit = 60 if key == "prompt" else 40
        shown = _code(_short(display_value(spec.attr, value), limit))
        lines.append(f"{spec.icon} {tr(spec.title)}: {shown}")
    state = tr("on") if settings.show_reasoning else tr("off")
    lines.append(tr("💭 Show reasoning: {state}", state=_code(state)))
    policy = settings.history_policy
    history = history_policy_title(policy.mode)
    if policy.mode == "last_n_pairs" and policy.message_pair_limit is not None:
        history += f" ({policy.message_pair_limit})"
    lines.append(tr("📜 History: {policy}", policy=history))
    return lines


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def render_session_preset_card(preset) -> str:
    lines = [f"💾 <b>{html.escape(preset.name, quote=False)}</b>"]
    if preset.description:
        lines.append(f"<i>{html.escape(preset.description, quote=False)}</i>")
    lines.append("")
    lines.extend(summarize_session_settings(preset.settings))
    return "\n".join(lines)


def render_model_preset_card(preset) -> str:
    s = preset.settings
    lines = [f"📦 <b>{html.escape(preset.name, quote=False)}</b>"]
    if preset.description:
        lines.append(f"<i>{html.escape(preset.description, quote=False)}</i>")
    lines.append("")
    lines.append(tr("🖥 GPU: {value}", value=_code(s.gpu)))
    lines.append(
        tr("📏 Context length: {value}", value=_code(s.context_length or tr("model default")))
    )
    lines.append(tr("🏷 Identifier: {value}", value=_code(s.identifier or tr("model name"))))
    lines.append("")
    lines.append(tr("<i>Applied on the next model load.</i>"))
    return "\n".join(lines)


def build_presets_keyboard(kind: str, presets, *, can_save: bool) -> InlineKeyboardMarkup:
    rows = []
    for index, preset in enumerate(presets.presets):
        label = f"{preset.name} — {preset.description[:30]}" if preset.description else preset.name
        rows.append([InlineKeyboardButton(
            label[:64], callback_data=f"settings:preset:{kind}:{index}"
        )])
    if can_save:
        rows.append([InlineKeyboardButton(
            tr("💾 Save current as preset"), callback_data="settings:save_session_preset"
        )])
    rows.append([InlineKeyboardButton(tr("⬅ Back"), callback_data="menu:settings")])
    return InlineKeyboardMarkup(rows)


def build_preset_card_keyboard(kind: str, index: int) -> InlineKeyboardMarkup:
    apply_cb = f"settings:apply_{kind}_preset:{index}"
    rows = [[InlineKeyboardButton(tr("✅ Apply"), callback_data=apply_cb)]]
    if kind == "session":
        rows[0].append(InlineKeyboardButton(
            tr("🗑 Delete"), callback_data=f"settings:del_session_preset:{index}"
        ))
    rows.append([InlineKeyboardButton(tr("⬅ Back"), callback_data=f"settings:{kind}_presets")])
    return InlineKeyboardMarkup(rows)
