# LMStudioBot

A Telegram bot for local LLM chat using [LM Studio](https://lmstudio.ai) as the backend. Features session-aware chat, inline settings, model/session presets, and persistent history.

## Features
- 💬 Multi-session chat with per-session history
- ⚙️ Inline menu for model & session settings
- 📦 Model and session preset support
- 🔄 Live-streamed replies with ⏹ Stop and 🔄 Regenerate buttons
- 🗂 Switch, rename and remove chats (paginated lists, delete confirmation)
- 💭 Optional collapsible model reasoning (`<think>`)
- 📊 `/status` — LM Studio, loaded models, chat and context window
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
HISTORIES_DIR=data/histories
MODEL_PRESETS_FILE=data/model-presets.json
SESSION_PRESETS_FILE=data/session-presets.json
LOG_LEVEL=INFO
```

Only the owner (`TELEGRAM_OWNER_ID`) can use the bot; messages from anyone else are ignored silently.

## Useful Commands
- `/start`, `/help`, `/menu` — Info & settings
- `/models`, `/loaded`, `/load`, `/unload` — Model management
- `/newchat`, `/chats`, `/switchchat`, `/removechat` — Session management
- `/regenerate`, `/stop` — Regenerate the last reply / stop the reply being generated
- Just send a message or image to chat!

## Development
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest -q          # tests
flake8 src tests   # lint
mypy src           # type check
pre-commit install # optional: run the checks on every commit
```

Layout:
- `src/bot/handlers/` — Telegram handlers (`menu/` is the inline menu package)
- `src/bot/services/` — `inference.py` (one code path for text/image/regenerate turns), `generation.py` (per-chat stop)
- `src/lms/` — LM Studio SDK streaming (`sdk.py`) and `lms` CLI wrapper (`cli.py`)
- `src/storage/` — sessions, histories and presets (atomic JSON writes; corrupt files are quarantined as `*.corrupt-<timestamp>`)

## More Info
- See [LAUNCH_GUIDE.md](LAUNCH_GUIDE.md) for full setup & troubleshooting
- Project is MIT licensed

---
**Happy chatting!** 🚀
