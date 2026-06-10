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
        :: Stash local changes to tracked files to prevent pull conflicts.
        git stash
        git pull
        git stash pop || echo note: some local changes could not be automatically reapplied.
    ) else (
        echo already up to date.
    )
) else (
    echo warning: git fetch failed. skipping update check.
)

if not exist "venv" (
    echo setting up virtual environment with %PYTHON_BIN%...
    %PYTHON_BIN% -m venv venv
)

:: 2. Ensure dependencies are up to date
echo ensuring dependencies are up to date...
venv\Scripts\python -m pip install -q --upgrade pip
venv\Scripts\python -m pip install -e .

echo.
echo done!
