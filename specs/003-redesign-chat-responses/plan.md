# Implementation Plan: 003 — Redesign Chat Responses

**Branch**: `003-redesign-chat-responses` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `/specs/003-redesign-chat-responses/spec.md`

## Summary

Redesign all user-facing responses in LMStudioBot: replace inline model listing (currently raw CLI text) with plain bulleted lists from the lmstudio SDK; replace text-prompt load/unload flows with clickable inline keyboards (with 🟢 markers for loaded models); strip `<think>` tags from all inference responses; convert fenced/inline code to Telegram HTML `<pre><code>`/`<code>`; HTML-escape all remaining plain text. A new `src/bot/formatting.py` module provides the formatting pipeline. The lmstudio SDK (already used for inference) is extended with `list_downloaded_models` and `list_loaded_models` async wrappers.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: `python-telegram-bot>=21.0`, `lmstudio>=1.5.0`, `pydantic>=2.0`, `python-dotenv`  
**Storage**: N/A (ephemeral `context.chat_data` only — no new persistent storage)  
**Testing**: pytest + pytest-asyncio (mode=auto), ruff/flake8 (line-length=100)  
**Target Platform**: Local host (single-owner Telegram bot, Linux/Windows)  
**Project Type**: Telegram bot application  
**Performance Goals**: No latency requirements; local bot for single user  
**Constraints**: Telegram inline button callback data ≤ 64 bytes; keyboard ≤ 100 buttons; button labels ≤ 64 chars  
**Scale/Scope**: Single owner, local bot; no concurrency requirements

## Constitution Check

### Gate Evaluation (pre-design)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Security & Privacy First | ✅ PASS | No new credentials; logs must not expose model content. `format_response()` is pure string manipulation. |
| II. Telegram API Discipline | ✅ PASS | Uses `parse_mode="HTML"` (documented feature). HTML-escaping prevents injection of unwanted tags. Callback data within 64-byte limit. |
| III. Robust Error Handling | ✅ PASS | SDK calls wrapped in `try/except`; empty-response case handled with `"*(no response)*"`. |
| IV. Test Coverage | ✅ PASS | `tests/unit/test_formatting.py` covers all formatting paths; SDK wrapper and handler tests required. |
| V. Logging & Observability | ✅ PASS | Structured logging already in place; no sensitive data in new log messages. |

### Gate Evaluation (post-design)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Security | ✅ PASS | HTML-escaping before `parse_mode="HTML"` is the key security control. `html.escape()` prevents XSS-equivalent tag injection by LLM output. |
| II. Telegram API | ✅ PASS | Callback data scheme validated against 64-byte limit in research. |
| III. Error Handling | ✅ PASS | All SDK paths have error branches; inline-keyboard edit failures caught. |
| IV. Testing | ✅ PASS | New module has dedicated unit tests; integration tests updated. |
| V. Logging | ✅ PASS | No sensitive data added to any log call. |

**Verdict**: No violations. No Complexity Tracking needed.

## Project Structure

### Documentation (this feature)

```text
specs/003-redesign-chat-responses/
├── plan.md              # This file
├── research.md          # Phase 0 output — SDK API, formatting pipeline, callback scheme
├── data-model.md        # Phase 1 output — entities, state transitions, module map
├── quickstart.md        # Phase 1 output — dev setup and test guide
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code — files changed by this feature

```text
src/
├── bot/
│   ├── formatting.py          # NEW  — format_response(), strip_think_tags(), _format_size()
│   └── handlers/
│       ├── models.py          # REWRITE — plain list + inline keyboard load/unload
│       ├── messages.py        # MODIFY  — apply format_response() to final response
│       ├── vision.py          # MODIFY  — apply format_response() to final response
│       └── menu.py            # MODIFY  — models:load/unload show SDK inline keyboards
└── lms/
    └── sdk.py                 # EXTEND  — add list_downloaded_models, list_loaded_models

tests/
├── unit/
│   ├── test_formatting.py     # NEW — unit tests for formatting module
│   └── test_menu.py           # UPDATE — new callback routing tests
└── integration/
    └── test_handlers.py       # UPDATE — load/unload keyboard flow tests
