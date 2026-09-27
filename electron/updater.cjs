// Automatic updates from the GitHub releases (build.publish in package.json).
// New versions download quietly in the background; the app then offers
// "Restart to update" and never restarts on its own while recording. An update
// that was never applied installs the next time Jotva quits. macOS only accepts
// an update signed with the same Developer ID, so a tampered download is refused.
const { app, ipcMain } = require("electron");

const CHECK_EVERY_MS = 6 * 60 * 60 * 1000;
const FIRST_CHECK_MS = 20 * 1000;

function setupAutoUpdates({ getWindow, isRecording }) {
  if (!app.isPackaged) {
    // Dev builds run from source: never update, but still answer the window.
    ipcMain.handle("jotva:update-status", () => null);
    ipcMain.handle("jotva:install-update", () => ({ ok: false, reason: "none" }));
    return;
  }
  const { autoUpdater } = require("electron-updater");
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.logger = null;

  let ready = null; // { version } once an update has downloaded
  const tell = () => {
    const win = getWindow();
    if (ready && win && !win.isDestroyed()) win.webContents.send("jotva:update-ready", ready);
  };

  autoUpdater.on("update-downloaded", (info) => {
    ready = { version: String(info?.version || "").slice(0, 32) };
    tell();
  });
  autoUpdater.on("error", (err) => {
    console.warn("[updater]", err?.message || err); // offline, rate-limited, etc.: try again later
  });

  const check = () => autoUpdater.checkForUpdates().catch(() => {});
  setTimeout(check, FIRST_CHECK_MS);
  setInterval(check, CHECK_EVERY_MS);

  // A window created after the download still learns about it.
  ipcMain.handle("jotva:update-status", () => ready);
  ipcMain.handle("jotva:install-update", () => {
    if (!ready) return { ok: false, reason: "none" };
    if (isRecording()) return { ok: false, reason: "recording" };
    setImmediate(() => autoUpdater.quitAndInstall());
    return { ok: true };
  });
}

module.exports = { setupAutoUpdates };
