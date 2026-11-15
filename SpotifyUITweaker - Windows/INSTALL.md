# Spotify UI Tweaker — Installation Guide (Google Chrome)

**Version 1.5.6** · Manifest V3 · for `https://open.spotify.com` · plus a
desktop-client injector

A Chrome extension that re-themes Spotify's **web player** with custom CSS:
five bundled themes (including one that adapts to the album art), a Themes
tab for saving **your own named presets**, a color-palette editor, a raw-CSS
editor and a selector diagnostics tool. Changes apply **live — no page
refresh needed**.

> **Plain Chrome means no DRM headaches.** Chrome already ships Widevine
> support, so everything plays exactly like it does normally. This extension
> only changes how the page *looks* — it never touches playback.

---

## Quick install (TL;DR)

1. Unzip `spotify-ui-tweaker-v1.5.6.zip` anywhere **permanent**.
2. Open `chrome://extensions`.
3. Turn on **Developer mode** (top-right toggle).
4. Click **Load unpacked** (top-left) and select the unzipped
   `spotify-ui-tweaker-v1.5.6` folder — the one containing `manifest.json`.
5. Open `https://open.spotify.com` and click the extension icon — the
   **Themes** tab has every theme, one click to apply.

Detailed steps below. For the **Spotify desktop client**, see "Desktop
client injection" further down.

---

## What's in this folder

| File | Purpose |
|---|---|
| `manifest.json` | Extension definition (MV3) — the file you must see when loading |
| `content.js` | Injects and hot-swaps the CSS; album-art color sampler; EQ canvas recolor |
| `default.css` | The maintained classic selector map ("Load default" button) |
| `popup.html` / `popup.js` | The toolbar popup (themes, presets, palette, editor, diagnostics) |
| `themes/` | Five bundled theme presets + index |
| `images/` | Toolbar/store icons |
| `main.py` | Desktop-client injector (Python) |
| `build.bat` | Builds the injector into a standalone `SpotifyUITweaker.exe` |
| `INSTALL.md` | This guide |

---

## Install in Google Chrome — step by step

### 1. Unzip and keep the folder

Unzip `spotify-ui-tweaker-v1.5.6.zip` anywhere you like — `Documents` or
`Desktop` is fine. You should end up with a folder that **directly contains
`manifest.json`** (some unzip tools nest it one level deeper — that's fine,
just note where it is).

> **Important:** Chrome loads an unpacked extension *from that exact folder*.
> Don't delete, rename or move it after installing — Chrome re-reads it every
> start. If you move it, just re-do step 4 below.

### 2. Open the Extensions page

Type this into Chrome's address bar and press Enter:

```
chrome://extensions
```

(Or: Chrome menu **⋮** → **Extensions** → **Manage Extensions**.)

### 3. Enable Developer mode

Flip the **Developer mode** switch in the **top-right corner** of the
Extensions page. It stays on — that's expected and safe; unpacked extensions
can only run while it's enabled.

### 4. Load the extension

Click **Load unpacked** (top-left), navigate to where you unzipped the
download, and select the `spotify-ui-tweaker-v1.5.6` folder — the one that
directly contains `manifest.json`, *not* the zip itself and not the parent
folder.

"Spotify UI Tweaker" now appears in your extensions list.

### 5. Pin it to the toolbar (recommended)

Click the **puzzle-piece** icon in Chrome's toolbar and click the **pin**
next to "Spotify UI Tweaker" so its icon is always one click away.

### 6. Open Spotify and theme it

Go to `https://open.spotify.com` (if the tab was already open, refresh it
once). Click the toolbar icon — the popup opens with four tabs:

- **Simple** — the **Palette** editor: accent / background / text colors
  with a live mini preview. "Auto-derive hover & press" recomputes the
  whole accent family from the accent color. This tab tunes whatever CSS
  is currently loaded.
- **Themes** — every theme, one click to apply. **Bundled themes**
  (**Adaptive Album Glass**, **Frosted Glass**, **Neon Synthwave Glass**,
  **Violet Nebula Glass**, **Amber Ember Glass**) at the top, then
  **your presets** (see below). A green border + "ON" badge marks what is
  currently applied.
- **Advanced** — paste or edit raw CSS. **Load default** puts the
  maintained classic selector map in the editor as a starting point.
- **Diagnostics** — checks every selector in the map against the live page
  and shows which ones hit (green) or miss (red). Click a row to highlight
  it on the page.

Applying a theme takes effect instantly on every open Spotify tab — no
refresh needed. Your settings survive browser restarts.

---

## The bundled themes

| Theme | Look |
|---|---|
| **Adaptive Album Glass** | Frosted glass panels over an ambient mesh that **re-tints itself from the active album cover** (vibrant color sampled per track — accents, hover/press and the backdrop all follow the music). Marked with the `@msc-adaptive-album` flag. |
| **Frosted Glass** | Ice-cyan accents, cool slate text, translucent glass columns over a fixed blue/violet mesh. |
| **Neon Synthwave Glass** | Pink → purple → cyan synthwave wallpaper with frosted glass columns and electric-cyan accents. |
| **Violet Nebula Glass** | Bright violet accents, lilac-white titles, violet-tinted ambient mesh + glass. |
| **Amber Ember Glass** | Warm amber accents, cream text, ember-toned ambient mesh + glass. |

