/* Spotify UI Tweaker popup — v1.5.6
   Tabs:
     - Simple     : palette GUI (SECTION 0 of the CSS) for whatever is loaded.
     - Themes     : bundled themes + your own saved presets — one click
                    applies a theme; presets can be renamed, exported and
                    re-imported as .css files.
     - Advanced   : raw CSS textarea (the classic view)
     - Diagnostics: selector checker against the live Spotify tab
   All tabs edit ONE source of truth (cssText). Applying a theme or
   "Apply & Save" writes chrome.storage.local.customCss, which content.js
   hot-reloads on every open Spotify tab. Saved presets live in
   chrome.storage.local.userPresets. */

/* ------------------------------------------------------------------ */
/* Element refs                                                        */
/* ------------------------------------------------------------------ */
const cssInput = document.getElementById("cssInput");
const saveBtn = document.getElementById("saveBtn");
const loadDefaultBtn = document.getElementById("loadDefaultBtn");
const diagBtn = document.getElementById("diagBtn");
const diagResults = document.getElementById("diagResults");
const status = document.getElementById("status");

const shippedList = document.getElementById("shippedList");
const userPresetList = document.getElementById("userPresetList");
const presetName = document.getElementById("presetName");
const savePresetBtn = document.getElementById("savePresetBtn");
const importPresetBtn = document.getElementById("importPresetBtn");
const importFile = document.getElementById("importFile");
const paletteRows = document.getElementById("paletteRows");
const paletteNotice = document.getElementById("paletteNotice");
const autoDerive = document.getElementById("autoDerive");
const preview = document.getElementById("preview");
const verBadge = document.getElementById("ver");
const updateNotice = document.getElementById("updateNotice");

/* Same GitHub repo main.py checks - this is the multi-platform monorepo
   (Windows/Mac launcher + this extension), so one tag covers all of them. */
const UPDATE_REPO = "CoolDev111/SpotifyUITweaker";
const UPDATE_API = "https://api.github.com/repos/" + UPDATE_REPO;
const UPDATE_PAGE = "https://github.com/" + UPDATE_REPO + "/releases";
const UPDATE_CACHE_TTL_MS = 12 * 60 * 60 * 1000;

/* ------------------------------------------------------------------ */
/* Palette definition (must match SECTION 0 of default.css)            */
/* ------------------------------------------------------------------ */
const PALETTE_VARS = [
  { key: "accent", cssVar: "--msc-accent", label: "Accent", desc: "replaces Spotify green everywhere" },
  { key: "accentHover", cssVar: "--msc-accent-hover", label: "Accent hover", desc: "accent surfaces on hover (lighter)" },
  { key: "accentPress", cssVar: "--msc-accent-press", label: "Accent press", desc: "accent surfaces while pressed (darker)" },
  { key: "textPrimary", cssVar: "--msc-text-primary", label: "Text primary", desc: "song titles, playlist names, headers" },
  { key: "textMuted", cssVar: "--msc-text-muted", label: "Text muted", desc: "artists, subtitles, metadata" },
  { key: "onAccent", cssVar: "--msc-on-accent", label: "On-accent", desc: "text/icons placed ON accent surfaces" },
];

/* ------------------------------------------------------------------ */
/* State                                                               */
/* ------------------------------------------------------------------ */
let cssText = "";
let defaultCss = "";
let palette = null;          // { accent:"#...", ... } raw values, or null
let wantDefaultPrefill = false;
let shippedEntries = [];     // bundled themes [{file, name, accent, css}]
let shippedSource = "builtin";
let userPresets = [];        // saved presets from chrome.storage.local.userPresets
const palRefs = {};          // key -> { color: input, hex: input }

/* ------------------------------------------------------------------ */
/* Small helpers                                                       */
/* ------------------------------------------------------------------ */
function setStatus(msg, ms = 1500) {
  status.textContent = msg;
  if (ms) {
    setTimeout(() => {
      if (status.textContent === msg) status.textContent = "";
    }, ms);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[c]);
}

