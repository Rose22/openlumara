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

if ! command -v uv >/dev/null 2>&1; then
    echo "error: uv is required. install it from https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# --inexact: keep module dependencies the app installed at runtime
uv sync --frozen --inexact || exit 1

exec uv run --frozen --no-sync main.py "$@"
