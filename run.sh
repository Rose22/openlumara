#!/bin/bash

# 1. Detect Python binary
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "error: no python binary found (checked python3 and python)"
    exit 1
fi

# 2. Set up virtual environment if needed
if [ ! -d "venv" ]; then
    echo "setting up virtual environment with $PYTHON_BIN..."
    $PYTHON_BIN -m venv venv
    venv/bin/pip install -r requirements.txt
fi

# 3. Smart auto-update
echo "checking for updates..."
if git fetch origin 2>/dev/null; then
    if git rev-parse --abbrev-ref @{u} >/dev/null 2>&1; then
        LOCAL=$(git rev-parse HEAD)
        REMOTE=$(git rev-parse @{u})

        if [ "$LOCAL" != "$REMOTE" ]; then
            echo "updates available! pulling changes..."
            # Stash local changes to tracked files to prevent pull conflicts.
            # config.yml and data/ are in .gitignore, so they remain untouched.
            git stash
            git pull
            git stash pop || echo "note: some local changes could not be automatically reapplied."
        else
            echo "already up to date."
        fi
    else
        echo "no upstream configured, skipping update check."
    fi
else
    echo "warning: git fetch failed. skipping update check."
fi

# 4. Run the app
echo "starting openlumara..."
source venv/bin/activate
python main.py "$@"
