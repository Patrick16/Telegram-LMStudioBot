"""Declarative table of session generation settings editable from the menu.

One ``SettingSpec`` per setting replaces a hand-written branch of parsing,
validation and messaging, so adding a setting is a single table entry.
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


SETTING_SPECS: dict[str, SettingSpec] = {
    "prompt": SettingSpec(
        attr="system_prompt",
        parse=lambda text: text,
        error="",
        on_set=lambda v: "✅ System prompt updated." if v else "✅ System prompt cleared.",
    ),
    "temperature": SettingSpec(
        attr="temperature",
        parse=_float_in(0.0, 2.0),
        error="❌ Temperature must be a number between 0.0 and 2.0.",
        on_set=lambda v: f"✅ Temperature set to {v}",
    ),
    "max_tokens": SettingSpec(
        attr="max_tokens",
        parse=_int_min(-1),
        error="❌ Max tokens must be an integer ≥ -1 (use -1 for unlimited).",
        on_set=lambda v: f"✅ Max tokens set to {v}",
    ),
    "top_p": SettingSpec(
        attr="top_p",
        parse=_float_in(0.0, 1.0),
        error="❌ Top-P must be a number between 0.0 and 1.0.",
        on_set=lambda v: f"✅ Top-P set to {v}",
    ),
    "top_k": SettingSpec(
        attr="top_k",
        parse=_int_min(1),
        error="❌ Top-K must be an integer ≥ 1, or 'none' to clear.",
        on_set=lambda v: f"✅ Top-K set to {v}",
        clear_words=("none", "null", "default"),
        on_clear="✅ Top-K cleared",
    ),
    "repeat_penalty": SettingSpec(
        attr="repeat_penalty",
        parse=_positive_float,
        error="❌ Repeat penalty must be a number > 0, or 'none' to clear.",
        on_set=lambda v: f"✅ Repeat penalty set to {v}",
        clear_words=("none", "null", "default"),
        on_clear="✅ Repeat penalty cleared",
    ),
    "stop_strings": SettingSpec(
        attr="stop_strings",
        parse=_split_csv,
        error="",
        on_set=lambda v: f"✅ Stop strings set to {v}",
        clear_words=("none", "clear", "[]"),
        cleared_value=[],
        on_clear="✅ Stop strings cleared",
    ),
    "seed": SettingSpec(
        attr="seed",
        parse=_int_min(0),
        error="❌ Seed must be an integer ≥ 0, or 'none' for random.",
        on_set=lambda v: f"✅ Seed set to {v}",
        clear_words=("none", "null", "random"),
        on_clear="✅ Seed cleared (random)",
    ),
}
