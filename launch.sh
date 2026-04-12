#!/bin/bash

# LMStudioBot Launcher (Unix/Linux/macOS)
# This script sets up the environment and launches the Telegram bot

set -e  # Exit on error

echo ""
echo "========================================"
echo "  LMStudioBot - Unix Launcher"
echo "========================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if Python is installed
echo "[1/5] Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 is not installed or not in PATH"
    echo "Please install Python 3.11+ using your package manager"
    echo "  Ubuntu/Debian: sudo apt-get install python3 python3-venv python3-pip"
    echo "  macOS: brew install python3"
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "[OK] Python $PYTHON_VERSION found"

# Create virtual environment if it doesn't exist
echo "[2/5] Setting up virtual environment..."
if [ ! -d ".venv" ]; then
    echo "Creating .venv..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment"
        exit 1
    fi
    echo "[OK] Virtual environment created"
else
    echo "[OK] Virtual environment already exists"
fi

# Activate virtual environment
echo "[3/5] Activating virtual environment..."
source .venv/bin/activate
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to activate virtual environment"
    exit 1
fi
echo "[OK] Virtual environment activated"

# Install/upgrade pip and install requirements
echo "[4/5] Installing dependencies..."
python3 -m pip install --upgrade pip >/dev/null 2>&1
pip install -r requirements.txt >/dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install dependencies"
    echo "Check requirements.txt and try again"
    exit 1
fi
echo "[OK] Dependencies installed"

# Check for .env file
echo "[5/5] Checking configuration..."
if [ ! -f ".env" ]; then
    echo ""
    echo "[WARNING] .env file not found!"
    echo "Please create a .env file with the following variables:"
    echo "  TELEGRAM_BOT_TOKEN=your_bot_token_here"
    echo "  LMS_HOST=localhost"
    echo "  LMS_PORT=1234"
    echo "  LOG_LEVEL=INFO"
    echo ""
    echo "You can copy from .env.example if it exists"
    exit 1
fi
echo "[OK] Configuration file (.env) found"

# Launch the bot
echo ""
echo "========================================"
echo "  Launching LMStudioBot..."
echo "========================================"
echo ""

python3 -m src.bot.main

# If we get here, the bot was interrupted or crashed
if [ $? -ne 0 ]; then
    echo ""
    echo "[ERROR] Bot exited with an error"
    exit 1
fi
