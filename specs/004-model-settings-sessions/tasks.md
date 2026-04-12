# Tasks: Session-Aware Model Controls

**Input**: Design documents from `specs/004-model-settings-sessions/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: Automated tests are included because the project constitution requires test coverage for core logic and user-facing flows.

---

## Phase 1: Setup

**Purpose**: Add runtime configuration for the new preset and history storage layout before shared implementation begins.

- [X] T001 Add preset/history path settings in `src/bot/config.py` and initialize the new storage paths in `src/bot/main.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish the split storage model, preset loading, and LM Studio config plumbing that all user stories build on.

**⚠️ CRITICAL**: No user story work should begin until this phase is complete.

- [X] T002 [P] Extend split-scope storage schemas in `src/storage/models.py` for `ModelRuntimeSettings`, `SessionGenerationSettings`, `HistoryReusePolicy`, `ModelPreset`, `SessionPreset`, and `SessionHistoryFile`
- [X] T003 [P] Refactor `src/storage/session_store.py` to persist session metadata separately from per-session history files and load model/session presets from disk
- [X] T004 [P] Extend `src/lms/sdk.py` to map expanded generation settings (`top_k`, `repeat_penalty`, `stop_strings`, `seed`) and expose reusable history-trimming helpers
- [X] T005 [P] Add foundational storage and SDK coverage in `tests/unit/test_session_store.py` and `tests/unit/test_sdk.py`

**Checkpoint**: Split storage, preset loading, and reusable LM Studio config/history helpers are ready.

---

## Phase 3: User Story 1 - Manage Model Settings From One Place (Priority: P1) 🎯 MVP

**Goal**: Users can inspect current settings, adjust model/session settings through the menu, and apply existing presets from disk.

**Independent Test**: Open the menu, navigate to settings, change several settings manually, apply a model preset and a session preset, and verify the current settings view reflects the active values after each change.

### Tests for User Story 1

- [X] T006 [P] [US1] Add unit tests for current settings rendering, split-scope setting validation, and invalid preset rejection in `tests/unit/test_menu.py` and `tests/unit/test_settings.py`
- [X] T007 [P] [US1] Add integration tests for current settings, preset browsing, and preset application flows in `tests/integration/test_handlers.py`

### Implementation for User Story 1

- [X] T008 [US1] Expand direct settings command support in `src/bot/handlers/settings.py` for session-scoped settings (`temperature`, `max_tokens`, `top_p`, `top_k`, `repeat_penalty`, `stop_strings`, `seed`) with validation and parity messages
- [X] T009 [US1] Replace the simple settings submenu in `src/bot/handlers/menu.py` with scoped entries for `Current Settings`, `Model Settings`, `Session Settings`, `Model Presets`, and `Session Presets`
- [X] T010 [US1] Implement combined current-settings rendering and no-model-loaded guard handling in `src/bot/handlers/menu.py` and `src/bot/handlers/models.py`
- [X] T011 [US1] Implement model-scoped runtime setting updates and model preset browse/apply flows in `src/bot/handlers/menu.py` and `src/lms/cli.py` using `data/model-presets.json`
- [X] T012 [US1] Implement session-scoped setting updates and session preset browse/apply flows in `src/bot/handlers/menu.py` using `data/session-presets.json`

**Checkpoint**: Settings are fully usable from the menu and current values can be inspected in one view.

---

## Phase 4: User Story 2 - Resume Conversation By Session (Priority: P1)

**Goal**: Chat histories are stored per session on disk, restored on session switch, trimmed by policy, and removed when a session is deleted.

**Independent Test**: Create two sessions, send different prompts in each, switch between them, and verify the next reply in each session uses only that session's saved history. Delete one session and verify its history file is gone.

### Tests for User Story 2

- [X] T013 [P] [US2] Add unit tests for history file CRUD, history policy selection, and context-budget fallback in `tests/unit/test_session_store.py` and `tests/unit/test_sdk.py`
- [X] T014 [P] [US2] Add integration tests for session switching isolation, history reuse modes, and delete cleanup in `tests/integration/test_handlers.py`

### Implementation for User Story 2