```

**Structure Decision**: Single-project layout (Option 1); no structural changes to existing directories.

---

## Implementation Design

### Module 1: `src/bot/formatting.py` (NEW)

**Purpose**: Pure string-processing pipeline — no I/O, no Telegram imports, easily unit-tested.

**Public API**:

- `format_response(text: str) -> str` — full pipeline
- `strip_think_tags(text: str) -> str` — remove `<think>…</think>` blocks
- `_format_size(size_bytes: int) -> str` — bytes to `X.X GB` / `X MB`

**Pipeline**:

1. Strip think tags: `re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()`
2. If blank → return `"*(no response)*"`
3. Process segment-by-segment (single regex pass):
   - Fenced code block: HTML-escape code content → `<pre><code>{code}</code></pre>` (language tag discarded)
   - Inline code: HTML-escape content → `<code>{code}</code>`
   - Plain text: `html.escape(segment)`
4. Join and return

**Dependencies**: `re`, `html` (stdlib only — no new packages)

---

### Module 2: `src/lms/sdk.py` (EXTEND)

Add two async wrappers using `asyncio.to_thread` (Python 3.9+):

- `list_downloaded_models(host, port)` — returns `list[DownloadedModel]`
- `list_loaded_models(host, port)` — returns `list[SyncModelHandle]`

Both use `with lmstudio.Client(api_host=f"{host}:{port}") as client:` pattern already established in the module.

---

### Module 3: `src/bot/handlers/models.py` (REWRITE)

| Handler | Change |
|---------|--------|
| `models_command` | Call `sdk.list_downloaded_models`; format `• {model_key}  {size}`; `parse_mode="HTML"` |
| `loaded_command` | Call `sdk.list_loaded_models`; format `• {identifier}  {size}`; `parse_mode="HTML"` |
| `load_command` no-args | Call `_send_load_keyboard()` — SDK gather for downloaded+loaded, build InlineKeyboardMarkup |
| `load_command` with-args | Unchanged (FR-013) |
| `unload_command` no-args | Call `_send_unload_keyboard()` — SDK list loaded, build InlineKeyboardMarkup |
| `unload_command` with-args | Unchanged (FR-013) |

**Load keyboard**: one button per model; `🟢 ` prefix if `model_key in loaded_keys`; label truncated to 64 chars; callback `models:loadmodel:{model_key}` (64-byte limit).

**Unload keyboard**: one button per loaded handle; label `{identifier}  {size}` truncated to 64 chars; callback `models:unloadmodel:{identifier}`.

Both keyboards capped at 100 buttons (FR-012).

---

### Module 4: `src/bot/handlers/menu.py` (MODIFY)

**In `_handle_models_action`**: replace `models:load` / `models:unload` branches (currently set `pending_input` to a text prompt) with SDK-based keyboard senders.

**In `menu_callback_handler`**: add routing for `models:loadmodel:` and `models:unloadmodel:` prefixes before the existing `models:` catch-all.

**New internal handlers**:

- `_handle_load_model_callback(query, context, data)`:
  1. Parse model key from `data.split(":", 2)[2]`
  2. `await query.edit_message_text(f"⏳ Loading {model_key}…")`
  3. `await cli.load_model(model_key)` — success: `✅ Loaded.` / error: `❌ Failed: {e}`

- `_handle_unload_model_callback(query, context, data)`:
  1. Parse identifier from `data.split(":", 2)[2]`
  2. `await query.edit_message_text(f"⏳ Unloading {identifier}…")`
  3. `await cli.unload_model(identifier)` — success: `✅ Unloaded.` / error: `❌ Failed: {e}`

`cli` import retained for load/unload operations. `cli.list_models` / `cli.list_loaded` usages in `_handle_models_action` replaced by SDK.

---

### Module 5: `src/bot/handlers/messages.py` (MODIFY)

After the streaming loop, replace the final `edit_text` call with:

```
formatted = format_response(full_response)
await sent_message.edit_text(formatted, parse_mode="HTML")
```

- Intermediate streaming edits (every 50 tokens) are **removed** — placeholder stays until final edit (spec Q1=B)
- Session history stores **raw** `full_response` (formatting is display-only; LLM context must be unformatted)

---

### Module 6: `src/bot/handlers/vision.py` (MODIFY)

Same change as `messages.py`: apply `format_response()` + `parse_mode="HTML"` to the final assembled response only. Intermediate streaming edits removed.

---

### Testing Strategy

#### `tests/unit/test_formatting.py` (NEW)

| Test | FR |
|------|----|
| Single `<think>` block removed | FR-009 |
| Multiple `<think>` blocks removed | FR-009 |
| No `<think>` — unchanged | FR-009 |
| Unclosed `<think>` — strip to end | Edge case |
| Entire response is think block → `"*(no response)*"` | FR-010 |
| Fenced code no lang tag → `<pre><code>` | FR-007 |
| Fenced code with lang tag — tag excluded | FR-007 |
| Multiple fenced code blocks | FR-007 |
| Inline code → `<code>` | FR-008 |
| `<`, `>`, `&` in plain text escaped | FR-011 |
| `<br>` in code block → `&lt;br&gt;` (escaped) | FR-011 |
| Plain prose unchanged | FR-006 |
| `_format_size` ≥ 1 GiB → `X.X GB` | Model display |
| `_format_size` < 1 GiB → `X MB` | Model display |

#### `tests/unit/test_menu.py` (UPDATE)

- `models:loadmodel:<key>` callback → `edit_message_text` called with `⏳ Loading…` then `✅ Loaded.`
- `models:unloadmodel:<id>` callback → same pattern
- `models:load` callback → no longer sets `pending_input`; sends inline keyboard

#### `tests/integration/test_handlers.py` (UPDATE)

- `load_command` no-args → inline keyboard reply
- `unload_command` no-args → inline keyboard or no-models message
- `models_command` → plain text, no `|` table characters
- `loaded_command` → plain text list or no-models message

---

## Decision Log

| Decision | Rationale |
|----------|-----------|
| SDK-only for model listing | Spec Q4=A; typed objects with `size_bytes`; avoids brittle CLI text parsing |
| Keep CLI for load/unload operations | No SDK load method found; FR-013 requires no regression |
| `asyncio.to_thread` for SDK listing | One-shot (not streaming); simpler than queue bridge pattern |
| Pure function for `format_response` | No I/O = easily unit-tested without mocking |
| Store raw response in session history | LLM must receive unformatted context; formatting is display-only |
| Remove intermediate streaming edits | Spec Q1=B; full formatting requires complete string; placeholder is sufficient UX |
| Callback data `models:loadmodel:<key>` | Fits 64-byte limit for all known model keys; simple `split(":", 2)[2]` parse |

---

## Implementation Design

### Module 1: `src/bot/formatting.py` (NEW)

**Purpose**: Pure string-processing pipeline — no I/O, no Telegram imports, easily unit-tested.

**Public API**:

```python
def format_response(text: str) -> str:
    """Full pipeline: strip think tags → convert code → escape plain text."""

