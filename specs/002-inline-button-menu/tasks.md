# Tasks: Inline Button Menu Navigation

**Input**: Design documents from `specs/002-inline-button-menu/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: User story label (US1–US6)
- All paths relative to repository root

---

## Phase 1: Setup

**Purpose**: Wire new handler file and update registrations. No user stories are blocked until T003 is done.

- [x] T001 Create empty `src/bot/handlers/menu.py` with module docstring and logger
- [x] T002 Register `CallbackQueryHandler` and `/menu` command in `src/bot/main.py`

**Checkpoint**: Bot still starts and existing commands work. Menu button press logs "unhandled callback".

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core keyboard builders, auth-safe callback routing, and stale-menu recovery that every user story phase depends on.

**⚠️ CRITICAL**: No user-story implementation can begin until this phase is complete.

- [x] T003 Implement `build_main_menu()` keyboard builder in `src/bot/handlers/menu.py` returning `InlineKeyboardMarkup` with 5 section buttons (`menu:models`, `menu:sessions`, `menu:settings`, `menu:inference`, `menu:help`)
- [x] T004 [P] Implement `build_back_button(target)` helper in `src/bot/handlers/menu.py` returning a single-row keyboard with a "⬅ Back" button pointing to the given callback key
- [x] T005 [P] Implement `menu_command_handler(update, context)` in `src/bot/handlers/menu.py` with `@require_owner`: sends main menu as new message, stores `context.chat_data["menu_message_id"]`; if menu message already exists, edits it instead and clears any `pending_input`
- [x] T006 Implement `menu_callback_handler(update, context)` in `src/bot/handlers/menu.py` with `@require_owner`: parse `callback_data` prefix, call `query.answer()`, route keys to the correct helper, and log callback actions plus unrecognised keys
- [x] T007 [P] Implement `_show_section(query, context, section)` in `src/bot/handlers/menu.py`: call `query.edit_message_text()` with the correct sub-menu keyboard; if the menu is stale/expired, answer with "Menu expired — opening a fresh menu.", clear `menu_message_id`, and send a fresh main menu; treat "message is not modified" as an idempotent no-op
- [x] T008 [P] Add unit tests for `build_main_menu()`, `build_back_button()`, and `_show_section()` in `tests/unit/test_menu.py`: verify keyboard layouts, button labels, callback data values, and stale-message recovery

**Checkpoint**: `/menu` opens main menu. Tapping any section shows correct sub-menu. "⬅ Back" returns to main menu. Stale-message recovery and owner-only access work.

---

## Phase 3: User Story 1 - Open Main Menu (Priority: P1) 🎯 MVP

**Goal**: `/start` and `/menu` open the persistent inline menu; navigation edits the message in place; "⬅ Back" returns to parent.

**Independent Test**: Send `/menu` → one message with 5 buttons appears. Tap "Model Management" → same message updates to model sub-menu + "⬅ Back". Tap "⬅ Back" → same message returns to main menu. Delete the message and send `/menu` → new menu created.

- [x] T009 [US1] Update `/start` handler in `src/bot/handlers/help.py` to call `menu_command_handler()` from `menu.py` instead of posting the text help block
- [x] T010 [US1] Add sub-menu keyboard builders to `src/bot/handlers/menu.py`: `build_models_menu()`, `build_sessions_menu()`, `build_settings_menu()`, `build_inference_menu(active_model)` with both "💬 Send Message" and "🔄 Regenerate", and `build_help_menu()`
- [x] T011 [P] [US1] Add keyboard builders for Help topics in `src/bot/handlers/menu.py`: `build_help_models()`, `build_help_sessions()`, `build_help_settings()`, `build_help_inference()`; each returns text + back button
- [x] T012 [P] [US1] Add unit tests in `tests/unit/test_menu.py`: verify all 5 sub-menu builders return correct layouts; verify `/menu` creates message and stores `menu_message_id`; verify stale message handler clears id and re-sends

**Checkpoint**: US1 fully functional — menu opens, all 5 sections navigable, back buttons work, stale recovery works.

---

## Phase 4: User Story 2 - Model Management Section (Priority: P2)

**Goal**: "📦 List", "🧠 Loaded", "⬆ Load", "⬇ Unload" buttons fully functional; LM Studio errors surfaced.

**Independent Test**: Open menu → tap "Model Management" → tap "📦 List Models" → result posted. Tap "⬆ Load Model" → bot prompts for identifier → type identifier → model loads with confirmation.

- [x] T013 [US2] Implement `_handle_models_action(query, context)` in `src/bot/handlers/menu.py`: route `models:list` → call `cli.list_models()` and post result; route `models:loaded` → call `cli.list_loaded()` and post result; route `models:load` / `models:unload` → set `context.chat_data["pending_input"]` and post prompt
- [x] T014 [US2] Implement `handle_pending_input(update, context)` in `src/bot/handlers/menu.py`: read `pending_input` key, delegate to per-action handler, clear `pending_input` on success; on validation failure re-set `pending_input` and re-prompt
- [x] T015 [US2] Implement `_execute_models_load(text, update, context)` and `_execute_models_unload(text, update, context)` in `src/bot/handlers/menu.py`: validate non-empty identifier, call `cli.load_model()` / `cli.unload_model()`, post confirmation or error
- [x] T016 [US2] Update `text_message_handler` in `src/bot/handlers/messages.py`: add `pending_input` check at the very top — if `context.chat_data.get("pending_input")` is set, call `menu.handle_pending_input(update, context)` and return immediately
- [x] T017 [P] [US2] Add unit tests in `tests/unit/test_menu.py`: verify `models:list` posts result; verify `models:load` sets `pending_input`; verify `_execute_models_load` validates empty identifier and calls cli; verify text handler delegates when `pending_input` is set

**Checkpoint**: US2 fully functional — all model management actions work via buttons.

---

## Phase 5: User Story 3 - Chat Sessions Section (Priority: P3)

**Goal**: "➕ New Chat", "🗂 List Chats" (dynamic buttons), tap to switch, "🗑 Remove Chat" all functional.

**Independent Test**: Open menu → tap "Chat Sessions" → tap "➕ New Chat" → prompt → enter name → session created. Tap "🗂 List Chats" → each chat shown as button. Tap a chat button → active session switches.

- [x] T018 [US3] Implement `build_sessions_list_keyboard(sessions, action)` in `src/bot/handlers/menu.py`: builds dynamic keyboard with one button per session (label = session name, callback = `sessions:switch:<id>` or `sessions:confirm_remove:<id>`) plus "⬅ Back" row
- [x] T019 [US3] Implement `_handle_sessions_action(query, context)` in `src/bot/handlers/menu.py`: route `sessions:new` → set `pending_input="sessions:new"` and post prompt; `sessions:list` → edit message to dynamic list keyboard; `sessions:remove` → edit message to removal list keyboard; `sessions:switch:<id>` → switch session, edit message to sessions sub-menu with confirmation; `sessions:confirm_remove:<id>` → remove session, edit message to sessions sub-menu with confirmation
- [x] T020 [US3] Implement `_execute_sessions_new(text, update, context)` in `src/bot/handlers/menu.py`: create session (auto-name if empty), post confirmation
- [x] T021 [P] [US3] Handle empty-session edge case in `_handle_sessions_action` for `sessions:list`: if no sessions exist, post "No chats yet — use ➕ New Chat" and return to sessions sub-menu
- [x] T022 [P] [US3] Add unit tests in `tests/unit/test_menu.py`: verify `build_sessions_list_keyboard` labels and callback data; verify `sessions:switch:<id>` delegates to store correctly; verify empty-session path; verify `sessions:new` sets `pending_input`

**Checkpoint**: US3 fully functional — all chat session management actions work via buttons.

---

## Phase 6: User Story 4 - Inference Section (Priority: P4)

**Goal**: Inference sub-menu shows the active model name and exposes both "💬 Send Message" and "🔄 Regenerate" actions; responses can be started from the button flow.

**Independent Test**: Open menu → tap "Inference" → sub-menu shows active model name plus "💬 Send Message" and "🔄 Regenerate". Tap "💬 Send Message" → bot prompts → type a message → response streams in chat. If a prior assistant response exists, tap "🔄 Regenerate" → the last answer is regenerated.

- [x] T023 [US4] Implement `_handle_inference_action(query, context)` in `src/bot/handlers/menu.py`: route `inference:send` → set `pending_input="inference:send"` and post prompt; route `inference:regenerate` → reuse the existing regenerate flow for the active session; show "No model loaded" error if no active session model exists
- [x] T024 [US4] Update `build_inference_menu(active_model)` in `src/bot/handlers/menu.py` to accept and display the active model name from `store.get_active_session()`; show both inference buttons and display "No model loaded" when None
- [x] T025 [US4] Implement `_execute_inference_send(text, update, context)` and `_execute_inference_regenerate(update, context)` in `src/bot/handlers/menu.py`: validate non-empty text; append user `ChatMessage` to the active session; reuse the streaming/regenerate logic already present in `src/bot/handlers/messages.py`
- [x] T026 [P] [US4] Add unit tests in `tests/unit/test_menu.py`: verify both inference buttons route correctly; verify `_execute_inference_send` rejects empty text; verify regenerate delegates to the existing inference path with the correct session

**Checkpoint**: US4 fully functional — user can send or regenerate inference without knowing any slash command.

---

## Phase 7: User Story 5 - Settings Section (Priority: P5)

**Goal**: System prompt and all inference parameters (temperature, max tokens, top-p) updateable via buttons; validation errors re-prompt; no active session → shows guidance.

**Independent Test**: Open menu → tap "Settings" → tap "🌡 Temperature" → prompt → enter `0.5` → confirmed. Enter `abc` → validation error, re-prompted. No active session → error message.

- [x] T027 [US5] Implement `_handle_settings_action(query, context)` in `src/bot/handlers/menu.py`: guard if no active session (post error + show sessions sub-menu hint); route `settings:prompt`, `settings:temperature`, `settings:max_tokens`, `settings:top_p` → set corresponding `pending_input` and post prompt
- [x] T028 [US5] Implement `_execute_settings_update(key, text, update, context)` in `src/bot/handlers/menu.py`: validate each type (float range, int range, any string); on failure re-set `pending_input` and re-post validation error; on success update `session.settings` or `session.system_prompt` via `store.update_session()` and post confirmation
- [x] T029 [P] [US5] Add unit tests in `tests/unit/test_menu.py`: verify each settings key invokes correct field update; verify out-of-range values produce error and re-set `pending_input`; verify no-session guard fires; verify empty string clears system prompt

**Checkpoint**: US5 fully functional — all settings adjustable via buttons.

---

## Phase 8: User Story 6 - Help Section (Priority: P6)

**Goal**: Per-section help topics accessible via buttons; help text displayed in-place; back navigation works.

**Independent Test**: Open menu → tap "Help" → tap "Model Management Help" → help text shown in menu message. Tap "⬅ Back" → returns to Help sub-menu. Tap "⬅ Back" → returns to main menu.

- [x] T030 [US6] Implement `_handle_help_section(query, context)` in `src/bot/handlers/menu.py`: route `menu:help:models`, `menu:help:sessions`, `menu:help:settings`, `menu:help:inference` → call `query.edit_message_text()` with the corresponding help text from `build_help_*()` builders and a "⬅ Back → menu:help" button
- [x] T031 [P] [US6] Write help text strings as module-level constants in `src/bot/handlers/menu.py` for all 4 topics (models, sessions, settings, inference)
- [x] T032 [P] [US6] Add unit tests in `tests/unit/test_menu.py`: verify each help topic route edits the message with correct text; verify back button points to `menu:help`

**Checkpoint**: US6 fully functional — help is navigable entirely via buttons.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Verify `/menu` cancellation behaviour, command parity, end-to-end workflow, structured logging, and final quality gates.

- [x] T033 [P] Add integration tests in `tests/integration/test_handlers.py`: verify non-owner `/menu` and callback interactions receive "⛔ Access denied." and do not expose menu actions
- [x] T034 Add unit/integration coverage in `tests/unit/test_menu.py` or `tests/integration/test_handlers.py`: verify `/menu` clears `context.chat_data["pending_input"]` before showing the main menu (satisfies FR-006)
- [x] T035 [P] Add integration tests in `tests/integration/test_handlers.py`: verify `text_message_handler` delegates to `handle_pending_input` when `pending_input` is set in `chat_data`; verify it proceeds to inference when `pending_input` is `None`
- [x] T036 [P] Add a parity test matrix in `tests/integration/test_handlers.py` verifying every existing user-facing command path (`/models`, `/loaded`, `/load`, `/unload`, `/newchat`, `/chats`, `/switchchat`, `/removechat`, `/setprompt`, `/set`, `/regenerate`) has a corresponding button path (SC-003)
- [x] T037 [P] Add an end-to-end workflow test in `tests/integration/test_handlers.py`: open menu → load model → create chat → send message via the button-driven flow (SC-004)
- [x] T038 [P] Add structured logging in `src/bot/handlers/menu.py` for callback routing, `pending_input` set/clear, stale-menu recovery, validation failures, and execution errors (Constitution Principle V)
- [x] T039 [P] Run full test suite (`cd src; pytest`) and confirm all existing plus new tests pass with 0 errors
- [x] T040 [P] Run linter (`ruff check .` or `flake8`) and fix any issues in new files

---

## Dependencies

```
T001 → T002 → T003 → T004, T005, T006 → T007, T008
T003-T008 (Phase 2) → all Phase 3+ tasks
T009-T012 (US1) ← MVP increment — can stop here for minimal viable delivery
T013-T017 (US2) ← independent of US3–US6
T018-T022 (US3) ← independent of US2, US4–US6
T023-T026 (US4) ← depends on T016 (pending input interception in `messages.py`)
T027-T029 (US5) ← independent of US2–US4
T030-T032 (US6) ← independent of all other user stories
T033-T040 (Polish) ← depends on all user story phases complete
```

## Parallel Execution per User Story

After Phase 2 (T001–T008) is complete, each user story phase can be started independently:

```
Phase 2 complete
├── US1 (T009–T012)   — can start immediately
├── US2 (T013–T017)   — can start immediately after T016 (`messages.py`) is done
├── US3 (T018–T022)   — can start immediately
├── US4 (T023–T026)   — can start after T016
├── US5 (T027–T029)   — can start immediately
└── US6 (T030–T032)   — can start immediately
```

Within each story, tasks marked **[P]** can run in parallel with other [P] tasks in the same story.

## Implementation Strategy

**Suggested MVP**: Phases 1–3 only (T001–T012) — delivers a fully navigable menu with stale-message recovery and owner-only access from the start. All existing commands still work. Remaining stories add functionality section by section.

**Full delivery order**: Phase 1 → 2 → 3 (MVP) → 4 → 5 → 6 → 7 → 8 → 9
