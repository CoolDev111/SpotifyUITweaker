// content.js — Spotify UI Tweaker
// 1. Injects the saved CSS (falls back to the maintained default map
//    in default.css when nothing is stored yet).
// 2. Live-updates on chrome.storage.onChanged — no page refresh.
// 3. Answers "selector diagnostics" requests from the popup so the
//    selector map can be verified against the LIVE logged-in DOM.

const STYLE_ELEMENT_ID = "my-spotify-custom-css";
const DEFAULT_CSS_URL = "default.css";

let defaultCss = "";

// ----------------------------------------------------------------
// CSS injection
// ----------------------------------------------------------------
function fetchDefaultCss() {
  try {
    fetch(chrome.runtime.getURL(DEFAULT_CSS_URL))
      .then((r) => r.text())
      .then((css) => {
        defaultCss = css;
        applySavedCSS(); // storage was empty and the default is now ready
      })
      .catch(() => {});
  } catch (e) {
    // runtime.getURL unavailable (should not happen) — ignore
  }
}

function applySavedCSS() {
  chrome.storage.local.get(["customCss"], (result) => {
    // undefined  -> first run / never saved  -> use default map
    // ""         -> user deliberately saved empty -> respect it
    const css = result.customCss === undefined ? defaultCss : result.customCss;
    if (!css) return; // default still loading, nothing to apply yet
    let styleEl = document.getElementById(STYLE_ELEMENT_ID);
    if (!styleEl) {
      styleEl = document.createElement("style");
      styleEl.id = STYLE_ELEMENT_ID;
      document.head.appendChild(styleEl);
    }
    styleEl.textContent = css;
  });
}

// ----------------------------------------------------------------
// Selector diagnostics (driven from the popup)
// ----------------------------------------------------------------
// Every entry mirrors a rule in default.css. The popup shows how many
// elements each selector matches on the CURRENT page, so any selector
// that stops matching after a Spotify update is caught immediately.
const DIAGNOSTIC_SELECTORS = [
  // Left sidebar
  { name: "Sidebar: library container", sel: "#Desktop_LeftSidebar_Id" },
  { name: "Sidebar: row wrapper (li :has title)", sel: "#Desktop_LeftSidebar_Id li:has([data-encore-id='listRowTitle'])" },
  { name: "Sidebar: row (li legacy role)", sel: "#Desktop_LeftSidebar_Id li[role='listitem']" },
  { name: "Sidebar: row title (any)", sel: "#Desktop_LeftSidebar_Id [data-encore-id='listRowTitle']" },
  { name: "Sidebar: row title (inactive)", sel: "#Desktop_LeftSidebar_Id [data-encore-id='listRowTitle']:not([class*='encore-internal-color-text-bright-accent'])" },
  { name: "Sidebar: row subtitle", sel: "#Desktop_LeftSidebar_Id [data-encore-id='listRowSubtitle']" },
  { name: "Sidebar: legacy title id", sel: "[id^='listrow-title-']" },
  // Middle main view
  { name: "Main view: entity header title", sel: "main [data-testid='entityTitle']" },
  { name: "Tracklist: row", sel: "main [data-testid='tracklist-row']" },
  { name: "Tracklist: title link", sel: "main a[data-testid='internal-track-link']" },
  { name: "Tracklist: title text (color carrier)", sel: "main [data-testid='tracklist-row'] [data-testid='internal-track-link'] [data-encore-id='text']" },
  { name: "Tracklist: artist link", sel: "main [data-testid='tracklist-row'] a[href*='/artist/']" },
  // Right panel (Queue / Now Playing view)
  { name: "Right panel: Queue/NPV aside", sel: "aside#Desktop_PanelContainer_Id, aside[aria-label='Queue'], aside[aria-label='Now playing view']" },
  { name: "NPV: container", sel: "[data-testid='now-playing-view-container']" },
  { name: "NPV: video player", sel: "[data-testid='video-player-npv']" },
  { name: "Queue: row (li role=row)", sel: "aside li[role='row']" },
  { name: "Queue: row title text", sel: "aside li[role='row'] [data-encore-id='text']" },
  // Bottom player bar — CURRENT V2 WIDGET (default since late 2025)
  { name: "Player bar: bar", sel: "[data-testid='now-playing-bar']" },
  { name: "Player bar: widget v2 (current)", sel: "[data-testid='now-playing-widget-v2']" },
  { name: "Player bar: v2 cover art", sel: "[data-testid='now-playing-widget-v2'] [data-testid='cover-art-container']" },
  { name: "Player bar: v2 title link", sel: "[data-testid='now-playing-widget-v2'] [data-testid='context-item-link']" },
  { name: "Player bar: v2 title text", sel: "[data-testid='now-playing-widget-v2'] [data-testid='context-item-link'] [data-encore-id='text']" },
  { name: "Player bar: v2 byline", sel: "[data-testid='now-playing-widget-v2-byline']" },
  { name: "Player bar: v2 byline artist links", sel: "[data-testid='now-playing-widget-v2-byline'] a" },
  { name: "Player bar: quality chip (accent)", sel: "[data-testid='context-item-info-quality']" },
  { name: "Player bar: video toggle (NPB)", sel: "[data-testid='video-player-npb']" },
  // Bottom player bar — LEGACY V1 / ad-variant fallbacks (may be 0)
  { name: "Player bar: widget v1 (legacy)", sel: "[data-testid='now-playing-widget']" },
  { name: "Player bar: v1 track info (class)", sel: "[data-testid='now-playing-bar'] [class*='trackInfo']" },
  { name: "Player bar: v1 title block (legacy/ad)", sel: "[data-testid='context-item-info-title']" },
  { name: "Player bar: v1 artist block", sel: "[data-testid='context-item-info-subtitles'], [data-testid='context-item-info-subtitle']" },
  { name: "Player bar: v1 artist link", sel: "[data-testid='context-item-info-artist']" },
  { name: "Player bar: progress fill", sel: "[data-testid='playback-progressbar'] [data-testid='progress-bar']" },
  { name: "Player bar: active toggles", sel: "[data-testid='now-playing-bar'] button[aria-checked='true'], [data-testid='now-playing-bar'] button[aria-pressed='true']" },
  // Panel indicator dots + play buttons (v1.4.0)
  { name: "Player bar: lyrics button (dot host)", sel: "[data-testid='lyrics-button']" },
  { name: "Player bar: queue button (dot host)", sel: "[data-testid='control-button-queue']" },
  { name: "Player bar: volume slider (6m tokens)", sel: "[data-testid='volume-bar'] [data-testid='progress-bar']" },
  { name: "Play button: primary accent surface", sel: "button[data-testid='play-button'] [class*='encore-bright-accent-set']" },
  { name: "Play/pause: bar button accent surface", sel: "button[data-testid='control-button-playpause'] [class*='encore-inverted-light-set']" },
  { name: "Player bar: full-bar text sweep", sel: "[data-testid='now-playing-bar'] [data-encore-id='text']:not([class*='encore-internal-color-text-subdued']):not([class*='encore-internal-color-text-bright-accent'])" },
];

