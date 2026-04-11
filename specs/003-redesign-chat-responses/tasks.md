# Tasks: 003 — Redesign Chat Responses

**Input**: Design documents from `specs/003-redesign-chat-responses/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅

---

## Phase 1: Setup

**Purpose**: No new project structure is required — this feature modifies existing files and adds two new modules within the established `src/bot/` and `tests/unit/` directories.

- [X] T001 Verify baseline tests pass before any changes by running `cd src; pytest` in repo root

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The formatting module and SDK wrappers must exist before any handler or test can use them. Both are independent of each other and can be built in parallel.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Create `src/bot/formatting.py` with `format_response(text)`, `strip_think_tags(text)`, and `_format_size(size_bytes)` per the pipeline in plan.md §Module 1 and data-model.md §FormattedResponse
- [X] T003 [P] Add `list_downloaded_models(host, port)` and `list_loaded_models(host, port)` async wrappers to `src/lms/sdk.py` using `asyncio.to_thread` per plan.md §Module 2

**Checkpoint**: `src/bot/formatting.py` and updated `src/lms/sdk.py` exist and are importable — user story work can now begin.

---

## Phase 3: User Story 1 — Plain Model Listing (Priority: P1) 🎯 MVP

**Goal**: `/models` and `/loaded` commands reply with a plain bulleted list (`• name  size`) sourced from the lmstudio SDK instead of raw CLI text.

**Independent Test**: Send `/models` — verify response contains `•` bullets with model sizes and no `|` table characters. Send `/loaded` — same format (or "No models are currently loaded.").

- [X] T004 [US1] Add shared helpers `_format_downloaded_list(models) -> str` and `_format_loaded_list(handles) -> str` in `src/bot/handlers/models.py`; rewrite `models_command` to call `sdk.list_downloaded_models` then `_format_downloaded_list`, reply with `parse_mode="HTML"` (FR-001); handle empty list ("No models found.") and SDK error
- [X] T005 [US1] Rewrite `loaded_command` in `src/bot/handlers/models.py` to call `sdk.list_loaded_models` then `_format_loaded_list`, reply with `parse_mode="HTML"` (FR-014); handle empty list ("No models are currently loaded.") and SDK error
- [X] T006 [US1] Update menu action `models:list` in `src/bot/handlers/menu.py`: replace `cli.list_models()` call with `sdk.list_downloaded_models` + `_format_downloaded_list` imported from `src.bot.handlers.models` — do NOT inline the formatting logic
- [X] T007 [US1] Update menu action `models:loaded` in `src/bot/handlers/menu.py`: replace `cli.list_loaded()` call with `sdk.list_loaded_models` + `_format_loaded_list` imported from `src.bot.handlers.models` — do NOT inline the formatting logic
- [X] T008 [P] [US1] Add integration tests for `models_command` (plain list, no `|` chars, empty, error) and `loaded_command` (same) in `tests/integration/test_handlers.py

**Checkpoint**: US1 is fully functional — `/models` and `/loaded` return SDK-backed plain bulleted lists.

---

## Phase 4: User Story 2 — Clickable Load Model List (Priority: P1)

**Goal**: `/load` with no args (and Load Model menu button) shows an inline keyboard; loaded models are prefixed `🟢`; tapping a button edits the message to `⏳ Loading…` then `✅ Loaded.`

**Independent Test**: Send `/load` — inline keyboard appears with model names and sizes. Tap a model — message changes to `⏳ Loading…` then `✅ Loaded.` or an error.

