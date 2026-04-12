@echo off
REM LMStudioBot Launcher (Windows)
REM This script sets up the environment and launches the Telegram bot

setlocal enabledelayedexpansion

echo.
echo ========================================
echo  LMStudioBot - Windows Launcher
echo ========================================
echo.

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Check if Python is installed
echo [1/5] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.11+ from python.org
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [OK] Python %PYTHON_VERSION% found

REM Create virtual environment if it doesn't exist
echo [2/5] Setting up virtual environment...
if not exist ".venv" (
    echo Creating .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment already exists
)

REM Activate virtual environment
echo [3/5] Activating virtual environment...
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment
    pause
    exit /b 1
)
echo [OK] Virtual environment activated

REM Install/upgrade pip and install requirements
echo [4/5] Installing dependencies...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies
    echo Check requirements.txt and try again
    pause
    exit /b 1
)
echo [OK] Dependencies installed

REM Check for .env file
echo [5/5] Checking configuration...
if not exist ".env" (
    echo.
    echo [WARNING] .env file not found!
    echo Please create a .env file with the following variables:
    echo   TELEGRAM_BOT_TOKEN=your_bot_token_here
    echo   LMS_HOST=localhost
    echo   LMS_PORT=1234
    echo   LOG_LEVEL=INFO
    echo.
    echo You can copy from .env.example if it exists
    pause
    exit /b 1
)
echo [OK] Configuration file (.env) found

REM Launch the bot
echo.
echo ========================================
echo  Launching LMStudioBot...
echo ========================================
echo.
python -m src.bot.main

REM Pause on error
if errorlevel 1 (
    echo.
    echo [ERROR] Bot exited with an error
    pause
)

endlocal
