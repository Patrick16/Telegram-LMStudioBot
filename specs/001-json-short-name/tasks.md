# Tasks: Telegram-LMStudio Integration Bot

**Input**: Design documents from `/specs/001-json-short-name/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/bot-commands.md ✅

**Tests**: Included — explicitly required by Functional Requirement #7.

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US7)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project skeleton, dependency declarations, runtime configuration files.

- [x] T001 Create project directory structure: `src/bot/handlers/`, `src/lms/`, `src/storage/`, `tests/unit/`, `tests/integration/`, `data/` plus all `__init__.py` files
- [x] T002 Create `requirements.txt` with pinned production dependencies: `python-telegram-bot>=21.0`, `lmstudio>=1.5.0`, `pydantic>=2.0`, `pydantic-settings>=2.0`, `python-dotenv>=1.0`
- [x] T003 [P] Create `requirements-dev.txt` with dev dependencies: `pytest`, `pytest-asyncio`, `black`, `flake8`
- [x] T004 [P] Create `.env.example` with all required variables: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_ID`, `LMS_HOST`, `LMS_PORT`, `SESSIONS_FILE`, `LOG_LEVEL`
- [x] T005 [P] Create `.gitignore` excluding `data/`, `.env`, `__pycache__/`, `*.pyc`, `.pytest_cache/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core building blocks that every user story handler depends on. Must be complete before any Phase 3+ task begins.

- [x] T006 Implement `BotConfig` using `pydantic-settings` to load and validate all environment variables in `src/bot/config.py`
- [x] T007 Implement `require_owner` async decorator that checks `update.effective_user.id == config.TELEGRAM_OWNER_ID` and silently drops unauthorized updates in `src/bot/auth.py`
- [x] T008 Implement Pydantic models: `ChatMessage`, `ModelSettings`, `LoadConfig`, `ChatSession`, `SessionStore` with all validation rules from data-model.md in `src/storage/models.py`
- [x] T009 Implement `SessionStore` CRUD class: load from / save to `sessions.json`, create session, get active session, list sessions, switch active session in `src/storage/session_store.py`
- [x] T010 Implement async LMS CLI subprocess wrapper with `list_models()`, `list_loaded()`, `load_model(model, config)`, `unload_model(identifier)` raising `LmsCliError` on failure in `src/lms/cli.py`
- [x] T011 Implement `lmstudio` Python SDK wrapper with `chat_stream(session)`, `get_model_info(identifier)`, `infer_with_image(session, image_path)` in `src/lms/sdk.py`
- [x] T012 [P] Write unit tests for `require_owner` decorator covering authorized and unauthorized user IDs in `tests/unit/test_auth.py`
- [x] T013 [P] Write unit tests for `SessionStore` CRUD (create, list, switch, delete) using tmp files in `tests/unit/test_session_store.py`
- [x] T014 [P] Write unit tests for LMS CLI wrapper mocking `asyncio.create_subprocess_exec` for all four operations in `tests/unit/test_cli.py`
- [x] T015 [P] Write unit tests for LMS SDK wrapper mocking `lmstudio.Client` for chat, image input, and model info in `tests/unit/test_sdk.py`

---

## Phase 3: User Story 1 — List Available Models (P1)

**Story goal**: User sends `/models` or `/loaded` and receives a formatted list from LM Studio.

**Independent test**: Start bot → send `/models` → verify list is returned; send `/loaded` → verify loaded models are shown; disconnect LM Studio → verify error message.

- [x] T016 [US1] Implement `/models` handler (calls `cli.list_models()`, formats response) and `/loaded` handler (calls `cli.list_loaded()`) in `src/bot/handlers/models.py`
- [x] T017 [P] [US1] Write integration tests for `/models` and `/loaded` with mocked CLI returning models and simulating LM Studio unreachable in `tests/integration/test_handlers.py`

---

## Phase 4: User Story 2 — Load/Unload Model (P2)

**Story goal**: User sends `/load <model> [options]` or `/unload <model>` to manage LM Studio model memory.

**Independent test**: Send `/load qwen/qwen3-4b gpu=max ctx=4096` → verify success confirmation; send `/unload qwen/qwen3-4b` → verify unload confirmation; send `/load nonexistent` → verify error.

- [x] T018 [US2] Implement `/load` command handler: parse `model`, `gpu=`, `ctx=`, `id=` arguments into `LoadConfig`, validate, call `cli.load_model()`, reply with confirmation in `src/bot/handlers/models.py`
- [x] T019 [US2] Implement `/unload` command handler: parse model/identifier argument, call `cli.unload_model()`, reply with confirmation in `src/bot/handlers/models.py`
- [x] T020 [P] [US2] Write integration tests for `/load` (valid args, invalid gpu value, model not found) and `/unload` (loaded model, not-loaded model) in `tests/integration/test_handlers.py`

---

## Phase 5: User Story 3 — Adjust Prompts & Model Settings (P3)

**Story goal**: User sends `/setprompt` or `/set <setting> <value>` to configure the active session.

**Independent test**: Create chat → send `/setprompt You are a Python expert.` → verify confirmation and persisted value; send `/set temperature 0.5` → verify stored; send `/set invalid 0.5` → verify validation error.

- [x] T021 [US3] Implement `/setprompt` handler: extract prompt text (or clear if empty), update `active_session.system_prompt`, save store, confirm in `src/bot/handlers/settings.py`
- [x] T022 [P] [US3] Implement `/set` handler: parse `<setting> <value>`, validate against `ModelSettings` field ranges, update `active_session.settings`, save store, confirm in `src/bot/handlers/settings.py`
- [x] T023 [P] [US3] Write integration tests for `/setprompt` (set, clear, no active chat) and `/set` (valid temperature, invalid value, unknown setting, no active chat) in `tests/integration/test_handlers.py`

---

## Phase 6: User Story 4 — Separate Chats with Model (P4)

**Story goal**: User can create, list, and switch between isolated chat sessions.

**Independent test**: Send `/newchat Alpha` → verify created and active; send `/newchat Beta` → send distinct messages → `/switchchat 1` → verify context is Alpha's; `/chats` → verify both listed.

- [x] T024 [US4] Implement `/newchat [name]` handler: create `ChatSession` with UUID, default settings, set as active, save store, confirm in `src/bot/handlers/chats.py`
- [x] T025 [P] [US4] Implement `/chats` handler: list all sessions with index, name, message count, mark active with `▶` in `src/bot/handlers/chats.py`
- [x] T026 [P] [US4] Implement `/switchchat <id_or_number>` handler: resolve by UUID prefix or list index, set `active_session_id`, save store, confirm in `src/bot/handlers/chats.py`
- [x] T027 [P] [US4] Write integration tests for `/newchat`, `/chats`, `/switchchat` (valid and invalid IDs, context isolation) in `tests/integration/test_handlers.py`

---

## Phase 7: User Story 5 — Vision Input (P5)

**Story goal**: User sends a photo; bot forwards it to vision-capable model and streams the response.

**Independent test**: Load vision model → send photo with caption → verify model response returned; load non-vision model → send photo → verify error message.

- [x] T028 [US5] Implement photo message handler: download highest-res Telegram photo to tmp file, call `sdk.get_model_info()` to verify vision support, call `sdk.infer_with_image()`, stream reply, append to session history in `src/bot/handlers/vision.py`
- [x] T029 [P] [US5] Write integration tests for photo handler: vision model loaded (success path), non-vision model (capability error), no active chat, no model loaded in `tests/integration/test_handlers.py`

---

## Phase 8: User Story 6 — Remove Chat (P6)

**Story goal**: User sends `/removechat <id>` to delete a session and its history.

**Independent test**: Create two chats → `/removechat 1` → verify chat absent from `/chats` list → verify auto-switch to remaining chat.

- [x] T030 [US6] Implement `/removechat <id_or_number>` handler: resolve session, delete from store, auto-select next available session (or clear active), save store, confirm in `src/bot/handlers/chats.py`
- [x] T031 [P] [US6] Write integration tests for `/removechat`: existing chat (auto-switch), last remaining chat (active cleared), not-found ID in `tests/integration/test_handlers.py`

---

## Phase 9: User Story 7 — Regenerate Model Answer (P7)

**Story goal**: User sends a plain text message to chat with the model; `/regenerate` re-submits the last user message for a new response.

**Independent test**: Load model → create chat → send message → verify streamed response → send `/regenerate` → verify new streamed response replaces last assistant message.

- [x] T032 [US7] Implement plain text `MessageHandler`: validate active session and loaded model, build `Chat` with history + system prompt, call `sdk.chat_stream()`, progressively edit Telegram message, append both turns to session history in `src/bot/handlers/messages.py`
- [x] T033 [US7] Implement `/regenerate` handler: verify history has a prior user message, remove last assistant message, re-run inference (same as text handler), replace in history in `src/bot/handlers/messages.py`
- [x] T034 [P] [US7] Write integration tests for text handler (happy path, no active chat, no model loaded) and `/regenerate` (with history, empty history) in `tests/integration/test_handlers.py`

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Entry point wiring, help command, error handling, linting, test infrastructure.

- [x] T035 Implement `/start` and `/help` handlers returning a formatted overview of all commands in `src/bot/handlers/help.py`
- [x] T036 Implement global PTB error handler, configure structured `logging` (timestamp, level, module), wire all handlers to `Application`, add entry point startup logic (load `SessionStore`, start server) in `src/bot/main.py`
- [x] T037 [P] Create `tests/conftest.py` with shared async pytest fixtures: mock `BotConfig`, mock `SessionStore`, mock LMS CLI and SDK
- [x] T038 [P] Create `pytest.ini` with `asyncio_mode = auto` and test path configuration
- [x] T039 [P] Configure `black` and `flake8` in `setup.cfg` (line length 100, per-file ignores for `__init__.py`)
- [x] T040 [P] Create `.github/workflows/ci.yml` GitHub Actions workflow: runs `flake8 src/ tests/` and `pytest` on every push and pull request to satisfy constitution principle IV

---

## Dependencies (User Story Completion Order)

```
Phase 1 (Setup)
  └── Phase 2 (Foundational: config, auth, models, store, CLI, SDK wrappers)
        ├── Phase 3 (US1: List Models)          ← can start after Phase 2
        ├── Phase 4 (US2: Load/Unload)           ← can start after Phase 2
        ├── Phase 5 (US3: Settings)              ← requires Phase 6 (US4) for active session
        ├── Phase 6 (US4: Separate Chats)        ← can start after Phase 2
        ├── Phase 7 (US5: Vision)                ← can start after Phase 2
        ├── Phase 8 (US6: Remove Chat)           ← can start after Phase 6 (US4)
        └── Phase 9 (US7: Regenerate)            ← can start after Phase 2
              └── Phase 10 (Polish: wiring all phases together)