function runDiagnostics() {
  return DIAGNOSTIC_SELECTORS.map((item) => {
    const out = { name: item.name, selector: item.sel, count: 0, color: null, error: null };
    try {
      const els = document.querySelectorAll(item.sel);
      out.count = els.length;
      const first = els[0];
      if (first) {
        out.color = getComputedStyle(first).color;
      }
    } catch (e) {
      out.error = e && e.message ? e.message : String(e);
    }
    return out;
  });
}

// ----------------------------------------------------------------
// Element highlighting (click a diagnostics row in the popup)
// ----------------------------------------------------------------
const HIGHLIGHT_MS = 1800;

function flashHighlight(selector) {
  let els;
  try {
    els = document.querySelectorAll(selector);
  } catch (e) {
    return;
  }
  els.forEach((el) => {
    const prev = el.getAttribute("style") || "";
    el.style.outline = "2px solid #ff5470";
    el.style.outlineOffset = "2px";
    el.style.backgroundColor = "rgba(255, 84, 112, 0.18)";
    setTimeout(() => {
      el.setAttribute("style", prev);
    }, HIGHLIGHT_MS);
  });
}

// ----------------------------------------------------------------
// Player bar HTML dump (from the popup) — captures the exact bottom
// bar DOM so build-specific structures (e.g. music-video mode) can
// be analyzed and matched precisely.
// ----------------------------------------------------------------
const DUMP_MAX_LENGTH = 150000;

