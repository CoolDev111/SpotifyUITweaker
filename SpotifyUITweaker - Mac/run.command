#!/bin/bash
# Runs the Spotify UI Tweaker directly from source (no build step).
# Double-click this file, or run: bash run.command
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[MSC] Python 3 is required. Install it from https://www.python.org/downloads/"
  echo "      (or run:  xcode-select --install)  and try again."
  [ -t 0 ] && read -r -p "Press Enter to close..." _
  exit 1
fi

if ! python3 -c "import websockets" >/dev/null 2>&1; then
  echo "[MSC] Installing required dependency: websockets"
  python3 -m pip install --upgrade websockets \
    || python3 -m pip install --user --upgrade websockets \
    || python3 -m pip install --user --break-system-packages --upgrade websockets
fi

echo "[MSC] Starting Spotify UI Tweaker... (Ctrl+C to quit; quitting closes Spotify)"
python3 main.py
STATUS=$?

if [ $STATUS -ne 0 ] && [ -t 0 ]; then
  echo
  echo "[MSC] Launcher exited with an error (see output above)."
  read -r -p "Press Enter to close..." _
fi
exit $STATUS
