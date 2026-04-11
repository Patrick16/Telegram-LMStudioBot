# Research: Telegram-LMStudio Integration Bot

**Feature**: 001-json-short-name  
**Date**: 2026-04-11  
**Status**: Complete — all NEEDS CLARIFICATION resolved

---

## 1. LM Studio Integration Approach

### Decision
Use the **`lmstudio` Python SDK** (`pip install lmstudio`) as the primary integration layer for inference (chat, image input, configuration parameters). Use the **`lms` CLI** (invoked via subprocess) for model management operations (list on disk, load, unload) where the CLI provides the most ergonomic interface.

### Rationale
- `lmstudio` Python SDK offers clean Python APIs for chat completion, streaming, image input, load/unload, and listing models.
- `lms` CLI is always available if LM Studio is installed, provides `lms ls`, `lms ps`, `lms load`, `lms unload`, `lms server start/stop`, and `lms daemon up/down`.
- `llmster` is the LM Studio headless daemon, started via `lms daemon up`. This must be running for the SDK/server to function without the GUI.
- The REST API (OpenAI-compatible, `http://localhost:1234`) is available as a fallback and can be used for cases where the Python SDK is insufficient.

### Alternatives Considered
- **REST API only (OpenAI-compatible)**: Viable but requires manual HTTP client and lacks direct Python SDK ergonomics.
- **TypeScript SDK**: Not applicable (project is Python-only).

---

## 2. Telegram Bot Framework

### Decision
Use **`python-telegram-bot` v21+** (async, PTB v21 uses `asyncio`) as the Telegram bot framework.

### Rationale
- Official, well-maintained Python library for Telegram Bot API.
- Native async support aligns with `lmstudio` Python SDK async API.
- Broad community, excellent documentation, inline keyboard and file handling built-in.
- Supports all needed features: command handlers, photo handlers, error handlers, conversation handlers.

### Alternatives Considered
- **aiogram v3**: Also excellent, similarly async-first. Rejected in favour of `python-telegram-bot` for wider adoption and documentation quality.
- **Telethon**: MTProto-based; overkill for a bot; not appropriate for Bot API use-cases.

---

## 3. Chat Session Persistence

### Decision
Store chat sessions and their histories as **JSON files** on the local filesystem (one file per user—since there is only one authorized user, a single sessions file is sufficient).

### Rationale
- No external database dependency; keeps deployment simple for a single-user bot running on a local machine.
- JSON is human-readable and easy to debug.
- Sufficient for single-user scale: no concurrency concerns beyond asyncio.

### Alternatives Considered
- **SQLite**: More robust but adds dependency and schema migration complexity not justified for single user.
- **In-memory only**: No persistence across bot restarts; unacceptable for chat histories.

---

## 4. Model Load Configuration Parameters

### Decision
Expose the following `lms load` options as optional command settings:
- `--context-length=N` (integer, max context window tokens)
- `--gpu=max|auto|0.0-1.0` (GPU offload ratio)
- `--identifier=<name>` (optional stable identifier for the loaded model)

Beyond load parameters, the following inference parameters are configured per chat session via the `lmstudio` Python SDK's `PredictionConfig`:
- `temperature` (float, 0.0–2.0)
- `max_tokens` (integer)
- `top_p` (float, 0.0–1.0)
- `stop` (list of stop strings)

### Rationale
These are the documented parameters exposed by both the CLI and the Python SDK. Exposing them via bot commands allows the user to tune model behaviour without touching LM Studio GUI.

---

## 5. System Prompt Handling

### Decision
System prompts are stored **per chat session** in the session JSON store and injected as the first message with `role=system` in every inference call constructed via `lmstudio`'s `Chat` object.

### Rationale
- The `lmstudio` Python SDK's `Chat` class supports constructing a history with system messages.
- Per-chat system prompts enable different personas or task contexts across sessions.

---

## 6. Vision (Image Input)

### Decision
Use the `lmstudio` Python SDK's `ImageHandle` for image input. Download the Telegram photo file, pass it as `lms.prepare_image(path)` to the `model.respond()` call.

### Rationale
- `lmstudio-python` has explicit `Image Input` documentation (`https://lmstudio.ai/docs/python/llm-prediction/image-input`).
- The bot downloads the highest-resolution Telegram photo, saves it to a temp file, and passes it as an image argument.
- Vision model detection: verify the currently loaded model supports vision by checking model info; if not, return a user-friendly error.

---

## 7. Single-User Authorization

### Decision
Authorization is enforced via a middleware/decorator that checks `update.effective_user.id` against the `TELEGRAM_OWNER_ID` environment variable. Any unauthorized user receives: *"Access denied."*

### Rationale
- Simplest implementation aligned with the constitution's security principle and the clarified requirement.
- No sensitive data (user IDs from other users) is logged.

---

## 8. Configuration Management

### Decision
All secrets and configuration are loaded from **environment variables** via a `.env` file (loaded with `python-dotenv`). Never hardcoded.

| Variable | Purpose |
|----------|---------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `TELEGRAM_OWNER_ID` | Authorized Telegram user ID (integer) |
| `LMS_HOST` | LM Studio server host (default: `localhost`) |
| `LMS_PORT` | LM Studio server port (default: `1234`) |
| `SESSIONS_FILE` | Path to JSON sessions file (default: `data/sessions.json`) |
| `LOG_LEVEL` | Logging level (default: `INFO`) |

---

## 9. Logging Strategy

### Decision
Use Python's `logging` module with structured formatting (timestamp, level, module, message). No sensitive data (tokens, user IDs, message content) in logs beyond DEBUG level (disabled in production).

### Rationale
- Aligns with the constitution's Logging & Observability principle.
- `python-telegram-bot` already integrates with the standard logging module.

---

## All NEEDS CLARIFICATION Items Resolved

All unknowns from the Technical Context are now resolved. No further research is required before Phase 1 design.
