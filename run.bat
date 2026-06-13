@echo off
setlocal enabledelayedexpansion

:: Switch to the directory where this .bat file is located
cd /d "%~dp0"

:: 1. Detect Python binary
where python >nul 2>nul
if %errorlevel% equ 0 (
    set PYTHON_BIN=python
) else (
    echo error: no python binary found. please make sure python is installed and in your PATH.
    pause
    exit /b 1
)

:: 2. Set up/Update virtual environment
if not exist "venv" (
    echo setting up virtual environment with %PYTHON_BIN%...
    %PYTHON_BIN% -m venv venv

    :: since this is the first run, install all requirements
    echo installing requirements...
    venv\Scripts\python -m pip install -q --upgrade pip
    venv\Scripts\python -m pip install -r requirements.txt
)

:: 3. Run the app
echo starting openlumara...
venv\Scripts\python main.py %*

if %errorlevel% neq 0 (
    echo.
    echo an error occurred while running the application.
    pause
)
