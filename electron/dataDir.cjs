// Shared with the Python backend (backend/app/config.py resolve_data_dir).
// Keep the two in step: macOS uses Application Support; Windows and Linux use
// the platform config directory unless a legacy Library database is the only one.
const fs = require("fs");
const path = require("path");

function resolveDataDir({ platform, home, appData, env, existsSync = fs.existsSync } = {}) {
  if (env) return path.resolve(env);
  const legacy = path.join(home, "Library", "Application Support", "Jotva");
  if (platform === "darwin") return path.join(appData, "Jotva");
  const standard = path.join(appData, "Jotva");
  const legacyDb = path.join(legacy, "jotva.db");
  const standardDb = path.join(standard, "jotva.db");
  if (existsSync(legacyDb) && !existsSync(standardDb)) return legacy;
  return standard;
}

module.exports = { resolveDataDir };
