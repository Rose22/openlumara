@echo off
setlocal enabledelayedexpansion

:: Switch to the directory where this .bat file is located
cd /d "%~dp0"

:: 1. Smart auto-update
echo checking for updates...
git fetch origin >nul 2>nul
if %errorlevel% equ 0 (
    :: Get local HEAD
    for /f "tokens=*" %%i in ('git rev-parse HEAD') do set LOCAL=%%i
    
    :: Get remote HEAD (using @{u} for upstream)
    set REMOTE=
    for /f "tokens=*" %%i in ('git rev-parse @{u} 2^>nul') do set REMOTE=%%i

    if "!REMOTE!"=="" (
        echo no upstream configured, skipping update check.
    ) else if "!LOCAL!" NEQ "!REMOTE!" (
        echo updates available! pulling changes...
        git pull
    ) else (
        echo already up to date.
    )
) else (
    echo warning: git fetch failed. skipping update check.
)

where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo error: uv is required. install it from https://docs.astral.sh/uv/getting-started/installation/
    pause
    exit /b 1
)

:: 2. Ensure dependencies are up to date
echo ensuring dependencies are up to date...
uv sync --frozen --inexact

echo.
echo done!
