# Feature Specification: Session-Aware Model Controls

**Feature Branch**: `004-model-settings-sessions`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "I want remove Iference section. It is unusefull. I want to extend model settings to cover most common and useful settings that usually are used, each setting user can adjust manually via menu or load config file. I want to store presets of model settings in config file on disk and be able to load them in menu. I want be able to watch what are current settings applied to loaded model. 'Regenerate command' i want to move on the top level of menu. Response from command should be auto deleted after 5 sec. Chat responses should not be removed. I want chat history to be saved on disk and when i switch to chat session it should be used in context of chat session. When chat session is removed, chat history should be deleted from disk."

## Clarifications

### Session 2026-04-11

- Q: How should settings scope be divided between chat sessions and loaded models? → A: Split scope: model/runtime settings belong to the loaded model, while prompt/generation settings belong to the active chat session.
- Q: How much saved chat history should be reused as context when a session becomes active? → A: Make history reuse policy adjustable in session settings.
- Q: How should reusable presets be organized across model-scoped and session-scoped settings? → A: Use separate preset types: model presets for model-scoped settings and session presets for session-scoped settings.
- Q: Which history reuse modes should the session setting support? → A: Support four modes: off, fit-budget recent, last N message pairs, and full if possible.
- Q: How much preset management should the menu provide? → A: Menu can browse and apply existing presets only; preset creation and editing happen outside the menu.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Manage Model Settings From One Place (Priority: P1)

The user opens the menu and can review, change, and apply the settings that matter most for a loaded model without editing files by hand. The same settings can also be sourced from stored presets on disk, so the user can switch between known configurations quickly.

**Why this priority**: This is the core request. If settings cannot be adjusted, inspected, and reused reliably, the feature does not deliver its main value.

**Independent Test**: Open the menu, navigate to model settings, change several settings manually, apply a saved preset, and verify the currently applied settings view reflects the active values after each change.

**Acceptance Scenarios**:

1. **Given** a model is loaded, **When** the user opens model settings, **Then** the menu shows the currently applied values for the supported settings.
2. **Given** a model is loaded, **When** the user changes an individual setting through the menu, **Then** the new value is validated, applied, and reflected in the current settings view.
3. **Given** one or more saved presets exist on disk, **When** the user chooses a model preset or a session preset from the menu, **Then** only the matching-scope preset values are applied and shown as the current active settings.
4. **Given** a preset contains an invalid or unsupported value, **When** the user attempts to apply it, **Then** the system rejects that preset cleanly and explains which setting could not be applied.
5. **Given** the user is in the menu, **When** they work with presets, **Then** they can browse and apply existing presets but cannot create, rename, edit, or delete presets there.

---

### User Story 2 - Resume Conversation By Session (Priority: P1)

The user can leave one chat session, switch to another, and continue each conversation with the correct prior context because chat history is stored on disk per session and restored automatically when that session becomes active.

**Why this priority**: Session isolation and continuity directly affect response quality. Without persistent per-session history, switching sessions breaks the chat workflow.

**Independent Test**: Create two sessions, send different prompts in each, restart or switch between sessions, and verify the next reply in each session uses only that session's prior conversation. Remove one session and verify its history is no longer available.

**Acceptance Scenarios**:

1. **Given** an active chat session, **When** the user sends chat messages, **Then** that session's conversation history is saved on disk.
2. **Given** multiple chat sessions with different histories, **When** the user switches to one session, **Then** subsequent chat responses use that selected session's saved history as context.
3. **Given** a session has no saved history yet, **When** the user switches to it, **Then** the session starts with an empty conversation context.
4. **Given** the user removes a chat session, **When** the removal completes, **Then** the stored history for that session is deleted from disk and is no longer available for future use.
5. **Given** a chat session has a configured history reuse policy, **When** the session becomes active, **Then** the system uses the saved history according to that policy.
6. **Given** the user changes the history reuse policy for a session, **When** they choose among the supported modes, **Then** the selected mode is saved and used for future replies in that session.

---

### User Story 3 - Simplify Top-Level Navigation (Priority: P2)

The user no longer has to enter an extra inference submenu for common actions. The menu is simplified by removing the Inference section, and the regenerate action is available directly from the main menu level.

