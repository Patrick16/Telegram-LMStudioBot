# Feature Specification: Inline Button Menu Navigation

**Feature Branch**: `[002-inline-button-menu]`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "UI-friendly inline button menu replacing bot commands, grouped into sections: Model Management, Chat Sessions, Settings, Inference, Help. Back navigation without chat spam."

## Clarifications

### Session 2026-04-11

- Q: What does the Inference section do in the menu? → A: Quick-start inference — shows the active model name and provides both a "💬 Send Message" button and a "🔄 Regenerate" button.
- Q: What happens to the next text message while a menu prompt is awaiting input? → A: It is consumed as the answer to that prompt and is not treated as inference; sending `/menu` cancels the prompt.
- Q: What should `/help` do after the menu is added? → A: `/help` remains supported as a text-based reference, while the Help menu provides the same guidance via buttons.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Open Main Menu (Priority: P1)
A user opens the bot and is presented with a persistent menu message containing clearly labelled buttons for all top-level sections. When the user presses a section button, the same message is updated in place (no new message is sent) to show the sub-menu for that section.

**Why this priority**: The main menu is the entry point to all functionality. Without it no other feature is accessible.

**Independent Test**: Send `/start` or `/menu` → verify a single message appears with 5 section buttons. Press "Model Management" → verify the same message updates to show model sub-menu options and a "⬅ Back" button. Press "⬅ Back" → verify the same message returns to the main menu.

**Acceptance Scenarios**:
1. **Given** the bot is running, **When** the user sends `/start` or `/menu`, **Then** the bot sends exactly one message containing a main-menu keyboard with buttons for all five sections.
2. **Given** the main menu is open, **When** the user taps a section button, **Then** the same message is edited to show that section's sub-menu and a "⬅ Back" button; no new message is posted.
3. **Given** a sub-menu is open, **When** the user taps "⬅ Back", **Then** the same message is edited back to the main menu.
4. **Given** the main menu message was deleted, **When** the user sends `/menu`, **Then** a new menu message is created.

---

### User Story 2 - Model Management Section (Priority: P2)
From the Model Management sub-menu the user can list available models, show loaded models, load a model, and unload a model — all triggered by inline buttons. Actions requiring additional input (e.g., model name, load options) prompt the user with a guided text input step, then return the result without leaving extra menu messages in the chat.

**Why this priority**: Model management is the most frequently used section and its usability directly determines whether users adopt the bot.

**Independent Test**: Open menu → tap "Model Management" → tap "📦 List Models" → verify a result message is posted below the menu (menu message itself stays unchanged). Tap "⬅ Back" → verify menu reverts to main.

**Acceptance Scenarios**:
1. **Given** the Model Management sub-menu is open, **When** the user taps "📦 List Models", **Then** a result message is posted showing all available models; the menu message is not duplicated.
2. **Given** the Model Management sub-menu is open, **When** the user taps "🧠 Loaded Models", **Then** a result message shows currently loaded models.
3. **Given** the Model Management sub-menu is open, **When** the user taps "⬆ Load Model", **Then** the bot prompts for the model identifier; after the user sends the input, the model is loaded and a confirmation is posted.
4. **Given** the Model Management sub-menu is open, **When** the user taps "⬇ Unload Model", **Then** the bot prompts for the identifier to unload; after input the model is unloaded and a confirmation is posted.
5. **Given** LM Studio is unreachable, **When** any model action is triggered, **Then** a user-friendly error is shown.

---

### User Story 3 - Chat Sessions Section (Priority: P3)
From the Chat Sessions sub-menu the user can create a new chat, view the list of chats, switch the active chat, and remove a chat — all via inline buttons. The list of chats is presented as a dynamic set of buttons (one per session) when needed.

**Why this priority**: Chat session management is the second most common workflow; managing sessions via buttons is far more usable than remembering opaque IDs.

**Independent Test**: Open menu → tap "Chat Sessions" → tap "➕ New Chat" → verify confirmation and return to Chat Sessions sub-menu. Tap "🗂 List Chats" → verify each existing chat appears as a selectable button. Tap a chat button → verify active session switches and confirmation is shown.