function escapeRegExp(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/* Leading dotted-number run from a tag/version string, as an int array.
   Ignores a "v" prefix and anything from "+" or other non-numeric text
   onward, so "v1.6", "1.5.7+taskbar6" and "v1.4 Built App" parse to
   [1,6], [1,5,7] and [1,4]. Mirrors _parse_version in main.py. */
function parseVersion(tag) {
  const m = String(tag || "").trim().match(/^v?(\d+(?:\.\d+)*)/);
  return m ? m[1].split(".").map(Number) : null;
}

function versionGreater(a, b) {
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i++) {
    const x = i < a.length ? a[i] : -1;
    const y = i < b.length ? b[i] : -1;
    if (x !== y) return x > y;
  }
  return false;
}

function titleCase(s) {
  return String(s)
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

function prettifyFileName(name) {
  const base = String(name).replace(/\.css$/i, "").replace(/^theme-/i, "");
  return titleCase(base.replace(/[-_]+/g, " "));
}

/* ------------------------------------------------------------------ */
/* Color math (hex <-> hsl, hover/press derivation)                    */
/* ------------------------------------------------------------------ */
function normalizeHex(v) {
  const m = String(v || "").trim().match(/^#?([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (!m) return null;
  let h = m[1].toLowerCase();
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  return "#" + h;
}

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

function rgbToHex(r, g, b) {
  return "#" + [r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("");
}

function hexToHsl(hex) {
  let [r, g, b] = hexToRgb(hex).map((v) => v / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0, s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0));
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
  }
  return [h, s * 100, l * 100];
}

function hslToHex(h, s, l) {
  const S = s / 100, L = l / 100;
  const c = (1 - Math.abs(2 * L - 1)) * S;
  const hp = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let [r, g, b] = hp < 1 ? [c, x, 0]
    : hp < 2 ? [x, c, 0]
    : hp < 3 ? [0, c, x]
    : hp < 4 ? [0, x, c]
    : hp < 5 ? [x, 0, c]
    : [c, 0, x];
  const m = L - c / 2;
  return rgbToHex((r + m) * 255, (g + m) * 255, (b + m) * 255);
}

function deriveHover(hex) {
  const [h, s, l] = hexToHsl(hex);
  return hslToHex(h, s, Math.min(90, l + 9));
}

function derivePress(hex) {
  const [h, s, l] = hexToHsl(hex);
  return hslToHex(h, s, Math.max(10, l - 7));
}

/* ------------------------------------------------------------------ */
/* Tabs                                                                */
/* ------------------------------------------------------------------ */
const tabButtons = document.querySelectorAll(".tab");
const tabPanels = {
  simple: document.getElementById("tab-simple"),
  themes: document.getElementById("tab-themes"),
  advanced: document.getElementById("tab-advanced"),
  diag: document.getElementById("tab-diag"),
};

function switchTab(name) {
  tabButtons.forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  Object.entries(tabPanels).forEach(([k, el]) => el.classList.toggle("active", k === name));
  if (name === "simple") refreshGuiFromCss();
  if (name === "themes") {
    renderShippedThemes();
    renderUserPresets();
  }
  if (name === "advanced") cssInput.value = cssText;
}

tabButtons.forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));

/* ------------------------------------------------------------------ */
/* Palette parse / serialize (operates on the :root block that         */
/* contains --msc-accent — SECTION 0 of the selector map)              */
/* ------------------------------------------------------------------ */
function findPaletteBlock(css) {
  if (!css) return null;
  const re = /:root\s*\{([^}]*)\}/g;
  let m;
  while ((m = re.exec(css))) {
    if (m[1].includes("--msc-accent")) {
      return { start: m.index, end: m.index + m[0].length, body: m[0] };
    }
  }
  return null;
}

function parsePalette(css) {
  const block = findPaletteBlock(css);
  if (!block) return null;
  const values = {};
  for (const v of PALETTE_VARS) {
    const vm = block.body.match(new RegExp(escapeRegExp(v.cssVar) + "\\s*:\\s*([^;\\n]+)"));
    values[v.key] = vm ? vm[1].trim() : null;
  }
  return values;
}

function serializePalette(css, values) {
  const block = findPaletteBlock(css);
  if (!block) return css;
  let body = block.body;
  for (const v of PALETTE_VARS) {
    const val = values[v.key];
    if (!val) continue;
    body = body.replace(
      new RegExp(escapeRegExp(v.cssVar) + "(\\s*:\\s*)[^;\\n]+(;)", "g"),
      (whole, p1, p2) => v.cssVar + p1 + val + p2
    );
  }
  return css.slice(0, block.start) + body + css.slice(block.end);
}

