// Jotva Electron main process (macOS + Windows).
// Spawns the Python backend, reads the {port, token} handshake from stdout,
// and exposes it to the renderer over IPC only (C2). Hardened window (C6).
const {
  app,
  BrowserWindow,
  ipcMain,
  shell,
  protocol,
  dialog,
  Tray,
  Menu,
  Notification,
  globalShortcut,
  nativeImage,
  net,
  session,
  systemPreferences,
} = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const { pathToFileURL } = require("url");

const IS_DEV = !app.isPackaged;
protocol.registerSchemesAsPrivileged([{ scheme: "app", privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } }]);
const IS_WIN = process.platform === "win32";
const PROJECT_ROOT = path.join(__dirname, "..");
const DATA_DIR = path.join(app.getPath("appData"), "Jotva");

// ---------- native-UI localization ----------
// English is loaded as the base/fallback at startup; applyLocale() overlays the
// OS language (app.getLocale()) once the app is ready.
const LOCALES_DIR = path.join(__dirname, "locales");
const SUPPORTED_LOCALES = ["en", "es", "pt", "fr", "zh", "ko"];
function loadLocaleFile(lang) {
  try {
    return JSON.parse(fs.readFileSync(path.join(LOCALES_DIR, `${lang}.json`), "utf8"));
  } catch {
    return null;
  }
}
let T = loadLocaleFile("en") || {};
function applyLocale(tag) {
  const base = String(tag || "").toLowerCase().split("-")[0];
  if (base !== "en" && SUPPORTED_LOCALES.includes(base)) {
    const loaded = loadLocaleFile(base);
    if (loaded) T = { ...T, ...loaded }; // overlay onto the English fallback
  }
}
function tr(key, vars) {
  let s = T[key] != null ? T[key] : key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{{${k}}}`).join(v);
  return s;
}

let mainWindow = null;
let tray = null;
let backendProc = null;
let backendInfo = null; // { port, token }
let isQuitting = false;
const pendingBackendWaiters = [];
// Preserve the backend's existing data location, including its legacy Windows path.
const speakerDataDir = process.env.JOTVA_DATA_DIR || path.join(app.getPath('home'), 'Library', 'Application Support', 'Jotva');
const speakerIntegration = require('./speakers.cjs')({app, systemPreferences, shell, getInfo: () => backendInfo, resolveBackend, dataDir: speakerDataDir});
app.on('before-quit', () => speakerIntegration.stop());

// ---------- single instance (also delivers win32 protocol deep links) ----------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}
app.on("second-instance", (_event, argv) => {
  showWindow();
  // On Windows the jotva:// URL arrives in the second instance's argv.
  const link = argv.find((a) => typeof a === "string" && a.startsWith("jotva://"));
  if (link && mainWindow) {
    mainWindow.webContents.send("jotva:deep-link", link.slice(0, 2048));
  }
});

// ---------- backend lifecycle ----------
function resolveBackend() {
  if (app.isPackaged) {
    const bundled = path.join(process.resourcesPath, "backend", "dist", "jotva-backend", IS_WIN ? "jotva-backend.exe" : "jotva-backend");
    if (fs.existsSync(bundled)) return { exe: bundled, useExe: true };
  }
  // Dev fallback: use .venv python
  const venvPython = IS_WIN
    ? path.join(PROJECT_ROOT, "backend", ".venv", "Scripts", "python.exe")
    : path.join(PROJECT_ROOT, "backend", ".venv", "bin", "python");
  return { exe: venvPython, useExe: false };
}

function startBackend() {
  const { exe, useExe } = resolveBackend();
  backendProc = spawn(exe, useExe ? [] : ["run.py"], {
    // Bundled exe is self-contained; its own dir always exists on disk. In dev
    // the interpreter needs the backend/ source dir so run.py resolves imports.
    cwd: useExe ? path.dirname(exe) : path.join(PROJECT_ROOT, "backend"),
    // DEV ONLY: signal dev mode to the backend so it can register
    // developer-testing endpoints (never set true in packaged builds).
    env: { ...process.env, PYTHONUNBUFFERED: "1", JOTVA_DEV: IS_DEV ? "1" : "0" },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  let buffer = "";
  backendProc.stdout.on("data", (chunk) => {
    buffer += chunk.toString();
    let idx;
    while ((idx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (!line) continue;
      try {
        const msg = JSON.parse(line);
        if (msg.event === "ready" && msg.port && msg.token) {
          backendInfo = { port: msg.port, token: msg.token, speakerToken: msg.speaker_token };
          speakerIntegration.start();
          pendingBackendWaiters.splice(0).forEach((resolve) => resolve(backendInfo));
        }
      } catch {
        /* non-JSON stdout noise; ignore */
      }
    }
  });
  backendProc.stderr.on("data", (chunk) => {
    if (IS_DEV) process.stderr.write(`[backend] ${chunk}`);
  });
  backendProc.on("error", (err) => {
    backendProc = null;
    if (!isQuitting) {
      dialog.showErrorBox(
        tr("backendFailedTitle"),
        tr("backendFailedMsg", { error: err.code || err.message })
      );
    }
  });
  backendProc.on("exit", (code) => {
    backendProc = null;
    if (code !== 0 && code !== null && mainWindow && !isQuitting) {
      dialog.showErrorBox(
        tr("backendStoppedTitle"),
        tr("backendStoppedMsg")
      );
    }
  });
}

function getBackendInfo() {
  if (backendInfo) return Promise.resolve(backendInfo);
  return new Promise((resolve) => pendingBackendWaiters.push(resolve));
}

// ---------- window ----------
function createWindow() {
  const platformChrome = IS_WIN
    ? { frame: false } // custom titlebar component, controls top-right
    : { titleBarStyle: "hiddenInset", trafficLightPosition: { x: 16, y: 16 } };

  mainWindow = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 900,
    minHeight: 600,
    title: "Jotva",
    icon: path.join(__dirname, "assets", process.platform === "win32" ? "icon.ico" : "icon.png"),
    backgroundColor: "#fbfaf6",
    ...platformChrome,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true, // C6
      nodeIntegration: false, // C6
      sandbox: true, // C6
      webSecurity: true,
      spellcheck: false,
    },
  });

  // Block any navigation away from the app and any window.open (C6).
  mainWindow.webContents.on("will-navigate", (event, url) => {
    const allowed = IS_DEV ? url.startsWith("http://localhost:5173") : url.startsWith("app://");
    if (!allowed) event.preventDefault();
  });
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));

  if (IS_DEV) {
    mainWindow.loadURL("http://localhost:5173");
  } else {
    mainWindow.loadURL("app://jotva/index.html");
  }

  // Closing hides to tray; Quit (tray/menu/Cmd+Q) really exits.
  mainWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function showWindow() {
  if (!mainWindow) {
    createWindow();
    return;
  }
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
}

// Serve the built renderer over app:// in production so the backend CORS
// allowlist never needs file:// (C3). Electron ≥36 API: protocol.handle.
function registerAppProtocol() {
  const base = app.isPackaged
    ? path.join(app.getAppPath(), "dist")
    : path.join(PROJECT_ROOT, "dist");
  protocol.handle("app", (request) => {
    try {
      const url = new URL(request.url);
      const rel = decodeURIComponent(url.pathname).replace(/^\/+/, "") || "index.html";
      const target = path.normalize(path.join(base, rel));
      if (target !== base && !target.startsWith(base + path.sep)) {
        return new Response("Forbidden", { status: 403 }); // traversal attempt
      }
      return net.fetch(pathToFileURL(target).toString());
    } catch {
      return new Response("Bad request", { status: 400 });
    }
  });
}

// Apply the Content-Security-Policy via response headers. NOTE: index.html also
// ships a <meta> CSP; browsers enforce the intersection of header + meta, so the
// effective policy stays as restrictive as the stricter of the two.
function applyContentSecurityPolicy() {
  const csp =
    "default-src 'self'; " +
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' app:; " +
    "style-src 'self' 'unsafe-inline' app:; " +
    "connect-src 'self' app: http://127.0.0.1:* ws://127.0.0.1:* http://localhost:* ws://localhost:* https://license.jotva.com; " +
    // Audio playback from the local backend — must match index.html's meta CSP,
    // since the effective policy is the stricter of the two.
    "media-src 'self' http://127.0.0.1:* http://localhost:*; " +
    // Profile photo is stored as a small re-encoded data: URL (images can't run script).
    "img-src 'self' app: data:";
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        "Content-Security-Policy": [csp],
      },
    });
  });
}

// ---------- tray ----------
function buildTrayIcon() {
  // Load the bundled icon, size it for the menu bar, and flag it as a template
  // image so macOS recolors it correctly in both light and dark mode.
  // tray-icon.png is 16px; nativeImage picks up tray-icon@2x.png on Retina automatically.
  const img = nativeImage.createFromPath(path.join(__dirname, "assets", "tray-icon.png"));
  img.setTemplateImage(true);
  return img;
}

function createTray() {
  tray = new Tray(buildTrayIcon());
  tray.setToolTip(tr("trayTooltip"));
  const menu = Menu.buildFromTemplate([
    { label: tr("trayShow"), click: () => showWindow() },
    { label: tr("trayHide"), click: () => mainWindow?.hide() },
    { type: "separator" },
    {
      label: tr("trayToggleRecord"),
      accelerator: "CommandOrControl+Shift+R",
      click: () => sendShortcut("toggle-record"),
    },
    { type: "separator" },
    {
      label: tr("trayQuit"),
      click: () => {
        isQuitting = true;
        app.quit();
      },
    },
  ]);
  tray.setContextMenu(menu);
  tray.on("click", () => {
    if (IS_WIN) showWindow(); // win: left-click opens; mac: click shows menu
  });
}

// ---------- global shortcut ----------
function sendShortcut(name) {
  if (mainWindow) {
    mainWindow.webContents.send("jotva:shortcut", name);
  }
}

// ---------- ambient mode (Cmd+Shift+A): menubar-only recording presence ----------
let ambient = false;
function toggleAmbient() {
  ambient = !ambient;
  if (ambient) {
    mainWindow?.hide();
    if (process.platform === "darwin") app.dock?.hide();
    sendShortcut("ambient-start"); // renderer starts recording if idle
    tray?.setToolTip(tr("trayRecordingAmbient"));
  } else {
    if (process.platform === "darwin") app.dock?.show();
    showWindow();
    tray?.setToolTip(tr("trayTooltip"));
  }
}

// Tray pulse while recording: alternate between accent dot and dim dot.
let pulseTimer = null;
let pulsePhase = false;
const ICON_IDLE = () => buildTrayIcon();
function buildRecordingIcon(dim) {
  // Use the same template image as the idle tray (no programmatic dot); macOS
  // handles light/dark rendering. `dim` is retained for the caller's signature.
  // tray-icon.png is 16px; nativeImage picks up tray-icon@2x.png on Retina automatically.
  const img = nativeImage.createFromPath(path.join(__dirname, "assets", "tray-icon.png"));
  img.setTemplateImage(true);
  return img;
}

function setTrayRecording(recording) {
  if (recording && !pulseTimer) {
    pulseTimer = setInterval(() => {
      pulsePhase = !pulsePhase;
      tray?.setImage(buildRecordingIcon(pulsePhase));
    }, 700);
    tray?.setImage(buildRecordingIcon(false));
  } else if (!recording && pulseTimer) {
    clearInterval(pulseTimer);
    pulseTimer = null;
    tray?.setImage(ICON_IDLE());
    if (ambient) toggleAmbient(); // recording ended → leave ambient mode
  }
}

ipcMain.handle("jotva:recording-state", (_event, recording) => {
  if (typeof recording !== "boolean") return { ok: false };
  setTrayRecording(recording);
  return { ok: true };
});

ipcMain.handle('jotva:speaker-setup', (_event, action) => {
  if (!['status', 'zoom', 'meet'].includes(action)) return {error: 'invalid_action'};
  try { return action === 'status' ? speakerIntegration.status() : speakerIntegration.setup(action); }
  catch { return {error: 'setup_failed'}; }
});

function registerShortcuts() {
  // Cmd+Shift+R on macOS, Ctrl+Shift+R on Windows — toggle recording
  const shortcuts = [
    ["CommandOrControl+Shift+R", () => sendShortcut("toggle-record")],
    ["CommandOrControl+Shift+A", () => toggleAmbient()],
    ["CommandOrControl+Shift+M", () => sendShortcut("drop-marker")],
  ];
  for (const [accel, handler] of shortcuts) {
    if (!globalShortcut.register(accel, handler)) {
      console.warn(`Global shortcut ${accel} is taken by another app`);
    }
  }
}

// ---------- IPC (all inputs validated, C6) ----------
ipcMain.handle("jotva:get-backend", async () => {
  const info = await getBackendInfo();
  return { port: info.port, token: info.token };
});

const SAFE_EXTERNAL = /^(https:|http:|mailto:)/i;
ipcMain.handle("jotva:open-external", async (_event, url) => {
  if (typeof url !== "string" || url.length > 2048 || !SAFE_EXTERNAL.test(url)) {
    return { ok: false, error: "Blocked URL" };
  }
  await shell.openExternal(url);
  return { ok: true };
});

ipcMain.handle("jotva:show-in-folder", async (_event, filePath) => {
  if (typeof filePath !== "string" || filePath.length > 1024) {
    return { ok: false, error: "Invalid path" };
  }
  const resolved = path.resolve(filePath);
  // Sandbox: only files inside our data directory may be revealed (C6).
  if (!resolved.startsWith(DATA_DIR + path.sep)) {
    return { ok: false, error: "Path outside Jotva data directory" };
  }
  if (!fs.existsSync(resolved)) {
    return { ok: false, error: "File not found" };
  }
  shell.showItemInFolder(resolved);
  return { ok: true };
});

// Prints whatever is currently in the renderer's #pdf-print-root (the only
// element visible under @media print — see styles.css) to a real PDF via
// Chromium itself, so the export matches the HTML/CSS template exactly
// instead of a separate PDF-drawing library re-implementing the design.
const EXPORTS_DIR = path.join(DATA_DIR, "exports");
ipcMain.handle("jotva:export-pdf", async (event, filename) => {
  if (typeof filename !== "string" || filename.length > 120) {
    return { ok: false, error: "Invalid filename" };
  }
  const safeName = filename.replace(/[^A-Za-z0-9 _-]/g, "").trim().slice(0, 60) || "meeting";
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win) return { ok: false, error: "No window" };
  try {
    fs.mkdirSync(EXPORTS_DIR, { recursive: true, mode: 0o700 });
    const buffer = await win.webContents.printToPDF({
      printBackground: true,
      preferCSSPageSize: true,
      margins: { marginType: "none" },
    });
    const dest = path.join(EXPORTS_DIR, `${safeName}.pdf`);
    fs.writeFileSync(dest, buffer, { mode: 0o600 });
    fs.chmodSync(dest, 0o600); // in case the file pre-existed with looser perms
    return { ok: true, path: dest };
  } catch (err) {
    console.error("[export-pdf] failed:", err.message);
    return { ok: false, error: err.message };
  }
});

const WINDOW_ACTIONS = new Set(["minimize", "maximize", "close"]);
ipcMain.handle("jotva:window-control", (_event, action) => {
  if (typeof action !== "string" || !WINDOW_ACTIONS.has(action) || !mainWindow) {
    return { ok: false };
  }
  if (action === "minimize") mainWindow.minimize();
  else if (action === "maximize") {
    if (mainWindow.isMaximized()) mainWindow.unmaximize();
    else mainWindow.maximize();
  } else if (action === "close") mainWindow.close(); // hides to tray
  return { ok: true };
});

ipcMain.handle("jotva:notify", (_event, title, body) => {
  if (
    typeof title !== "string" ||
    typeof body !== "string" ||
    title.length === 0 ||
    title.length > 120 ||
    body.length > 400
  ) {
    return { ok: false };
  }
  if (!Notification.isSupported()) return { ok: false };
  const n = new Notification({ title, body, silent: true });
  n.on("click", () => showWindow());
  n.show();
  return { ok: true };
});

ipcMain.handle("jotva:get-auto-launch", () => {
  try {
    return { enabled: app.getLoginItemSettings().openAtLogin === true };
  } catch {
    return { enabled: false };
  }
});

ipcMain.handle("jotva:set-auto-launch", (_event, enabled) => {
  if (typeof enabled !== "boolean") return { ok: false };
  try {
    app.setLoginItemSettings({ openAtLogin: enabled, path: process.execPath });
    return { ok: true };
  } catch {
    return { ok: false };
  }
});

// ---------- app lifecycle ----------
app.setAsDefaultProtocolClient("jotva"); // license/Stripe callbacks (C9)

app.on("open-url", (event, url) => {
  event.preventDefault();
  // macOS deep links: jotva://license/activated etc.
  if (mainWindow && typeof url === "string" && url.startsWith("jotva://")) {
    mainWindow.webContents.send("jotva:deep-link", url.slice(0, 2048));
  }
});

// macOS only: system audio capture needs Screen Recording permission. Nudge the
// user toward the right pane if it hasn't been granted yet.
function checkScreenRecordingPermission() {
  if (process.platform !== "darwin") return;
  let status;
  try {
    status = systemPreferences.getMediaAccessStatus("screen");
  } catch {
    return;
  }
  if (status === "granted") return;
  dialog
    .showMessageBox(mainWindow, {
      type: "info",
      title: tr("screenRecTitle"),
      message: tr("screenRecMsg"),
      detail: tr("screenRecDetail"),
      buttons: [tr("openSettings"), tr("later")],
      defaultId: 0,
      cancelId: 1,
    })
    .then(({ response }) => {
      if (response === 0) {
        shell.openExternal(
          "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
        );
      }
    })
    .catch(() => {});
}

app.whenReady().then(() => {
  applyLocale(app.getLocale());
  if (IS_DEV && process.platform === "darwin") {
    try {
      app.dock.setIcon(path.join(__dirname, "assets", "icon.png"));
    } catch { /* dev nicety only */ }
  }
  // Trigger the macOS microphone permission dialog on first launch via the
  // Electron process (which holds the app bundle identity and entitlements).
  // The Python subprocess cannot reliably trigger TCC dialogs on its own.
  if (process.platform === "darwin") {
    systemPreferences.askForMediaAccess("microphone").catch(() => {});
  }
  if (!IS_DEV) registerAppProtocol();
  applyContentSecurityPolicy();
  startBackend();
  createWindow();
  checkScreenRecordingPermission();
  createTray();
  registerShortcuts();
  app.on("activate", () => showWindow());
});

app.on("window-all-closed", () => {
  // Tray keeps the app alive on both platforms; Quit comes from the tray/menu.
});

app.on("before-quit", () => {
  isQuitting = true;
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  if (backendProc) {
    backendProc.kill("SIGTERM");
    backendProc = null;
  }
});