**Why this priority**: This reduces friction in the most repetitive workflow and removes a menu layer the user has identified as unnecessary.

**Independent Test**: Open the main menu and verify there is no Inference section. Verify a top-level regenerate action is visible and can be triggered without entering any submenu.

**Acceptance Scenarios**:

1. **Given** the user opens the main menu, **When** the menu is displayed, **Then** no Inference section appears.
2. **Given** the user opens the main menu, **When** they look at the top-level actions, **Then** regenerate is available there.
3. **Given** a previous assistant answer exists in the active session, **When** the user triggers regenerate from the top level, **Then** the last assistant answer is regenerated for that same session.
4. **Given** no prior assistant answer exists in the active session, **When** the user triggers regenerate, **Then** the system shows a clear message explaining that there is nothing to regenerate.

---

### User Story 4 - Keep Command Output Ephemeral But Preserve Chat Replies (Priority: P2)

The user wants command results to clean themselves up so the chat stays readable, while normal assistant replies remain visible as part of the conversation history.

**Why this priority**: This improves day-to-day usability without changing the main chat experience.

**Independent Test**: Run several command-driven actions and verify their result messages disappear after five seconds. Send normal chat prompts and verify assistant replies stay in the chat.

**Acceptance Scenarios**:

1. **Given** the user triggers a command-driven action, **When** the result message is shown, **Then** that message is automatically removed after five seconds.
2. **Given** the user receives a normal assistant chat reply, **When** five seconds pass, **Then** that chat reply remains visible.
3. **Given** a command result message cannot be deleted because it was already removed, **When** the cleanup runs, **Then** the system handles the condition without surfacing an error to the user.
4. **Given** the user is actively navigating the menu, **When** a temporary command result is cleaned up, **Then** the menu remains available for continued interaction.

### Edge Cases

- A settings preset is available on disk but omits some supported settings.
- A settings preset includes values outside the accepted range for one or more settings.
- The user tries to inspect or change model settings while no model is currently loaded.
- The user switches to a session whose stored history file is missing or unreadable.
- The user selects a history reuse policy that would otherwise exceed the available context budget.
- The user selects `last N message pairs` but the configured `N` exceeds the available history or the available context budget.
- The user deletes the currently active session and the system must choose a safe next active session state.
- A command result message expires while the user is still navigating the menu.
- A newly loaded model does not support every configurable setting exposed by the product.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The main menu MUST remove the Inference section entirely.
- **FR-002**: The main menu MUST expose regenerate as a top-level action that is reachable without entering a submenu.
- **FR-003**: The system MUST preserve existing normal chat messaging so users can continue sending prompts directly in chat without using an inference menu.
- **FR-004**: The system MUST provide a dedicated model settings area in the menu.
- **FR-005**: The model settings area MUST allow the user to inspect the currently applied settings for the loaded model.
- **FR-006**: The model settings area MUST allow the user to manually adjust each supported setting through the menu according to its scope.
- **FR-007**: Model-scoped runtime settings MUST belong to the currently loaded model and MUST remain attached to that loaded model until changed or replaced.
- **FR-008**: Session-scoped prompt and generation settings MUST belong to the active chat session and MUST be restored when that session becomes active again.
- **FR-009**: The supported settings MUST include, at minimum, context length as a model-scoped runtime setting, and system prompt, output length limit, randomness, probability mass threshold, candidate token limit, repetition control, optional stop sequences, and optional deterministic seed as session-scoped prompt or generation settings.
- **FR-010**: The system MUST validate every manually entered setting value before applying it and MUST explain any validation failure in user-facing terms.
- **FR-011**: The system MUST store named presets in on-disk configuration files that persist across restarts.
- **FR-012**: The system MUST support separate preset types for model-scoped settings and session-scoped settings.
- **FR-013**: The menu MUST let the user browse and apply saved model presets and saved session presets from disk.
- **FR-014**: The system MUST allow the user to load settings from the on-disk configuration source without manually re-entering each value, while applying only the preset type that matches the selected scope.
- **FR-015**: The menu MUST NOT create, rename, edit, overwrite, or delete presets; those actions occur outside the menu.
- **FR-016**: After a manual change or preset application succeeds, the current settings view MUST reflect the active values.
- **FR-017**: If a setting cannot be applied to the currently loaded model, the system MUST tell the user that the setting is unavailable or deferred.
- **FR-018**: The system MUST save chat history on disk separately for each chat session.
- **FR-019**: The active chat session MUST expose an adjustable history reuse policy in settings.
- **FR-020**: The supported history reuse policy modes MUST include `off`, `fit-budget recent`, `last N message pairs`, and `full if possible`.
- **FR-021**: When the user switches chat sessions, the system MUST restore that selected session's saved history and use it as context for subsequent chat replies and regenerate actions according to that session's configured history reuse policy.
- **FR-022**: Chat history from one session MUST NOT appear in another session's context unless the user explicitly switches to that session.
- **FR-023**: If a configured history reuse policy would exceed the available context budget, the system MUST reduce the reused history deterministically while preserving the configured policy's intent as closely as possible.
- **FR-024**: When a chat session is removed, the system MUST delete that session's stored chat history from disk.
- **FR-025**: Command-generated result messages MUST be automatically deleted five seconds after they are shown.
- **FR-026**: Normal assistant chat responses MUST remain visible and MUST NOT be automatically deleted.
- **FR-027**: If automatic deletion of a command result message fails, the system MUST continue operating without showing an internal error to the user.
- **FR-028**: Menu navigation messages that are required for ongoing interaction MUST remain available long enough to complete the current interaction.

