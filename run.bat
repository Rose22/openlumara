@echo off
setlocal enabledelayedexpansion

:: Switch to the directory where this .bat file is located
cd /d "%~dp0"

:: uv manages the environment when available, plain venv + pip otherwise
where uv >nul 2>nul
if %errorlevel% equ 0 (
    :: --inexact keeps module dependencies the app installed at runtime
    uv sync --frozen --inexact --extra webui --extra channels --extra modules || exit /b 1
    echo starting openlumara...
    uv run --frozen --no-sync main.py %*
    goto :check
)

echo uv not found, using venv + pip...

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo error: no python binary found. please make sure python is installed and in your PATH.
    pause
    exit /b 1
)

if not exist "venv" (
    echo setting up virtual environment...
    python -m venv venv || exit /b 1
    venv\Scripts\python -m pip install -r requirements.txt || exit /b 1
)

echo starting openlumara...
venv\Scripts\python main.py %*

:check
if !errorlevel! neq 0 (
    echo.
    echo an error occurred while running the application.
    pause
)