- [X] T015 [US2] Update `src/bot/handlers/messages.py` and `src/bot/handlers/vision.py` to append/read chat history through `SessionStoreManager` history-file methods instead of inline `session.history`
- [X] T016 [US2] Update `src/bot/handlers/menu.py` regenerate/send flows and `src/bot/handlers/chats.py` switch/remove flows to use per-session history files and delete history files on session removal
- [X] T017 [US2] Implement history reuse policy menu flows and pending-input handling in `src/bot/handlers/menu.py` for `off`, `fit-budget recent`, `last N message pairs`, and `full if possible`
- [X] T018 [US2] Wire trimmed-history assembly into `src/lms/sdk.py` chat builders so text, regenerate, and vision inference use only the active session's selected history context

**Checkpoint**: Session switching, regenerate, and inference all use durable per-session context correctly.

---

## Phase 5: User Story 3 - Simplify Top-Level Navigation (Priority: P2)

**Goal**: The Inference section is removed, Regenerate is promoted to the main menu, and direct chat inference remains unchanged.

**Independent Test**: Open the main menu and verify there is no Inference section. Verify a top-level Regenerate action is present and works without entering any submenu.

### Tests for User Story 3

- [X] T019 [P] [US3] Add unit and integration coverage for the new main-menu layout and top-level regenerate action in `tests/unit/test_menu.py` and `tests/integration/test_handlers.py`

### Implementation for User Story 3

- [X] T020 [US3] Remove the Inference section from main/help menu builders and help copy in `src/bot/handlers/menu.py` and `src/bot/handlers/help.py`
- [X] T021 [US3] Add top-level `Regenerate` button routing and handler reuse in `src/bot/handlers/menu.py` while preserving direct plain-text inference in `src/bot/handlers/messages.py`
- [X] T022 [US3] Update `/start` and `/menu` menu text/layout handling in `src/bot/handlers/help.py` and `src/bot/handlers/menu.py` so navigation still works without an inference submenu

**Checkpoint**: The menu is flatter, regenerate is easier to reach, and direct chat input still works.

---

## Phase 6: User Story 4 - Keep Command Output Ephemeral But Preserve Chat Replies (Priority: P2)

**Goal**: Command and menu result messages auto-delete after 5 seconds, while the menu message and chat/inference replies remain visible.

**Independent Test**: Trigger command-driven actions and verify their result messages disappear after 5 seconds. Send normal chat prompts and verify assistant replies remain visible.

### Tests for User Story 4

- [X] T023 [P] [US4] Add unit and integration coverage for temporary command message deletion, stale-delete fallback, and durable chat replies in `tests/unit/test_menu.py` and `tests/integration/test_handlers.py`

### Implementation for User Story 4

- [X] T024 [US4] Create shared temporary command-response helpers in `src/bot/ephemeral.py` for send/edit/delete-after-5s behavior that excludes the persistent menu message and chat replies
- [X] T025 [US4] Update command handlers in `src/bot/handlers/models.py`, `src/bot/handlers/settings.py`, and `src/bot/handlers/chats.py` to use `src/bot/ephemeral.py` for command-generated result messages
- [X] T026 [US4] Update menu-generated non-navigation status replies in `src/bot/handlers/menu.py` to use `src/bot/ephemeral.py` while leaving the persistent menu message untouched
- [X] T027 [US4] Keep inference/chat response paths in `src/bot/handlers/messages.py` and `src/bot/handlers/vision.py` outside ephemeral deletion and document the distinction in helper usage

**Checkpoint**: Command clutter is cleaned up automatically without affecting chat transcript visibility.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final verification, runtime data bootstrap alignment, and full quality pass.

- [X] T028 [P] Align preset bootstrap behavior in `src/storage/session_store.py` with `specs/004-model-settings-sessions/contracts/storage-schemas.md` for `data/model-presets.json` and `data/session-presets.json`
- [X] T029 Run the manual validation flow from `specs/004-model-settings-sessions/quickstart.md` and fix any implementation gaps in `src/` and `tests/`
- [X] T030 [P] Run `e:/Git/pet-projects/LMStudioBot/.venv/Scripts/python.exe -m pytest tests -q` and resolve regressions in `src/` and `tests/`
- [X] T031 [P] Run `e:/Git/pet-projects/LMStudioBot/.venv/Scripts/python.exe -m flake8 src tests` and resolve lint issues introduced by this feature

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: Starts immediately.
- **Foundational (Phase 2)**: Depends on Setup completion and blocks all user-story work.
- **User Story 1 (Phase 3)**: Starts after Phase 2.
- **User Story 2 (Phase 4)**: Starts after Phase 2.
- **User Story 3 (Phase 5)**: Starts after Phase 2.
- **User Story 4 (Phase 6)**: Starts after Phase 2.
- **Polish (Phase 7)**: Starts after all desired user stories are complete.

