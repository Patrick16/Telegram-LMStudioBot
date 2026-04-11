# Quickstart: Inline Button Menu Navigation

**Feature**: 002-inline-button-menu  
**Branch**: `002-inline-button-menu`

---

## What this feature adds

Replaces all slash-command discovery with an inline button menu. Users open the menu with `/menu` (or `/start`) and navigate to every bot feature via tappable buttons. Navigation edits a single message in place — no chat spam.

---

## New Files

| File | Purpose |
|------|---------|
| `src/bot/handlers/menu.py` | All inline menu logic: keyboard builders, callback router, pending input handler, `/menu` command handler |
| `tests/unit/test_menu.py` | Unit tests for keyboard builders, callback routing, input validation, pending input dispatch |

---

## Changed Files

| File | Change |
|------|--------|
| `src/bot/main.py` | Register `CallbackQueryHandler` and `/menu` command |
| `src/bot/handlers/help.py` | Update `/start` to invoke the menu builder while keeping `/help` as text guidance |
| `src/bot/handlers/messages.py` | Check `context.chat_data.get("pending_input")` at the top of `text_message_handler`; if set, delegate to `menu.handle_pending_input()` |
| `tests/integration/test_handlers.py` | Add integration tests for menu navigation, command parity, and pending input flow |

---

## Architecture Overview

```
User taps button
      │
      ▼
CallbackQueryHandler ──► menu.menu_callback_handler()
      │                        │
      │              parse callback_data prefix
      │              dispatch to sub-handler function
      │                        │
      │              query.edit_message_text(...)  ← in-place navigation
      │              query.answer()                ← dismiss spinner
      │
User sends text message
      │
      ▼
text_message_handler()
      │
      ├─ chat_data["pending_input"] is set?
      │         │
      │         YES ──► menu.handle_pending_input()
      │                      │
      │             validate input
      │             execute action (cli call / store update / inference)
      │             clear pending_input
      │
      └─ NO ──► existing inference path (unchanged)
```

---

## Key Design Decisions

- **In-place editing**: All navigation calls `query.edit_message_text()` on the stored `menu_message_id`. No new messages are created during navigation.
- **Single handler**: One `CallbackQueryHandler` with prefix pattern `^(menu|models|sessions|settings|inference):` routes all button presses.
- **Pending input**: `context.chat_data["pending_input"]` stores the awaited action key. The existing text handler checks this first, so no `ConversationHandler` is needed.
- **`/menu` cancels pending input**: The `/menu` handler clears `pending_input` before showing the menu.
- **No new dependencies**: `InlineKeyboardMarkup`, `InlineKeyboardButton`, `CallbackQueryHandler` are all available in `python-telegram-bot>=21.0`.

---

## Running Tests

```bash
cd e:\Git\pet-projects\LMStudioBot
& .venv\Scripts\Activate.ps1
cd src; pytest; ruff check .
```

All 58 existing tests must continue to pass. New tests cover:
- `test_menu.py`: keyboard builder output, callback routing, input validation, pending input dispatch
- `test_handlers.py`: updated integration tests for text message interception by pending input
