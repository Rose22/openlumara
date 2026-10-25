#!/bin/bash
# resolve this script's real location
target="$0"
while [ -L "$target" ]; do
    link=$(readlink "$target")
    case "$link" in
        /*) target="$link" ;;
        *)  target="$(dirname "$target")/$link" ;;
    esac
done
cd "$(dirname "$target")" || exit 1

# uv manages the environment when available, plain venv + pip otherwise
if command -v uv >/dev/null 2>&1; then
    # --inexact keeps module dependencies the app installed at runtime
    uv sync --frozen --inexact || exit 1
    exec uv run --frozen --no-sync main.py "$@"
fi

if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "error: no python binary found (checked python3 and python)"
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "uv not found, setting up virtual environment with $PYTHON_BIN..."
    $PYTHON_BIN -m venv venv || exit 1
    venv/bin/pip install -r requirements.txt || exit 1
fi

exec venv/bin/python main.py "$@"
