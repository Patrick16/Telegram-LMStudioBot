"""Single registry of the bot's slash commands.

``/help`` text and the command list shown by Telegram's "/" menu are both generated from
:data:`COMMANDS`, so a command is documented in exactly one place.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from telegram import BotCommand

from src.bot.i18n import LANGUAGES, mark, tr, translate

SECTION_MODELS = mark("Model Management")
SECTION_CHATS = mark("Chat Sessions")
SECTION_SETTINGS = mark("Settings")
SECTION_CHAT = mark("Chat")
SECTION_GENERAL = mark("General")


@dataclass(frozen=True)
class CommandInfo:
    name: str
    description: str          # translatable
    section: str              # translatable
    usage: str = ""           # arguments, shown after the command in /help
    in_menu: bool = False     # listed in Telegram's "/" menu


COMMANDS: tuple[CommandInfo, ...] = (
    CommandInfo("models", mark("List available models on disk"), SECTION_MODELS),
    CommandInfo("loaded", mark("List currently loaded models"), SECTION_MODELS),
    CommandInfo(
        "load", mark("Load a model"), SECTION_MODELS,
        usage="<model> [gpu=max|auto|0.0-1.0] [ctx=N] [id=name]",
    ),
    CommandInfo("unload", mark("Unload a model"), SECTION_MODELS, usage="<model>"),
    CommandInfo(
        "newchat", mark("Start a new chat"), SECTION_CHATS, usage="[name]", in_menu=True
    ),
    CommandInfo("chats", mark("List all chats"), SECTION_CHATS),
    CommandInfo(
        "switchchat", mark("Switch the active chat"), SECTION_CHATS, usage="<id_or_number>"
    ),
    CommandInfo("removechat", mark("Delete a chat"), SECTION_CHATS, usage="<id_or_number>"),
    CommandInfo("renamechat", mark("Rename the active chat"), SECTION_CHATS, usage="<name>"),
    CommandInfo("setprompt", mark("Set or clear the system prompt"), SECTION_SETTINGS,
                usage="[prompt]"),
    CommandInfo(
        "set", mark("Adjust a generation setting"), SECTION_SETTINGS, usage="<setting> <value>"
    ),
    CommandInfo("stop", mark("Stop the current reply"), SECTION_CHAT, in_menu=True),
    CommandInfo(
        "regenerate", mark("Regenerate the last reply"), SECTION_CHAT, in_menu=True
    ),
    CommandInfo("status", mark("LM Studio and chat status"), SECTION_GENERAL, in_menu=True),
    CommandInfo("menu", mark("Open the interactive menu"), SECTION_GENERAL, in_menu=True),
    CommandInfo("help", mark("Show all commands"), SECTION_GENERAL, in_menu=True),
)

# Commands handled elsewhere (not part of /help's list): /start only opens the welcome flow.
ALL_COMMAND_NAMES = frozenset(c.name for c in COMMANDS) | {"start"}


def _command_lines(commands: list[CommandInfo]) -> list[str]:
    lines = []
    for command in commands:
        usage = f" <code>{html.escape(command.usage, quote=False)}</code>" if command.usage else ""
        lines.append(f"/{command.name}{usage} — {tr(command.description)}")
    return lines


def render_commands_list() -> str:
    """The grouped command list (Telegram HTML) used by /help and the Help → Commands topic."""
    sections: dict[str, list[CommandInfo]] = {}
    for command in COMMANDS:
        sections.setdefault(command.section, []).append(command)
    blocks = []
    for section, commands in sections.items():
        lines = [f"<b>{tr(section)}</b>", *_command_lines(commands)]
        if section == SECTION_CHAT:
            lines.insert(1, tr("Send any text message — chat with the model"))
            lines.insert(2, tr("Send a photo — analyze it with a vision model"))
            lines.insert(3, tr("Send a file (text, code, PDF, DOCX) — the model reads it"))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def render_help() -> str:
    header = tr("🤖 <b>LMStudioBot</b> — Control LM Studio from Telegram")
    return header + "\n\n" + render_commands_list()


def bot_commands(language: str) -> list[BotCommand]:
    """Entries for Telegram's "/" menu in *language*."""
    return [
        BotCommand(c.name, translate(c.description, language)) for c in COMMANDS if c.in_menu
    ]


def menu_languages() -> list[str]:
    return list(LANGUAGES)
