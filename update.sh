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

if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv is required. install it from https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

echo "ensuring dependencies are up to date..."
uv sync --frozen --inexact

echo
echo "done!"
