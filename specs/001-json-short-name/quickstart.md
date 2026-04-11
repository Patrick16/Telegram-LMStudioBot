# Quickstart: Telegram-LMStudio Integration Bot

**Feature**: 001-json-short-name  
**Date**: 2026-04-11

---

## Prerequisites

1. **LM Studio installed** with at least one model downloaded.
2. **`lms` CLI** available in `PATH` (ships with LM Studio).
3. **Python 3.11+** installed.
4. **A Telegram Bot token** — create via [@BotFather](https://t.me/BotFather).
5. **Your Telegram user ID** — get it from [@userinfobot](https://t.me/userinfobot).

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd LMStudioBot
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_OWNER_ID=123456789
LMS_HOST=localhost
LMS_PORT=1234
SESSIONS_FILE=data/sessions.json
LOG_LEVEL=INFO
```

### 3. Start LM Studio (headless)

```bash
# Option A: Using the daemon (headless, no GUI)
lms daemon up
lms server start

# Option B: Launch LM Studio GUI, enable Local Server in settings
```

### 4. Run the bot

```bash
python -m src.bot.main
```

---

## Quick Usage

Once the bot is running, open Telegram and message your bot:

```
/help              — Show all commands
/models            — List available models
/load qwen/qwen3-4b gpu=auto ctx=4096
/newchat My Chat
Hello, who are you?
/set temperature 0.5
/setprompt You are a Python expert.
/regenerate
```

To send an image for a vision model:
1. Load a vision-capable model: `/load llava/llava-1.6 gpu=max`
2. Send a photo in the chat — the bot will forward it to the model.

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/
```
