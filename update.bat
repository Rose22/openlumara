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

:: 2. Ensure dependencies are up to date
echo ensuring dependencies are up to date...
where uv >nul 2>nul
if %errorlevel% equ 0 (
    uv sync --frozen --inexact --extra webui --extra channels --extra modules
) else (
    echo uv not found, using venv + pip...
    where python >nul 2>nul
    if !errorlevel! neq 0 (
        echo error: no python binary found. please make sure python is installed and in your PATH.
        pause
        exit /b 1
    )

    if not exist "venv" (
        python -m venv venv || exit /b 1
    )

    venv\Scripts\python -m pip install -r requirements.txt || exit /b 1
)

echo.
echo done!
