#!/bin/bash

# Detect Python binary
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "error: no python binary found (checked python3 and python)"
    exit 1
fi

# Set up/Update virtual environment
if [ ! -d "venv" ]; then
    echo "setting up virtual environment with $PYTHON_BIN..."
    $PYTHON_BIN -m venv venv

    # since this is the first run, update openlumara and install all requirements
    bash update.sh
fi

# aaand run!
source venv/bin/activate
python main.py "$@"
