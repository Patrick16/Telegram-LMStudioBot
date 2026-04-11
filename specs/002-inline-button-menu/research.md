# Research: Inline Button Menu Navigation

**Feature**: 002-inline-button-menu  
**Date**: 2026-04-11

---

## 1. python-telegram-bot v21+ Inline Keyboard Pattern

**Decision**: Use `InlineKeyboardMarkup` / `InlineKeyboardButton` with `CallbackQueryHandler`.  
**Rationale**: PTB v21+ natively supports inline keyboards. `CallbackQueryHandler` fires for every button tap. Registration order in `main.py` controls priority.  
**Pattern**:
```python
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("Model Management", callback_data="menu:models")],
    [InlineKeyboardButton("⬅ Back", callback_data="menu:main")],
])
await query.edit_message_text("Choose:", reply_markup=keyboard)
await query.answer()  # always call to dismiss spinner
```

**Alternatives considered**:
- `ReplyKeyboardMarkup` (persistent bottom keyboard) — rejected because it persists across all messages, cannot be "per-message" or edited in-place.
- `ConversationHandler` for menu state — rejected because it only supports one active ConversationHandler per chat; conflicts with existing inference text handler.

---

## 2. Per-Conversation State: `context.chat_data`

**Decision**: Use PTB's built-in `context.chat_data` (a `dict` per `chat_id`) to store:
- `menu_message_id`: `int | None` — Telegram message ID of the persistent menu message.
- `pending_input`: `str | None` — callback key identifying which action is awaiting free-text input (e.g., `"models:load"`, `"settings:temperature"`).

**Rationale**: `chat_data` is automatically scoped per `chat_id`, survives across handler invocations within a session, requires no extra infrastructure, and is the canonical PTB pattern for per-conversation state.  
**Alternatives considered**:
- Separate in-memory dict keyed by `chat_id` — equivalent but more verbose; no benefit over `chat_data`.
- Database/file persistence for menu state — rejected; menu state is ephemeral and meaningless across bot restarts.

---

## 3. In-Place Message Editing

**Decision**: Use `query.edit_message_text(text, reply_markup=keyboard)` for navigation. Store `menu_message_id` on first send; re-use for `/menu` refresh.  
**Rationale**: Editing an existing message does not create clutter. Telegram imposes no meaningful rate-limit on editing the same message repeatedly (only ~20 edits/min per message, which navigation won't exceed).  
**Stale message handling**: If `edit_message_text` raises `telegram.error.BadRequest` (message not modified or message deleted), catch it: if `"message to edit not found"` → clear `menu_message_id`, send a fresh menu.  
**Alternatives considered**:
- Deleting the old message and sending a new one — rejected; causes chat spam (violates FR-002, SC-002).

---

## 4. Text Input Interception

**Decision**: Modify `text_message_handler` (in `messages.py`) to check `context.chat_data.get("pending_input")` at the top. If set, route to a `handle_pending_input()` function in `menu.py` instead of running inference.  
**Rationale**: A single `MessageHandler(filters.TEXT & ~filters.COMMAND, ...)` is already registered. Adding a priority check at the top of this handler is the simplest approach with no handler registration changes.  
**`/menu` cancellation**: The `/menu` command handler clears `pending_input` and shows the main menu — this satisfies FR-006.  
**Alternatives considered**:
- `ConversationHandler` states — rejected (conflicts with existing inference handler; adds complexity).
- Registering a second `MessageHandler` with higher priority — would work but is harder to reason about; in-handler routing is simpler.

---

## 5. Callback Data Routing

**Decision**: Use a `"namespace:action"` prefix scheme parsed in a single `CallbackQueryHandler(pattern=r"^(menu|models|sessions|settings|inference):")`.  
**All callback data keys**:

| Key | Effect |
|-----|--------|
| `menu:main` | Edit message → main menu keyboard |
| `menu:models` | Edit message → Model Management sub-menu |
| `menu:sessions` | Edit message → Chat Sessions sub-menu |
| `menu:settings` | Edit message → Settings sub-menu |
| `menu:inference` | Edit message → Inference sub-menu |
| `menu:help` | Edit message → Help sub-menu |
| `menu:help:models` | Edit message → Model Management help text |
| `menu:help:sessions` | Edit message → Chat Sessions help text |
| `menu:help:settings` | Edit message → Settings help text |
| `menu:help:inference` | Edit message → Inference help text |
| `models:list` | Post result of `cli.list_models()` |
| `models:loaded` | Post result of `cli.list_loaded()` |
| `models:load` | Set `pending_input="models:load"`, post prompt |
| `models:unload` | Set `pending_input="models:unload"`, post prompt |
| `sessions:new` | Set `pending_input="sessions:new"`, post prompt |
| `sessions:list` | Edit message → dynamic chat-list keyboard |
| `sessions:switch:<id>` | Switch active session, edit message → sessions sub-menu + confirmation |
| `sessions:remove` | Edit message → dynamic chat-list keyboard (for removal) |
| `sessions:confirm_remove:<id>` | Remove session, edit message → sessions sub-menu + confirmation |
| `settings:prompt` | Set `pending_input="settings:prompt"`, post prompt |
| `settings:temperature` | Set `pending_input="settings:temperature"`, post prompt |
| `settings:max_tokens` | Set `pending_input="settings:max_tokens"`, post prompt |
| `settings:top_p` | Set `pending_input="settings:top_p"`, post prompt |
| `inference:send` | Set `pending_input="inference:send"`, post prompt |
| `inference:regenerate` | Reuse the existing regenerate flow for the active session |

**Rationale**: A single handler + dispatcher avoids registering ~20 individual handlers; string prefix routing is clear and cheap.

---

## 6. Inference Section Sub-Menu

**Decision**: The Inference sub-menu displays:
- A status line: `Active model: <identifier>` or `No model loaded`
- Button: `💬 Send Message` → `callback_data="inference:send"`
- Button: `🔄 Regenerate` → `callback_data="inference:regenerate"`
- Button: `⬅ Back` → `callback_data="menu:main"`

After text input is received for `inference:send`, it runs through the same `_stream_in_thread` path used by the existing `text_message_handler`, appending to the active session history. The regenerate action reuses the existing `/regenerate` behaviour so command and button flows stay in parity.

**Rationale**: Reuses existing SDK plumbing; no new inference code needed.

---

## 7. Handler Registration Order in main.py

**Decision**: Register `CallbackQueryHandler` before `MessageHandler(TEXT)`:
```python
app.add_handler(CallbackQueryHandler(menu_callback_handler, pattern=r"^(menu|models|sessions|settings|inference):"))
```
PTB processes handlers in registration order; inline callbacks are a separate update type (`Update.CALLBACK_QUERY`) so ordering vs text handlers doesn't matter functionally — but registering early makes intent explicit.

**`/menu` command** replaces `/start` as the menu entry point, and also updates `/start` to call the same menu builder.

---

## Resolved Clarifications

- **Text during pending input**: Text message is consumed as input answer (not as inference). Rationale: the user entered the menu flow deliberately; consuming unexpected text as the answer is predictable. (See spec clarification 2026-04-11: implied by FR-005, FR-008 co-existence; text while pending_input is set goes to pending handler.)
- **Inference section**: shows active model + `💬 Send Message` button (spec clarification 2026-04-11, Answer A).
