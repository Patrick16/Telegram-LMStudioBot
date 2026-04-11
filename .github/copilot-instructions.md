# LMStudioBot Development Guidelines

Auto-generated from all feature plans. Last updated: 2026-04-11

## Active Technologies
- Python 3.11+ + `python-telegram-bot>=21.0` (`InlineKeyboardMarkup`, `InlineKeyboardButton`, `CallbackQueryHandler`), `lmstudio>=1.5.0`, `pydantic>=2.0` (002-inline-button-menu)
- Ephemeral only (`context.chat_data`) — no new persistent storage (002-inline-button-menu)

- Python 3.11+ + `python-telegram-bot>=21.0`, `lmstudio>=1.5.0`, `pydantic>=2.0`, `python-dotenv` (001-json-short-name)

## Project Structure

```text
src/
tests/
```

## Commands

cd src; pytest; ruff check .

## Code Style

Python 3.11+: Follow standard conventions

## Recent Changes
- 002-inline-button-menu: Added Python 3.11+ + `python-telegram-bot>=21.0` (`InlineKeyboardMarkup`, `InlineKeyboardButton`, `CallbackQueryHandler`), `lmstudio>=1.5.0`, `pydantic>=2.0`

- 001-json-short-name: Added Python 3.11+ + `python-telegram-bot>=21.0`, `lmstudio>=1.5.0`, `pydantic>=2.0`, `python-dotenv`

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->
