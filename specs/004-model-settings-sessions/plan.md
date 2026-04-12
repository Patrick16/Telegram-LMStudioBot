# Implementation Plan: Session-Aware Model Controls

**Branch**: `004-model-settings-sessions` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/004-model-settings-sessions/spec.md`

## Summary

Reshape LMStudioBot around three coordinated changes: remove the Inference menu section and promote regenerate to the main menu; expand settings into a split-scope system where model runtime settings stay with the loaded model and prompt/generation settings stay with the active chat session; move chat history to per-session files on disk with adjustable reuse policies. The implementation keeps the current single-project Python Telegram bot structure, extends the existing `ChatSession`/`LoadConfig` models, introduces preset files for both scopes, and adds a shared ephemeral command-response helper so command results auto-delete after five seconds without touching chat replies or the persistent menu message.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: `python-telegram-bot>=21.0`, `lmstudio>=1.5.0`, `pydantic>=2.0`, `pydantic-settings>=2.0`, `python-dotenv`  
**Storage**: Local JSON files on disk: existing `data/sessions.json` plus new preset files and per-session history files  
**Testing**: `pytest`, `pytest-asyncio`, `unittest.mock`, `flake8`, `ruff`  
**Target Platform**: Local Windows/Linux machine running Telegram bot and LM Studio on the same host  
**Project Type**: Single-process Telegram bot application  
**Performance Goals**: Command/menu feedback remains immediate; command-result cleanup occurs after 5 seconds; history assembly stays bounded by the configured reuse policy and active context budget  
**Constraints**: Single owner only; no cloud services; menu must remain navigable while temporary command messages disappear; Telegram callback/menu limits still apply; preset management in-menu is browse/apply only  
**Scale/Scope**: One user, one machine, modest number of sessions/presets/history files; no concurrency-heavy workload

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Gate Evaluation (pre-design)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Security & Privacy First | ✅ PASS | No new secrets. On-disk JSON files contain local chat/session data only; plan avoids logging raw message contents or preset bodies. |
| II. Telegram API Discipline | ✅ PASS | Uses existing `python-telegram-bot` flow, callback handlers, and message deletion APIs. Temporary command cleanup is implemented with supported bot delete operations only. |
| III. Robust Error Handling & Validation | ✅ PASS | All new setting inputs, preset loading, history-file reads, and message deletion paths are explicitly validated and must fail with user-safe messages or silent cleanup fallback. |
| IV. Test Coverage & Automation | ✅ PASS | Feature requires unit coverage for schema validation/history selection and integration coverage for menu/settings/session flows. |
| V. Logging & Observability | ✅ PASS | Existing structured logging remains sufficient; new logs should capture failures to load presets/history or delete command messages without including message content. |

### Gate Evaluation (post-design)

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Security & Privacy First | ✅ PASS | Design keeps preset/history storage local and avoids introducing networked persistence; command auto-delete reduces chat clutter without weakening access control. |
| II. Telegram API Discipline | ✅ PASS | Menu navigation remains message-edit based; ephemeral command cleanup excludes the persistent menu message and normal assistant replies. |
| III. Robust Error Handling & Validation | ✅ PASS | Deterministic history trimming, schema-backed preset loading, and safe delete failures are built into the design. |
| IV. Test Coverage & Automation | ✅ PASS | Plan includes new unit, integration, and contract-style schema tests for storage and menu callback flows. |
| V. Logging & Observability | ✅ PASS | Failure branches for missing history files, invalid presets, and delete failures are all loggable without leaking prompt or response bodies. |

**Verdict**: No constitution violations. No Complexity Tracking entries required.

## Project Structure

### Documentation (this feature)

```text
specs/004-model-settings-sessions/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── menu-contract.md
│   └── storage-schemas.md
└── tasks.md
```

### Source Code (repository root)

```text
src/
├── bot/
│   ├── config.py
│   ├── main.py
│   └── handlers/
│       ├── chats.py
│       ├── help.py
│       ├── menu.py
│       ├── messages.py
│       ├── models.py
│       ├── settings.py
│       └── vision.py
├── lms/
│   ├── cli.py
│   └── sdk.py
└── storage/
    ├── models.py
    └── session_store.py

tests/
├── integration/
│   └── test_handlers.py
└── unit/
    ├── test_menu.py
    ├── test_session_store.py
    ├── test_settings.py
    └── test_sdk.py

data/
├── sessions.json
├── histories/
├── model-presets.json
└── session-presets.json
```

**Structure Decision**: Keep the existing single-project layout. Extend current bot, storage, and LM Studio integration modules rather than introducing a new service layer.

## Implementation Design

### Design Overview

1. Split persistent state into three concerns:
   - session metadata in `sessions.json`
   - per-session message history files in `data/histories/`
   - scope-specific preset files for model and session settings
2. Expand settings handling so model-scoped runtime controls and session-scoped generation controls are edited through separate menu paths but displayed together in a current-settings view.
3. Keep history reuse policy session-scoped and enforce it before building the LM Studio chat payload.
4. Add a shared command-response deletion helper used by command/menu flows only; inference/chat responses remain durable.

### Planned Module Changes

| Module | Change |
|--------|--------|
| `src/storage/models.py` | Extend settings models for split scopes, preset types, and history reuse policy metadata. |
| `src/storage/session_store.py` | Separate session metadata persistence from per-session history file persistence and cleanup. |
| `src/lms/sdk.py` | Build chat payload from trimmed history based on session policy; extend config mapping for additional supported generation knobs. |
| `src/lms/cli.py` | Accept richer model runtime load config (context length, GPU, identifier) from selected model preset/runtime settings. |
| `src/bot/handlers/menu.py` | Remove inference section, promote regenerate to main menu, add expanded settings/preset/current-settings flows. |
| `src/bot/handlers/settings.py` | Keep command parity for direct text commands or delegate to shared validation/update helpers. |
| `src/bot/handlers/messages.py` | Use session-file-backed history instead of inline session history and preserve durable chat replies. |
| `src/bot/handlers/chats.py` | Delete history file when removing a session and surface active-session changes correctly. |
| `src/bot/handlers/models.py` | Integrate current model runtime settings display and preset-backed load flows. |
| `src/bot/main.py` | Register any new helpers/config paths and preserve existing command routing. |

### Testing Strategy

- Unit-test schema validation for new setting fields, history policy modes, and preset file parsing.
- Unit-test session store behavior for metadata/history split, history trimming selection, and delete cleanup.
- Integration-test menu navigation after removing Inference and promoting regenerate.
- Integration-test command-result auto-delete scheduling separately from durable chat replies.
- Regression-test direct commands (`/set`, `/setprompt`, `/load`, `/unload`, `/regenerate`) so text-command parity is preserved.

## Complexity Tracking

No constitution violations. No complexity justification required.
