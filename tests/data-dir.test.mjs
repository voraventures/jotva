import assert from "node:assert/strict";
import test from "node:test";
import { resolveDataDir } from "../electron/dataDir.cjs";

const norm = (p) => p.replaceAll("\\", "/");

test("darwin uses Application Support", () => {
  const dir = resolveDataDir({
    platform: "darwin",
    home: "/Users/luis",
    appData: "/Users/luis/Library/Application Support",
    env: "",
    existsSync: () => false,
  });
  assert.equal(norm(dir), "/Users/luis/Library/Application Support/Jotva");
});

test("windows keeps a legacy database when AppData has none", () => {
  const dir = resolveDataDir({
    platform: "win32",
    home: "/Users/luis",
    appData: "/Users/luis/AppData/Roaming",
    env: "",
    existsSync: (p) => norm(p).endsWith("Library/Application Support/Jotva/jotva.db"),
  });
  assert.equal(norm(dir), "/Users/luis/Library/Application Support/Jotva");
});

test("windows uses AppData for a new install", () => {
  const dir = resolveDataDir({
    platform: "win32",
    home: "/Users/luis",
    appData: "/Users/luis/AppData/Roaming",
    env: "",
    existsSync: () => false,
  });
  assert.equal(norm(dir), "/Users/luis/AppData/Roaming/Jotva");
});

test("an explicit data directory wins", () => {
  const dir = resolveDataDir({
    platform: "linux",
    home: "/home/luis",
    appData: "/home/luis/.config",
    env: "/custom/Jotva",
    existsSync: () => true,
  });
  assert.equal(norm(dir), "/custom/Jotva");
});
