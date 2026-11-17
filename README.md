# Spotify UI Tweaker

Re-theme Spotify with custom CSS — **four glass themes**, a live palette
editor, **named presets**, a raw-CSS editor and a selector diagnostics tool.
Works as an MV3 extension in the **Chrome web player**, and in the
**Spotify desktop client** (Windows & macOS) through the launcher packages
in this repo. All changes apply **live — no page refresh** — and it never
touches playback or DRM: the extension only changes how Spotify *looks*.

> [![Build SpotifyUITweaker](https://github.com/CoolDev111/SpotifyUITweaker/actions/workflows/build.yml/badge.svg)](https://github.com/CoolDev111/SpotifyUITweaker/actions/workflows/build.yml)

> [!IMPORTANT]
> **Unofficial project.** This is a fan-made customization tool. It is not
> affiliated with, endorsed by, or connected to Spotify AB in any way.
> "Spotify" is a trademark of Spotify AB, referenced here solely to describe
> compatibility. Customizing the client may violate Spotify's Terms of Use —
> use at your own risk.


## What's in this repo

| Path | What it is |
|----|----|
| `.github/workflows/build.yml` | CI — builds the Windows exe + macOS app on every push; `v*` tags publish a GitHub Release with both builds. |
| `images/` | Contains the images to showcase the ui for the client and extensions. |
| `SpotifyUITweaker - Extension/` | The Chrome extension (Manifest V3). This is the folder you **Load unpacked** in Chrome. Full install guide in its [INSTALL.md](SpotifyUITweaker%20-%20Extension/INSTALL.md). |
| `SpotifyUITweaker - Mac/` | Desktop-client launcher for macOS: the same cross-platform injector; `run.command` runs it from source, `build.command` builds a standalone `SpotifyUITweaker.app`. |
| `SpotifyUITweaker - Windows/` | Desktop-client launcher for Windows: `main.py` injects the extension into the Spotify client; `build.bat` builds a standalone `SpotifyUITweaker.exe`. |
| `.gitignore` | The file to ignore when building the launcher packages. |
| `LICENSE` | The MIT license. |
| `README.md` | This file. |

Each launcher package also contains a **full copy of the extension assets**,
so it works standalone — and even doubles as a loadable Chrome extension
folder if you ever want the web-player version from the same place.

## Features

- **Themes tab** — one-click bundled themes:
  - **Adaptive Album Glass** — frosted panels over an ambient backdrop that
    **re-tints itself from the current album cover** (accents, hover/press
    and backdrop all follow the music)
  - **Neon Synthwave Glass**, **Violet Nebula Glass**,
    **Amber Ember Glass**
- **Named presets** — save any look with a name; rename, export/import as
  `.css`, delete (two-click confirm). A green border + **ON** badge marks
  what's currently applied.
- **Palette editor (Simple tab)** — accent / background / text colors with a
  live mini preview; *Auto-derive hover & press* rebuilds the whole accent
  family from one color.
- **Advanced tab** — raw CSS editor; *Load default* drops in the maintained
  selector map.
- **Diagnostics tab** — checks every selector against the live page
  (green = hit, red = miss) and highlights it on the page when clicked.
- **Instant hot-reload** — every edit applies to all open Spotify tabs
  without a refresh.
- In the desktop client, the green **Equalizer canvas** is recolored live to
  match the theme accent.

All five themes share the same selector map, so new Spotify UI surfaces are
themed consistently.

## Showcase
#### (↓ Client ↓)
<img src="images/Client.png" alt="Theme Picture" width="700">

#### (↓ Extension ↓)
<img src="images/Extension.png" alt="Theme Picture" width="700">

## Install — Chrome (web player)

1. Unzip/clone, then open `chrome://extensions` in your browser (must be Chromium and have access to adding extensions).
2. Enable **Developer mode** (top-right).
3. **Load unpacked** → select the `SpotifyUITweaker - Extension/` folder — the one
   directly containing `manifest.json`.
4. Open `https://open.spotify.com`, click the toolbar icon, pick a theme in
   the **Themes** tab.

Edge/Brave/etc work the same (`edge://extensions`, `brave://extensions`, etc.).
<br>Step-by-step details, updates-preserving-presets and troubleshooting:
[`SpotifyUITweaker - Extension/INSTALL.md`](SpotifyUITweaker%20-%20Extension/INSTALL.md).

## Install — Spotify desktop client

No Chrome needed — the launcher injects the **same themes and the same popup
GUI** straight into the client. 
<br>It closes Spotify, relaunches it with remote
debugging on `127.0.0.1:9222`, attaches over the DevTools protocol and
injects the whole extension.

**Windows**

1. Install [Python 3](https://www.python.org/downloads/) (tick
   *"Add python.exe to PATH"*), then `python -m pip install websockets`
2. Double-click `main.py` inside `SpotifyUITweaker - Windows/`
   — or build the exe once with `build.bat` and run that

**macOS**

1. Install [Python 3](https://www.python.org/downloads/)
2. First time only: `chmod +x run.command build.command`
3. Double-click `run.command` inside `SpotifyUITweaker - Mac/`
   (installs `websockets` for you, then injects)
   — or build the app once with `build.command`

**Using it:** click the palette button left of the notification bell in
Spotify's top bar, or press **Alt+C** (**Option+C** on macOS).
<br>**Ctrl+Shift+D / Alt+D** opens DevTools. (Curently not working!)
<br>Quitting the launcher closes Spotify — that's expected, the client must relaunch with the debug port.

Package details and troubleshooting:
[`SpotifyUITweaker - Windows/README.md`](SpotifyUITweaker%20-%20Windows/README.md) ·
[`SpotifyUITweaker - Mac/README.md`](SpotifyUITweaker%20-%20Mac/README.md)

## Build it yourself

### With GitHub Actions (no local Python needed)

- Every push to `main` builds both packages — download from
  **Actions → Build SpotifyUITweaker → latest run → Artifacts**
  (`SpotifyUITweaker-Windows`, `SpotifyUITweaker-macOS-AppleSilicon`).
- Push a version tag and both builds are published to a **GitHub Release**:

  ```bash
  git tag v(VER)
  git push origin v(VER)
  ```

- CI mac builds are **Apple-silicon only** (GitHub retired its Intel macOS
  runners). Intel Macs: build locally or run from source.

### Locally

| Platform | Command | Output |
|---|---|---|
| Windows | `build.bat` in `SpotifyUITweaker - Windows/` | `dist\SpotifyUITweaker.exe` |
| macOS | `build.command` in `SpotifyUITweaker - Mac/` | `dist/SpotifyUITweaker.app` |

### **(↓ THIS IS EXPECTED TO HAPPEN ↓)**
CI and local builds are **unsigned** and can produce a **false positive**.
<br>To allow the app to run you must:
<br>**macOS** → right-click → **Open** (once), or `xattr -cr dist/SpotifyUITweaker.app` in the terminal.
<br>**Windows** → SmartScreen **More info → Run anyway**.
### **(↑ THIS IS EXPECTED TO HAPPEN ↑)**

## Privacy, permissions & legal

- The extension only touches `https://open.spotify.com/*` — it cannot see or
  modify any other website.
- No remote code, no analytics, nothing leaves your machine.
- Settings live in `chrome.storage.local` (browser) or a local `storage.json`
  next to the launcher executable / app (desktop client).
- **No Spotify assets are included or redistributed.** All code and artwork
  in this repo are original; the build scripts copy the Spotify icon from
  your own locally installed client (if present) purely at build time.
- **No ad blocking, no DRM circumvention, no audio extraction** — the tool
  changes appearance only.
- "Spotify" is a trademark of Spotify AB; it is used here solely to indicate
  compatibility. See [LICENSE](LICENSE) for the code license (MIT).

---

**Version 1.5.7** · Manifest V3 · for `https://open.spotify.com` ·
Python 3 + `websockets` for the desktop-client launcher ·
[MIT licensed](LICENSE)
