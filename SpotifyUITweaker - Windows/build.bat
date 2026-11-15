@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo  Building Spotify UI Tweaker Standalone Executable
echo ===================================================

:: 1. Ensure PyInstaller and websockets are installed
python -m pip install --upgrade pyinstaller websockets

:: 2. Clean previous build artifacts
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "*.spec" del /q "*.spec"

:: 3. Build single-file windowed EXE with all extension assets embedded
::    --noconsole hides the black terminal window on launch
::    --add-data bundles your HTML, JS, CSS, and themes folder inside the EXE
python -m PyInstaller ^
  --noconfirm ^
  --onefile ^
  --noconsole ^
  --name "SpotifyUITweaker" ^
  --icon "%APPDATA%\Spotify\Spotify.exe" ^
  --add-data "default.css;." ^
  --add-data "content.js;." ^
  --add-data "popup.html;." ^
  --add-data "popup.js;." ^
  --add-data "themes;themes" ^
  main.py

echo.
if exist "dist\SpotifyUITweaker.exe" (
    echo [SUCCESS] Build complete!
    echo Output: "%~dp0dist\SpotifyUITweaker.exe"
    echo Note: storage.json will be created automatically next to SpotifyUITweaker.exe when you save settings.
) else (
    echo [ERROR] Build failed. Check the output above for missing files.
)

pause
