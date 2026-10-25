@echo off
setlocal enabledelayedexpansion

:: Switch to the directory where this .bat file is located
cd /d "%~dp0"

where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo error: uv is required. install it from https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

:: --inexact: keep module dependencies the app installed at runtime
uv sync --frozen --inexact || exit /b 1

echo starting openlumara...
uv run --frozen --no-sync main.py %*

if %errorlevel% neq 0 (
    echo.
    echo an error occurred while running the application.
    pause
)
