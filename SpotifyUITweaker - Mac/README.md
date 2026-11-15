# SpotifyUITweaker - Mac

Injects the Spotify UI Tweaker straight into the **Spotify desktop client on
macOS** — themes, palette editor and saved presets, no Chrome needed.
There is a matching `SpotifyUITweaker - Windows` package for Windows.

## What's in here

| File | Purpose |
|---|---|
| `main.py` | The injector — cross-platform (auto-detects Windows / macOS) |
| `build.command` | Builds a standalone `dist/SpotifyUITweaker.app` (PyInstaller) |
| `run.command` | Runs it from source, no build step (installs `websockets` for you) |
| `manifest.json`, `default.css`, `content.js`, `popup.html`, `popup.js`, `themes/`, `images/` | The extension payload that gets injected |
| `INSTALL.md` | Full guide — Chrome install, themes, presets, client injection |
| `README.md` | This quick-start |

This folder doubles as a regular unpacked Chrome extension: it contains
`manifest.json`, so if you ever want the web-player version instead, load
this folder via `chrome://extensions` → Developer mode → **Load unpacked**.

## First time only: allow the scripts

If Finder says the scripts can't be opened (downloaded files get
quarantined), pick either:

```bash
chmod +x build.command run.command          # restore the executable bit
xattr -d com.apple.quarantine build.command run.command   # drop the quarantine
```

or simply **right-click → Open** each script once.

## Quick start (run from source)

1. Install **Python 3** — from
   [python.org](https://www.python.org/downloads/) or run
   `xcode-select --install` for Apple's version.
2. Double-click **`run.command`**. It installs the one dependency
   (`websockets`) if missing, then: Spotify closes, relaunches with remote
   debugging on `127.0.0.1:9222`, and the whole extension — content script,
   popup GUI and all five themes — is injected automatically.

## Build the standalone app

Double-click **`build.command`** → `dist/SpotifyUITweaker.app`
(everything embedded, uses Spotify's own icon when the client is in
/Applications).

- First launch of the unsigned app: **right-click → Open** (once), or run
  `xattr -cr dist/SpotifyUITweaker.app`.
- `storage.json` is created **next to the .app** when you save settings —
  keep the app in a permanent spot and your presets survive rebuilds.

## Build with GitHub Actions (no local Python needed)

If this folder lives in a GitHub repository, `.github/workflows/build.yml`
builds everything for you:

- Every push to the repo builds `SpotifyUITweaker.app` (Apple silicon)
  automatically, plus the Windows exe on a Windows runner.
- **Actions tab → Build SpotifyUITweaker → latest run → Artifacts** →
  download `SpotifyUITweaker-macOS-AppleSilicon` (the zipped app is inside
  the artifact zip).
- Prefer manual control? **Actions → Build SpotifyUITweaker → Run workflow**.
- Push a tag (`git tag v1.0.0 && git push origin v1.0.0`) and both platform
  builds are attached to a GitHub Release automatically.

GitHub retired its Intel macOS runners, so CI produces Apple-silicon builds
only — on an Intel Mac, build locally with `build.command` or run from
source with `run.command`.

CI-built apps are unsigned: right-click → **Open** (once), or run
`xattr -cr SpotifyUITweaker.app`.

## Using it

- Click the palette button left of the notification bell in Spotify's top
  bar, or press **Option+C** (Alt+C).
- **Ctrl+Shift+D** / **Option+D** opens DevTools.
- Quitting the launcher closes Spotify — the client must relaunch with the
  debug flag for the injection, so that is normal.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Spotify desktop client not found" | Install Spotify to `/Applications`, or add your install path to `SPOTIFY_CANDIDATES` at the top of `main.py`. |
| `python3: command not found` | Install Python 3 (python.org) and open a fresh Terminal. |
| pip refuses to install ("externally managed environment") | Run `python3 -m pip install --user --break-system-packages pyinstaller websockets`. |
| Double-click does nothing / "Permission denied" | `chmod +x build.command run.command`, then right-click → Open. |
| Injection times out | Fully quit Spotify (Cmd+Q, check the Dock and menu bar), rerun; make sure nothing else occupies port 9222. |
| Settings disappeared | `storage.json` follows the app — launch it from the same spot as before. |