function dumpPlayerBarHtml() {
  const bar = document.querySelector("[data-testid='now-playing-bar']");
  if (!bar) {
    return { ok: false, html: "", note: "Player bar not found on this page." };
  }
  const full = bar.outerHTML;
  if (full.length > DUMP_MAX_LENGTH) {
    return {
      ok: true,
      html: full.slice(0, DUMP_MAX_LENGTH),
      truncated: true,
      fullLength: full.length,
    };
  }
  return { ok: true, html: full, truncated: false, fullLength: full.length };
}

// ----------------------------------------------------------------
// Message wiring
// ----------------------------------------------------------------
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg.type !== "string") return false;
  if (msg.type === "MSC_DIAG") {
    sendResponse({ ok: true, results: runDiagnostics() });
    return true;
  }
  if (msg.type === "MSC_HIGHLIGHT" && typeof msg.selector === "string") {
    flashHighlight(msg.selector);
    sendResponse({ ok: true });
    return true;
  }
  if (msg.type === "MSC_DUMP_BAR") {
    sendResponse({ ok: true, dump: dumpPlayerBarHtml() });
    return true;
  }
  return false;
});

// ----------------------------------------------------------------
// Boot
// ----------------------------------------------------------------
fetchDefaultCss();
applySavedCSS();

// Listen for live updates from the popup without needing a page refresh
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes.customCss) {
    applySavedCSS();
  }
});

// ================================================================
// 1. Adaptive Album Art Color Sampler (activated by @msc-adaptive-album)
// ================================================================
let adaptiveEnabled = false;
let lastSampledSrc = "";

function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0, l = (max + min) / 2;
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
  return "#" + [r, g, b].map((v) =>
    Math.max(0, Math.min(255, Math.round((v + m) * 255))).toString(16).padStart(2, "0")
  ).join("");
}

function extractVibrantColor(imgEl) {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  canvas.width = 32;
  canvas.height = 32;
  ctx.drawImage(imgEl, 0, 0, 32, 32);

  const data = ctx.getImageData(0, 0, 32, 32).data;
  let rSum = 0, gSum = 0, bSum = 0, totalWeight = 0;

  for (let i = 0; i < data.length; i += 4) {
    const r = data[i], g = data[i + 1], b = data[i + 2];
    const [, s, l] = rgbToHsl(r, g, b);
    // Skip crushed blacks and blown-out whites; favor saturated colors
    if (l < 12 || l > 90) continue;
    const weight = 1 + (s / 100) * 4;
    rSum += r * weight;
    gSum += g * weight;
    bSum += b * weight;
    totalWeight += weight;
  }

  if (!totalWeight) return null;

  const avgR = rSum / totalWeight;
  const avgG = gSum / totalWeight;
  const avgB = bSum / totalWeight;
  let [h, s, l] = rgbToHsl(avgR, avgG, avgB);

  // Boost saturation and clamp lightness so accents pop against dark glass
  s = Math.max(s, 55);
  l = Math.max(48, Math.min(68, l));

  const accent = hslToHex(h, s, l);
  const hover = hslToHex(h, s, Math.min(88, l + 10));
  const press = hslToHex(h, s, Math.max(20, l - 9));
  const deepBg = hslToHex(h, Math.min(s, 45), 14);
  const onAccent = l > 62 ? "#0b0d12" : "#ffffff";

  return { accent, hover, press, deepBg, onAccent };
}

function clearAdaptiveOverrides() {
  const root = document.documentElement.style;
  ["--msc-accent", "--msc-accent-hover", "--msc-accent-press", "--msc-on-accent", "--msc-adaptive-bg"]
    .forEach((prop) => root.removeProperty(prop));
  lastSampledSrc = "";
}

function sampleCurrentAlbumArt() {
  if (!adaptiveEnabled) return;
  const img = document.querySelector('[data-testid="now-playing-bar"] [data-testid="cover-art-container"] img');
  if (!img || !img.src || img.src === lastSampledSrc) return;

  const probe = new Image();
  probe.crossOrigin = "anonymous";
  probe.onload = () => {
    if (!adaptiveEnabled) return;
    try {
      const palette = extractVibrantColor(probe);
      if (!palette) return;
      lastSampledSrc = img.src;
      const root = document.documentElement.style;
      root.setProperty("--msc-accent", palette.accent);
      root.setProperty("--msc-accent-hover", palette.hover);
      root.setProperty("--msc-accent-press", palette.press);
      root.setProperty("--msc-on-accent", palette.onAccent);
      root.setProperty("--msc-adaptive-bg", palette.deepBg);
    } catch (e) {
      // Ignore if image fails CORS probe
    }
  };
  probe.src = img.src;
}

