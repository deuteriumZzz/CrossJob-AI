const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = readFileSync(join(__dirname, "../src/webui/static/app.js"), "utf8");
const styles = readFileSync(join(__dirname, "../src/webui/static/style.css"), "utf8");
const helperCode = source.slice(source.indexOf("const htmlSnapshots ="), source.indexOf("// Причины пропуска"));

test("unchanged live feed keeps its rows and animation state", async () => {
  const start = source.indexOf("async function renderLiveFeed()");
  const end = source.indexOf("// Пометки «не поддерживается»", start);
  const feed = { writes: 0, _html: "", querySelector: () => ({ addEventListener() {} }) };
  Object.defineProperty(feed, "innerHTML", {
    get() { return this._html; },
    set(value) { this._html = value; this.writes += 1; },
  });
  const dot = { className: "" };
  const line = "2026-10-11 09:28:07.211 | INFO     | main:run:1 - Found matching vacancies";
  const context = vm.createContext({
    document: { getElementById: (id) => id === "live-feed-body" ? feed : dot },
    lastStatus: { daemon_running: true },
    lastRunNow: { running: false },
    api: async () => ({ lines: [line] }),
    staggerDelay: () => 0,
    escapeHtml: (value) => String(value),
  });
  vm.runInContext(helperCode + source.slice(start, end), context);
  await vm.runInContext("renderLiveFeed()", context);
  await vm.runInContext("renderLiveFeed()", context);
  assert.equal(feed.writes, 1);
  assert.doesNotMatch(feed.innerHTML, /stagger-item/);
});

test("unchanged HTML does not replace animated cards", () => {
  assert.match(helperCode, /function setHtmlIfChanged/);
  const element = { writes: 0, _html: "" };
  Object.defineProperty(element, "innerHTML", {
    get() { return this._html; },
    set(value) { this._html = value; this.writes += 1; },
  });
  const context = vm.createContext({ element });
  vm.runInContext(helperCode, context);
  vm.runInContext('setHtmlIfChanged(element, "same"); setHtmlIfChanged(element, "same"); setHtmlIfChanged(element, "changed")', context);
  assert.equal(element.writes, 2);
});

test("platform rows do not replay entrance animation on a status change", () => {
  const start = source.indexOf("function platformRowHtml(");
  const end = source.indexOf("function sourceRowModel(", start);
  const context = vm.createContext({
    CHEVRON_SVG: "",
    staggerDelay: () => 0,
    escapeHtml: (value) => String(value),
  });
  vm.runInContext(source.slice(start, end), context);
  const html = vm.runInContext('platformRowHtml({ key: "hh", name: "HH", logo: "", dot: "ok", statusText: "работает", pct: 50 })', context);
  assert.doesNotMatch(html, /stagger-item|animation-delay/);
  assert.match(styles, /\.platform-row \.bar > span\s*\{\s*animation:\s*none;/);
});

test("a slow live request is not started twice by desktop and browser timers", async () => {
  const start = source.indexOf("  const LIVE_TABS = new Set([");
  const end = source.indexOf("  // ponytail: desktop_app.py pokes", start);
  assert.ok(start >= 0 && end > start);
  let finish;
  let calls = 0;
  const context = vm.createContext({
    currentView: "overview",
    render: { overview() { calls += 1; return new Promise((resolve) => { finish = resolve; }); } },
  });
  vm.runInContext(source.slice(start, end), context);
  vm.runInContext("refreshActiveTab(); refreshActiveTab()", context);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls, 1);
  finish();
  await new Promise((resolve) => setImmediate(resolve));
  vm.runInContext("refreshActiveTab()", context);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(calls, 2);
  finish();
});

test("overview checks new employer replies even when source status is unchanged", async () => {
  const start = source.indexOf("  async overview() {");
  const end = source.indexOf("  async history() {", start);
  const status = { sources: [] };
  const stats = {};
  const runNow = {};
  const calls = { kpis: 0, split: 0 };
  const elements = new Map();
  const context = vm.createContext({
    document: { getElementById: (id) => {
      if (!elements.has(id)) elements.set(id, { innerHTML: "", style: {} });
      return elements.get(id);
    } },
    api: async (path) => ({ "/api/status": status, "/api/stats": stats, "/api/run-now/status": runNow, "/api/todo": {} })[path],
    overviewLoaded: true,
    lastOverviewSnapshot: JSON.stringify({ status, stats, runNow }),
    renderTodo: async () => false,
    renderOwnChannels: async () => {},
    renderLiveFeed: async () => {},
    renderDaemonState() {}, renderPauseAll() {}, renderHomeMode() {}, renderHomeLimit() {},
    renderKpis: async () => { calls.kpis += 1; },
    renderHomeSplit: async () => { calls.split += 1; },
    INTL_SOURCES: new Set(), OWN_CHANNELS: new Set(),
    applySourceOrder: (rows) => rows,
    setHtmlIfChanged() {},
  });
  vm.runInContext(`const render = { ${source.slice(start, end)} };`, context);
  await vm.runInContext("render.overview()", context);
  assert.deepEqual(calls, { kpis: 1, split: 1 });
});

test("replies refresh waits for conversation and post requests", async () => {
  const start = source.indexOf("  async replies() {");
  const end = source.indexOf("  async analytics() {", start);
  let finishTelegram;
  let finishPosts;
  const settled = { done: false };
  const context = vm.createContext({
    document: { getElementById: () => ({ innerHTML: "" }) },
    repliesLoaded: true,
    lastRepliesCount: 0,
    lastRepliesSnapshot: "[]",
    renderDraftsQueue() {}, renderHhRemindersQueue() {},
    renderTelegramPosts: () => new Promise((resolve) => { finishPosts = resolve; }),
    telegram: () => new Promise((resolve) => { finishTelegram = resolve; }),
    settled,
    api: async () => [],
  });
  vm.runInContext(`const render = { ${source.slice(start, end)} telegram };`, context);
  vm.runInContext("render.replies().then(() => { settled.done = true; })", context);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(settled.done, false);
  finishTelegram();
  finishPosts();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(settled.done, true);
});

test("a Telegram refresh error does not hide new inbox replies", async () => {
  const start = source.indexOf("  async replies() {");
  const end = source.indexOf("  async analytics() {", start);
  const seen = { rows: 0 };
  const context = vm.createContext({
    document: { getElementById: () => ({ innerHTML: "" }) },
    repliesLoaded: true,
    lastRepliesCount: 1,
    lastRepliesSnapshot: "[]",
    lastRepliesEntries: [],
    renderDraftsQueue: async () => {},
    renderHhRemindersQueue: async () => {},
    renderTelegramPosts: async () => {},
    renderRepliesRows: () => { seen.rows += 1; },
    fireConfetti() {}, showToast() {},
    api: async () => [{ company: "Example", stage: "replied" }],
    telegram: async () => { throw new Error("Telegram unavailable"); },
  });
  vm.runInContext(`const render = { ${source.slice(start, end)} telegram };`, context);
  await vm.runInContext("render.replies()", context);
  assert.equal(seen.rows, 1);
});