def strip_think_tags(text: str) -> str:
    """Remove all <think>…</think> blocks. Strip whitespace."""

def _format_size(size_bytes: int) -> str:
    """Convert bytes to 'X.X GB' or 'X MB'."""
```

**Pipeline detail**:

1. `strip_think_tags(text)` — `re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()`
2. If blank after strip → return `"*(no response)*"`
3. Process text segment-by-segment using a single regex pass:
   - Fenced code block (`` ```[lang]\n…\n``` ``): HTML-escape code content → `<pre><code>{escaped_code}</code></pre>`
   - Inline code (`` `…` ``): HTML-escape content → `<code>{escaped_code}</code>`
   - Plain text remainder: `html.escape(segment)`
4. Join and return

**Dependencies**: `re`, `html` (stdlib only — no new packages)

---

### Module 2: `src/lms/sdk.py` (EXTEND)

Add two async helper functions after existing helpers:

```python
async def list_downloaded_models(host: str, port: int) -> list:
    """Return list of DownloadedModel objects from the SDK."""
    def _sync():
        with lmstudio.Client(api_host=f"{host}:{port}") as client:
            return list(client.list_downloaded_models())
    return await asyncio.to_thread(_sync)

async def list_loaded_models(host: str, port: int) -> list:
    """Return list of SyncModelHandle objects from the SDK."""
    def _sync():
        with lmstudio.Client(api_host=f"{host}:{port}") as client:
            return list(client.list_loaded_models())
    return await asyncio.to_thread(_sync)