```

**Notes**:
- US3 (settings) logically requires US4 (chat sessions) to exist — implement US4 first in practice
- US6 (remove chat) and US7 (regenerate) require the session management from US4 to be complete
- US1 and US2 are independent of sessions and can be implemented before or after US4

---

## Parallel Execution Examples

### Sprint A — Foundation + MVP (US1 + US2)
```
┌─ T001-T005 (Setup, sequential) ──────────────────────────────────────┐
└─ T006-T011 (Foundational impl, sequential) ──────────────────────────┤
   ┌─ T012 (test_auth.py) ─────────────────────┐                        │
   ├─ T013 (test_session_store.py) ────────────┤ parallel               │
   ├─ T014 (test_cli.py) ──────────────────────┤                        │
   └─ T015 (test_sdk.py) ──────────────────────┘                        │
      └─ T016 (US1 handlers) ─ T017 (US1 tests) ───────────────────────┤
         ┌─ T018 (US2 /load)                                             │
         └─ T019 (US2 /unload) ─ T020 (US2 tests) ────────────────────┘
```

### Sprint B — Chat Management (US3, US4, US6)
```
T024 (/newchat) → T025 [P] (/chats) + T026 [P] (/switchchat) → T027 (tests)
  └─ T030 (/removechat) → T031 (tests)
  └─ T021 (/setprompt) + T022 [P] (/set) → T023 (tests)
```

### Sprint C — Inference + Vision (US5, US7)
```
T032 (text handler) → T033 (/regenerate) → T034 (tests)
T028 (vision handler) ─────────────────── T029 (tests)   ← parallel with US7
```

---

## Implementation Strategy

**Suggested MVP** (US1 only — T001–T017): Delivers a working bot that can list LM Studio models. Fully testable, demonstrable, and provides the foundation for all other stories.

**Delivery increments**:
1. **T001–T017** — MVP: list models (US1)
2. **T018–T020** — Load/unload model management (US2)
3. **T021–T031** — Chat sessions with prompts, settings, and removal (US3, US4, US6)
4. **T032–T034** — Full inference + regenerate (US7)
5. **T028–T029** — Vision input (US5)
6. **T035–T039** — Polish and wiring

---

## Summary

| Metric | Count |
|--------|-------|
| Total tasks | 40 |
| Setup tasks | 5 |
| Foundational tasks | 10 |
| US1 tasks | 2 |
| US2 tasks | 3 |
| US3 tasks | 3 |
| US4 tasks | 4 |
| US5 tasks | 2 |
| US6 tasks | 2 |
| US7 tasks | 3 |
| Polish tasks | 6 |
| Parallelizable tasks [P] | 24 |