**Acceptance Scenarios**:
1. **Given** the Chat Sessions sub-menu is open, **When** the user taps "➕ New Chat", **Then** the bot prompts for an optional name; after input a new session is created and confirmed.
2. **Given** the Chat Sessions sub-menu is open, **When** the user taps "🗂 List Chats", **Then** the menu message is updated to show one button per chat session plus a "⬅ Back" button.
3. **Given** the chat list is displayed, **When** the user taps a chat button, **Then** that chat becomes active and the menu returns to the Chat Sessions sub-menu with confirmation.
4. **Given** the Chat Sessions sub-menu is open, **When** the user taps "🗑 Remove Chat", **Then** the bot shows the chat list as buttons; tapping a chat button removes that session with confirmation.
5. **Given** no chats exist, **When** the user taps "🗂 List Chats", **Then** a message indicates no chats and offers to create one.

---

### User Story 4 - Inference Section (Priority: P4)
From the Inference sub-menu the user can see the currently active model, send a new message for inference, and regenerate the last model answer directly — without needing to know any slash commands.

**Why this priority**: Inference is the core bot capability; the button path makes it discoverable for new users, while preserving parity with the existing direct text and `/regenerate` workflows.

**Independent Test**: Open menu → tap "Inference" → verify the sub-menu displays the active model name plus "💬 Send Message" and "🔄 Regenerate" buttons. Tap "💬 Send Message" → bot prompts for message text → user sends text → verify the response is streamed in the chat. If a prior assistant response exists, tap "🔄 Regenerate" → verify the last answer is regenerated.

**Acceptance Scenarios**:
1. **Given** the Inference sub-menu is open, **Then** the name of the currently active model is displayed, or "No model loaded" if none is active.
2. **Given** the Inference sub-menu is open, **When** the user taps "💬 Send Message", **Then** the bot prompts the user to type their message; after input the response is streamed to the chat.
3. **Given** the Inference sub-menu is open and a prior assistant response exists, **When** the user taps "🔄 Regenerate", **Then** the bot regenerates the last answer and streams the replacement response.
4. **Given** no model is loaded, **When** the user taps either inference action, **Then** the bot shows an error advising the user to load a model first.
5. **Given** the Inference sub-menu is open, **When** the user taps "⬅ Back", **Then** the menu returns to the main menu.

---

### User Story 5 - Settings Section (Priority: P5)
From the Settings sub-menu the user can update the system prompt and adjust inference parameters (temperature, max tokens, top-p) for the active chat session — all via inline button triggers and guided text input prompts.

**Why this priority**: Settings are less frequently changed and depend on an active session existing, making them lower priority than session management and inference.

**Independent Test**: Open menu → tap "Settings" → tap "📝 System Prompt" → bot prompts for new prompt text → user sends text → bot confirms update. Tap "🌡 Temperature" → bot prompts for value → user sends value → bot confirms.

**Acceptance Scenarios**:
1. **Given** an active chat exists, **When** the user taps "📝 System Prompt" in the Settings sub-menu, **Then** the bot prompts for a new prompt; after input the system prompt is updated and confirmed.
2. **Given** an active chat exists, **When** the user taps any inference parameter button (Temperature, Max Tokens, Top-P), **Then** the bot prompts for the new value; after valid input the setting is updated and confirmed.
3. **Given** the user provides an out-of-range value, **When** input is submitted, **Then** the bot shows a validation error and prompts again.
4. **Given** no active chat session exists, **When** the user opens the Settings sub-menu, **Then** a message advises the user to create a chat first.

---

### User Story 6 - Help Section (Priority: P6)
From the Help sub-menu the user can view a concise reference for each section. Help content is shown by editing the menu message and can be dismissed back to the main menu via "⬅ Back".

**Why this priority**: Help is supplementary and only needed occasionally; all other sections are more critical to daily use.

**Independent Test**: Open menu → tap "Help" → tap "Model Management Help" → verify usage text appears inline. Tap "⬅ Back" → verify return to Help sub-menu. Tap "⬅ Back" again → verify return to main menu.

