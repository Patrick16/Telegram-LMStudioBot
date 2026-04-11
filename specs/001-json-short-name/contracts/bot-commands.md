# Bot Command Contract

**Feature**: 001-json-short-name  
**Date**: 2026-04-11  
**Interface type**: Telegram Bot Commands

This document defines the complete public interface of the LMStudioBot — every command a user can send, its arguments, and expected responses.

---

## Authorization

Every command and message is protected by single-user authorization. If the sender's Telegram user ID does not match `TELEGRAM_OWNER_ID`, the bot responds with:

```
⛔ Access denied.
```

---

## Model Management Commands

### `/models`
List all models available on disk.

**Arguments**: none  
**Success response**:
```
📦 Available models:
• qwen/qwen3-4b
• mistral/mistral-7b-instruct
• llava/llava-1.6-mistral-7b
```
**Error response** (LM Studio unreachable):
```
❌ Could not connect to LM Studio. Is it running?
```

---

### `/loaded`
List models currently loaded in memory.

**Arguments**: none  
**Success response**:
```
🧠 Loaded models:
• qwen/qwen3-4b [identifier: my-model]
```
**Error response**: same as `/models`

---

### `/load <model> [options]`
Load a model into LM Studio memory.

**Arguments**:  
- `<model>` — model path/identifier (required)  
- `gpu=max|auto|<0.0-1.0>` — GPU offload (optional, default: `auto`)  
- `ctx=<N>` — context length in tokens (optional, uses model default if omitted)  
- `id=<name>` — stable identifier (optional)

**Example**:
```
/load qwen/qwen3-4b gpu=max ctx=4096 id=mymodel
```
**Success response**:
```
✅ Model qwen/qwen3-4b loaded successfully.
```
**Error responses**:
```
❌ Model not found: qwen/qwen3-4b
❌ Invalid gpu value: must be max, auto, or a float between 0.0 and 1.0
❌ Load failed: <reason from lms>
```

---

### `/unload <model_or_identifier>`
Unload a loaded model from memory.

**Arguments**:  
- `<model_or_identifier>` — model path or identifier (required)

**Success response**:
```
✅ Model qwen/qwen3-4b unloaded.
```
**Error response**:
```
❌ Model not loaded: qwen/qwen3-4b
```

---

## Settings Commands

### `/setprompt [<prompt>]`
Set the system prompt for the active chat session. If no prompt is given, clears the system prompt.

**Arguments**:  
- `<prompt>` — system prompt text (optional; omit to clear)

**Success responses**:
```
✅ System prompt updated.
✅ System prompt cleared.
```
**Error response**:
```
❌ No active chat. Use /newchat first.
```

---

### `/set <setting> <value>`
Adjust an inference parameter for the active chat session.

**Supported settings**:

| Setting | Type | Range |
|---------|------|-------|
| `temperature` | float | 0.0 – 2.0 |
| `max_tokens` | int | -1 or ≥ 1 |
| `top_p` | float | 0.0 – 1.0 |

**Example**:
```
/set temperature 0.7
/set max_tokens 512
```
**Success response**:
```
✅ temperature set to 0.7
```
**Error responses**:
```
❌ Unknown setting: <name>. Valid: temperature, max_tokens, top_p
❌ Invalid value for temperature: must be a float between 0.0 and 2.0
❌ No active chat. Use /newchat first.
```

---

## Chat Session Commands

### `/newchat [<name>]`
Create a new chat session and make it active.

**Arguments**:  
- `<name>` — optional session name (default: `Chat <N>`)

**Success response**:
```
💬 New chat "Code Review" created and activated.
```

---

### `/chats`
List all chat sessions.

**Success response**:
```
💬 Your chats:
[1] ▶ Code Review (qwen/qwen3-4b) — 5 messages
[2]   General Chat — 12 messages
```
(`▶` marks the active session)

---

### `/switchchat <id_or_number>`
Switch the active chat session.

**Arguments**:  
- `<id_or_number>` — session ID (UUID prefix accepted) or list number from `/chats`

**Success response**:
```
✅ Switched to "General Chat".
```
**Error response**:
```
❌ Chat not found: <id>
```

---

### `/removechat <id_or_number>`
Delete a chat session and its history.

**Arguments**:  
- `<id_or_number>` — session ID or list number from `/chats`

**Success response**:
```
🗑 Chat "Code Review" removed.
```
**Error responses**:
```
❌ Chat not found: <id>
```
> If the removed session was active, the next available session is auto-selected, or the user is prompted to create one.

---

## Inference Commands

### (Any plain text message)
Send a message to the model in the active chat session and stream the response.

**Preconditions**: Active chat session exists; a model is loaded in LM Studio.  
**Success response**: Streamed model reply.  
**Error responses**:
```
❌ No active chat. Use /newchat first.
❌ No model loaded. Use /load <model> first.
❌ LM Studio is unreachable.
```

---

### `/regenerate`
Regenerate the last model answer in the active chat. Removes the last assistant message from history and re-submits the last user message.

**Success response**: New streamed model reply (same format as plain message).  
**Error responses**:
```
❌ Nothing to regenerate (no messages in this chat).
❌ No active chat. Use /newchat first.
```

---

## Vision Input

### (Photo message)
Attach and send a photo to the model in the active chat session (vision-capable models only).

**Preconditions**: Active chat; vision-capable model loaded.  
**Behaviour**: Bot downloads highest-resolution photo from Telegram, passes it with any caption text to the model.  
**Success response**: Streamed model reply describing/analyzing the image.  
**Error responses**:
```
❌ The loaded model does not support image input.
❌ No active chat. Use /newchat first.
❌ No model loaded. Use /load <model> first.
```

---

## Help Command

### `/start` / `/help`
Show command overview.

**Response**: Formatted list of all commands with brief descriptions.