### Key Entities *(include if feature involves data)*

- **Model Setting**: A single user-visible control that affects behavior, including its name, scope, current value, allowed range or format, and whether it is supported by the active model or active chat session.
- **Model Preset**: A named collection of model-scoped runtime setting values stored on disk and reusable from the menu.
- **Session Preset**: A named collection of session-scoped prompt and generation setting values stored on disk and reusable from the menu.
- **Current Model Settings View**: The user-facing summary of the values actively applied to the loaded model at the time it is displayed.
- **Chat Session History**: The ordered record of user and assistant messages stored for one chat session and reused when that session becomes active again.
- **History Reuse Policy**: A session-scoped setting that determines how much of the saved chat session history is reused as context when generating the next reply, including the selected mode and any mode-specific value such as `N`.
- **Command Result Message**: A non-chat informational, confirmation, or error message produced by a command-driven action and scheduled for automatic removal.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can reach the current model settings view and apply a saved preset from the menu in no more than three taps after opening the main menu.
- **SC-002**: In acceptance testing, 100% of session switches use only the selected session's saved history for the next generated response.
- **SC-003**: In acceptance testing, 100% of removed chat sessions no longer have retrievable stored history after deletion completes.
- **SC-004**: In acceptance testing, 100% of command-generated result messages are removed automatically within five seconds of being shown, except when the user has already deleted them.
- **SC-005**: In acceptance testing, 100% of normal assistant chat replies remain visible until the user removes them manually.
- **SC-006**: A user can determine the currently applied settings for a loaded model from a single menu view without opening any configuration file.

## Assumptions

- The bot remains a single-owner workflow, so one person's menu actions and session history do not need to be merged with another user's state.
- Existing named chat sessions remain the primary unit for organizing conversations; this feature adds durable history to those sessions rather than replacing the session concept.
- Context length remains tied to the loaded model lifecycle, while prompt and generation controls remain tied to the active chat session lifecycle.
- Model presets and session presets are stored separately enough that applying one type does not implicitly overwrite the other type.
- History reuse behavior is configured per chat session rather than globally.
- The `last N message pairs` mode stores its `N` value as part of the session settings.
- Preset files are authored or edited outside the menu flow; this feature only requires the menu to consume them.
- The product may hide, disable, or label unsupported settings when a loaded model does not accept every supported control.
- Loading settings from disk refers to reading from the bot's own stored configuration files, not to arbitrary user-supplied files uploaded at runtime.
- Regenerate continues to operate on the active chat session only.

## Out of Scope

- Replacing normal chat messaging with menu-only prompting.
- Introducing shared chat history across different sessions.
- Importing ad hoc settings files from a user device during a live chat.
- Expanding the feature to multi-user collaboration or shared ownership.
- Managing preset file contents from inside the menu.