/* ------------------------------------------------------------------ */
/* Single source of truth                                              */
/* ------------------------------------------------------------------ */
function setCssText(text) {
  cssText = text || "";
  cssInput.value = cssText;
  refreshGuiFromCss();
}

function commitGui() {
  if (!palette) return;
  const values = {};
  for (const v of PALETTE_VARS) {
    const typed = palRefs[v.key].hex.value.trim();
    values[v.key] = typed || palette[v.key] || "";
  }
  cssText = serializePalette(cssText, values);
  cssInput.value = cssText; // keep Advanced tab in sync
  palette = parsePalette(cssText);
  updatePreview(values);
}

/* ------------------------------------------------------------------ */
/* Palette GUI                                                         */
/* ------------------------------------------------------------------ */
function buildPaletteRows() {
  for (const v of PALETTE_VARS) {
    const row = document.createElement("div");
    row.className = "pal-row";
    const color = document.createElement("input");
    color.type = "color";
    const hex = document.createElement("input");
    hex.type = "text";
    hex.className = "hex";
    hex.spellcheck = false;
    const label = document.createElement("div");
    label.className = "pal-label";
    label.innerHTML = "<b>" + escapeHtml(v.label) + "</b><small>" + escapeHtml(v.desc) + "</small>";
    row.append(color, hex, label);
    paletteRows.appendChild(row);
    palRefs[v.key] = { color, hex };

    color.addEventListener("input", () => {
      hex.value = color.value;
      if (v.key === "accent" && autoDerive.checked) deriveFamilyFrom(color.value);
      commitGui();
    });

    hex.addEventListener("change", () => {
      const norm = normalizeHex(hex.value);
      if (!norm) {
        hex.value = palette && palette[v.key] ? palette[v.key] : "";
        setStatus("Not a hex color — kept the previous value", 2000);
        return;
      }
      hex.value = norm;
      color.value = norm;
      if (v.key === "accent" && autoDerive.checked) deriveFamilyFrom(norm);
      commitGui();
    });
  }
}

function deriveFamilyFrom(accentHex) {
  const hover = deriveHover(accentHex);
  const press = derivePress(accentHex);
  palRefs.accentHover.color.value = hover;
  palRefs.accentHover.hex.value = hover;
  palRefs.accentPress.color.value = press;
  palRefs.accentPress.hex.value = press;
  palette = palette || {};
  palette.accentHover = hover;
  palette.accentPress = press;
}

function refreshGuiFromCss() {
  palette = parsePalette(cssText);
  if (!palette) {
    paletteNotice.textContent =
      "No palette block found in the current CSS (looked for :root { --msc-accent: ... }). " +
      "Use Advanced > Load default, or a preset, then come back.";
    paletteNotice.hidden = false;
    paletteRows.hidden = true;
    autoDerive.hidden = true;
    preview.hidden = true;
    return;
  }
  paletteNotice.hidden = true;
  paletteRows.hidden = false;
  autoDerive.hidden = false;
  preview.hidden = false;
  for (const v of PALETTE_VARS) {
    const raw = palette[v.key] || "";
    const norm = normalizeHex(raw);
    palRefs[v.key].color.value = norm || "#000000";
    palRefs[v.key].hex.value = raw;
  }
  updatePreview();
}

function updatePreview(values) {
  if (!palette) return;
  const get = (k, fallback) => (values && values[k]) || (palette && palette[k]) || fallback;
  preview.style.setProperty("--pv-accent", get("accent", "#1ed760"));
  preview.style.setProperty("--pv-on-accent", get("onAccent", "#000000"));
  preview.style.setProperty("--pv-text", get("textPrimary", "#ffffff"));
  preview.style.setProperty("--pv-muted", get("textMuted", "#b3b3b3"));
}

/* ------------------------------------------------------------------ */
/* Bundled themes (themes/ folder inside the extension package)        */
/* ------------------------------------------------------------------ */
/* Last-resort list, used only when BOTH the folder scan and themes/themes.json
   are unavailable. Keep in sync with themes/themes.json. */
