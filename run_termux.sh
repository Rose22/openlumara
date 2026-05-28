#!/bin/bash

pkg update
pkg upgrade
pkg install python build-essential rust
python -m venv venv
source venv/bin/activate

export ANDROID_API_LEVEL="$(getprop ro.build.version.sdk)"
pip install -r requirements_termux.txt