### User Story Dependencies

- **US1**: Depends only on foundational schema/storage/config work.
- **US2**: Depends only on foundational schema/storage/config work.
- **US3**: Depends only on foundational menu/config readiness.
- **US4**: Depends only on foundational config/runtime readiness.

### Within Each User Story

- Test tasks should be implemented before or alongside story logic and must fail before the corresponding implementation is complete.
- Rendering/validation helpers should land before menu callback wiring that depends on them.
- Handler integration should land before final regression and lint passes.

## Parallel Opportunities

- **Foundational**: `T002`, `T003`, and `T004` can run in parallel; `T005` follows once the new helpers exist.
- **US1**: `T006` and `T007` can run in parallel; `T011` and `T012` can proceed in parallel after `T009` and `T010` define the scoped menu layout.
- **US2**: `T013` and `T014` can run in parallel; `T017` and `T018` can proceed in parallel after the history-file store methods are stable.
- **US3**: `T019` can run independently while `T020`–`T022` reshape the menu.
- **US4**: `T023` can run independently; `T025` and `T026` can proceed in parallel after `T024` creates the shared ephemeral helper.
- **Polish**: `T028`, `T030`, and `T031` can run in parallel once implementation is complete.

## Parallel Example: User Story 1

```text
Task: "T006 [US1] Add unit tests for current settings rendering, split-scope setting validation, and invalid preset rejection in tests/unit/test_menu.py and tests/unit/test_settings.py"
Task: "T007 [US1] Add integration tests for current settings, preset browsing, and preset application flows in tests/integration/test_handlers.py"

Task: "T011 [US1] Implement model-scoped runtime setting updates and model preset browse/apply flows in src/bot/handlers/menu.py and src/lms/cli.py using data/model-presets.json"
Task: "T012 [US1] Implement session-scoped setting updates and session preset browse/apply flows in src/bot/handlers/menu.py using data/session-presets.json"
```

## Parallel Example: User Story 2

```text
Task: "T013 [US2] Add unit tests for history file CRUD, history policy selection, and context-budget fallback in tests/unit/test_session_store.py and tests/unit/test_sdk.py"
Task: "T014 [US2] Add integration tests for session switching isolation, history reuse modes, and delete cleanup in tests/integration/test_handlers.py"

Task: "T017 [US2] Implement history reuse policy menu flows and pending-input handling in src/bot/handlers/menu.py for off, fit-budget recent, last N message pairs, and full if possible"
Task: "T018 [US2] Wire trimmed-history assembly into src/lms/sdk.py chat builders so text, regenerate, and vision inference use only the active session's selected history context"
```

## Implementation Strategy

### MVP First

1. Complete Phase 1 and Phase 2.
2. Complete Phase 3 (US1).
3. Complete Phase 4 (US2).
4. Validate settings, presets, and per-session history together before moving on.

### Incremental Delivery

1. Foundation first: new storage layout, preset readers, and LM Studio config helpers.
2. Deliver US1: settings management and preset application.
3. Deliver US2: persistent per-session history and reuse policy.
4. Deliver US3: flatter menu with top-level regenerate.
5. Deliver US4: ephemeral command output cleanup.

### Suggested MVP Scope

The strongest MVP is **US1 + US2** after foundational work, because it delivers the highest-value behavior from the spec: reusable settings management and durable per-session chat context.

---

## Notes

- All tasks follow the required checklist format: checkbox, task ID, optional `[P]`, optional `[US#]`, and exact file path(s).
- Total tasks: **31**
- User story task counts: **US1 = 7**, **US2 = 6**, **US3 = 4**, **US4 = 5**