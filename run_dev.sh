#!/bin/sh

# set everything up if needed
if [ ! -d "venv" ]; then
    echo "setting up virtual environment..."
    python -m venv venv
    venv/bin/pip install -r requirements.txt
fi

source venv/bin/activate
python main.py $*
