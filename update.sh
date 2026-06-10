#!/bin/bash

echo "checking for updates..."
if git fetch origin 2>/dev/null; then
    if git rev-parse --abbrev-ref @{u} >/dev/null 2>&1; then
        LOCAL=$(git rev-parse HEAD)
        REMOTE=$(git rev-parse @{u})

        if [ "$LOCAL" != "$REMOTE" ]; then
            echo "updates available! pulling changes..."
            # Stash local changes to tracked files to prevent pull conflicts.
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

if [ ! -d "venv" ]; then
    echo "setting up virtual environment with $PYTHON_BIN..."
    $PYTHON_BIN -m venv venv
fi

echo "ensuring dependencies are up to date..."
source venv/bin/activate
pip install -q --upgrade pip
pip install -e .

echo
echo "done!"
