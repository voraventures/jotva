// Run: JOTVA_TEST_DEPS=/path/to/temporary/jsdom/install node --test tests/ui.test.mjs
// jsdom is deliberately not added to the existing dirty dependency lockfile.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdtemp, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { build } from "esbuild";
import { DOCK_GROUPS, SETTINGS_SECTIONS, normalizeSettingsSection, settingsLabel } from "../src/navigation.js";

test("every settings section has one dock destination", () => {
  const destinations = DOCK_GROUPS.flatMap(g => g.items).filter(i => i.section).map(i => i.section);
  assert.deepEqual([...destinations].sort(), [...SETTINGS_SECTIONS].sort());
  assert.equal(new Set(destinations).size, 11);
  assert.equal(normalizeSettingsSection("unknown"), "general");
});

for (const fixtureState of ["cards", "no-today", "empty", "boot-loading", "boot-error"]) test(`meeting cards, navigation, and existing screens (${fixtureState})`, async () => {
  const require = createRequire(import.meta.url);
  const { JSDOM } = require(process.env.JOTVA_TEST_DEPS ? join(process.env.JOTVA_TEST_DEPS, "node_modules/jsdom") : "jsdom");
  const dom = new JSDOM('<div id="root"></div>', { url: `http://127.0.0.1:5198/tests/visual/frame.html?state=${fixtureState}`, pretendToBeVisual: true });
  for (const name of ["window", "document", "location", "localStorage", "HTMLElement", "Node", "Event", "MouseEvent", "KeyboardEvent", "requestAnimationFrame", "cancelAnimationFrame"])
    Object.defineProperty(globalThis, name, { configurable: true, value: dom.window[name] });
  Object.defineProperty(globalThis, "navigator", { configurable: true, value: dom.window.navigator });
  dom.window.HTMLElement.prototype.scrollTo = () => {};
  dom.window.HTMLElement.prototype.scrollIntoView = () => {};
  const clockCallbacks = [];
  const interval = dom.window.setInterval.bind(dom.window);
  dom.window.setInterval = (callback, ms, ...args) => {
    if (ms === 60000) clockCallbacks.push(callback);
    return interval(callback, ms, ...args);
  };
  const output = join(await mkdtemp(join(tmpdir(), "jotva-dom-")), "preview.cjs");
  globalThis.IS_REACT_ACT_ENVIRONMENT = false;
  await build({ entryPoints: [resolve("tests/visual/preview.jsx")], outfile: output, bundle: true, platform: "node", format: "cjs", loader: { ".css": "empty", ".svg": "text", ".woff2": "empty", ".webm": "empty", ".jpg": "empty" }, define: { "import.meta.env.DEV": "true" }, logLevel: "silent" });
  const { act, previewRoot } = require(output);
  await new Promise(r => setTimeout(r, 70));
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const click = async el => { assert.ok(el, "click target exists"); await act(async () => { el.click(); }); };
  const key = async (el, key) => act(async () => el.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key, bubbles: true, cancelable: true })));
  const button = label => [...document.querySelectorAll("button")].find(e => e.textContent.trim() === label);
  try {
    if (fixtureState.startsWith('boot-')) {
      assert.equal(document.querySelector('.boot .brand-wordmark-large').textContent, 'Jotva');
      assert.ok(document.querySelector('.boot .logo-img'));
      assert.equal(!!document.querySelector('.processing-ring'), fixtureState === 'boot-loading');
      return;
    }
    assert.equal(document.querySelector('.app-brand .brand-wordmark').textContent, 'Jotva');
    assert.equal(document.querySelectorAll(".dock-button").length, 6); // Meetings, Record, Agent, AI, Connections, Settings
    assert.equal(document.querySelector('.meeting-day-header h2').textContent, "Today");
    assert.equal(document.querySelectorAll('.date-badge').length, 0);
    assert.equal(document.querySelectorAll('.meeting-card button button').length, 0);
    if (fixtureState !== "cards") {
      assert.ok(document.querySelector('.no-recordings-today'));
      assert.equal(document.querySelector('.upcoming-card'), null);
      assert.equal(document.querySelectorAll('.meeting-card').length, fixtureState === "empty" ? 0 : 2);
      if (fixtureState === "empty") assert.ok(document.querySelector('.empty-cta'));
      return;
    }
    assert.ok(document.querySelector(".ws-title"));
    assert.equal(document.querySelectorAll('.heads-up-callout').length, 1);
    assert.ok(document.querySelector('.heads-up-callout svg'));
    assert.ok(document.querySelector('.callout.risk:not(.heads-up-callout)'));
    assert.equal(document.querySelectorAll('.meeting-card').length, 9);
    assert.equal(document.querySelectorAll('.upcoming-card').length, 2);
    assert.equal(document.querySelector('.upcoming-card .meeting-card-title').textContent, "A little space for the next big idea");
    assert.ok(!document.querySelector('.list-panel').textContent.includes('Must not appear'));
    assert.deepEqual([...document.querySelectorAll('.meeting-card-status')].map(e => e.textContent), ['Recording', 'Processing', 'Processing', 'Failed']);
    assert.ok(!document.querySelector('.list-panel').textContent.match(/Invalid Date|NaN/));
    const cards = [...document.querySelectorAll('.meeting-card-main')];
    const long = cards.find(e => e.title.includes('deliberately long'));
    assert.equal(long.getAttribute('aria-label'), long.title);
    await click(long);
    assert.equal(long.getAttribute('aria-current'), 'true');
    const overflow = cards[0].parentElement.querySelector('.meeting-card-overflow');
    await click(overflow);
    assert.equal(long.getAttribute('aria-current'), 'true', 'options do not select their meeting');
    assert.equal(document.querySelectorAll('.meeting-options-menu').length, 1);
    assert.equal(document.activeElement.getAttribute('role'), 'menuitem');
    await key(document.activeElement, 'ArrowDown');
    await key(document.activeElement, 'Escape');
    assert.equal(document.activeElement, overflow);
    assert.equal(document.querySelector('.meeting-options-menu'), null);
    await key(overflow, 'ArrowDown');
    await click(document.querySelector('.meeting-options-menu button'));
    assert.ok(document.querySelector('[role="alertdialog"]'));
    assert.equal(document.querySelectorAll('.meeting-card').length, 9, 'delete requires confirmation');
    await key(document.activeElement, 'Escape');
    assert.equal(document.activeElement, overflow);
    assert.equal(document.querySelector('[role="alertdialog"]'), null);
    await click(overflow);
    await act(async () => document.body.dispatchEvent(new dom.window.Event('pointerdown', { bubbles: true })));
    assert.equal(document.querySelector('.meeting-options-menu'), null);
    const input = document.querySelector('.list-search input');
    const search = async value => {
      await act(async () => {
        Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, value);
        input.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
      });
      await act(async () => { await new Promise(r => setTimeout(r, 280)); });
    };
    await search('Customer discovery');
    assert.equal(document.querySelector('.meeting-day-header h2').textContent, 'Search results');
    assert.equal(document.querySelectorAll('.meeting-card').length, 1);
    assert.ok(document.querySelector('.meeting-card-meta').textContent.includes(String(new Date().getFullYear())));
    await click(document.querySelector('.meeting-card-overflow'));
    await click(document.querySelector('.meeting-options-menu button'));
    await click(document.querySelector('.confirm-actions .danger'));
    assert.equal(document.querySelectorAll('.meeting-card').length, 0, 'search reflects optimistic deletion');
    await click(document.querySelector('.toast-action'));
    assert.equal(document.querySelectorAll('.meeting-card').length, 1, 'search reflects Undo without a new query');
    await search('no-such-meeting');
    assert.equal(document.querySelectorAll('.meeting-card').length, 0);
    assert.ok(document.querySelector('.list-no-match'));
    await search('');
    await click(document.querySelector('.meeting-card-main'));
    const RealDate = globalThis.Date;
    const tomorrow = new RealDate(); tomorrow.setDate(tomorrow.getDate() + 1);
    globalThis.Date = class extends RealDate { constructor(...args) { super(...(args.length ? args : [+tomorrow])); } static now() { return +tomorrow; } };
    try {
      await act(async () => window.dispatchEvent(new dom.window.Event('focus')));
      assert.ok(document.querySelector('.no-recordings-today'), 'window focus refreshes local day groups');
    } finally { globalThis.Date = RealDate; }
    await act(async () => clockCallbacks.forEach(callback => callback()));
    assert.equal(document.querySelector('.no-recordings-today'), null, 'minute tick refreshes day groups');
    for (const group of DOCK_GROUPS) {
      for (const item of group.items.filter(i => i.section)) {
        await click(document.getElementById(`dock-${group.id}`));
        assert.equal(document.querySelectorAll(".dock-menu").length, 1);
        await click([...document.querySelectorAll('[role="menuitem"]')].find(e => e.textContent === item.label));
        assert.equal(document.querySelector("#settings-panel-title")?.textContent, settingsLabel(item.section));
        assert.equal(document.activeElement.id, "settings-panel-title");
        assert.equal(document.querySelectorAll(".settings-nav").length, 0);
        if (item.section === "general") {
          const select = document.querySelector('.settings-panel [aria-haspopup="listbox"]');
          await click(select);
          await key(select, "Escape");
          assert.ok(document.querySelector(".settings-panel"), "Escape closes the select, not its containing panel");
        }
        await key(document.activeElement, "Escape");
        assert.equal(document.querySelector(".settings-panel"), null);
        assert.equal(document.activeElement.id, `dock-${group.id}`);
      }
    }
    await click(document.querySelector("#dock-settings"));
    assert.equal(document.activeElement.textContent, "General");
    await key(document.activeElement, "ArrowUp");
    assert.equal(document.activeElement.textContent, "Subscription");
    await key(document.activeElement, "Home");
    assert.equal(document.activeElement.textContent, "General");
    await key(document.activeElement, "End");
    assert.equal(document.activeElement.textContent, "Subscription");
    await key(document.activeElement, "Escape");
    assert.equal(document.activeElement.id, "dock-settings");
    await click(document.querySelector("#dock-ai"));
    await act(async () => document.body.dispatchEvent(new dom.window.Event("pointerdown", { bubbles: true })));
    assert.equal(document.querySelector(".dock-menu"), null);
    await click(document.querySelector(".header-account"));
    assert.equal(document.querySelector("#settings-panel-title").textContent, "Subscription");
    await click(document.querySelector('[aria-label="Close settings"]'));
    for (const label of ["Transcript", "Timeline", "Ask", "Overview"]) {
      await click(button(label));
      assert.ok(document.querySelector(".workspace"));
      assert.ok(!document.body.textContent.includes("Something went wrong"));
    }
    await click(document.querySelectorAll('.meeting-card-overflow')[1]);
    await click(document.querySelector('.meeting-options-menu button'));
    await click(document.querySelector('.confirm-actions .danger'));
    assert.equal(document.querySelectorAll('.meeting-card').length, 8, 'confirmed deletion invokes the existing store action');
    assert.equal(document.activeElement, input);
    await click(document.getElementById("dock-meetings"));
    await click([...document.querySelectorAll('[role="menuitem"]')].find(e => e.textContent === "Digest"));
    assert.ok(document.querySelector(".digest-inner"));
    await click(document.getElementById("dock-record"));
    await click([...document.querySelectorAll('[role="menuitem"]')].find(e => e.textContent === "Start recording"));
    assert.ok(document.querySelector(".capture-card"));
    assert.equal(document.querySelector('.capture-wordmark.brand-wordmark').textContent, 'Jotva');
    await key(document.activeElement, "Escape");
    assert.equal(document.querySelector(".capture-card"), null);
  } finally {
    await act(async () => previewRoot.unmount());
    dom.window.close();
  }
});

