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
    uv sync --frozen --inexact --extra webui --extra channels --extra modules || exit 1
else
    if [ ! -d "venv" ]; then
        if command -v python3 >/dev/null 2>&1; then
            PYTHON_BIN="python3"
        elif command -v python >/dev/null 2>&1; then
            PYTHON_BIN="python"
        else
            echo "error: no python binary found (checked python3 and python)"
            exit 1
        fi

        echo "uv not found, setting up virtual environment with $PYTHON_BIN..."
        $PYTHON_BIN -m venv venv || exit 1
    fi

    venv/bin/python tools/dump_requirements.py --groups webui,channels,modules --output venv/requirements.txt || exit 1
    venv/bin/pip install -r venv/requirements.txt || exit 1
fi

echo
echo "done!"
