# LMStudioBot - Quick Start Guide

This guide will help you quickly set up and launch the LMStudioBot.

## Prerequisites

- **Python 3.11+** - Download from [python.org](https://python.org)
- **Telegram Bot Token** - Get one from [@BotFather](https://t.me/botfather) on Telegram
- **LM Studio** - Running locally (default: localhost:1234)
- **Your Telegram User ID** - Get it from [@userinfobot](https://t.me/userinfobot)

## Quick Start

### Option 1: Windows (Easiest)

Simply double-click `launch.bat`:

```bash
launch.bat
```

The script will:
1. ✅ Check Python installation
2. ✅ Create virtual environment (if needed)
3. ✅ Install dependencies from requirements.txt
4. ✅ Verify .env configuration
5. ✅ Launch the bot

### Option 2: Linux/macOS

Make the script executable and run it:

```bash
chmod +x launch.sh
./launch.sh
```

The script will:
1. ✅ Check Python 3 installation
2. ✅ Create virtual environment (if needed)
3. ✅ Install dependencies from requirements.txt
4. ✅ Verify .env configuration
5. ✅ Launch the bot

### Option 3: Manual Setup

If you prefer to do it manually:

```bash
# Windows - Create and activate venv
python -m venv .venv
.venv\Scripts\activate

# Linux/macOS - Create and activate venv
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the bot
python src/bot/main.py
```

## Configuration

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your settings:**
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   TELEGRAM_OWNER_ID=123456789
   LMS_HOST=localhost
   LMS_PORT=1234
   SESSIONS_FILE=data/sessions.json
   LOG_LEVEL=INFO
   ```

### Configuration Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | **Required** - Bot token from @BotFather | - |
| `TELEGRAM_OWNER_ID` | **Required** - Your Telegram user ID | - |
| `LMS_HOST` | LM Studio server hostname | `localhost` |
| `LMS_PORT` | LM Studio server port | `1234` |
| `SESSIONS_FILE` | Path to sessions database | `data/sessions.json` |
| `LOG_LEVEL` | Logging level (INFO, DEBUG, WARNING) | `INFO` |

## Troubleshooting

### "Python is not installed"
- Install Python 3.11+ from [python.org](https://python.org)
- On Windows, check **"Add Python to PATH"** during installation

### ".env file not found"
- Copy `.env.example` to `.env`
- Fill in `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_ID`

### "Failed to install dependencies"
- Manually run: `pip install -r requirements.txt`
- Check your internet connection
- Try: `pip install --upgrade pip` first

### "LM Studio is unreachable"
- Ensure LM Studio is running on `localhost:1234`
- Check with browser: `http://localhost:1234`
- Verify `LMS_HOST` and `LMS_PORT` in `.env`

### Bot doesn't respond
- Check TELEGRAM_BOT_TOKEN is correct (no spaces)
- Check TELEGRAM_OWNER_ID matches your user ID
- Check LM Studio is running with a model loaded

## Data Storage

The bot creates the following directories:

- `data/sessions.json` - Active chat sessions
- `data/histories/` - Per-session message history
- `data/model-presets.json` - Saved model settings
- `data/session-presets.json` - Saved session settings

## Available Commands

Once running, use these Telegram commands:

- `/start` - Show welcome message
- `/help` - Show help and commands
- `/menu` - Open the settings menu
- `/models` - List available models
- `/loaded` - Show loaded models
- `/load <model>` - Load a model
- `/unload <model>` - Unload a model
- `/newchat [name]` - Create new chat session
- `/chats` - List chat sessions
- `/switchchat <id>` - Switch to chat session
- `/removechat <id>` - Delete chat session
- `<text>` - Send message to LM Studio

## Requirements

The following Python packages are installed:

- `python-telegram-bot>=21.0` - Telegram Bot API
- `lmstudio>=1.5.0` - LM Studio SDK
- `pydantic>=2.0` - Data validation
- `pydantic-settings>=2.0` - Configuration management
- `python-dotenv>=1.0` - Environment variables

See `requirements.txt` for details.

## More Information

- [Project Repository](https://github.com/yourusername/LMStudioBot)
- [LM Studio Documentation](https://lmstudio.ai)
- [Telegram Bot API Docs](https://core.telegram.org/bots/api)

---

**Happy chatting!** 🚀
