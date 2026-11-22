"""Tiny translation layer: English text is the key, other languages are a lookup table.

* ``tr("Some text {name}", name=value)`` — translate and format at call time.
* ``mark("Some text")`` — flag a module-level constant as translatable without translating
  it yet (the constant is passed through ``tr()`` where it is used).

A missing translation falls back to the English text, so the UI never breaks; a test
verifies that every ``tr``/``mark`` literal in the source has a Russian entry.
"""

from __future__ import annotations

from src.bot.i18n_ru import RU

LANGUAGES: dict[str, str] = {"en": "English", "ru": "Русский"}
DEFAULT_LANGUAGE = "en"

_CATALOGS: dict[str, dict[str, str]] = {"ru": RU}
_current = DEFAULT_LANGUAGE


def set_language(code: str) -> str:
    """Switch the UI language; unknown codes fall back to the default. Returns the active code."""
    global _current
    _current = code if code in LANGUAGES else DEFAULT_LANGUAGE
    return _current


def get_language() -> str:
    return _current


def mark(text: str) -> str:
    """Declare *text* translatable (translate with ``tr`` where it is displayed)."""
    return text


def translate(text: str, language: str, **values) -> str:
    """Translate *text* into *language* (English text is returned as is) and format it."""
    translated = _CATALOGS.get(language, {}).get(text, text)
    return translated.format(**values) if values else translated


def tr(text: str, **values) -> str:
    """Translate *text* into the active language and fill ``{placeholders}``."""
    return translate(text, _current, **values)