test("screen theme contrast and print isolation", async () => {
  const css = await readFile("src/green-glass.css", "utf8");
  assert.ok(css.startsWith("/* Green Glass screen system."));
  assert.ok(css.includes("@media screen"));
  assert.ok(css.includes("@media print"));
  const luminance = hex => {
    const rgb = hex.match(/\w\w/g).map(c => parseInt(c, 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
    return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
  };
  for (const [fg,bg] of [["18241f","f3f6f5"],["617267","f3f6f5"],["ffffff","176b46"],["edf5ef","1a2520"],["9db3a4","1a2520"],["11251a","91d5ac"],["18241f","dfefe5"],["4e6257","dfefe5"],["edf5ef","283f31"],["b8cabe","283f31"],["18241f","edf3f7"],["edf5ef","202d36"],["4f6b80","edf3f7"],["9fbdd2","202d36"]]) {
    const [a,b] = [luminance(fg), luminance(bg)].sort((a,b)=>b-a);
    assert.ok((a+.05)/(b+.05) >= 4.5, `${fg} on ${bg} meets normal-text contrast`);
  }
  assert.match(css, /--warning: #86540f; --warning-bg: #fcf3df/);
  assert.match(css, /\.meeting-sample, \.demo-badge \{ color: var\(--muted\); background: transparent;/);
  assert.match(css, /--warning: #eccb80; --warning-bg: #352e20/);
  assert.match(css, /\.heads-up-callout \{ background: var\(--heads-up-bg\); border-color: var\(--heads-up-border\); color: var\(--text\); \}/);
  assert.match(css, /\.brand-wordmark \{ font-family: "Hanken Grotesk", var\(--font-body\); font-size: calc\(20rem \/ 15\); font-weight: 600; letter-spacing: -\.02em; line-height: 1\.2; \}/);
  const fonts = await readFile('src/fonts.css', 'utf8');
  assert.ok(fonts.includes('./assets/fonts/hanken-grotesk-latin.woff2'));
  assert.ok(!fonts.includes('https://'));
});
