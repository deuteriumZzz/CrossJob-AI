const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const html = readFileSync(join(__dirname, "../src/webui/static/index.html"), "utf8");
const app = readFileSync(join(__dirname, "../src/webui/static/app.js"), "utf8");
const styles = readFileSync(join(__dirname, "../src/webui/static/style.css"), "utf8");

test("company table sorting is keyboard accessible and announces sort state", () => {
  assert.match(html, /<th[^>]*data-sort="company"[^>]*>[\s\S]*?<button[^>]*type="button"/);
  assert.match(app, /aria-sort/);
  assert.match(app, /#base-table th\[data-sort\] button/);
});

test("static and generated buttons declare their activation type", () => {
  const staticButtons = html.match(/<button\b[^>]*>/g) || [];
  const generatedButtons = app.match(/<button\b[^>]*>/g) || [];
  for (const button of [...staticButtons, ...generatedButtons]) {
    assert.ok(/\btype="(?:button|submit|reset)"/.test(button), button);
  }
});

test("command palette exposes the active result to assistive technology", () => {
  assert.match(html, /id="command-input"[^>]*role="combobox"/);
  assert.match(html, /id="command-results"[^>]*role="listbox"/);
  assert.match(app, /role="option"/);
  assert.match(app, /aria-activedescendant/);
});

test("async button actions expose loading and restore the original button state", async () => {
  const start = app.indexOf("async function withButtonLoading(btn, fn)");
  const end = app.indexOf("// ---------- Confetti", start);
  const helper = app.slice(start, end);
  assert.match(helper, /btn\.disabled\s*=\s*true/);
  assert.match(helper, /aria-busy/);
  assert.match(helper, /finally/);

  const attributes = new Map([["aria-busy", "mixed"]]);
  const classes = new Set();
  const btn = {
    disabled: false,
    classList: {
      add: (value) => classes.add(value),
      remove: (value) => classes.delete(value),
    },
    getAttribute: (name) => attributes.has(name) ? attributes.get(name) : null,
    setAttribute: (name, value) => attributes.set(name, value),
    removeAttribute: (name) => attributes.delete(name),
  };
  const context = vm.createContext({});
  vm.runInContext(`${helper}; globalThis.runLoading = withButtonLoading`, context);
  let finishWork;
  const work = new Promise((resolve) => { finishWork = resolve; });
  const pending = context.runLoading(btn, () => work);
  assert.equal(btn.disabled, true);
  assert.equal(attributes.get("aria-busy"), "true");
  assert.equal(classes.has("is-loading"), true);
  finishWork("done");
  assert.equal(await pending, "done");
  assert.equal(btn.disabled, false);
  assert.equal(attributes.get("aria-busy"), "mixed");
  assert.equal(classes.has("is-loading"), false);
  await assert.rejects(
    context.runLoading(btn, async () => { throw new Error("request failed"); }),
    /request failed/
  );
  assert.equal(btn.disabled, false);
  assert.equal(attributes.get("aria-busy"), "mixed");
  assert.equal(classes.has("is-loading"), false);
});

test("clickable table rows provide a real keyboard-accessible action", () => {
  assert.ok(app.includes('class="base-row-open" aria-label="Открыть карточку компании:'));
  assert.ok(app.includes('class="job-row-open job-cell" aria-label="Открыть вакансию'));
  assert.ok(app.includes('querySelector(".job-row-open")?.focus'));
});

test("onboarding tour announces each step and can be dismissed from the keyboard", () => {
  const start = app.indexOf("function initOnboardingTour()");
  const end = app.indexOf("// 13 недель", start);
  const tour = app.slice(start, end);
  assert.ok(tour.includes('setAttribute("role", "dialog")'));
  assert.ok(tour.includes('setAttribute("aria-modal", "true")'));
  assert.ok(tour.includes('aria-live="polite"'));
  assert.ok(tour.includes('event.key === "Escape"'));
  assert.ok(tour.includes('event.key !== "Tab"'));
  assert.ok(tour.includes('event.shiftKey'));
  assert.ok(tour.includes("previouslyFocused.focus()"));
  assert.ok(tour.includes('localStorage.getItem("cj-seen-tour") === "1"'));
  assert.ok(tour.includes("catch (e) {}"));
});

test("system reduced-motion changes are picked up during the session", () => {
  assert.ok(app.includes('motionQuery.addEventListener("change", syncReducedMotionPreference)'));
  assert.ok(styles.includes("@media (prefers-reduced-motion: reduce)"));
  assert.ok(styles.includes(':root[data-motion="reduce"]'));

  const start = app.indexOf("const motionQuery = window.matchMedia");
  const end = app.indexOf("function countUp", start);
  let onChange;
  const query = {
    matches: false,
    addEventListener: (_event, callback) => { onChange = callback; },
  };
  const context = vm.createContext({
    window: { matchMedia: () => query },
    localStorage: { getItem: () => "system" },
    document: { documentElement: { dataset: {} } },
    clearPointerEffects() {},
  });
  vm.runInContext(app.slice(start, end), context);
  query.matches = true;
  onChange();
  assert.equal(vm.runInContext("REDUCE_MOTION", context), true);
  query.matches = false;
  onChange();
  assert.equal(vm.runInContext("REDUCE_MOTION", context), false);
  context.syncMotion = vm.runInContext("syncReducedMotionPreference", context);
  context.syncMotion("reduce");
  assert.equal(vm.runInContext("REDUCE_MOTION", context), true);
  context.syncMotion("system");
  assert.equal(vm.runInContext("REDUCE_MOTION", context), false);
});

test("primary buttons give a restrained hover response", () => {
  assert.match(styles, /@media \(hover: hover\) and \(pointer: fine\)[\s\S]*?\.btn:hover:not\(:disabled\)[\s\S]*?transform: translateY\(-1px\)/);
  assert.match(styles, /@media \(hover: hover\) and \(pointer: fine\)[\s\S]*?\.btn-primary:hover:not\(:disabled\)[\s\S]*?box-shadow: 0 4px 12px/);
  assert.ok(/\.btn:active:not\(:disabled\)\s*\{[^}]*transform: scale\(0\.98\)/.test(styles));
});

test("toast duration is visible as a subtle countdown", () => {
  assert.ok(app.includes('setProperty("--toast-duration"'));
  const savedToast = app.slice(app.indexOf("function showSavedToast("), app.indexOf("// Общий плавающий индикатор"));
  assert.ok(savedToast.includes('setProperty("--toast-duration", `${Math.max(1, duration)}ms`)'));
  assert.ok(styles.includes(".toast::after"));
  assert.ok(styles.includes("@keyframes toast-progress"));
  assert.ok(/\.toast::after\s*\{\s*animation: none;\s*transform: none;\s*\}/.test(styles));
});

test("reduced-motion preference also disables pointer-driven effects", () => {
  assert.ok(app.includes("if (REDUCE_MOTION) clearPointerEffects()"));
  assert.ok(app.includes("function clearPointerEffects()"));
});

test("hover movement is limited to devices with a precise hover pointer", () => {
  assert.ok(styles.includes("@media (hover: hover) and (pointer: fine)"));
  assert.match(styles, /@media \(hover: hover\) and \(pointer: fine\)[\s\S]*?\.btn:hover:not\(:disabled\)[\s\S]*?transform: translateY\(-1px\)/);
  assert.match(styles, /@media \(hover: hover\) and \(pointer: fine\)[\s\S]*?\.icon-btn:hover[\s\S]*?transform: translateY\(-1px\)/);
});
