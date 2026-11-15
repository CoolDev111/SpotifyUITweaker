import asyncio
import atexit
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser

import websockets

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------
IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"

BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


def _resolve_app_dir():
    """Directory that holds storage.json.

    Frozen (PyInstaller): next to the executable. On macOS the executable
    lives inside SpotifyUITweaker.app/Contents/MacOS/, so walk up to the
    .app's parent folder instead — that keeps storage.json OUTSIDE the
    bundle, where rebuilding the app won't wipe your saved settings.
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if exe_dir.endswith(os.path.join("Contents", "MacOS")):
            return os.path.dirname(os.path.dirname(os.path.dirname(exe_dir)))
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = _resolve_app_dir()
STORAGE_PATH = os.path.join(APP_DIR, "storage.json")

# Standard Spotify desktop client install locations, per platform.
# Running a portable/custom install? Add its path to this list.
SPOTIFY_CANDIDATES = (
    [os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")]
    if IS_WINDOWS
    else [
        "/Applications/Spotify.app/Contents/MacOS/Spotify",
        os.path.expanduser("~/Applications/Spotify.app/Contents/MacOS/Spotify"),
    ]
)

DEBUG_PORT = 9222


def find_spotify():
    for path in SPOTIFY_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def _quiet(**extra):
    """Common subprocess kwargs; also hides console windows on Windows."""
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if IS_WINDOWS:
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    kwargs.update(extra)
    return kwargs


def kill_spotify():
    if IS_WINDOWS:
        subprocess.run(["taskkill", "/F", "/IM", "Spotify.exe"], **_quiet())
    elif IS_MAC:
        subprocess.run(["killall", "Spotify"], **_quiet())
    else:
        subprocess.run(["pkill", "-x", "Spotify"], **_quiet())


atexit.register(kill_spotify)
signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))


def collect_extension_bundle():
    """Reads all extension HTML, CSS, JS, and theme files into a dictionary."""
    files = {}
    for root, _, filenames in os.walk(BUNDLE_DIR):
        for fname in filenames:
            if fname.endswith((".css", ".js", ".html", ".json")) and fname not in ("main.py", "storage.json"):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, BUNDLE_DIR).replace("\\", "/")
                with open(full_path, "r", encoding="utf-8") as f:
                    files[rel_path] = f.read()

    storage = {}
    if os.path.exists(STORAGE_PATH):
        try:
            with open(STORAGE_PATH, "r", encoding="utf-8") as f:
                storage = json.load(f)
        except Exception:
            storage = {}

    return {"files": files, "storage": storage}


def extract_popup_parts(html_text):
    # 1. Grab every <style>...</style> block from <head> (or anywhere in popup.html)
    styles = re.findall(r"<style[^>]*>([\s\S]*?)</style>", html_text, re.IGNORECASE)
    combined_css = "\n".join(styles)

    # 2. Remap :root, html, and body selectors so they work inside the Shadow DOM
    combined_css = re.sub(
        r'(^|[\s,}])(?::root|html|body)(?=[\s,{:.#\[])',
        r'\1:host, #msc-popup-modal',
        combined_css,
        flags=re.MULTILINE
    )

    # 3. Extract <body> content and strip <script> tags
    m = re.search(r"<body[^>]*>([\s\S]*?)</body>", html_text, re.IGNORECASE)
    body_inner = m.group(1) if m else html_text
    body_inner = re.sub(r"<script[\s\S]*?</script>", "", body_inner, flags=re.IGNORECASE)

    return body_inner, combined_css

def is_debug_port_open():
    try:
        with urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json", timeout=0.5):
            return True
    except Exception:
        return False

def restart_spotify_with_debug():
    spotify_exe = find_spotify()
    if not spotify_exe:
        raise FileNotFoundError(
            "Spotify desktop client not found. Looked in:\n  "
            + "\n  ".join(SPOTIFY_CANDIDATES)
        )

    print("[MSC] Closing existing Spotify instances...")
    kill_spotify()
    time.sleep(1.0)

    print(f"[MSC] Launching Spotify with --remote-debugging-port={DEBUG_PORT} and --remote-debugging-address=127.0.0.1...")
    subprocess.Popen(
        [spotify_exe, f"--remote-debugging-port={DEBUG_PORT}", "--remote-debugging-address=127.0.0.1"],
        **_quiet()
    )

def wait_for_spotify_target(timeout=30):
    deadline = time.time() + timeout
    url = f"http://localhost:{DEBUG_PORT}/json"
    print("[MSC] Waiting for Spotify page target...")

    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                targets = json.loads(resp.read().decode("utf-8"))
                for target in targets:
                    target_url = target.get("url", "")
                    if target.get("type") == "page" and "spotify.com" in target_url:
                        print(f"[MSC] Attached to: {target_url}")
                        return target["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)

    raise TimeoutError(f"Timed out after {timeout}s waiting for Spotify target.")

def build_extension_payload(bundle):
    files = bundle["files"]
    popup_html_body, popup_css = extract_popup_parts(files.get("popup.html", ""))
    content_js = files.get("content.js", "")
    popup_js = files.get("popup.js", "")

    serialized_files = json.dumps(files)
    serialized_storage = json.dumps(bundle["storage"])
    serialized_popup_html = json.dumps(popup_html_body)
    serialized_popup_css = json.dumps(popup_css)

    ver = "1.5.6"

    return f"""
    (() => {{
        if (window.__MSC_EXT_BOOTED__) return;
        window.__MSC_EXT_BOOTED__ = true;

        // 0. Allow innerHTML under Spotify's Trusted Types CSP
        if (window.trustedTypes && window.trustedTypes.createPolicy) {{
            try {{
                window.trustedTypes.createPolicy('default', {{
                    createHTML: (s) => s,
                    createScriptURL: (s) => s,
                    createScript: (s) => s
                }});
            }} catch (e) {{}}
        }}

        const EXT_FILES = {serialized_files};
        const STORAGE_DATA = {serialized_storage};
        const storageListeners = [];
        const messageListeners = [];

        // 1. Intercept fetch() for extension assets (default.css, themes/themes.json, themes/*.css)
        const origFetch = window.fetch.bind(window);
        window.fetch = (input, init) => {{
            const url = typeof input === 'string' ? input : (input && input.url) || '';
            if (url.startsWith('msc-ext://')) {{
                const key = url.replace('msc-ext://', '').replace(/^\\/+/, '');
                if (Object.prototype.hasOwnProperty.call(EXT_FILES, key)) {{
                    return Promise.resolve(new Response(EXT_FILES[key], {{
                        status: 200,
                        headers: {{ 'Content-Type': key.endsWith('.json') ? 'application/json' : 'text/plain' }}
                    }}));
                }}
                return Promise.resolve(new Response('', {{ status: 404 }}));
            }}
            return origFetch(input, init);
        }};

        // 2. Chrome Extension API Shim (runtime, storage.local, tabs)
        window.chrome = window.chrome || {{}};
        window.chrome.runtime = {{
            getURL: (p) => 'msc-ext://' + String(p || '').replace(/^\\/+/, ''),
            getManifest: () => ({{ version: '{ver}' }}),
            lastError: null,
            onMessage: {{
                addListener: (fn) => messageListeners.push(fn)
            }}
        }};

        window.chrome.storage = {{
            local: {{
                get: (keys, cb) => {{
                    const res = {{}};
                    const list = Array.isArray(keys) ? keys : (typeof keys === 'string' ? [keys] : Object.keys(STORAGE_DATA));
                    for (const k of list) {{
                        if (Object.prototype.hasOwnProperty.call(STORAGE_DATA, k)) {{
                            res[k] = STORAGE_DATA[k];
                        }}
                    }}
                    if (cb) setTimeout(() => cb(res), 0);
                    return Promise.resolve(res);
                }},
                set: (items, cb) => {{
                    const changes = {{}};
                    for (const [k, v] of Object.entries(items || {{}})) {{
                        changes[k] = {{ oldValue: STORAGE_DATA[k], newValue: v }};
                        STORAGE_DATA[k] = v;
                    }}
                    if (typeof window.mscPersistStorage === 'function') {{
                        window.mscPersistStorage(JSON.stringify(STORAGE_DATA));
                    }}
                    for (const fn of storageListeners) {{
                        try {{ fn(changes, 'local'); }} catch (e) {{}}
                    }}
                    if (cb) setTimeout(() => cb(), 0);
                    return Promise.resolve();
                }}
            }},
            onChanged: {{
                addListener: (fn) => storageListeners.push(fn)
            }}
        }};

        window.chrome.tabs = {{
            query: async () => [{{ id: 1, url: 'https://open.spotify.com' }}],
            sendMessage: (tabId, msg) => new Promise((resolve) => {{
                let responded = false;
                for (const fn of messageListeners) {{
                    fn(msg, {{ tab: {{ id: 1 }} }}, (resp) => {{
                        responded = true;
                        resolve(resp);
                    }});
                }}
                if (!responded) resolve(null);
            }})
        }};

        const mountFullExtension = () => {{
            // Run content.js on the main Spotify document
            (function() {{
                {content_js}
            }})();

            // Keep <style id="my-spotify-custom-css"> locked right above </head>
            const headObs = new MutationObserver(() => {{
                const st = document.getElementById('my-spotify-custom-css');
                if (st && document.head && document.head.lastElementChild !== st) {{
                    document.head.appendChild(st);
                }}
            }});
            if (document.head) headObs.observe(document.head, {{ childList: true }});

            // Mount popup.html + popup.css + popup.js inside an isolated Shadow DOM
            const host = document.createElement('div');
            host.id = 'msc-shadow-host';
            document.documentElement.appendChild(host);
            const shadow = host.attachShadow({{ mode: 'open' }});

            const wrapper = document.createElement('div');
            wrapper.id = 'msc-popup-modal';
            Object.assign(wrapper.style, {{
                display: 'none', // Closed on boot; click the top-bar button (or Alt+C) to open
                position: 'fixed',
                top: '56px',
                right: '24px',
                zIndex: '999999',
                borderRadius: '12px',
                overflow: 'hidden',
                boxShadow: '0 16px 40px rgba(0, 0, 0, 0.85)',
                border: '1px solid #2e2e32',
                maxHeight: '84vh',
                overflowY: 'auto',
                background: '#161618'
            }});

            const styleTag = document.createElement('style');
            styleTag.textContent = {serialized_popup_css};
            wrapper.innerHTML = {serialized_popup_html};

            shadow.appendChild(styleTag);
            shadow.appendChild(wrapper);

            // Scope document DOM lookups inside popup.js to the ShadowRoot
            const shadowDocProxy = new Proxy(document, {{
                get(target, prop) {{
                    if (prop === 'getElementById') return (id) => shadow.getElementById(id);
                    if (prop === 'querySelector') return (sel) => shadow.querySelector(sel);
                    if (prop === 'querySelectorAll') return (sel) => shadow.querySelectorAll(sel);
                    const val = target[prop];
                    return typeof val === 'function' ? val.bind(target) : val;
                }}
            }});

            ((document) => {{
                {popup_js}
            }})(shadowDocProxy);

            const togglePopup = () => {{
                const isHidden = wrapper.style.display === 'none';
                wrapper.style.display = isHidden ? 'block' : 'none';
            }};

            const ensureNavButton = () => {{
                const bellBtn = document.querySelector('button[data-testid="whats-new-feed-button"]');
                if (!bellBtn || !bellBtn.parentElement) return;
                if (document.getElementById('msc-nav-tweaker-btn')) return;

                const btn = document.createElement('button');
                btn.id = 'msc-nav-tweaker-btn';
                btn.type = 'button';
                btn.className = bellBtn.className;
                btn.setAttribute('aria-label', 'Spotify UI Tweaker');
                btn.setAttribute('title', 'Spotify UI Tweaker (Alt+C)');
                btn.setAttribute('data-encore-id', 'buttonTertiary');

                const bellSvg = bellBtn.querySelector('svg');
                const svgClass = bellSvg ? bellSvg.getAttribute('class') : '';
                const svgStyle = bellSvg
                    ? bellSvg.getAttribute('style')
                    : '--encore-icon-height: var(--encore-graphic-size-decorative-smaller); --encore-icon-width: var(--encore-graphic-size-decorative-smaller);';

                btn.innerHTML = `
                    <svg data-encore-id="icon" role="img" aria-hidden="true" class="${{svgClass}}" viewBox="0 0 16 16" style="${{svgStyle}}">
                        <path d="M8 1a7 7 0 0 0-7 7c0 3.866 3.134 7 7 7a1.5 1.5 0 0 0 1.41-2.012 1.5 1.5 0 0 1 1.41-2.012H12a3 3 0 0 0 3-3c0-3.866-3.134-6.976-7-6.976zm-3.25 7.5a1 1 0 1 1 0-2 1 1 0 0 1 0 2zm1.75-3a1 1 0 1 1 0-2 1 1 0 0 1 0 2zm3.5 0a1 1 0 1 1 0-2 1 1 0 0 1 0 2zm2 3a1 1 0 1 1 0-2 1 1 0 0 1 0 2z"></path>
                    </svg>
                `;

                btn.addEventListener('click', (e) => {{
                    e.stopPropagation();
                    togglePopup();
                }});

                bellBtn.parentElement.insertBefore(btn, bellBtn);
            }};

            ensureNavButton();
            const navObs = new MutationObserver(() => ensureNavButton());
            navObs.observe(document.body, {{ childList: true, subtree: true }});

            document.addEventListener(
                'mousedown',
                (e) => {{
                    if (wrapper.style.display === 'none') return;
                    const path = e.composedPath ? e.composedPath() : [];
                    const navBtn = document.getElementById('msc-nav-tweaker-btn');
                    if (!path.includes(host) && (!navBtn || !path.includes(navBtn))) {{
                        wrapper.style.display = 'none';
                    }}
                }},
                true,
            );

            window.addEventListener(
                'keydown',
                (e) => {{
                    if (e.altKey && e.key.toLowerCase() === 'c') {{
                        e.preventDefault();
                        e.stopPropagation();
                        togglePopup();
                    }}
                }},
                true,
            );

            window.addEventListener(
                'keydown',
                (e) => {{
                    const isDevShortcut = (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === 'd')
                                    || (e.altKey && e.key.toLowerCase() === 'd');
                    if (isDevShortcut) {{
                        e.preventDefault();
                        e.stopPropagation();
                        if (typeof window.mscOpenDevTools === 'function') {{
                            window.mscOpenDevTools();
                        }}
                    }}
                }},
                true,
            );
        }};

        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', mountFullExtension);
        }} else {{
            mountFullExtension();
        }}
    }})();
    """

def launch_devtools_window():
    """Opens the active Spotify DevTools inspector in a standalone browser window."""
    try:
        with urllib.request.urlopen(f"http://localhost:{DEBUG_PORT}/json", timeout=2) as resp:
            targets = json.loads(resp.read().decode("utf-8"))
            target = next((t for t in targets if t.get("type") == "page"), None)
            if not target:
                return

            ws_part = target["webSocketDebuggerUrl"].replace("ws://", "")
            inspector_url = f"http://localhost:{DEBUG_PORT}/devtools/inspector.html?ws={ws_part}"

            if IS_WINDOWS:
                browser_candidates = [
                    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
                ]
            elif IS_MAC:
                browser_candidates = [
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                    "/Applications/Chromium.app/Contents/MacOS/Chromium",
                ]
            else:
                browser_candidates = [
                    shutil.which(name)
                    for name in ("google-chrome", "microsoft-edge", "brave-browser", "chromium", "chromium-browser")
                ]

            browser_exe = next((p for p in browser_candidates if p and os.path.exists(p)), None)

            if browser_exe:
                dev_profile = os.path.join(tempfile.gettempdir(), "msc-devtools-profile")
                subprocess.Popen(
                    [
                        browser_exe,
                        f"--user-data-dir={dev_profile}",
                        "--disable-web-security",
                        "--no-first-run",
                        "--no-default-browser-check",
                        f"--app={inspector_url}"
                    ],
                    **_quiet()
                )
            else:
                webbrowser.open(f"http://localhost:{DEBUG_PORT}")
    except Exception as e:
        print(f"[MSC] Failed to launch DevTools: {e}")

async def session_loop(ws_url, payload):
    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
        await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))

        # Register both storage persistence and the Ctrl+Shift+I DevTools trigger
        await ws.send(json.dumps({
            "id": 3,
            "method": "Runtime.addBinding",
            "params": {"name": "mscPersistStorage"}
        }))
        await ws.send(json.dumps({
            "id": 4,
            "method": "Runtime.addBinding",
            "params": {"name": "mscOpenDevTools"}
        }))

        await ws.send(json.dumps({
            "id": 5,
            "method": "Page.addScriptToEvaluateOnNewDocument",
            "params": {"source": payload}
        }))

        await ws.send(json.dumps({
            "id": 6,
            "method": "Runtime.evaluate",
            "params": {"expression": payload}
        }))

        print("[MSC] Extension injected! Click the palette icon left of the notification bell (or press Alt+C).")

        async for raw_msg in ws:
            msg = json.loads(raw_msg)
            if msg.get("method") == "Runtime.bindingCalled":
                params = msg.get("params", {})
                name = params.get("name")
                if name == "mscPersistStorage":
                    with open(STORAGE_PATH, "w", encoding="utf-8") as f:
                        f.write(params.get("payload", "{}"))
                elif name == "mscOpenDevTools":
                    launch_devtools_window()

def main():
    bundle = collect_extension_bundle()
    if not is_debug_port_open():
        restart_spotify_with_debug()
    else:
        print("[MSC] Spotify already running with DevTools enabled, attaching directly...")

    ws_url = wait_for_spotify_target()
    payload = build_extension_payload(bundle)

    try:
        asyncio.run(session_loop(ws_url, payload))
    except websockets.exceptions.ConnectionClosed:
        print("[MSC] Spotify closed. Exiting cleanly.")


if __name__ == "__main__":
    try:
        main()
    finally:
        kill_spotify()
