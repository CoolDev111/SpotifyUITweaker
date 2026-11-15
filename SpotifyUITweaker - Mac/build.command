#!/bin/bash
# Builds a standalone SpotifyUITweaker.app with all extension assets embedded.
# Double-click this file, or run: bash build.command
cd "$(dirname "$0")"

echo "==================================================="
echo " Building Spotify UI Tweaker (macOS)"
echo "==================================================="

echo "[1/3] Installing build requirements (pyinstaller, websockets)..."
if ! python3 -m pip install --upgrade pyinstaller websockets \
   && ! python3 -m pip install --user --upgrade pyinstaller websockets \
   && ! python3 -m pip install --user --break-system-packages --upgrade pyinstaller websockets; then
  echo "[ERROR] Could not install pyinstaller/websockets via pip."
  echo "        Try manually:  python3 -m pip install --user --break-system-packages pyinstaller websockets"
  [ -t 0 ] && read -r -p "Press Enter to close..." _
  exit 1
fi

echo "[2/3] Cleaning previous build artifacts..."
rm -rf build dist
rm -f *.spec 2>/dev/null || true

ICON_ARGS=""
if [ -f "/Applications/Spotify.app/Contents/Resources/Spotify.icns" ]; then
  echo "      Using Spotify's own icon."
  ICON_ARGS="--icon /Applications/Spotify.app/Contents/Resources/Spotify.icns"
fi

echo "[3/3] Building dist/SpotifyUITweaker.app ..."
python3 -m PyInstaller \
  --noconfirm \
  --onefile \
  --windowed \
  --name "SpotifyUITweaker" \
  $ICON_ARGS \
  --add-data "default.css:." \
  --add-data "content.js:." \
  --add-data "popup.html:." \
  --add-data "popup.js:." \
  --add-data "themes:themes" \
  main.py

echo
if [ -d "dist/SpotifyUITweaker.app" ]; then
  echo "[SUCCESS] Build complete!"
  echo "Output: $(pwd)/dist/SpotifyUITweaker.app"
  echo ""
  echo "Notes:"
  echo "  - storage.json is created NEXT TO the .app when you save settings,"
  echo "    so keep the app in a permanent spot and your presets survive rebuilds."
  echo "  - First launch of the unsigned app: right-click it and choose Open,"
  echo "    or run:  xattr -cr dist/SpotifyUITweaker.app"
  exit 0
else
  echo "[ERROR] Build failed. Check the output above for missing files."
  [ -t 0 ] && read -r -p "Press Enter to close..." _
  exit 1
fi
