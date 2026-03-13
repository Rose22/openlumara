@echo off

:: set everything up if needed
if not exist "venv" (
    echo setting up virtual environment...
    python -m venv venv
    venv\Scripts\pip install -r requirements.txt
)

git pull
venv\Scripts\python main.py
