const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");

const html = readFileSync(join(__dirname, "../src/webui/static/index.html"), "utf8");
const app = readFileSync(join(__dirname, "../src/webui/static/app.js"), "utf8");

test("company table sorting is keyboard accessible and announces sort state", () => {
  assert.match(html, /<th[^>]*data-sort="company"[^>]*>[\s\S]*?<button[^>]*type="button"/);
  assert.match(app, /aria-sort/);
  assert.match(app, /#base-table th\[data-sort\] button/);
});

test("command palette exposes the active result to assistive technology", () => {
  assert.match(html, /id="command-input"[^>]*role="combobox"/);
  assert.match(html, /id="command-results"[^>]*role="listbox"/);
  assert.match(app, /role="option"/);
  assert.match(app, /aria-activedescendant/);
});

test("async button actions expose and enforce their loading state", () => {
  const start = app.indexOf("async function withButtonLoading(btn, fn)");
  const end = app.indexOf("// ---------- Confetti", start);
  const helper = app.slice(start, end);
  assert.match(helper, /btn\.disabled\s*=\s*true/);
  assert.match(helper, /aria-busy/);
  assert.match(helper, /finally/);
});
