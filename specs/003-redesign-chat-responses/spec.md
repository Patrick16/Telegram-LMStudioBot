# Feature Specification: Redesign Chat Responses

**Feature Branch**: `003-redesign-chat-responses`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "i want redesign responses in chat. list of models should give simple list of models with their sizes, don't use table format. command 'load model' should give clickable list of models with their size. when user clicks on model, the model is loading in lm studio. command 'unload model' should give clickable list of loaded models. when user clicks on model, the model is unloading in lm studio. chat responses should be reconverted to telegram formats. there should not be markdown syntax. code snippets in responses (usually it is wrapped like: ```<code>```) should be formated as monospace in telegram, to be able copy this snippet from response. do not include <think> </think> section in responses."

## Clarifications

### Session 2026-04-11

- Q: How should streaming intermediate updates be handled given think-tag stripping and code formatting? → A: Show `⏳ Thinking...` static placeholder during the think/streaming phase; apply all formatting (strip think tags, convert code blocks, HTML-escape) only to the final fully assembled response before the last edit.
- Q: What happens to the load/unload inline keyboard message when the user taps a model button? → A: Edit the keyboard message in place — show `⏳ Loading <model>…` while the operation runs, then replace with `✅ Loaded <model>.` (or an error) when complete.
- Q: Should already-loaded models appear in the Load Model keyboard? → A: Yes — show all models; prefix already-loaded ones with `🟢` so the user can see which are active and still reload intentionally.
- Q: How should the bot obtain the model list to build keyboards and plain lists? → A: Use the lmstudio Python SDK exclusively (no CLI shelling); call `lmstudio.Client()` methods to list downloaded and loaded models.
- Q: Should `/loaded` (currently loaded models) also be reformatted as a plain bulleted list? → A: Yes — reformat `/loaded` to the same `• <name>  <size>` plain list style for consistency with `/models`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Plain Model Listing (Priority: P1)

The user sends `/models` (or taps "List Models" in the menu). Instead of a table, they receive a plain bulleted list showing each model's name and size. The output is immediately readable without any markdown rendering issues in Telegram.

**Why this priority**: The most frequently used informational command. Malformed table output appears every time it is used.

**Independent Test**: Send `/models` with LM Studio running. Verify a plain text list (no `|` table characters, no markdown headers) appears with at least one model name and its file size.

**Acceptance Scenarios**:

1. **Given** LM Studio has models on disk, **When** the user requests the model list, **Then** the bot replies with a plain bulleted list, one model per line, each line showing the model name and its size (e.g. `• qwen/qwen3-4b  3.2 GB`).
2. **Given** LM Studio is unreachable, **When** the user requests the model list, **Then** the bot replies with a clear error message.
3. **Given** no models are on disk, **When** the user requests the model list, **Then** the bot replies with "No models found."

---

### User Story 2 - Clickable Load Model List (Priority: P1)

Instead of typing a model identifier to load, the user taps "Load Model" (via the menu or `/load` with no arguments). The bot presents an inline keyboard with one button per available model, each labelled with the model name and size. Tapping a button loads that model in LM Studio without any further typing.

**Why this priority**: Typing long model identifiers is error-prone. A clickable list is the primary UX improvement in this feature.

**Independent Test**: Tap "⬆ Load Model" in the menu (or `/load` with no args). Verify an inline keyboard appears with model buttons. Tap one. Verify a confirmation message appears and the model loads in LM Studio.

**Acceptance Scenarios**:

1. **Given** models are available on disk, **When** the user triggers load-model without arguments, **Then** the bot shows an inline keyboard with one button per model (label: `name  size`).
2. **Given** the user taps a model button, **When** the callback is received, **Then** the bot starts loading and replies with a confirmation on success.
3. **Given** LM Studio is unreachable or the model fails to load, **When** the user taps a button, **Then** the bot replies with a meaningful error.
4. **Given** no models exist on disk, **When** the user triggers load-model without arguments, **Then** the bot replies with "No models available to load."
5. **Given** the user sends `/load <identifier>` with an explicit identifier, **When** the command is processed, **Then** the existing direct-load behaviour is unchanged.

---

### User Story 3 - Clickable Unload Model List (Priority: P1)

The user taps "Unload Model" (via the menu or `/unload` with no arguments). The bot presents an inline keyboard listing only the currently loaded models. Tapping a button unloads that model without further text input.

**Why this priority**: Symmetric with US2 — same UX improvement for the unload path.

**Independent Test**: Load a model first, then tap "⬇ Unload Model". Verify inline buttons showing only loaded models appear. Tap one. Verify confirmation and the model is unloaded.

**Acceptance Scenarios**:

