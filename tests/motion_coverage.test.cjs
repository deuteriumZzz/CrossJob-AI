const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");

const source = readFileSync(join(__dirname, "../src/webui/static/app.js"), "utf8");
const css = readFileSync(join(__dirname, "../src/webui/static/style.css"), "utf8");

test("Telegram login, key, and settings saves expose request-bound busy state", () => {
  for (const id of [
    "telegram-login-send-code",
    "telegram-login-submit-code",
    "telegram-login-submit-password",
    "tg-keys-save",
    "tg-settings-save",
  ]) {
    const handler = source.slice(source.indexOf(`getElementById("${id}")`), source.indexOf("\n  });", source.indexOf(`getElementById("${id}")`)));
    assert.match(handler, /withButtonLoading\(/, `${id} should use the shared async busy state`);
  }
});

test("opening a vacancy gives its selected history row a short target highlight", () => {
  assert.match(source, /function highlightHistoryTarget\(row\)/);
  assert.match(source, /if \(open\) \{\s*highlightHistoryTarget\(rows\[historySelected\]\);\s*openJobDrawer/s);
  assert.match(css, /\.job-row\.is-target-highlight\s*\{[^}]*animation:\s*job-target-highlight/s);
  assert.match(css, /:root\[data-motion="reduce"\][\s\S]*?\.job-row\.is-target-highlight/);
});

test("weekly chart draws only when its data changes and honors reduced motion", () => {
  assert.match(source, /let weeklyChartSnapshot = null/);
  assert.match(source, /function animateWeeklyChart\(svg\)/);
  assert.match(source, /animateWeeklyChart\(svg\)/);
  assert.match(source, /if \(REDUCE_MOTION\) return/);
  assert.match(css, /\.area-svg\.is-entering \.chart-line\s*\{[^}]*animation:\s*chart-line-draw/s);
});

test("heatmap keeps its cells and transitions only changed activity levels", () => {
  assert.match(source, /function syncHeatmapCells\(container, cells, animateEntrance = false\)/);
  assert.match(source, /syncHeatmapCells\(el, cells/);
  assert.match(source, /cell\.dataset\.date = item\.date/);
  assert.match(css, /\.heatmap-cell\s*\{[^}]*transition:\s*background-color/s);
  assert.match(css, /\.heatmap\.is-entering/);
});

test("talk context menu animates for pointer use and closes accessibly", () => {
  assert.match(source, /function closeTalkMenu\(animate = false\)/);
  assert.match(source, /setTalkMotionVisibility\(menu, false, animate\)/);
  assert.match(source, /setTalkMotionVisibility\(menu, true, event\.type === "contextmenu" \|\| event\.detail > 0\)/);
  assert.match(source, /event\.type === "contextmenu"\s*\? \{ left: event\.clientX, top: event\.clientY \}\s*:\s*row\.getBoundingClientRect\(\)/);
  assert.match(source, /closeTalkMenu\(event\.detail > 0\)/);
});
