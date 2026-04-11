# Data Model: Inline Button Menu Navigation

**Feature**: 002-inline-button-menu  
**Date**: 2026-04-11

---

## Overview

This feature adds no persistent data storage. All menu state is **ephemeral** and lives in PTB's per-conversation `context.chat_data`. The existing `SessionStore` / `ChatSession` models are unchanged.

---

## Runtime Entities (in-memory only, `context.chat_data`)

### MenuMessageId
Stores the Telegram message ID of the single persistent menu message for the conversation.

| Key | Type | Description |
|-----|------|-------------|
| `chat_data["menu_message_id"]` | `int \| None` | Message ID of the current menu message. `None` when no menu has been sent yet or after it was deleted. |

**Lifecycle**:
- Set when `/menu` or `/start` sends a new menu message.
- Cleared (set to `None`) when a `BadRequest` edit error confirms the message was deleted.
- Re-used on subsequent navigations to call `edit_message_text`.

---

### PendingInput
Stores the callback key identifying which action is waiting for free-text input from the user.

| Key | Type | Description |
|-----|------|-------------|
| `chat_data["pending_input"]` | `str \| None` | Callback key such as `"models:load"`, `"settings:temperature"`, `"inference:send"`. `None` when no input is awaited. |

**Lifecycle**:
- Set when a button action requires text input (e.g., user taps "⬆ Load Model").
- Cleared when the user submits input text OR sends `/menu`.
- Checked at the top of `text_message_handler` to intercept input before inference.

**Valid values**:

| Value | Expected input | Handler action |
|-------|---------------|----------------|
| `models:load` | Model identifier string | Call `cli.load_model(identifier)` |
| `models:unload` | Model identifier string | Call `cli.unload_model(identifier)` |
| `sessions:new` | Session name (or empty for auto-name) | `store.create_session(name)` |
| `settings:prompt` | System prompt text (or empty to clear) | `session.system_prompt = text` |
| `settings:temperature` | Float `0.0–2.0` | `session.settings.temperature = value` |
| `settings:max_tokens` | Int `≥ -1` | `session.settings.max_tokens = value` |
| `settings:top_p` | Float `0.0–1.0` | `session.settings.top_p = value` |
| `inference:send` | Message text | Run full inference stream via `sdk.chat_stream()` |

---

## Existing Models (unchanged)

All existing pydantic models remain as-is:

- `ModelSettings` — temperature, max_tokens, top_p, stop
- `LoadConfig` — gpu, context_length, identifier
- `ChatMessage` — role, content, image_path, timestamp
- `ChatSession` — id, name, model_identifier, system_prompt, settings, history, created_at, updated_at
- `SessionStore` — active_session_id, sessions dict

No fields are added to any existing model.

---

## Keyboard Definitions (logical, not persisted)

The following keyboard layouts are constructed at runtime by `menu.py`:

### Main Menu
```
[📦 Model Management]  [🧠 Chat Sessions]
[⚙️ Settings]           [🔮 Inference]
[❓ Help]
```

### Model Management Sub-Menu
```
[📦 List Models]    [🧠 Loaded Models]
[⬆ Load Model]     [⬇ Unload Model]
[⬅ Back]
```

### Chat Sessions Sub-Menu
```
[➕ New Chat]    [🗂 List Chats]
[🗑 Remove Chat]
[⬅ Back]
```

### Settings Sub-Menu
```
[📝 System Prompt]
[🌡 Temperature]   [🔢 Max Tokens]   [📊 Top-P]
[⬅ Back]
```

### Inference Sub-Menu
```
Active model: <identifier | "No model loaded">
[💬 Send Message]   [🔄 Regenerate]
[⬅ Back]
```

### Help Sub-Menu
```
[📦 Model Help]     [🧠 Sessions Help]
[⚙️ Settings Help]  [🔮 Inference Help]
[⬅ Back]
```

### Dynamic Chat List (for List / Switch / Remove)
Each button: `[<session.name>]` with `callback_data="sessions:switch:<id>"` or `sessions:confirm_remove:<id>`  
Footer: `[⬅ Back]`

---

## Validation Rules

| Input type | Rule | Error message |
|------------|------|---------------|
| temperature | Must parse as float, 0.0 ≤ x ≤ 2.0 | "❌ Temperature must be a number between 0.0 and 2.0." |
| max_tokens | Must parse as integer, ≥ -1 | "❌ Max tokens must be an integer ≥ -1 (use -1 for unlimited)." |
| top_p | Must parse as float, 0.0 ≤ x ≤ 1.0 | "❌ Top-P must be a number between 0.0 and 1.0." |
| model identifier | Non-empty string | "❌ Model identifier cannot be empty." |
| session name | Any string (auto-named if empty) | — |
| system prompt | Any string (empty = clear prompt) | — |
| inference message | Non-empty string | "❌ Message cannot be empty." |

On validation failure: post error message and re-set `pending_input` to prompt again.
