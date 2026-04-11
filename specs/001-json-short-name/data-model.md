# Data Model: Telegram-LMStudio Integration Bot

**Feature**: 001-json-short-name  
**Date**: 2026-04-11

---

## Entities

### ChatSession

Represents a single isolated conversation context between the user and a model.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `id` | `str` (UUID4) | Unique identifier for the session | Non-empty, unique |
| `name` | `str` | User-assigned display name | Max 64 chars, non-empty |
| `model_identifier` | `str \| None` | Model loaded for this session (LM Studio model path/identifier) | Optional; validated against available models when set |
| `system_prompt` | `str` | System prompt injected at the start of each inference call | Default: `""`, max 4096 chars |
| `settings` | `ModelSettings` | Inference configuration for this session | See ModelSettings below |
| `history` | `list[ChatMessage]` | Ordered list of messages in this session | Max entries enforced by context window |
| `created_at` | `str` (ISO 8601) | Timestamp when session was created | Auto-set on creation |
| `updated_at` | `str` (ISO 8601) | Timestamp of last activity | Auto-updated on every message |

**State Transitions:**
```
created → active (message sent or model loaded)
active  → active (messages sent, settings changed)
active  → deleted (/removechat)
```

---

### ChatMessage

A single message within a `ChatSession` history.

| Field | Type | Description | Validation |
|-------|------|-------------|------------|
| `role` | `Literal["user", "assistant"]` | Message sender role | One of: `user`, `assistant` |
| `content` | `str` | Text content of the message | Non-empty |
| `image_path` | `str \| None` | Local path to a downloaded image for vision messages | Optional; must be valid path if set |
| `timestamp` | `str` (ISO 8601) | When the message was created | Auto-set |

---

### ModelSettings

Inference configuration parameters applied per chat session.

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `temperature` | `float` | `0.7` | 0.0–2.0 |
| `max_tokens` | `int` | `-1` (unlimited) | -1 or ≥ 1 |
| `top_p` | `float` | `1.0` | 0.0–1.0 |
| `stop` | `list[str]` | `[]` | Max 4 stop strings, each max 64 chars |

---

### LoadConfig

Parameters used when loading a model into LM Studio memory via `lms load`.

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `gpu` | `str` | `"auto"` | One of: `"max"`, `"auto"`, or float string `"0.0"`–`"1.0"` |
| `context_length` | `int \| None` | `None` (model default) | ≥ 512 if set |
| `identifier` | `str \| None` | `None` | Max 64 chars if set |

---

### SessionStore (aggregate)

Top-level object serialized to `sessions.json`.

| Field | Type | Description |
|-------|------|-------------|
| `active_session_id` | `str \| None` | ID of the currently active `ChatSession` |
| `sessions` | `dict[str, ChatSession]` | All sessions, keyed by `ChatSession.id` |

---

## Relationships

```
SessionStore
  └── sessions: dict[str, ChatSession]   (1 store → many sessions)
        ├── settings: ModelSettings       (1 session → 1 settings object)
        └── history: list[ChatMessage]    (1 session → ordered messages)
```

---

## Validation Rules

1. A `ChatSession` cannot be set as active if it has been deleted.
2. `ChatMessage.role` must alternate between `user` and `assistant` in normal flow; back-to-back same roles are permitted only for system injection.
3. `ModelSettings.temperature` of `0.0` produces deterministic output; this is permitted but should be noted to the user.
4. `LoadConfig.gpu` float values outside `0.0`–`1.0` must be rejected before invoking `lms load`.
5. `ChatSession.model_identifier` is optional; if not set, the session uses whatever model is currently loaded in LM Studio.

---

## Persistence Format (sessions.json)

```json
{
  "active_session_id": "a1b2c3d4-...",
  "sessions": {
    "a1b2c3d4-...": {
      "id": "a1b2c3d4-...",
      "name": "Code Review",
      "model_identifier": "qwen/qwen3-4b",
      "system_prompt": "You are a senior Python code reviewer.",
      "settings": {
        "temperature": 0.5,
        "max_tokens": -1,
        "top_p": 1.0,
        "stop": []
      },
      "history": [
        {
          "role": "user",
          "content": "Review this function...",
          "image_path": null,
          "timestamp": "2026-04-11T10:00:00Z"
        },
        {
          "role": "assistant",
          "content": "The function looks good, but...",
          "image_path": null,
          "timestamp": "2026-04-11T10:00:05Z"
        }
      ],
      "created_at": "2026-04-11T09:55:00Z",
      "updated_at": "2026-04-11T10:00:05Z"
    }
  }
}
```
