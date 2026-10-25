#!/bin/bash

echo "checking for updates..."
if git fetch origin 2>/dev/null; then
    if git rev-parse --abbrev-ref @{u} >/dev/null 2>&1; then
        LOCAL=$(git rev-parse HEAD)
        REMOTE=$(git rev-parse @{u})

        if [ "$LOCAL" != "$REMOTE" ]; then
            echo "updates available! pulling changes..."
            git pull
        else
            echo "already up to date."
        fi
    else
        echo "no upstream configured, skipping update check."
    fi
else
    echo "warning: git fetch failed. skipping update check."
fi

echo "ensuring dependencies are up to date..."
if command -v uv >/dev/null 2>&1; then
    uv sync --frozen --inexact
else
    if [ ! -d "venv" ]; then
        echo "uv not found, setting up virtual environment with python3..."
        python3 -m venv venv || exit 1
    fi

    venv/bin/pip install -r requirements.txt || exit 1
fi

echo
echo "done!"
