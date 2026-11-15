# SpotifyUITweaker - Windows

Injects the Spotify UI Tweaker straight into the **Spotify desktop client on
Windows** — themes, palette editor and saved presets, no Chrome needed.
There is a matching `SpotifyUITweaker - Mac` package for macOS.

## What's in here

| File | Purpose |
|---|---|
| `main.py` | The injector — cross-platform (auto-detects Windows / macOS) |
| `build.bat` | Builds a standalone `dist\SpotifyUITweaker.exe` (PyInstaller) |
| `manifest.json`, `default.css`, `content.js`, `popup.html`, `popup.js`, `themes/`, `images/` | The extension payload that gets injected |
| `INSTALL.md` | Full guide — Chrome install, themes, presets, client injection |
| `README.md` | This quick-start |

This folder doubles as a regular unpacked Chrome extension: it contains
`manifest.json`, so if you ever want the web-player version instead, load
this folder via `chrome://extensions` → Developer mode → **Load unpacked**.

## Quick start (run from source)

1. Install **Python 3** from
   [python.org](https://www.python.org/downloads/) — tick
   "Add python.exe to PATH" in the installer.
2. Install the one dependency:
   ```
   python -m pip install websockets
   ```
3. Double-click `main.py` (or run `python main.py` inside this folder).
   Spotify closes, relaunches with remote debugging on `127.0.0.1:9222`,
   and the whole extension — content script, popup GUI and all five themes —
   is injected automatically.

## Build the standalone exe

Double-click **`build.bat`** → `dist\SpotifyUITweaker.exe`
(everything embedded, no console window, Spotify's own icon when the client
is installed in the standard location).

`storage.json` is created next to the exe when you save settings — keep the
exe in a permanent spot and your presets survive rebuilds.

## Build with GitHub Actions (no local Python needed)

If this folder lives in a GitHub repository, `.github/workflows/build.yml`
builds everything for you:

- Every push to the repo builds `SpotifyUITweaker.exe` automatically
  (plus the macOS app on a mac runner).
- **Actions tab → Build SpotifyUITweaker → latest run → Artifacts** →
  download `SpotifyUITweaker-Windows` (the exe is inside the artifact zip).
- Prefer manual control? **Actions → Build SpotifyUITweaker → Run workflow**.
- Push a tag (`git tag v1.0.0 && git push origin v1.0.0`) and both platform
  builds are attached to a GitHub Release automatically.

CI-built exes are unsigned, so SmartScreen may show a warning —
**More info** → **Run anyway**.

## Using it

- Click the palette button left of the notification bell in Spotify's top
  bar, or press **Alt+C**.
- **Ctrl+Shift+D** / **Alt+D** opens DevTools.
- Quitting the launcher closes Spotify — the client must relaunch with the
  debug flag for the injection, so that is normal.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Spotify desktop client not found" | Install the Spotify client, or add your install path to `SPOTIFY_CANDIDATES` at the top of `main.py`. |
| `'python' is not recognized…` | Reinstall Python and tick "Add python.exe to PATH", or use `py main.py`. |
| Injection times out | Fully close Spotify (check the system tray), rerun; make sure nothing else occupies port 9222. |
| Settings disappeared | `storage.json` follows the exe — launch it from the same spot as before. |
| Built exe won't start | Some antivirus flags PyInstaller builds. Add an exclusion for the exe, or just run from source (`python main.py`). |
