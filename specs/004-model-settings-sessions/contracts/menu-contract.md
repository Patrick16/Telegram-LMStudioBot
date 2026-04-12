# Contract: Menu and Interaction Flow

**Feature**: `004-model-settings-sessions`  
**Purpose**: Define the menu-level interaction contract introduced by this feature.

---

## 1. Top-Level Menu Contract

The main menu removes the Inference section and exposes Regenerate directly at the top level.

### Required top-level actions

- `Model Management`
- `Chat Sessions`
- `Settings`
- `Regenerate`
- `Help`

### Required behavior

- Regenerate is reachable from the main menu without entering a submenu.
- Plain text chat input outside the menu still triggers normal inference.
- The persistent menu message is not auto-deleted.

---

## 2. Settings Menu Contract

The Settings area must distinguish scope explicitly.

### Required sections

- `Current Settings`
- `Model Settings`
- `Session Settings`
- `Model Presets`
- `Session Presets`
- `History Reuse Policy`

### Required behavior

- Model settings edit only model-scoped runtime fields.
- Session settings edit only session-scoped prompt/generation fields.
- Preset menus browse and apply existing presets only.
- Current Settings presents both scopes in one user-readable summary.

---

## 3. Pending Input Contract

When a setting requires free-text input, the next plain-text message is consumed by that pending action and is not treated as inference.

### Required pending-input key groups

- `settings:model:*`
- `settings:session:*`
- `settings:history_policy:*`
- Existing chat/session prompts that remain text-driven

### Required behavior

- `/menu` clears active pending input and returns the user to the main menu.
- Validation errors keep the pending key active only when retrying the same field is useful.

---

## 4. Temporary Command Message Contract

### Messages that must auto-delete after 5 seconds

- command confirmations
- command validation errors
- list/readout result messages
- menu-generated non-navigation status messages

### Messages that must not auto-delete

- the persistent menu message
- normal assistant chat replies
- image/chat inference responses
- the final visible conversation transcript stored in session history

### Failure behavior

- If a temporary message was already removed, deletion failure is logged quietly and no user-facing error is shown.