```

**No changes** to existing functions. `asyncio` is already imported.

---

### Module 3: `src/bot/handlers/models.py` (REWRITE)

Replace all four handlers:

#### `models_command` (FR-001)
- Call `await sdk.list_downloaded_models(host, port)` 
- Format: `"📦 Available models:\n" + "\n".join(f"• {m.model_key}  {_format_size(m.info.size_bytes)}" for m in models)` or `"No models found."` if empty
- Send with `parse_mode="HTML"` (plain text, but consistent with other handlers)
- Error → `"❌ Could not connect to LM Studio."`

#### `loaded_command` (FR-014)
- Call `await sdk.list_loaded_models(host, port)`
- For each handle: `info = handle.get_info()`
- Format: `"🧠 Loaded models:\n" + "\n".join(f"• {info.identifier}  {_format_size(info.size_bytes)}")` or `"No models are currently loaded."`
- Send with `parse_mode="HTML"`

#### `load_command` (FR-002 / FR-013)
- **With args** → unchanged CLI path (FR-013)
- **No args** → delegate to `_send_load_keyboard(update, context)`

```python
async def _send_load_keyboard(update, context):
    config = context.bot_data["config"]
    downloaded, loaded_handles = await asyncio.gather(
        sdk.list_downloaded_models(config.LMS_HOST, config.LMS_PORT),
        sdk.list_loaded_models(config.LMS_HOST, config.LMS_PORT),
    )
    if not downloaded:
        await update.effective_message.reply_text("No models available to load.")
        return
    loaded_keys = {h.get_info().model_key for h in loaded_handles}
    keyboard = _build_load_keyboard(downloaded, loaded_keys)
    await update.effective_message.reply_text("Select a model to load:", reply_markup=keyboard)
```

#### `unload_command` (FR-003 / FR-013)
- **With args** → unchanged CLI path (FR-013)
- **No args** → delegate to `_send_unload_keyboard(update, context)`

#### Keyboard builders (in `models.py`)

```python
def _build_load_keyboard(models, loaded_keys: set) -> InlineKeyboardMarkup:
    rows = []
    for m in models[:100]:  # FR-012: max 100 buttons
        prefix = "🟢 " if m.model_key in loaded_keys else ""
        label = f"{prefix}{m.model_key}  {_format_size(m.info.size_bytes)}"
        label = label[:64]  # FR-012: max 64 chars
        cb = f"models:loadmodel:{m.model_key}"[:64]
        rows.append([InlineKeyboardButton(label, callback_data=cb)])
    return InlineKeyboardMarkup(rows)

def _build_unload_keyboard(handles) -> InlineKeyboardMarkup:
    rows = []
    for h in handles[:100]:
        info = h.get_info()
        label = f"{info.identifier}  {_format_size(info.size_bytes)}"[:64]
        cb = f"models:unloadmodel:{info.identifier}"[:64]
        rows.append([InlineKeyboardButton(label, callback_data=cb)])
    return InlineKeyboardMarkup(rows)
```

---

### Module 4: `src/bot/handlers/menu.py` (MODIFY)

#### Changes to `_handle_models_action`

Replace the `models:load` and `models:unload` branches (currently set `pending_input`):

```python
if data == "models:load":
    await _send_load_keyboard_from_menu(query, context)
    return

if data == "models:unload":
    await _send_unload_keyboard_from_menu(query, context)
    return
```

Add routing for new callback prefixes in `menu_callback_handler`:

```python
if data.startswith("models:loadmodel:"):
    await _handle_load_model_callback(query, context, data)
    return

if data.startswith("models:unloadmodel:"):
    await _handle_unload_model_callback(query, context, data)
    return
```

#### New handlers

```python
async def _handle_load_model_callback(query, context, data):
    model_key = data.split(":", 2)[2]
    await query.edit_message_text(f"⏳ Loading {model_key}…")
    config = context.bot_data["config"]
    try:
        await cli.load_model(model_key)
        await query.edit_message_text(f"✅ Loaded {model_key}.")
    except LmsCliError as e:
        await query.edit_message_text(f"❌ Failed to load {model_key}: {e}")

