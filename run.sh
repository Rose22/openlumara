#!/bin/bash

# detect Python binary
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "error: no python binary found (checked python3 and python)"
    exit 1
fi

# set up virtual environment
if [ ! -d "venv" ]; then
    echo "setting up virtual environment with $PYTHON_BIN..."
    $PYTHON_BIN -m venv venv
    venv/bin/pip install --upgrade pip
fi

# install package in editable mode
venv/bin/pip install -e .

# aaand run!
source venv/bin/activate
openlumara "$@"
