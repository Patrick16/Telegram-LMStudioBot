# LMStudioBot

A Telegram bot for local LLM chat using [LM Studio](https://lmstudio.ai) as the backend. Features session-aware chat, inline settings, model/session presets, and persistent history.

## Features
- 💬 Multi-session chat with per-session history
- ⚙️ Inline menu for model & session settings
- 📦 Model and session preset support
- 🔄 Regenerate, switch, and remove chats
- 🗑️ Ephemeral command replies (auto-delete)
- 🖼️ Vision (image input) support
- 🛠️ Easy setup: Windows (`launch.bat`), Linux/macOS (`launch.sh`)

## Quick Start

### 1. Clone & Configure
```bash
git clone https://github.com/yourusername/LMStudioBot.git
cd LMStudioBot
cp .env.example .env  # Edit with your Telegram bot token, owner ID, etc.
```

### 2. Launch
- **Windows:** Double-click `launch.bat`
- **Linux/macOS:**
  ```bash
  chmod +x launch.sh
  ./launch.sh
  ```

### 3. Chat!
- Open Telegram, find your bot, and send `/start`

## Requirements
- Python 3.11+
- [LM Studio](https://lmstudio.ai) running locally
- Telegram bot token ([@BotFather](https://t.me/botfather))

## Configuration
Edit `.env`:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_OWNER_ID=your_telegram_id
LMS_HOST=localhost
LMS_PORT=1234
SESSIONS_FILE=data/sessions.json
LOG_LEVEL=INFO
```

## Useful Commands
- `/start`, `/help`, `/menu` — Info & settings
- `/models`, `/loaded`, `/load`, `/unload` — Model management
- `/newchat`, `/chats`, `/switchchat`, `/removechat` — Session management
- Just send a message or image to chat!

## More Info
- See [LAUNCH_GUIDE.md](LAUNCH_GUIDE.md) for full setup & troubleshooting
- Project is MIT licensed

---
**Happy chatting!** 🚀
