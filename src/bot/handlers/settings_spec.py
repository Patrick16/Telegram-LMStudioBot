"""Declarative table of session generation settings.

One ``SettingSpec`` per setting drives *everything* about it: parsing and validation
of typed input (menu and ``/set`` share it), confirmation messages, and how the menu
presents it (title, range hint, quick-pick values, +/- step). Adding a setting is a
single table entry.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SettingSpec:
    attr: str                           # attribute on SessionGenerationSettings
    parse: Callable[[str], Any]         # raises ValueError on invalid input
    error: str                          # shown when parse fails
    on_set: Callable[[Any], str]        # confirmation message for a new value
    clear_words: tuple[str, ...] = ()   # input that resets the setting
    cleared_value: Any = None
    on_clear: str = ""
    # --- presentation (menu) ---
    icon: str = ""
    title: str = ""
    description: str = ""
    hint: str = ""                      # allowed range / format, shown on the parameter screen
    prompt: str = ""                    # asked when the user chooses "Enter value"
    choices: tuple[tuple[str, Any], ...] = ()   # quick picks: (button label, value)
    step: float | None = None           # +/- button size, for numeric settings
    step_base: float | None = None      # starting point for +/- when the value is unset


def _float_in(lo: float, hi: float) -> Callable[[str], float]:
    def parse(text: str) -> float:
        value = float(text)
        if not (lo <= value <= hi):
            raise ValueError
        return value

    return parse


def _int_min(minimum: int) -> Callable[[str], int]:
    def parse(text: str) -> int:
        value = int(text)
        if value < minimum:
            raise ValueError
        return value

    return parse


def _positive_float(text: str) -> float:
    value = float(text)
    if value <= 0:
        raise ValueError
    return value


def _split_csv(text: str) -> list[str]:
    return [s.strip() for s in text.split(",") if s.strip()]


_CODER_PROMPT = (
    "You are an expert programmer. Give correct, idiomatic code with short explanations."
)
_TRANSLATOR_PROMPT = (
    "You are a translator. Translate the user's text keeping meaning and tone. "
    "Reply with the translation only."
)

SETTING_SPECS: dict[str, SettingSpec] = {
    "prompt": SettingSpec(
        attr="system_prompt",
        parse=lambda text: text,
        error="",
        on_set=lambda v: "✅ System prompt updated." if v else "✅ System prompt cleared.",
        icon="📝",
        title="System Prompt",
        description="Instructions the model follows in every reply of this chat.",
        prompt="Enter the system prompt (or send empty to clear):",
        choices=(
            ("🤖 Assistant", "You are a helpful assistant."),
            ("✂️ Concise", "Answer briefly and to the point."),
            ("💻 Coder", _CODER_PROMPT),
            ("🌐 Translator", _TRANSLATOR_PROMPT),
        ),
    ),
    "temperature": SettingSpec(
        attr="temperature",
        parse=_float_in(0.0, 2.0),
        error="❌ Temperature must be a number between 0.0 and 2.0.",
        on_set=lambda v: f"✅ Temperature set to {v}",
        icon="🌡",
        title="Temperature",
        description="Lower = precise and repeatable, higher = more creative.",
        hint="0.0 – 2.0",
        prompt="Enter temperature (0.0–2.0):",
        choices=(("0.0", 0.0), ("0.3", 0.3), ("0.7", 0.7), ("1.0", 1.0), ("1.5", 1.5)),
        step=0.1,
    ),
    "max_tokens": SettingSpec(
        attr="max_tokens",
        parse=_int_min(-1),
        error="❌ Max tokens must be an integer ≥ -1 (use -1 for unlimited).",
        on_set=lambda v: f"✅ Max tokens set to {v}",
        icon="🔢",
        title="Max Tokens",
        description="Upper limit for the length of one reply.",
        hint="integer ≥ 1, or -1 for unlimited",
        prompt="Enter max tokens (integer ≥ -1, use -1 for unlimited):",
        choices=(("∞", -1), ("256", 256), ("512", 512), ("1024", 1024),
                 ("2048", 2048), ("4096", 4096)),
    ),
    "top_p": SettingSpec(
        attr="top_p",
        parse=_float_in(0.0, 1.0),
        error="❌ Top-P must be a number between 0.0 and 1.0.",
        on_set=lambda v: f"✅ Top-P set to {v}",
        icon="📊",
        title="Top-P",
        description="Only the most probable words that add up to this share are considered.",
        hint="0.0 – 1.0",
        prompt="Enter top-p (0.0–1.0):",
        choices=(("0.5", 0.5), ("0.8", 0.8), ("0.9", 0.9), ("0.95", 0.95), ("1.0", 1.0)),
        step=0.05,
    ),
    "top_k": SettingSpec(
        attr="top_k",
        parse=_int_min(1),
        error="❌ Top-K must be an integer ≥ 1, or 'none' to clear.",
        on_set=lambda v: f"✅ Top-K set to {v}",
        clear_words=("none", "null", "default"),
        on_clear="✅ Top-K cleared",
        icon="🔝",
        title="Top-K",
        description="Only this many most probable words are considered at each step.",
        hint="integer ≥ 1, or default",
        prompt="Enter top-k (integer ≥ 1, or 'none' to clear):",
        choices=(("Default", None), ("20", 20), ("40", 40), ("100", 100)),
    ),
    "repeat_penalty": SettingSpec(
        attr="repeat_penalty",
        parse=_positive_float,
        error="❌ Repeat penalty must be a number > 0, or 'none' to clear.",
        on_set=lambda v: f"✅ Repeat penalty set to {v}",
        clear_words=("none", "null", "default"),
        on_clear="✅ Repeat penalty cleared",
        icon="🔁",
        title="Repeat Penalty",
        description="Values above 1.0 discourage the model from repeating itself.",
        hint="number > 0 (typical 1.0 – 1.3), or default",
        prompt="Enter repeat penalty (> 0, or 'none' to clear):",
        choices=(("Default", None), ("1.0", 1.0), ("1.1", 1.1), ("1.2", 1.2), ("1.3", 1.3)),
        step=0.05,
        step_base=1.0,
    ),
    "stop_strings": SettingSpec(
        attr="stop_strings",
        parse=_split_csv,
        error="",
        on_set=lambda v: f"✅ Stop strings set to {v}",
        clear_words=("none", "clear", "[]"),
        cleared_value=[],
        on_clear="✅ Stop strings cleared",
        icon="🛑",
        title="Stop Strings",
        description="Generation stops as soon as the model writes one of these.",
        hint="comma-separated, up to 4",
        prompt="Enter stop strings (comma-separated, or 'none' to clear):",
    ),
    "seed": SettingSpec(
        attr="seed",
        parse=_int_min(0),
        error="❌ Seed must be an integer ≥ 0, or 'none' for random.",
        on_set=lambda v: f"✅ Seed set to {v}",
        clear_words=("none", "null", "random"),
        on_clear="✅ Seed cleared (random)",
        icon="🎲",
        title="Seed",
        description="A fixed seed makes replies reproducible.",
        hint="integer ≥ 0, or random",
        prompt="Enter seed (integer ≥ 0, or 'none' for random):",
        choices=(("Random", None), ("0", 0), ("42", 42), ("1234", 1234)),
    ),
}


def apply_text(spec: SettingSpec, text: str) -> tuple[Any, str]:
    """Interpret typed *text* for *spec*: returns ``(new_value, confirmation_message)``.

    Raises ``ValueError`` carrying the user-facing error when the input is invalid.
    """
    text = text.strip()
    if text.lower() in spec.clear_words:
        return spec.cleared_value, spec.on_clear
    try:
        value = spec.parse(text)
    except ValueError:
        raise ValueError(spec.error) from None
    return value, spec.on_set(value)


def confirmation_for(spec: SettingSpec, value: Any) -> str:
    """Confirmation message for a value chosen with a button (``None`` = back to default)."""
    if value is None and spec.on_clear:
        return spec.on_clear
    return spec.on_set(value)


def step_value(spec: SettingSpec, current: Any, direction: int) -> Any:
    """Next value one ``step`` up (+1) or down (-1); raises ``ValueError`` at a limit."""
    if spec.step is None:
        raise ValueError
    base = spec.step_base if current is None else current
    if base is None:
        raise ValueError
    candidate = round(base + direction * spec.step, 4)
    return spec.parse(str(candidate))  # validates the range
