@echo off

:: Switch to the directory where this .bat file is located
cd /d "%~dp0"

:: set everything up if needed
if not exist "venv" (
    echo setting up virtual environment...
    python -m venv venv
    venv\Scripts\pip install -r requirements.txt
)

:: Update the code (requires Git to be installed and in PATH)
echo auto-updating from openlumara github..
git pull

:: Run the main script
venv\Scripts\python main.py