1. **Given** one or more models are loaded, **When** the user triggers unload-model without arguments, **Then** the bot shows an inline keyboard with one button per loaded model.
2. **Given** the user taps a loaded model button, **When** the callback is received, **Then** the bot unloads it and confirms.
3. **Given** no models are currently loaded, **When** the user triggers unload-model without arguments, **Then** the bot replies with "No models are currently loaded."
4. **Given** the user sends `/unload <identifier>` with an explicit identifier, **When** the command is processed, **Then** the existing direct-unload behaviour is unchanged.

---

### User Story 4 - Telegram-Safe Response Formatting (Priority: P2)

All chat responses (inference output) are sanitised before delivery. Markdown syntax characters (`*`, `_`, `` ` ``, `[`, `]`, `~`, `>`, `#`) that would be interpreted by Telegram as invisible formatting are escaped so the user sees the plain text the model intended to send.

**Why this priority**: Broken markdown is visually noisy but does not block core functionality, hence P2.

**Independent Test**: Prompt the model to produce a response containing `**bold**`, `_italic_`, and `[link](url)`. Verify the raw characters appear in the Telegram message rather than being silently consumed.

**Acceptance Scenarios**:

1. **Given** a model response contains markdown emphasis syntax (`*word*`, `**word**`, `_word_`), **When** the bot sends it, **Then** the asterisks and underscores appear literally in Telegram — they are not hidden.
2. **Given** a model response is plain prose with no special characters, **When** the bot sends it, **Then** it is delivered unchanged.

---

### User Story 5 - Code Snippets as Telegram Monospace (Priority: P2)

Code blocks delimited by triple backticks in model responses are converted to Telegram's monospace block, so the user can read and copy code cleanly with a single tap.

**Why this priority**: Code formatting is the most common structured output format from LLMs; it significantly improves readability and usability.

**Independent Test**: Ask the model to write a Python function. Verify the bot's reply shows the code in a fixed-width copyable block in Telegram.

**Acceptance Scenarios**:

1. **Given** the model response includes a fenced code block (` ```python\n…\n``` `), **When** the bot sends it, **Then** the code appears in a Telegram monospace/pre block.
2. **Given** the code block has a language tag, **When** the bot sends it, **Then** the language tag does not appear as raw text in the output.
3. **Given** the response has multiple code blocks, **When** the bot sends it, **Then** each is individually formatted as monospace.
4. **Given** the response has inline code (single backtick), **When** the bot sends it, **Then** it is rendered as Telegram inline code.

---

### User Story 6 - Strip Think Tags from Responses (Priority: P2)

Reasoning model responses often include a `<think>…</think>` block containing internal chain-of-thought. The bot strips this block entirely before sending so the user only sees the final answer.

**Why this priority**: Think-tag output is internal reasoning noise that leaks model internals and is distracting.

**Independent Test**: Use a reasoning model (e.g. qwen3 with thinking enabled). Send a message. Verify the bot's reply does not contain `<think>` or `</think>` tags and does not show thinking content.

**Acceptance Scenarios**:

1. **Given** a response contains a `<think>…</think>` block, **When** the bot receives it, **Then** the entire block (tags and content) is removed before sending.
2. **Given** a response contains multiple `<think>` blocks, **When** processed, **Then** all blocks are removed.
3. **Given** a response has no `<think>` block, **When** the bot sends it, **Then** the response is unaffected.
4. **Given** a streaming response where the `<think>` block spans multiple chunks, **When** the full response is assembled, **Then** the block is stripped from the final result before display.
5. **Given** the entire response is a think block with nothing else, **When** stripped, **Then** the bot sends "*(no response)*" rather than an empty message.

---

### Edge Cases

- What if the model list is very long (100+ models)? Inline keyboards are limited to 100 buttons — the list is truncated with a note appended.
- What if a model identifier contains characters that break button labels? The label is truncated to 64 characters (Telegram button text limit); the `🟢` prefix is included in the 64-character count.
- What if a `<think>` block is not properly closed? Strip from `<think>` to the next `</think>` or to end-of-string, whichever comes first.
- What if a response consists entirely of a think block? The bot sends "*(no response)*" rather than an empty message.
- What if code block conversion and think-tag stripping interact? Think tags are stripped first, then code formatting is applied.
- What if HTML special characters (`<`, `>`, `&`) appear in plain text outside code blocks? They are escaped to prevent broken HTML parse mode rendering.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `/models` command and "List Models" menu button MUST reply with a plain bulleted list (one model per line, format: `• <name>  <size>`), with no table syntax or markdown headers.
- **FR-002**: The "Load Model" action triggered without arguments MUST present an inline keyboard listing all available models; models that are already loaded MUST be prefixed with `🟢` in their button label; each button label MUST show the model name and size; selecting a button MUST trigger loading that model without further text input; the keyboard message MUST be edited in place to show `⏳ Loading <model>…` during the operation and `✅ Loaded <model>.` (or an error message) on completion.
- **FR-003**: The "Unload Model" action triggered without arguments MUST present an inline keyboard listing only currently loaded models; selecting a button MUST trigger unloading that model without further text input; the keyboard message MUST be edited in place to show `⏳ Unloading <model>…` during the operation and `✅ Unloaded <model>.` (or an error message) on completion.
- **FR-004**: When no models are on disk, the load-model action MUST reply "No models available to load." instead of showing an empty keyboard.
- **FR-005**: When no models are loaded, the unload-model action MUST reply "No models are currently loaded." instead of showing an empty keyboard.
- **FR-006**: All inference responses MUST be delivered using Telegram HTML parse mode; markdown syntax characters in model output MUST be HTML-escaped so they appear as literal characters.
- **FR-007**: Fenced code blocks (` ```…``` `) in model responses MUST be converted to `<pre><code>…</code></pre>` HTML blocks before sending.
- **FR-008**: Inline code (single backtick) in model responses MUST be converted to `<code>…</code>` HTML tags before sending.
- **FR-009**: The `<think>…</think>` block (and all its content) MUST be stripped from every response before it is sent.
- **FR-010**: If stripping think tags produces an empty or whitespace-only response, the bot MUST send "*(no response)*" instead of sending nothing.
- **FR-011**: HTML special characters (`<`, `>`, `&`) in plain-text portions of a response (outside code blocks) MUST be escaped before sending in HTML parse mode.
- **FR-012**: Inline keyboard button labels MUST be truncated to 64 characters and the total button count per keyboard MUST NOT exceed 100; if truncation occurs, a note MUST inform the user.
- **FR-013**: `/load <identifier>` and `/unload <identifier>` with explicit arguments MUST continue to work as before (no regression).
- **FR-014**: The `/loaded` command MUST reply with a plain bulleted list of currently loaded models in the same format as FR-001 (`• <name>  <size>`); no table syntax or markdown headers.

### Key Entities

- **ModelEntry**: A model discovered via `lmstudio.Client().list_downloaded_models()` (SDK type: `DownloadedModel`), with key attributes `.model_key` (str) and `.info.size_bytes` (int). Display format: `• {model_key}  {_format_size(info.size_bytes)}`. Used to build list displays and load keyboards.
- **LoadedModelEntry**: A model currently in memory discovered via `lmstudio.Client().list_loaded_models()` (SDK type: `SyncModelHandle`); call `.get_info()` to obtain `LlmInstanceInfo` with `.identifier` (str) and `.size_bytes` (int). Display format: `• {identifier}  {_format_size(size_bytes)}`. Used to build the unload keyboard.
- **FormattedResponse**: The cleaned output string ready for Telegram: think tags stripped, code blocks converted to HTML `<pre>/<code>`, plain text HTML-escaped.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can load any model by tapping two elements only (Load Model action → model button), with zero text typing required.
- **SC-002**: A user can unload any loaded model by tapping two elements only (Unload Model action → model button), with zero text typing required.
- **SC-003**: 100% of responses containing `<think>` blocks are delivered without the think content visible to the user.
- **SC-004**: 100% of responses containing fenced code blocks are delivered with the code in a copyable monospace block in Telegram.
- **SC-005**: 100% of responses are delivered without raw markdown syntax characters silently consumed by Telegram's renderer.

## Assumptions

- The lmstudio Python SDK (`lmstudio.Client()`) is used exclusively to fetch model lists; no CLI (`lms ls` / `lms ps`) shelling is performed.
- `lmstudio.Client().list_downloaded_models()` returns `DownloadedModel` objects with `.model_key` (str) and `.info.size_bytes` (int) sufficient to render `• <model_key>  <size>` lines.
- `lmstudio.Client().list_loaded_models()` returns `SyncModelHandle` objects; calling `.get_info()` on each yields `LlmInstanceInfo` with `.identifier` (str) and `.size_bytes` (int) sufficient to render unload keyboard buttons.
- Response formatting applies to all text output paths: direct chat (`text_message_handler`), vision (`photo_message_handler`), and menu-driven inference (`_execute_inference_send`, `_execute_inference_regenerate`).
- Streaming responses accumulate the full text before conversion; during streaming the bot displays a static `⏳ Thinking...` placeholder and does NOT apply incremental formatting updates; all formatting (think-tag stripping, code conversion, HTML escaping) is applied once to the complete assembled string, and a single final edit replaces the placeholder.
- Think-tag stripping uses a non-greedy regex (`<think>.*?</think>`) with `re.DOTALL` to handle multi-line blocks and multiple blocks correctly.
- The inline load/unload keyboard replaces the pending-input text prompt for the no-argument case; the menu `pending_input` flow for `models:load` and `models:unload` is replaced by a direct inline keyboard response.

