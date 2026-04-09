#!/bin/sh

# set everything up if needed
if [ ! -d "venv" ]; then
    echo "setting up virtual environment..."
    python -m venv venv
    venv/bin/pip install -r requirements.txt
fi

# auto update
echo "auto updating from openlumara github.."
git pull
# aaand run!
source venv/bin/activate
python main.py
