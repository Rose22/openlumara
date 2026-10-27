#!/bin/sh
#   usage: sh install.sh [--reinstall]
#   --reinstall   discard the existing venv and build a fresh one
# env: PYTHON_BIN=<path>  use this interpreter instead of auto-detecting

# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) harness:openlumara
set -eu
cd "$(dirname "$0")"

# expose an `openlumara` command by symlinking run.sh into ~/.local/bin
# (done before the venv early-exit so re-running install.sh also repairs it)
setup_command() {
    BIN_DIR="$HOME/.local/bin"
    LINK="$BIN_DIR/openlumara"
    TARGET="$(pwd)/run.sh"
    mkdir -p "$BIN_DIR"
    if [ -L "$LINK" ]; then
        rm -f "$LINK"
        ln -s "$TARGET" "$LINK"
    elif [ -e "$LINK" ]; then
        echo "note: $LINK already exists and is not a symlink - leaving it alone"
    else
        ln -s "$TARGET" "$LINK"
    fi

    # make sure ~/.local/bin is on PATH for future shells (macOS notably lacks it)
    case ":$PATH:" in
        *":$BIN_DIR:"*) ;;
        *)
            for rc in "$HOME/.profile" "$HOME/.zshrc"; do
                if [ "$rc" = "$HOME/.zshrc" ] && [ ! -f "$rc" ] && [ "$(uname)" != "Darwin" ]; then
                    continue
                fi
                grep -q '.local/bin' "$rc" 2>/dev/null || {
                    printf '\n# added by OpenLumara installer\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$rc"
                }
            done
            echo "added ~/.local/bin to PATH - reopen your shell, or run:"
            echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
            ;;
    esac
}
setup_command

if [ "${1:-}" = "--reinstall" ]; then
    echo "removing existing venv..."
    rm -rf venv
fi

if [ -x "venv/bin/python" ]; then
    echo "venv already set up - nothing to do (use --reinstall to rebuild)"
    echo "start OpenLumara with: openlumara   (or ./run.sh)"
    exit 0
fi

# find a python new enough for OpenLumara (3.12+)
MIN_PY="3.12"
py_ok() {
    command -v "$1" >/dev/null 2>&1 || return 1
    "$1" -c "import sys; sys.exit(0 if sys.version_info >= tuple(int(x) for x in '${MIN_PY}'.split('.')) else 1)" 2>/dev/null
}

if [ -n "${PYTHON_BIN:-}" ] && py_ok "$PYTHON_BIN"; then
    :
else
    PYTHON_BIN=""
    for cand in python3.13 python3.12 python3 python; do
        if py_ok "$cand"; then PYTHON_BIN="$cand"; break; fi
    done
fi

if [ -z "$PYTHON_BIN" ]; then
    echo "error: no python ${MIN_PY}+ found (checked python3.13, python3.12, python3, python)"
    echo "       hint: use the quick installer, it installs python for you:"
    echo "             curl -fsSL https://raw.githubusercontent.com/Rose22/openlumara/main/curl.sh | sh"
    exit 1
fi

echo "setting up virtual environment with $PYTHON_BIN ($($PYTHON_BIN -c 'import platform; print(platform.python_version())'))..."
"$PYTHON_BIN" -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/python tools/dump_requirements.py --groups webui,channels,modules --output venv/requirements.txt
venv/bin/pip install -r venv/requirements.txt

echo "done! start OpenLumara with: openlumara   (or ./run.sh)"
