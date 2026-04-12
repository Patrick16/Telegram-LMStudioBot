# Contract: Storage Schemas

**Feature**: `004-model-settings-sessions`  
**Purpose**: Define the persisted file shapes introduced or changed by this feature.

---

## 1. Session Metadata File

**Path**: `data/sessions.json`

```json
{
  "active_session_id": "0d4d3e8e-6e6d-4d9e-91de-1f4a6b6d2b1a",
  "sessions": {
    "0d4d3e8e-6e6d-4d9e-91de-1f4a6b6d2b1a": {
      "id": "0d4d3e8e-6e6d-4d9e-91de-1f4a6b6d2b1a",
      "name": "Research Chat",
      "model_identifier": "qwen/qwen3-4b",
      "settings": {
        "temperature": 0.7,
        "max_tokens": 512,
        "top_p": 0.95,
        "top_k": 40,
        "repeat_penalty": 1.05,
        "stop_strings": [],
        "seed": null,
        "history_policy": {
          "mode": "fit_budget_recent",
          "message_pair_limit": null
        }
      },
      "created_at": "2026-04-11T10:00:00+00:00",
      "updated_at": "2026-04-11T10:15:00+00:00"
    }
  }
}
```

### Contract Rules

- `history` is not stored inline in this file.
- `settings` in this file contains session-scoped prompt/generation settings only.
- `active_session_id` may be `null`.

---

## 2. Session History File

**Path pattern**: `data/histories/<session_id>.json`

```json
{
  "session_id": "0d4d3e8e-6e6d-4d9e-91de-1f4a6b6d2b1a",
  "messages": [
    {
      "role": "user",
      "content": "Summarize this file",
      "image_path": null,
      "timestamp": "2026-04-11T10:00:10+00:00"
    },
    {
      "role": "assistant",
      "content": "Here is the summary...",
      "image_path": null,
      "timestamp": "2026-04-11T10:00:13+00:00"
    }
  ],
  "updated_at": "2026-04-11T10:15:00+00:00"
}
```

### Contract Rules

- File name session id and `session_id` field must match.
- Deleting a chat session deletes this file.
- Missing file is treated as empty history, not a fatal store error.

---

## 3. Model Presets File

**Path**: `data/model-presets.json`

```json
{
  "presets": [
    {
      "name": "32k Balanced",
      "description": "Context-heavy profile for longer tasks",
      "settings": {
        "gpu": "auto",
        "context_length": 32768,
        "identifier": "qwen-32k"
      }
    }
  ]
}
```

### Contract Rules

- Contains only model-scoped runtime settings.
- Menu may browse and apply these presets but does not write this file.

---

## 4. Session Presets File

**Path**: `data/session-presets.json`

```json
{
  "presets": [
    {
      "name": "Precise Coding",
      "description": "Lower randomness and bounded length",
      "settings": {
        "temperature": 0.2,
        "max_tokens": 700,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.05,
        "stop_strings": [],
        "seed": 42,
        "history_policy": {
          "mode": "last_n_pairs",
          "message_pair_limit": 6
        }
      }
    }
  ]
}
```

### Contract Rules

- Contains only session-scoped prompt/generation settings.
- Menu may browse and apply these presets but does not write this file.
- `message_pair_limit` is required only when `mode` is `last_n_pairs`.