const FALLBACK_PRESETS = ["themes/theme-amber-ember.css", "themes/theme-violet-nebula.css"];

function listThemeFiles() {
  return new Promise((resolve) => {
    if (
      typeof chrome === "undefined" ||
      !chrome.runtime ||
      typeof chrome.runtime.getPackageDirectoryEntry !== "function"
    ) {
      resolve(null);
      return;
    }
    try {
      chrome.runtime.getPackageDirectoryEntry((root) => {
        if (chrome.runtime.lastError || !root) {
          resolve(null);
          return;
        }
        root.getDirectory("themes", { create: false }, (dir) => {
          const reader = dir.createReader();
          const files = [];
          const readBatch = () => {
            reader.readEntries((entries) => {
              if (!entries.length) {
                files.sort();
                resolve(files);
                return;
              }
              for (const e of entries) {
                if (e.isFile && /\.css$/i.test(e.name)) files.push("themes/" + e.name);
              }
              readBatch();
            }, () => resolve(files));
          };
          readBatch();
        }, () => resolve(null));
      });
    } catch (e) {
      resolve(null);
    }
  });
}

async function readPresetMeta(file) {
  const fallbackName = prettifyFileName(file.split("/").pop());
  try {
    const res = await fetch(chrome.runtime.getURL(file));
    if (!res.ok) throw new Error("HTTP " + res.status);
    const text = res.text ? await res.text() : "";
    const nameM = text.match(/MY SPOTIFY CUSTOM[^\n]*?THEME:\s*([^\n(]+)/);
    const accentM = text.match(/--msc-accent\s*:\s*(#[0-9a-fA-F]{6})\b/);
    return {
      file,
      css: text,
      name: nameM ? titleCase(nameM[1].trim()) : fallbackName,
      accent: accentM ? accentM[1].toLowerCase() : null,
    };
  } catch (e) {
    return { file, css: null, name: fallbackName, accent: null };
  }
}

/* themes/themes.json — the universal preset index. A real folder scan is
   only possible for UNPACKED Chrome installs (getPackageDirectoryEntry);
   packed extensions read this file instead. */
async function fetchThemesIndex() {
  if (!extensionApiAvailable) return null;
  try {
    const res = await fetch(chrome.runtime.getURL("themes/themes.json"));
    if (!res.ok) return null;
    const data = await res.json();
    if (!data || !Array.isArray(data.presets)) return null;
    return data.presets.filter((p) => typeof p === "string" && /\.css$/i.test(p));
  } catch (e) {
    return null;
  }
}

async function loadShippedThemes() {
  const scannedFiles = await listThemeFiles();   // unpacked Chrome: real scan
  const indexedFiles = await fetchThemesIndex(); // packed Chrome: index
  let files, source;
  if (scannedFiles && scannedFiles.length) {
    files = scannedFiles; source = "scan";
  } else if (indexedFiles && indexedFiles.length) {
    files = indexedFiles; source = "index";
  } else {
    files = FALLBACK_PRESETS; source = "builtin";
  }

  const entries = [];
  if (defaultCss) {
    const accentM = defaultCss.match(/--msc-accent\s*:\s*(#[0-9a-fA-F]{6})\b/);
    entries.push({
      file: "default.css",
      name: "Default (Spotify Classic)",
      accent: accentM ? accentM[1].toLowerCase() : "#1ed760",
      css: defaultCss,
    });
  }
  for (const f of files) entries.push(await readPresetMeta(f));
  shippedEntries = entries;
  shippedSource = source;
  renderShippedThemes();
}

function renderShippedThemes() {
  shippedList.innerHTML = "";
  for (const p of shippedEntries) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "preset-chip" + (p.css && cssText && cssText === p.css ? " active" : "");
    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = p.accent || "#555";
    const label = document.createElement("span");
    label.textContent = p.name;
    chip.append(dot, label);
    chip.title = p.name + (p.accent ? " — accent " + p.accent : "") + " — one click applies it";
    chip.addEventListener("click", () => applyTheme(p.name, p.css));
    shippedList.appendChild(chip);
  }
  if (shippedSource !== "scan") {
    const note = document.createElement("span");
    note.className = "muted";
    note.textContent = shippedSource === "index"
      ? "(bundled themes from themes/themes.json — drop new .css files in that folder)"
      : "(theme index unavailable — showing built-in themes)";
    shippedList.appendChild(note);
  }
}

/* Apply a theme (bundled or saved): load into the editor AND save, so
   every open Spotify tab hot-reloads immediately via storage.onChanged. */
function applyTheme(name, css) {
  if (!css) {
    setStatus("Could not load theme: " + name, 2500);
    return;
  }
  setCssText(css);
  if (!extensionApiAvailable) {
    setStatus('Loaded "' + name + '" — standalone preview', 2200);
    renderShippedThemes();
    renderUserPresets();
    return;
  }
  chrome.storage.local.set({ customCss: cssText }, () => {
    if (chrome.runtime.lastError) {
      setStatus("Save failed: " + chrome.runtime.lastError.message, 3000);
      return;
    }
    setStatus("Theme applied: " + name, 2000);
    renderShippedThemes();
    renderUserPresets();
  });
}

/* ------------------------------------------------------------------ */
/* User presets (saved in chrome.storage.local.userPresets)            */
/* ------------------------------------------------------------------ */
function extractAccent(css) {
  const m = String(css || "").match(/--msc-accent\s*:\s*(#[0-9a-fA-F]{6})\b/);
  return m ? m[1].toLowerCase() : null;
}

function newPresetId() {
  return (typeof crypto !== "undefined" && crypto.randomUUID)
    ? crypto.randomUUID()
    : "p" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
}

function formatStamp(ts) {
  const d = new Date(ts || Date.now());
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) +
    " · " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function getUserPresets() {
  return new Promise((resolve) => {
    if (!extensionApiAvailable) { resolve([]); return; }
    chrome.storage.local.get(["userPresets"], (res) => {
      const arr = res && Array.isArray(res.userPresets) ? res.userPresets : [];
      resolve(arr.filter((p) => p && typeof p.name === "string" && typeof p.css === "string"));
    });
  });
}

function setUserPresets(arr) {
  return new Promise((resolve, reject) => {
    if (!extensionApiAvailable) { resolve(); return; }
    chrome.storage.local.set({ userPresets: arr }, () => {
      if (chrome.runtime.lastError) reject(chrome.runtime.lastError);
      else resolve();
    });
  });
}

function getUpdateCheckCache() {
  return new Promise((resolve) => {
    if (!extensionApiAvailable) { resolve(null); return; }
    chrome.storage.local.get(["updateCheckCache"], (res) => {
      resolve(res && res.updateCheckCache ? res.updateCheckCache : null);
    });
  });
}

function setUpdateCheckCache(cache) {
  return new Promise((resolve) => {
    if (!extensionApiAvailable) { resolve(); return; }
    chrome.storage.local.set({ updateCheckCache: cache }, () => resolve());
  });
}

/* Same two-step lookup as main.py's _latest_remote_version: a proper
   Release first, falling back to bare tags (404) for a repo that only
   pushes tags. Never throws - a failed/blocked fetch just means no
   update notice this time, not a broken popup. */
async function fetchLatestTag() {
  try {
    const res = await fetch(UPDATE_API + "/releases/latest", {
      headers: { Accept: "application/vnd.github+json" },
    });
    if (res.ok) {
      const data = await res.json();
      const v = parseVersion(data.tag_name);
      if (v) return { version: v, tag: data.tag_name };
    } else if (res.status !== 404) {
      return null;
    }
  } catch (e) {
    return null;
  }
  try {
    const res = await fetch(UPDATE_API + "/tags", {
      headers: { Accept: "application/vnd.github+json" },
    });
    if (!res.ok) return null;
    const tags = await res.json();
    let best = null;
    for (const t of tags) {
      const v = parseVersion(t.name);
      if (v && (!best || versionGreater(v, best.version))) best = { version: v, tag: t.name };
    }
    return best;
  } catch (e) {
    return null;
  }
}

async function checkForUpdate() {
  if (!extensionApiAvailable || !chrome.runtime.getManifest) return;
  let current;
  try {
    current = parseVersion(chrome.runtime.getManifest().version);
  } catch (e) {
    return;
  }
  if (!current) return;

  let cached = await getUpdateCheckCache();
  const fresh = cached && typeof cached.ts === "number" && (Date.now() - cached.ts) < UPDATE_CACHE_TTL_MS;
  if (!fresh) {
    const found = await fetchLatestTag();
    cached = found ? { version: found.version, tag: found.tag, ts: Date.now() } : { ts: Date.now() };
    await setUpdateCheckCache(cached);
  }
  if (!cached || !cached.version || !versionGreater(cached.version, current)) return;

  updateNotice.innerHTML =
    "Update available: " + escapeHtml(cached.tag) +
    ' — <a href="#" id="updateLink" style="color:var(--accent);font-weight:bold">View release</a>';
  updateNotice.hidden = false;
  document.getElementById("updateLink").addEventListener("click", (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: UPDATE_PAGE });
  });
}

async function refreshUserPresets() {
  userPresets = await getUserPresets();
  renderUserPresets();
}

function renderUserPresets() {
  userPresetList.innerHTML = "";
  if (!userPresets.length) {
    const empty = document.createElement("div");
    empty.className = "thm-empty";
    empty.textContent = extensionApiAvailable
      ? "Nothing saved yet. Tweak the palette or CSS, name it below and hit Save."
      : "Extension APIs unavailable — standalone preview.";
    userPresetList.appendChild(empty);
    return;
  }
  userPresets.forEach((p, idx) => {
    const active = cssText && cssText === p.css;
    const row = document.createElement("div");
    row.className = "thm-row" + (active ? " active" : "");

    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = p.accent || "#555";

    const main = document.createElement("div");
    main.className = "thm-main";
    main.title = 'Click to apply "' + p.name + '" (saved ' + formatStamp(p.createdAt) + ")";
    const nameSpan = document.createElement("span");
    nameSpan.className = "thm-name";
    nameSpan.textContent = p.name;
    const dateSpan = document.createElement("div");
    dateSpan.className = "thm-date";
    dateSpan.textContent = "saved " + formatStamp(p.createdAt);
    main.append(nameSpan, dateSpan);
    main.addEventListener("click", () => {
      if (row.dataset.renaming) return;
      applyTheme(p.name, p.css);
    });

    row.append(dot, main);

    if (active) {
      const badge = document.createElement("span");
      badge.className = "thm-badge";
      badge.textContent = "on";
      row.appendChild(badge);
    }

    const actions = document.createElement("div");
    actions.className = "thm-actions";

    const renameBtn = document.createElement("button");
    renameBtn.type = "button";
    renameBtn.textContent = "Rename";
    renameBtn.title = "Rename this preset";
    renameBtn.addEventListener("click", () => startRename(p, nameSpan, row));

    const exportBtn = document.createElement("button");
    exportBtn.type = "button";
    exportBtn.textContent = "Export";
    exportBtn.title = "Download this preset as a .css file";
    exportBtn.addEventListener("click", () => exportPreset(p));

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.textContent = "Delete";
    delBtn.className = "danger";
    delBtn.title = "Delete this preset (click again to confirm)";
    delBtn.addEventListener("click", () => deletePreset(idx, delBtn, p));

    actions.append(renameBtn, exportBtn, delBtn);
    row.appendChild(actions);
    userPresetList.appendChild(row);
  });
}

function startRename(p, nameSpan, row) {
  if (row.dataset.renaming) return;
  row.dataset.renaming = "1";
  const input = document.createElement("input");
  input.type = "text";
  input.maxLength = 40;
  input.spellcheck = false;
  input.value = p.name;
  input.addEventListener("click", (ev) => ev.stopPropagation());
  nameSpan.textContent = "";
  nameSpan.appendChild(input);
  input.focus();
  input.select();
  let done = false;
  const commit = async () => {
    if (done) return;
    done = true;
    const newName = input.value.trim().replace(/\s+/g, " ");
    if (!newName || newName === p.name) {
      renderUserPresets();
      return;
    }
    if (userPresets.some((q) => q.id !== p.id && q.name.toLowerCase() === newName.toLowerCase())) {
      setStatus('Another preset is already called "' + newName + '"', 2800);
      renderUserPresets();
      return;
    }
    p.name = newName;
    try {
      await setUserPresets(userPresets);
      setStatus('Renamed to "' + newName + '"', 1800);
    } catch (e) {
      setStatus("Rename failed: " + e.message, 2800);
    }
    renderUserPresets();
  };
  input.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") { ev.preventDefault(); input.blur(); }
    else if (ev.key === "Escape") { done = true; renderUserPresets(); }
  });
  input.addEventListener("blur", commit);
}

function exportPreset(p) {
  try {
    const safe = p.name.replace(/[\\/:*?"<>|]+/g, "-").trim() || "preset";
    const blob = new Blob([p.css], { type: "text/css" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = safe + ".css";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    setStatus('Exported "' + p.name + '.css" — check your downloads', 2400);
  } catch (e) {
    setStatus("Export failed", 2200);
  }
}

function deletePreset(idx, btn, p) {
  if (!btn.dataset.confirming) {
    btn.dataset.confirming = "1";
    btn.classList.add("confirm");
    btn.textContent = "Sure?";
    setTimeout(() => {
      if (!btn.isConnected) return;
      delete btn.dataset.confirming;
      btn.classList.remove("confirm");
      btn.textContent = "Delete";
    }, 2600);
    return;
  }
  userPresets.splice(idx, 1);
  setUserPresets(userPresets)
    .then(() => {
      renderUserPresets();
      setStatus('Deleted preset: "' + p.name + '"', 2000);
    })
    .catch((e) => {
      setStatus("Delete failed: " + e.message, 2600);
      refreshUserPresets();
    });
}

async function saveCurrentAsPreset() {
  const name = presetName.value.trim().replace(/\s+/g, " ");
  if (!extensionApiAvailable) {
    setStatus("Extension APIs unavailable — standalone preview", 2600);
    return;
  }
  if (!name) {
    setStatus("Give the preset a name first", 2200);
    presetName.focus();
    return;
  }
  if (!cssText || !cssText.trim()) {
    setStatus("Nothing to save — the current CSS is empty", 2600);
    return;
  }
  if (userPresets.some((p) => p.name.toLowerCase() === name.toLowerCase())) {
    setStatus('You already have a preset named "' + name + '"', 3000);
    return;
  }
  const preset = {
    id: newPresetId(),
    name: name,
    css: cssText,
    accent: extractAccent(cssText),
    createdAt: Date.now(),
  };
  userPresets.push(preset);
  try {
    await setUserPresets(userPresets);
    presetName.value = "";
    renderUserPresets();
    setStatus('Preset saved: "' + name + '" — one click applies it any time', 2800);
  } catch (e) {
    userPresets.pop();
    setStatus("Save failed: " + e.message, 3000);
  }
}

savePresetBtn.addEventListener("click", saveCurrentAsPreset);
presetName.addEventListener("keydown", (ev) => {
  if (ev.key === "Enter") { ev.preventDefault(); saveCurrentAsPreset(); }
});

importPresetBtn.addEventListener("click", () => importFile.click());
importFile.addEventListener("change", async () => {
  const file = importFile.files && importFile.files[0];
  importFile.value = ""; // allow picking the same file again
  if (!file) return;
  if (!extensionApiAvailable) {
    setStatus("Extension APIs unavailable — standalone preview", 2600);
    return;
  }
  try {
    const css = await file.text();
    if (!css || !css.trim()) {
      setStatus("That file is empty", 2400);
      return;
    }
    const base = prettifyFileName(file.name) || "Imported preset";
    let name = base;
    let n = 2;
    while (userPresets.some((p) => p.name.toLowerCase() === name.toLowerCase())) {
      name = base + " (" + n + ")";
      n++;
    }
    userPresets.push({
      id: newPresetId(),
      name: name,
      css: css,
      accent: extractAccent(css),
      createdAt: Date.now(),
    });
    await setUserPresets(userPresets);
    renderUserPresets();
    setStatus('Imported preset: "' + name + '"', 2400);
  } catch (e) {
    setStatus("Import failed: " + e.message, 2800);
  }
});

/* ------------------------------------------------------------------ */
/* Extension API boot (guarded so the popup can be previewed standalone)*/
/* ------------------------------------------------------------------ */
const extensionApiAvailable =
  typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.getURL;

async function getSpotifyTab() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.url && tab.url.startsWith("https://open.spotify.com")) {
      return tab;
    }
  } catch (e) {
    // ignore, handled by caller
  }
  return null;
}

if (extensionApiAvailable) {
  fetch(chrome.runtime.getURL("default.css"))
    .then((r) => r.text())
    .then((css) => {
      defaultCss = css;
      if (wantDefaultPrefill) {
        wantDefaultPrefill = false;
        setCssText(defaultCss);
      }
      loadShippedThemes(); // re-render so the Default chip shows the real accent
    })
    .catch(() => {});

  chrome.storage.local.get(["customCss"], (res) => {
    if (res.customCss !== undefined) {
      setCssText(res.customCss);
    } else {
      wantDefaultPrefill = true;
      if (defaultCss) {
        wantDefaultPrefill = false;
        setCssText(defaultCss);
      }
    }
  });
} else {
  shippedList.innerHTML = '<span class="muted">Extension APIs unavailable — standalone preview.</span>';
  renderUserPresets();
}

/* ------------------------------------------------------------------ */
/* Save / Load default / Advanced textarea                             */
/* ------------------------------------------------------------------ */
cssInput.addEventListener("input", () => {
  cssText = cssInput.value;
});

saveBtn.addEventListener("click", () => {
  // Save unconditionally: content.js hot-reloads via storage.onChanged on
  // every open Spotify tab; saving with no Spotify tab open simply stages
  // the CSS for the next page load.
  chrome.storage.local.set({ customCss: cssText }, () => {
    if (chrome.runtime.lastError) {
      setStatus("Save failed: " + chrome.runtime.lastError.message, 3000);
      return;
    }
    getSpotifyTab().then((tab) => {
      setStatus(
        tab ? "Saved — live on the page" : "Saved — open Spotify tabs update automatically",
        tab ? 1500 : 2600
      );
    });
  });
});

loadDefaultBtn.addEventListener("click", () => {
  if (!defaultCss) {
    setStatus("Default map still loading — try again");
    return;
  }
  setCssText(defaultCss);
  setStatus("Default selector map loaded. Click Apply & Save.", 2500);
});

/* ------------------------------------------------------------------ */
/* Diagnostics (unchanged protocol with content.js)                    */
/* ------------------------------------------------------------------ */
diagBtn.addEventListener("click", async () => {
  const tab = await getSpotifyTab();
  if (!tab) {
    setStatus("Open https://open.spotify.com first!");
    return;
  }
  diagResults.innerHTML = '<div class="diag-loading">Checking selectors&hellip;</div>';
  try {
    const res = await chrome.tabs.sendMessage(tab.id, { type: "MSC_DIAG" });
    renderDiagnostics(res && res.results ? res.results : []);
  } catch (e) {
    diagResults.innerHTML = "";
    setStatus("Could not reach the page — reload the Spotify tab", 3000);
  }
});

function renderDiagnostics(results) {
  diagResults.innerHTML = "";
  if (!results.length) {
    diagResults.innerHTML = '<div class="diag-loading">No results.</div>';
    return;
  }
  for (const r of results) {
    const row = document.createElement("div");
    row.className = "diag-row " + (r.count > 0 ? "hit" : "miss");
    const colorChip = r.color
      ? '<span class="diag-color" style="background:' + escapeHtml(r.color) + '"></span>'
      : "";
    row.innerHTML =
      '<span class="diag-name">' + escapeHtml(r.name) + "</span>" +
      '<span class="diag-count">' + r.count + "</span>" +
      colorChip;
    row.title =
      r.selector +
      (r.error ? " — ERROR: " + r.error : "") +
      " (click to highlight on page)";
    row.addEventListener("click", async () => {
      const tab = await getSpotifyTab();
      if (!tab) return;
      try {
        await chrome.tabs.sendMessage(tab.id, {
          type: "MSC_HIGHLIGHT",
          selector: r.selector,
        });
      } catch (e) {
        // page navigated away mid-click — ignore
      }
    });
    diagResults.appendChild(row);
  }
}

/* ------------------------------------------------------------------ */
/* Init                                                                */
/* ------------------------------------------------------------------ */
buildPaletteRows();
if (verBadge && extensionApiAvailable && chrome.runtime.getManifest) {
  try {
    verBadge.textContent = "v" + chrome.runtime.getManifest().version;
  } catch (e) {
    /* keep static badge */
  }
}
refreshUserPresets();
loadShippedThemes();
checkForUpdate();