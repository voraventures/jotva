// Preload: minimal, validated bridge. Runs sandboxed with contextIsolation (C6).
// Every function type-checks its arguments before crossing the IPC boundary;
// main process re-validates everything independently.
const { contextBridge, ipcRenderer } = require("electron");

const VALID_WINDOW_ACTIONS = new Set(["minimize", "maximize", "close"]);

contextBridge.exposeInMainWorld("jotva", {
  platform: process.platform, // 'darwin' | 'win32' | 'linux'
  speakerSetup: action => ['status', 'zoom', 'meet'].includes(action) ? ipcRenderer.invoke('jotva:speaker-setup', action) : Promise.resolve({error: 'invalid_action'}),

  getBackend: () => ipcRenderer.invoke("jotva:get-backend"),
  mcpConfig: () => ipcRenderer.invoke("jotva:mcp-config"),
  mcpInstallClaude: () => ipcRenderer.invoke("jotva:mcp-install-claude"),

  openExternal: (url) => {
    if (typeof url !== "string") return Promise.resolve({ ok: false });
    return ipcRenderer.invoke("jotva:open-external", url);
  },

  showInFolder: (filePath) => {
    if (typeof filePath !== "string") return Promise.resolve({ ok: false });
    return ipcRenderer.invoke("jotva:show-in-folder", filePath);
  },

  exportPdf: (filename) => {
    if (typeof filename !== "string") return Promise.resolve({ ok: false });
    return ipcRenderer.invoke("jotva:export-pdf", filename);
  },

  windowControl: (action) => {
    if (!VALID_WINDOW_ACTIONS.has(action)) return Promise.resolve({ ok: false });
    return ipcRenderer.invoke("jotva:window-control", action);
  },

  notify: (title, body) => {
    if (typeof title !== "string" || typeof body !== "string") {
      return Promise.resolve({ ok: false });
    }
    return ipcRenderer.invoke("jotva:notify", title, body);
  },

  setRecordingState: (recording) => {
    if (typeof recording !== "boolean") return Promise.resolve({ ok: false });
    return ipcRenderer.invoke("jotva:recording-state", recording);
  },

  getAutoLaunch: () => ipcRenderer.invoke("jotva:get-auto-launch"),
  setAutoLaunch: (enabled) => {
    if (typeof enabled !== "boolean") return Promise.resolve({ ok: false });
    return ipcRenderer.invoke("jotva:set-auto-launch", enabled);
  },

  // Automatic updates: { version } once a new version has downloaded.
  updateStatus: () => ipcRenderer.invoke("jotva:update-status"),
  installUpdate: () => ipcRenderer.invoke("jotva:install-update"),
  onUpdateReady: (callback) => {
    if (typeof callback !== "function") return () => {};
    const handler = (_event, info) => callback({ version: String(info?.version || "") });
    ipcRenderer.on("jotva:update-ready", handler);
    return () => ipcRenderer.removeListener("jotva:update-ready", handler);
  },

  onShortcut: (callback) => {
    if (typeof callback !== "function") return () => {};
    const handler = (_event, name) => {
      if (typeof name === "string") callback(name);
    };
    ipcRenderer.on("jotva:shortcut", handler);
    return () => ipcRenderer.removeListener("jotva:shortcut", handler);
  },

  onDeepLink: (callback) => {
    if (typeof callback !== "function") return () => {};
    const handler = (_event, url) => callback(url);
    ipcRenderer.on("jotva:deep-link", handler);
    return () => ipcRenderer.removeListener("jotva:deep-link", handler);
  },
});