- [X] T009 [US2] Add `_send_load_keyboard(update, context)` helper in `src/bot/handlers/models.py`: gather `list_downloaded_models` + `list_loaded_models` concurrently, build `loaded_keys` set, call `_build_load_keyboard`, send keyboard message; handle empty list (FR-004) and SDK error
- [X] T010 [US2] Add `_build_load_keyboard(models, loaded_keys)` in `src/bot/handlers/models.py`: one `InlineKeyboardButton` per model with `🟢 ` prefix if in `loaded_keys`, label truncated to 64 chars, callback `models:loadmodel:{model_key}`, capped at 100 buttons; if `len(models) > 100` the keyboard is built from the first 100 entries and the caller appends a follow-up text note `(showing 100 of {total}; {total - 100} model(s) not shown)` to the reply (FR-002, FR-012)
- [X] T011 [US2] Update `load_command` in `src/bot/handlers/models.py`: no-args path calls `_send_load_keyboard`; with-args path is unchanged (FR-013)
- [X] T012 [US2] Add `models:load` branch in `_handle_models_action` in `src/bot/handlers/menu.py` to call `_send_load_keyboard` (replacing the `pending_input` text-prompt approach)
- [X] T013 [US2] Add `models:loadmodel:` routing in `menu_callback_handler` in `src/bot/handlers/menu.py` (before the existing `models:` catch-all)
- [X] T014 [US2] Add `_handle_load_model_callback(query, context, data)` in `src/bot/handlers/menu.py`: parse model key, `edit_message_text("⏳ Loading…")`, call `cli.load_model`, edit to `✅ Loaded.` or `❌ Failed: {e}` (FR-002)
- [X] T015 [P] [US2] Add unit tests for `_build_load_keyboard` (🟢 prefix, truncation, cap) and `_handle_load_model_callback` (⏳→✅ flow, error flow) in `tests/unit/test_menu.py`
- [X] T016 [P] [US2] Add integration tests for `load_command` no-args (keyboard reply) and with-args (unchanged) in `tests/integration/test_handlers.py

**Checkpoint**: US2 fully functional — load inline keyboard works end-to-end from both `/load` and menu.

---

## Phase 5: User Story 3 — Clickable Unload Model List (Priority: P1)

**Goal**: `/unload` with no args (and Unload Model menu button) shows an inline keyboard of loaded models; tapping unloads with `⏳ Unloading…` → `✅ Unloaded.`

**Independent Test**: Load a model. Send `/unload` — inline keyboard with loaded models appears. Tap one — message changes to `⏳ Unloading…` then `✅ Unloaded.`

- [X] T017 [US3] Add `_send_unload_keyboard(update, context)` helper in `src/bot/handlers/models.py`: call `list_loaded_models`, build `_build_unload_keyboard`, send keyboard message; handle empty list (FR-005) and SDK error
- [X] T018 [US3] Add `_build_unload_keyboard(handles)` in `src/bot/handlers/models.py`: one `InlineKeyboardButton` per handle using `info.identifier`, label `{identifier}  {size}` truncated to 64 chars, callback `models:unloadmodel:{identifier}`, capped at 100 buttons; if `len(handles) > 100` the caller appends a text note `(showing 100 of {total}; {total - 100} model(s) not shown)` to the reply (FR-003, FR-012)
- [X] T019 [US3] Update `unload_command` in `src/bot/handlers/models.py`: no-args path calls `_send_unload_keyboard`; with-args path is unchanged (FR-013)
- [X] T020 [US3] Add `models:unload` branch in `_handle_models_action` in `src/bot/handlers/menu.py` to call `_send_unload_keyboard` (replacing `pending_input` text-prompt)
- [X] T021 [US3] Add `models:unloadmodel:` routing in `menu_callback_handler` in `src/bot/handlers/menu.py` (before the existing `models:` catch-all)
- [X] T022 [US3] Add `_handle_unload_model_callback(query, context, data)` in `src/bot/handlers/menu.py`: parse identifier, `edit_message_text("⏳ Unloading…")`, call `cli.unload_model`, edit to `✅ Unloaded.` or `❌ Failed: {e}` (FR-003)
- [X] T023 [P] [US3] Add unit tests for `_build_unload_keyboard` (truncation, cap, no-models) and `_handle_unload_model_callback` (⏳→✅ flow, error flow) in `tests/unit/test_menu.py`
- [X] T024 [P] [US3] Add integration tests for `unload_command` no-args (keyboard or no-models message) and with-args (unchanged) in `tests/integration/test_handlers.py`

**Checkpoint**: US3 fully functional — unload inline keyboard works end-to-end from both `/unload` and menu.

---

## Phase 6: User Story 4 — Telegram-Safe Response Formatting (Priority: P2)

**Goal**: All inference responses use `parse_mode="HTML"`; markdown characters (`*`, `_`, `[`, `]`, etc.) in model output are HTML-escaped so they appear literally instead of being consumed by Telegram's renderer.

**Independent Test**: Ask model to output `**bold** _italic_ [link](url)` — verify asterisks, underscores, and brackets appear verbatim in the Telegram message.

- [X] T025 [P] [US4] Add unit tests in `tests/unit/test_formatting.py`: `test_plain_prose_unchanged`, `test_html_escape_plain_text` (verifies `<`, `>`, `&` escaped), `test_markdown_chars_in_plain_text` (verifies `*`, `_` etc. pass through unmodified since they are not HTML-special)
- [X] T026 [US4] Update `text_message_handler` in `src/bot/handlers/messages.py`: import `format_response` from `src.bot.formatting`; after streaming completes apply `format_response(full_response)` and send with `parse_mode="HTML"`; remove intermediate streaming edit calls; store raw `full_response` in session history (FR-006, FR-011; spec Q1=B)
- [X] T027 [US4] Update `regenerate_command` in `src/bot/handlers/messages.py` to apply the same `format_response` + `parse_mode="HTML"` pattern to its final response
- [X] T028 [US4] Update `photo_message_handler` in `src/bot/handlers/vision.py`: same `format_response` + `parse_mode="HTML"` on final response; remove intermediate streaming edits (FR-006)
- [X] T029 [US4] Update `_execute_inference_send` and `_execute_inference_regenerate` in `src/bot/handlers/menu.py` (if they exist and send inference output) to apply `format_response` + `parse_mode="HTML"`

**Checkpoint**: US4 complete — all inference output paths apply HTML-safe formatting.

---

## Phase 7: User Story 5 — Code Snippets as Telegram Monospace (Priority: P2)

**Goal**: Fenced code blocks (` ``` `) become `<pre><code>…</code></pre>`; inline code (`` ` ``) becomes `<code>…</code>`. Already enabled by Phase 6's `format_response` pipeline — this phase adds the tests.

**Independent Test**: Ask model to write a Python function — verify the code appears in a fixed-width copyable block in Telegram.

- [X] T030 [P] [US5] Add unit tests in `tests/unit/test_formatting.py` for code conversion: `test_fenced_code_no_lang`, `test_fenced_code_with_lang` (lang tag excluded), `test_fenced_multiple_blocks`, `test_inline_code`, `test_html_escape_inside_code` (`<br>` in code block → `&lt;br&gt;`) (FR-007, FR-008)

**Checkpoint**: US5 complete — `format_response` pipeline verified for all code block variants.

---

## Phase 8: User Story 6 — Strip Think Tags from Responses (Priority: P2)

**Goal**: `<think>…</think>` blocks are stripped from all responses before display. Already enabled by Phase 6's `format_response` pipeline — this phase adds the tests.

**Independent Test**: Use a reasoning model. Send a message. Verify the reply contains no `<think>` or `</think>` tags.

- [X] T031 [P] [US6] Add unit tests in `tests/unit/test_formatting.py` for think-tag stripping: `test_strip_think_single`, `test_strip_think_multiple`, `test_strip_think_none`, `test_strip_think_unclosed` (strip to end-of-string), `test_empty_after_strip` (returns `"*(no response)*"`) (FR-009, FR-010)

**Checkpoint**: US6 complete — `format_response` verified for all think-tag scenarios.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Lint, regression sweep, cleanup of replaced CLI list calls.

- [X] T032 Remove `cli.list_models` and `cli.list_loaded` imports and usages from `src/bot/handlers/menu.py` (now replaced by SDK calls via `models.py` helpers)
- [X] T033 [P] Run full test suite `cd src; pytest` and confirm all tests pass (147 baseline + new tests)
- [X] T034 [P] Run `ruff check .` (or `flake8`) from `src/` and resolve any lint errors introduced by this feature

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)
  └── Phase 2 (Foundational: formatting.py + sdk.py) — BLOCKS all stories
        ├── Phase 3 (US1: Plain lists)         — T002, T003 required
        ├── Phase 4 (US2: Load keyboard)        — T002, T003 required
        ├── Phase 5 (US3: Unload keyboard)      — T002, T003 required
        ├── Phase 6 (US4: Response formatting)  — T002 required
        ├── Phase 7 (US5: Code monospace)       — T002 required; tests only after T026
        └── Phase 8 (US6: Think tags)           — T002 required; tests only after T026
              └── Phase 9 (Polish)              — all story phases complete
```

### Within-Phase Parallel Opportunities

| Phase | Parallel tasks |
|-------|---------------|
| Phase 2 | T002 and T003 are fully independent (different files) |
| Phase 3 | T004 and T005 are independent (different commands); T008 is independent |
| Phase 4 | T009 + T010 can be written together; T015 and T016 are independent of each other |
| Phase 5 | T017 + T018 together; T023 and T024 independent |
| Phase 6 | T025 independent; T026 and T027 are the same file (sequential); T028 independent |
| Phase 7 | T030 independent (test only) |
| Phase 8 | T031 independent (test only) |
| Phase 9 | T033 and T034 are independent |

### User Story Independence

- **US1** (T004–T008): No dependency on US2/US3/US4/US5/US6
- **US2** (T009–T016): No dependency on US3. Depends on US1's SDK wrappers (T003) but not US1's handlers
- **US3** (T017–T024): No dependency on US2. Depends on T003 only
- **US4** (T025–T029): No dependency on US1/US2/US3. Depends only on T002 (`format_response`)
- **US5** (T030): Tests only — depends on T026 (format_response wired into handler)
- **US6** (T031): Tests only — depends on T026 (format_response wired into handler)

### Suggested MVP Scope

**Minimum to deliver the most visible fix**: Phase 2 + Phase 3 (US1) + Phase 6 (US4)

This gives: plain model lists from SDK + HTML-safe formatted responses with think-tag stripping and code formatting.

---

## Implementation Strategy

1. **Start with Phase 2** — two independent files, pure logic, no Telegram interaction
2. **US1 first** — low-risk (read-only SDK calls, no keyboard complexity); validates SDK wrappers in production
3. **US2 + US3 in parallel** — symmetric implementations; can be developed concurrently
4. **US4/US5/US6** — one `format_response` call wired into three handlers, plus tests
5. **Polish last** — lint and cleanup after all functionality verified

Total tasks: **T001–T034** (34 tasks)
