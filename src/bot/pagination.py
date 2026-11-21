"""Tiny pagination helpers for inline keyboards."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from telegram import InlineKeyboardButton

T = TypeVar("T")

PAGE_SIZE = 8
NOOP = "noop"


def paginate(items: Sequence[T], page: int, per_page: int = PAGE_SIZE) -> tuple[list[T], int, int]:
    """Return ``(items_on_page, clamped_page, total_pages)``; pages are 0-based."""
    pages = max(1, -(-len(items) // per_page))
    page = min(max(page, 0), pages - 1)
    start = page * per_page
    return list(items[start:start + per_page]), page, pages


def nav_row(callback_prefix: str, page: int, pages: int) -> list[InlineKeyboardButton]:
    """``◀ 2/5 ▶`` row; empty when everything fits on one page.

    Buttons send ``f"{callback_prefix}{target_page}"``; the counter is inert.
    """
    if pages <= 1:
        return []
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("◀", callback_data=f"{callback_prefix}{page - 1}"))
    row.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data=NOOP))
    if page < pages - 1:
        row.append(InlineKeyboardButton("▶", callback_data=f"{callback_prefix}{page + 1}"))
    return row