**Acceptance Scenarios**:
1. **Given** the Help sub-menu is open, **When** the user taps a help topic button, **Then** the menu message is edited to display the relevant help text and a "⬅ Back" button.
2. **Given** a help topic is displayed, **When** the user taps "⬅ Back", **Then** the menu returns to the Help sub-menu.
3. **Given** the Help sub-menu is open, **When** the user taps "⬅ Back", **Then** the menu returns to the main menu.

---

### Edge Cases

- What happens when the menu message has been deleted by the user? → Bot re-creates the menu from scratch on the next `/menu` command.
- What happens when a user interacts with an expired inline keyboard (after bot restart)? → The bot answers with a graceful "Menu expired — opening a fresh menu." notice, clears stale state, and sends a fresh main menu.
- What happens when an input prompt is cancelled (user sends `/menu` instead of replying)? → The pending input state is cleared and the main menu is shown.
- What happens when the user taps a menu button multiple times rapidly? → Idempotent: the bot treats duplicate taps and "message is not modified" edit responses as harmless no-ops.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The bot MUST present all existing user-facing functionality through inline keyboard buttons grouped into five top-level sections: Model Management, Chat Sessions, Settings, Inference, and Help.
- **FR-002**: The bot MUST edit the existing menu message in place when navigating between menu levels; no additional messages are sent for navigation.
- **FR-003**: Every sub-menu and nested view MUST include a "⬅ Back" button that returns the user to the parent menu level.
- **FR-004**: The commands `/start` and `/menu` MUST open or refresh the main menu, re-using the existing menu message where possible.
- **FR-005**: Actions requiring free-text input (model name, prompt text, setting value) MUST guide the user via a reply prompt; after input is received, the result is posted and the pending input state is cleared. While a prompt is active, the next plain-text message MUST be consumed as that prompt answer and MUST NOT trigger inference.
- **FR-006**: Sending `/menu` while a text input prompt is active MUST cancel the pending input and display the main menu.
- **FR-007**: The bot MUST restrict all menu interactions to the single pre-configured owner; unauthorized users receive "⛔ Access denied."
- **FR-008**: Plain text messages, photo messages, and the existing `/regenerate` command sent outside the menu MUST continue to trigger inference as before, preserving existing behaviour.
- **FR-009**: The bot MUST recover gracefully from stale or missing menu messages by notifying the user that the menu expired and generating a fresh menu on the current or next interaction.
- **FR-010**: The Inference sub-menu MUST display the currently active model name and provide both a "💬 Send Message" action and a "🔄 Regenerate" action.

### Key Entities

- **Menu State**: Tracks the currently displayed menu level (main, section sub-menu, nested list, help topic) for the active conversation.
- **Pending Input**: Records when the bot is awaiting free-text input from the user in response to a button action, and which action will consume that input.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The user can reach any feature within two button taps from the main menu.
- **SC-002**: Navigating between menu levels produces zero additional messages in the chat; all navigation updates the same message in place.
- **SC-003**: All existing functionality accessible via text commands remains accessible via the button menu.
- **SC-004**: A first-time user can complete a full workflow (open menu → load model → create chat → send message) without knowing any slash commands.

## Assumptions

- The existing command-based handlers (`/models`, `/load`, etc.) remain in place and continue to work; the button menu is additive, not a replacement.
- The `/help` command remains available as a text-based reference, while the Help section exposes the same guidance via inline buttons.
- A single persistent menu message per conversation is sufficient given the single-user nature of the bot.
- Inline keyboard limits (8 buttons per row, 100 buttons total) are not a concern given the bounded set of features.
- The Telegram Bot API `editMessageText` / `editMessageReplyMarkup` calls are used for in-place navigation; rate limits are handled by the `python-telegram-bot` library.
- The bot owner is the only user, so no concurrent state management for menu or pending input is required.

## Out of Scope

- Replacing or removing existing slash commands.
- Persistent menu pinning (pinned messages in the chat).
- Menu localisation or multiple languages.
- Multi-step wizard flows beyond a single prompted text input.
- Editing stop sequences (`settings.stop`) via the button menu in this version.
- Graphical or web-based UI.

## Open Questions

None at this time.