async def _handle_unload_model_callback(query, context, data):
    identifier = data.split(":", 2)[2]
    await query.edit_message_text(f"⏳ Unloading {identifier}…")
    try:
        await cli.unload_model(identifier)
        await query.edit_message_text(f"✅ Unloaded {identifier}.")
    except LmsCliError as e:
        await query.edit_message_text(f"❌ Failed to unload {identifier}: {e}")
```

Remove `cli` import for `list_models`/`list_loaded` (replaced by SDK), but keep for `load_model`/`unload_model`.

---

### Module 5: `src/bot/handlers/messages.py` (MODIFY)

After streaming completes, replace the final `edit_text` call:

```python
from src.bot.formatting import format_response

# ...existing streaming loop unchanged...

if full_response:
    formatted = format_response(full_response)
    try:
        await sent_message.edit_text(formatted, parse_mode="HTML")
    except Exception:
        pass
    session.history.append(ChatMessage(role="assistant", content=full_response))  # store raw
    store.update_session(session)
else:
    await sent_message.edit_text("❌ No response from model.")
```

Note: store raw `full_response` in history (not formatted), so history context to LLM is unmodified.

The intermediate streaming edits (every 50 tokens) are removed — the placeholder `⏳ Thinking...` stays until the final formatted edit (spec Q1=B).

---

### Module 6: `src/bot/handlers/vision.py` (MODIFY)

Same change as `messages.py`: apply `format_response()` and `parse_mode="HTML"` to the final assembled response only.

---

### Testing Strategy

#### `tests/unit/test_formatting.py` (NEW)

Cover every formatting rule from the spec:

| Test | Covers |
|------|--------|
| `test_strip_think_single` | Single `<think>` block removed |
| `test_strip_think_multiple` | Multiple blocks removed |
| `test_strip_think_none` | No `<think>` — text unchanged |
| `test_strip_think_unclosed` | Unclosed tag — strip to end |
| `test_empty_after_strip` | Returns `"*(no response)*"` |
| `test_fenced_code_no_lang` | ` ```\ncode\n``` ` → `<pre><code>` |
| `test_fenced_code_with_lang` | ` ```python\ncode\n``` ` — lang tag excluded |
| `test_fenced_multiple_blocks` | Multiple code blocks |
| `test_inline_code` | `` `word` `` → `<code>word</code>` |
| `test_html_escape_plain` | `<`, `>`, `&` in plain text escaped |
| `test_html_escape_not_in_code` | `<br>` inside code block escaped to `&lt;br&gt;` |
| `test_plain_prose_unchanged` | No special chars — text unchanged |
| `test_format_size_gb` | size_bytes ≥ 1 GiB → `X.X GB` |
| `test_format_size_mb` | size_bytes < 1 GiB → `X MB` |

#### `tests/unit/test_menu.py` (UPDATE)

Add tests for:
- `models:loadmodel:<key>` callback → edit_message_text called with `⏳ Loading…` then `✅ Loaded.`
- `models:unloadmodel:<id>` callback → same pattern
- `models:load` callback → no longer sets `pending_input`; sends inline keyboard message

#### `tests/integration/test_handlers.py` (UPDATE)

Add tests for:
- `load_command` with no args → inline keyboard sent
- `unload_command` with no args → inline keyboard sent OR no-models message
- `models_command` → plain text list, no table characters
- `loaded_command` → plain text list

---

## Decision Log

| Decision | Rationale |
|----------|-----------|
| SDK-only for model listing | Q4=A; avoids brittle CLI text parsing; SDK already in use |
| Keep CLI for load/unload operations | No SDK method found for loading; FR-013 requires no regression |
| `asyncio.to_thread` for SDK calls | Simpler than queue bridge; one-shot (not streaming) |
| `format_response` is pure string function | No I/O = easily unit-tested; no Telegram dependency |
| Store raw response in session history | LLM should see unformatted context; formatting is display-only |
| Intermediate streaming edits removed | Q1=B; full formatting requires complete string; placeholder sufficient |
| Callback data: `models:loadmodel:<key>` | Fits 64-byte limit for typical model keys; simple to parse |
