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

if not exist "venv" (
    echo setting up virtual environment with %PYTHON_BIN%...
    %PYTHON_BIN% -m venv venv
)

:: 2. Ensure dependencies are up to date
echo ensuring dependencies are up to date...
venv\Scripts\python -m pip install -q --upgrade pip

:: Check if requirements.txt has changed before installing
if exist ".requirements_hash" (
    set /p OLD_HASH=<.requirements_hash
    for /f "delims=" %%a in ('powershell -Command "(Get-FileHash requirements.txt).Hash" 2^>nul') do set NEW_HASH=%%a
    if "!NEW_HASH!"=="!OLD_HASH!" (
        echo requirements.txt unchanged, skipping pip install.
    ) else (
        echo requirements.txt changed, updating dependencies...
        venv\Scripts\python -m pip install -r requirements.txt
        echo !NEW_HASH! > .requirements_hash
    )
) else (
    echo requirements.txt changed (or first run), updating dependencies...
    venv\Scripts\python -m pip install -r requirements.txt
    for /f "delims=" %%a in ('powershell -Command "(Get-FileHash requirements.txt).Hash" 2^>nul') do set NEW_HASH=%%a
    if defined NEW_HASH (
        echo !NEW_HASH! > .requirements_hash
    )
)

echo.
echo done!