All five share the same v4.1 selector map — only palettes and glass tokens
differ — so new Spotify UI surfaces (global nav bar, filter pills, Settings,
Equalizer) are themed consistently everywhere.

The desktop client's green **Equalizer canvas** is recolored live by
`content.js` (canvas drawing calls are intercepted and any Spotify-green
stroke is swapped for the theme accent) in every theme.

---

## Your saved presets (Themes tab)

Anything you can build, you can keep:

1. **Tweak** the palette on the Simple tab (or paste CSS on Advanced).
2. Open **Themes**, type a name in the "Name the current CSS…" field and
   click **Save**. Your preset now has a set name and appears in the list
   with its accent color and save date.
3. Click any preset (or row) to **apply** it instantly. Use **Rename**,
   **Export** and **Delete** (click twice — "Sure?" — to confirm) on each
   row.
4. **Export** downloads the preset as a `.css` file; **Import .css file…**
   brings it back on any machine — handy for backups or sharing.

Saved presets are stored in this browser profile and stay put across
restarts and extension reloads.

---

## Desktop client injection (Spotify.exe)

`main.py` loads the **same themes and the same popup GUI into the Spotify
desktop client** — no Chromium wrapper involved:

1. **Requirements:** Python 3 with `pip install websockets pyinstaller`.
2. **Run it:** `python main.py` next to the extension files. It closes
   Spotify, relaunches it with remote debugging on `127.0.0.1:9222`,
   attaches over the DevTools protocol and injects the whole extension
   (content script + popup + themes).
3. **Standalone exe:** run `build.bat` — it produces
   `dist\SpotifyUITweaker.exe` with every asset embedded. Launch that and
   `storage.json` is created next to it automatically when you save
   settings.
4. **Using it:** click the palette button left of the notification bell in
   Spotify's top bar, or press **Alt+C**. **Ctrl+Shift+D** / **Alt+D**
   opens DevTools.

Notes:

- `main.py` bundles every `.css/.js/.html/.json` file next to it — edit
  themes in the folder and rerun (or rebuild) to pick up changes.
- The injector closes Spotify when it exits; close it with Ctrl+C or by
  closing the console/exe rather than killing the process, to keep things
  tidy.
- The client needs the debug port, so the injector relaunches Spotify on
  every start — that is normal.

---

## Updating to a newer version

Your current CSS and saved presets live in Chrome's storage, **keyed to the
folder path you loaded the extension from** (that's how Chrome derives the
ID of an unpacked extension). To keep them:

1. Unzip the new version somewhere temporary.
2. Copy the new files **over the existing folder** — same path, same name.
3. On `chrome://extensions` click the **reload (↻)** icon on Spotify UI
   Tweaker, then refresh Spotify tabs once.

If you'd rather start fresh, **Remove** the old entry and **Load unpacked**
the new folder — you'll get a clean slate (bundled themes are always one
click away). To rescue presets first, Export them from the Themes tab and
Import them after reinstalling.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Could not load extension" / red error card | You selected the wrong folder — pick the one **directly containing `manifest.json`**. Check for a nested folder inside your unzipped download. |
| No theme applied after install | Refresh the `open.spotify.com` tab once. Content scripts only attach on page load. |
| Theme applied but popup edits don't show | Make sure you clicked **Apply & Save** (Advanced tab). Still stuck: refresh the tab, then reload the extension (↻). |
| Bundled themes missing on the Themes tab | The `themes/` folder must stay next to `manifest.json` — don't move or delete it. |
| Saved presets disappeared | You loaded the extension from a different folder path (storage follows the folder-derived ID). Load from the original path again, or Import the preset's exported `.css` file. |
| Album-adaptive colors don't change | Adaptive sampling only runs with **Adaptive Album Glass** (the `@msc-adaptive-album` marker). Pick another theme for a fixed palette. |
| Client injector: "Spotify.exe not found" | It looks in `%APPDATA%\Spotify\Spotify.exe` — the standard client install location. |
| Client injector times out | Close Spotify fully (including the tray), rerun, or check that nothing else occupies port 9222. |
| Chrome shows a startup notice about developer mode | Expected for unpacked extensions. Dismiss it — the extension keeps working. |
| Want it gone | `chrome://extensions` → Spotify UI Tweaker → **Remove**. |

---

## Notes for other browsers

The same steps work in any Chromium browser — just swap the address:

- **Microsoft Edge:** `edge://extensions` → enable Developer mode → Load unpacked
- **Brave:** `brave://extensions` → Developer mode → Load unpacked

## Privacy & permissions

- Only touches pages on `https://open.spotify.com/*` — it cannot see or
  modify any other website.
- Stores your theme and presets locally in Chrome (`chrome.storage.local`).
  No remote code, no analytics, nothing leaves your machine. The client
  injector writes its state to a local `storage.json` next to the exe.
- Does **not** work on the Spotify desktop app **via Chrome** — use the
  `main.py` / `SpotifyUITweaker.exe` injector for that.