// Hook into applySavedCSS() so selecting/deselecting the theme toggles live sampling
if (typeof applySavedCSS === "function") {
  const _origApplySavedCSS = applySavedCSS;
  applySavedCSS = function () {
    chrome.storage.local.get(["customCss"], (result) => {
      const css = result.customCss === undefined ? (typeof defaultCss !== "undefined" ? defaultCss : "") : result.customCss;
      adaptiveEnabled = Boolean(css && css.includes("@msc-adaptive-album"));
      if (!adaptiveEnabled) clearAdaptiveOverrides();
      else sampleCurrentAlbumArt();
    });
    _origApplySavedCSS();
  };
}

// Watch the bottom player bar for track/cover art changes
const albumObserver = new MutationObserver(() => {
  if (adaptiveEnabled) sampleCurrentAlbumArt();
});
albumObserver.observe(document.body, {
  childList: true,
  subtree: true,
  attributes: true,
  attributeFilter: ["src"]
});

// ================================================================
// 2. Equalizer Canvas Color Override (catches ANY green shade on EQ canvas)
// ================================================================
(function hookEqualizerCanvas() {
  const probeCtx = document.createElement("canvas").getContext("2d");

  const parseColorRgba = (val) => {
    if (typeof val !== "string") return null;
    probeCtx.fillStyle = "#000001";
    probeCtx.fillStyle = val;
    const norm = probeCtx.fillStyle; // Browser normalizes any CSS color to #rrggbb or rgba(r, g, b, a)
    if (norm === "#000001" && val.trim() !== "#000001") return null;
    if (norm.startsWith("#")) {
      return {
        r: parseInt(norm.slice(1, 3), 16),
        g: parseInt(norm.slice(3, 5), 16),
        b: parseInt(norm.slice(5, 7), 16),
        a: 1
      };
    }
    const m = norm.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([0-9.]+))?\)/);
    if (!m) return null;
    return { r: +m[1], g: +m[2], b: +m[3], a: m[4] !== undefined ? +m[4] : 1 };
  };

  const isGreenHue = (val) => {
    const c = parseColorRgba(val);
    if (!c) return false;
    // True if green channel clearly dominates both red and blue
    return c.g > 80 && c.g > c.r * 1.25 && c.g > c.b * 1.25;
  };

  const getActiveAccentRgba = (alpha = 1) => {
    const raw = getComputedStyle(document.documentElement).getPropertyValue("--msc-accent").trim() || "#38bdf8";
    const c = parseColorRgba(raw) || { r: 56, g: 189, b: 248, a: 1 };
    return `rgba(${c.r}, ${c.g}, ${c.b}, ${alpha})`;
  };

  // Track which CanvasGradients belong to the Equalizer canvas
  const eqGradients = new WeakSet();
  const origCreateLinearGradient = CanvasRenderingContext2D.prototype.createLinearGradient;
  CanvasRenderingContext2D.prototype.createLinearGradient = function (...args) {
    const grad = origCreateLinearGradient.apply(this, args);
    if (this.canvas && this.canvas.getAttribute("aria-label") === "Equalizer") {
      eqGradients.add(grad);
    }
    return grad;
  };

  // 1. Intercept strokeStyle & fillStyle on the Equalizer canvas
  for (const prop of ["strokeStyle", "fillStyle"]) {
    const desc = Object.getOwnPropertyDescriptor(CanvasRenderingContext2D.prototype, prop);
    if (!desc || !desc.set) continue;
    Object.defineProperty(CanvasRenderingContext2D.prototype, prop, {
      get: desc.get,
      set(value) {
        if (this.canvas && this.canvas.getAttribute("aria-label") === "Equalizer" && isGreenHue(value)) {
          const parsed = parseColorRgba(value);
          return desc.set.call(this, getActiveAccentRgba(parsed ? parsed.a : 1));
        }
        return desc.set.call(this, value);
      }
    });
  }

  // 2. Intercept addColorStop ONLY on gradients created by the Equalizer canvas
  const origAddColorStop = CanvasGradient.prototype.addColorStop;
  CanvasGradient.prototype.addColorStop = function (offset, color) {
    if (eqGradients.has(this) && isGreenHue(color)) {
      const parsed = parseColorRgba(color);
      return origAddColorStop.call(this, offset, getActiveAccentRgba(parsed ? parsed.a : 1));
    }
    return origAddColorStop.call(this, offset, color);
  };
})();