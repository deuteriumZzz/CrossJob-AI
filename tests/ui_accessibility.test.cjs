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

test("confirmation dialogs do not override the focused button on Enter", () => {
  const start = app.indexOf("function showConfirm(message)");
  const end = app.indexOf("function initCommandPalette()", start);
  const confirmDialog = app.slice(start, end);
  assert.match(confirmDialog, /e\.key === "Escape"\) cleanup\(false\)/);
  assert.doesNotMatch(confirmDialog, /e\.key === "Enter"/);
  assert.match(confirmDialog, /okBtn\.addEventListener\("click", onOk\)/);
  assert.match(confirmDialog, /cancelBtn\.addEventListener\("click", onCancel\)/);
});

test("destructive and external actions use the app confirmation dialog", () => {
  assert.equal((app.match(/!confirm\(/g) || []).length, 0);
  assert.match(app, /await showConfirm\("Отправить письма через Gmail/);
  assert.match(app, /await showConfirm\(\`Бот начнёт сам отправлять отклики/);
});

test("company bulk network actions expose a busy state", () => {
  const start = app.indexOf("function renderBaseBulk()");
  const end = app.indexOf("// Удаление без", start);
  const bulkActions = app.slice(start, end);
  assert.ok(bulkActions.includes('await withButtonLoading(b, async () =>'));
  assert.ok(bulkActions.includes('action === "clear" || action === "all"'));
  const undoStart = app.indexOf("function showUndo(text, undo)");
  const undoEnd = app.indexOf("\nfunction ", undoStart + 10);
  const undo = app.slice(undoStart, undoEnd);
  assert.ok(undo.includes('setProperty("--undo-duration"'));
  assert.match(undo, /showToast\(err\.message\.replace\([\s\S]*?"error"\)/);
  assert.ok(styles.includes(".undo-bar::after"));
});

test("outreach settings show saving feedback and stop dependent mail tests on save failure", () => {
  const start = app.indexOf("async function saveOutreachSettings()");
  const end = app.indexOf("// Что бот делает прямо сейчас", start);
  const saveSettings = app.slice(start, end);
  assert.ok(saveSettings.includes('status.textContent = "Сохранение…"'));
  assert.ok(saveSettings.includes("withButtonLoading(button"));
  assert.ok(saveSettings.includes("return saved"));
  assert.match(app, /async function testOutreachEmail\(\)[\s\S]*?if \(!\(await saveOutreachSettings\(\)\)\) return/);
});

test("analytics and logs replace failed loading states with retry actions", () => {
  const analyticsStart = app.indexOf("async analytics() {");
  const analyticsEnd = app.indexOf("async settings()", analyticsStart);
  const analytics = app.slice(analyticsStart, analyticsEnd);
  const logsStart = app.indexOf("async logs() {");
  const logsEnd = app.indexOf("};", logsStart);
  const logs = app.slice(logsStart, logsEnd);
  const resultsStart = app.indexOf("async function renderResults()");
  const resultsEnd = app.indexOf("// «Отклики по неделям»", resultsStart);
  const results = app.slice(resultsStart, resultsEnd);
  assert.ok(analytics.includes("Promise.allSettled"));
  assert.ok(analytics.includes("renderRetryState"));
  assert.ok(logs.includes("renderRetryState"));
  assert.ok(results.includes("renderRetryState"));
  assert.ok(html.includes('id="log-error"'));
  assert.ok(html.includes('id="log-loading"'));
  assert.ok(logs.includes('getElementById("log-loading")'));
  assert.ok(analytics.includes('aria-label="Кандидат: ${escapeHtml(c)}"'));
});

test("resume loading and delete actions provide recovery feedback", () => {
  const start = app.indexOf("async function renderResumes()");
  const end = app.indexOf("// ----------", start);
  const resumes = app.slice(start, end);
  assert.ok(resumes.includes("Не удалось загрузить резюме"));
  assert.ok(resumes.includes("renderRetryState(el"));
  assert.ok(resumes.includes("await withButtonLoading(b, async () =>"));
  assert.ok(resumes.includes('showToast("Дополнительное резюме удалено", "success")'));
  assert.match(resumes, /catch \(err\)[\s\S]*?showToast\(err\.message\.replace/);
});

test("settings search exposes and controls an active listbox result", () => {
  assert.match(html, /id="settings-find-input"[^>]*role="combobox"/);
  assert.match(html, /id="settings-find-input"[^>]*aria-controls="settings-search-list"/);
  assert.match(app, /id="settings-search-list"[^>]*role="listbox"/);
  assert.match(app, /id="settings-option-\$\{i\}"[^>]*role="option"/);
  assert.match(app, /settings-find-input[\s\S]*ArrowDown[\s\S]*ArrowUp[\s\S]*aria-activedescendant/);
});

test("radio groups support arrow-key selection with one tab stop", () => {
  const start = app.indexOf("function initRadioGroupKeyboard()");
  const end = app.indexOf("\nfunction ", start + 10);
  const helper = app.slice(start, end);
  assert.ok(start >= 0);
  assert.ok(helper.includes('event.key === "ArrowRight" || event.key === "ArrowDown"'));
  assert.ok(helper.includes("syncRadioGroupTabStops(group"));
  assert.ok(app.includes("initRadioGroupKeyboard();"));
  assert.ok(helper.includes("new MutationObserver"));
  assert.ok(helper.includes("syncRadioGroupTabStops(node)"));
});

test("settings and conversation render failures show local retry states", () => {
  assert.ok(html.includes('id="settings-load-error"'));
  assert.ok(html.includes('id="replies-load-error"'));
  const settingsStart = app.indexOf("async settings() {");
  const settingsEnd = app.indexOf("async telegram()", settingsStart);
  const settings = app.slice(settingsStart, settingsEnd);
  const repliesStart = app.indexOf("async replies() {");
  const repliesEnd = app.indexOf("async analytics()", repliesStart);
  const replies = app.slice(repliesStart, repliesEnd);
  assert.ok(settings.includes("settings-load-error"));
  assert.ok(settings.includes("showSettingsLoadError"));
  assert.match(app, /function showSettingsLoadError\(error\)[\s\S]*?renderRetryState\(container/);
  assert.ok(replies.includes("Promise.allSettled"));
  assert.ok(replies.includes("replies-load-error"));
  assert.ok(replies.includes("renderRetryState"));
  assert.match(app, /function showViewRenderFailure\(name, error\)[\s\S]*?renderRetryState\(host/);
  const switchStart = app.indexOf("function switchTab(name)");
  const switchEnd = app.indexOf("\nfunction ", switchStart + 10);
  const switchTab = app.slice(switchStart, switchEnd);
  assert.ok(switchTab.includes("pendingRender.then("));
  assert.ok(switchTab.includes("clearViewRenderFailure(name)"));
  assert.ok(switchTab.includes("showViewRenderFailure(name, error)"));
});

test("analytics blacklist actions recover buttons and explain API failures", () => {
  const start = app.indexOf('document\n    .getElementById("blacklist-add")');
  const end = app.indexOf("Promise.all([", start);
  const handlers = app.slice(start, end);
  assert.ok(handlers.includes("await withButtonLoading(button"));
  assert.ok(handlers.includes("await withButtonLoading(btn"));
  assert.ok(handlers.includes('showToast(err.message.replace(/^\\d+: /, ""), "error")'));
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

test("motion effects avoid duplicate transforms and high-frequency layout animation", () => {
  const toastStart = app.indexOf("function showToast(");
  const toastEnd = app.indexOf("function showSavedToast(", toastStart);
  const toast = app.slice(toastStart, toastEnd);
  const pointerStart = app.indexOf("function initPointerEffects()");
  const pointerEnd = app.indexOf("// ---------- Directional", pointerStart);
  const pointerEffects = app.slice(pointerStart, pointerEnd);
  assert.doesNotMatch(toast, /gsap\.(?:fromTo|to)\(/);
  assert.ok(styles.includes(".toast.is-closing"));
  assert.ok(styles.includes("#command-overlay.is-instant > .command-palette"));
  assert.ok(styles.includes(".drawer-overlay.is-closing .drawer-panel"));
  assert.match(app, /function closePlatformDrawer\(\)[\s\S]*?classList\.add\("is-closing"\)/);
  assert.match(styles, /\.tab-indicator\s*\{[^}]*transition: transform[^}]*opacity/s);
  assert.doesNotMatch(styles.match(/\.tab-indicator\s*\{[^}]*\}/s)?.[0] || "", /transition:[^;]*(?:width|height)/);
  assert.match(styles, /@media \(hover: hover\) and \(pointer: fine\)[\s\S]*?\.source-card:hover/);
  assert.ok(pointerEffects.includes("requestAnimationFrame"));
});

test("motion indicators avoid geometry transitions and constant card glow", () => {
  const indicatorRules = [...styles.matchAll(/\.tab-indicator\s*\{([^}]*)\}/g)]
    .map((match) => match[1]);
  assert.ok(indicatorRules.length > 0);
  assert.ok(indicatorRules.every((rule) => !/transition:[^;]*(?:width|height)/s.test(rule)));

  const runningCard = styles.match(/\.source-card\.is-running\s*\{([^}]*)\}/);
  assert.ok(runningCard);
  assert.doesNotMatch(runningCard[1], /animation\s*:/);
  assert.match(styles, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
});

test("toast entry and exit are interruptible transitions", () => {
  const toastRules = [...styles.matchAll(/\.toast\s*\{([^}]*)\}/g)].map((match) => match[1]);
  const motionToastRule = toastRules.find((rule) => rule.includes("translateY(10px)"));
  assert.ok(motionToastRule);
  assert.match(motionToastRule, /transition:\s*opacity[^;]*transform/);
  assert.doesNotMatch(motionToastRule, /animation\s*:/);
  assert.match(styles, /\.toast\.is-visible\s*\{/);
  assert.match(styles, /\.toast\.is-closing\s*\{[^}]*opacity:\s*0/s);
  assert.match(app, /function revealToast\(el\)/);
  assert.equal((app.match(/revealToast\(el\)/g) || []).length, 3);
  assert.doesNotMatch(styles, /@keyframes toast-(?:in|out)/);
});

test("source card hover actions are limited to fine pointer devices", () => {
  assert.match(styles, /@media \(hover: hover\) and \(pointer: fine\)\s*\{\s*\.source-card:hover \.source-card-actions/);
});

test("search results escape text and expose removable active filter chips", () => {
  const start = app.indexOf("function highlightText(value, query)");
  const end = app.indexOf("\n}", start) + 2;
  assert.ok(start >= 0, "highlightText helper should exist");
  const helper = app.slice(start, end);
  const context = vm.createContext({
    escapeHtml: (value) => String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[char]),
  });
  vm.runInContext(`${helper}; globalThis.highlightText = highlightText`, context);
  assert.equal(
    context.highlightText("<Acme> Python developer", "acme"),
    "&lt;<mark class=\"search-highlight\">Acme</mark>&gt; Python developer"
  );
  assert.match(html, /id="history-active-filters"[^>]*aria-live="polite"/);
  assert.match(html, /id="contacts-active-filters"[^>]*aria-live="polite"/);
  assert.match(app, /data-remove-filter/);
  assert.match(app, /renderActiveFilters\("history"/);
  assert.match(app, /renderActiveFilters\("contacts"/);
});

test("favorite views and grouped breadcrumbs stay within existing navigation", () => {
  assert.match(html, /id="favorite-nav"[^>]*aria-label="Избранные разделы"/);
  assert.match(app, /function toggleFavoriteView\(view\)/);
  assert.match(app, /function renderFavoriteViews\(\)/);
  assert.match(app, /function renderPageBreadcrumb\(view\)/);
  assert.match(app, /data-favorite-toggle/);
  assert.match(app, /data-breadcrumb-view/);
  assert.match(app, /aria-label="Открыть раздел:/);
  assert.match(app, /cj-favorite-views/);
});

test("reply search highlights safe matches and slash focuses the current view search", () => {
  assert.match(html, /id="replies-active-filters"/);
  assert.match(app, /data-clear-replies-query/);
  assert.match(app, /highlightText\(e\.company[\s\S]*highlightText\(truncate\(preview/);
  assert.match(app, /if \(e\.key === "\/"\)/);
  assert.match(app, /replies-filter-query/);
});

test("all copy actions share repeat-safe success and visible failure feedback", () => {
  assert.match(app, /const copyFeedbackState = new WeakMap\(\)/);
  assert.match(app, /clearTimeout\(state\.timer\)/);
  assert.match(app, /fallbackField\?\.select\(\)/);
  assert.match(app, /copyToClipboard\(body\.querySelector\("#drawer-prompt"\)\.value/);
  assert.match(app, /copyToClipboard\(prompt\.value, e\.currentTarget, prompt\)/);
  assert.match(app, /showToast\("Не удалось скопировать/);
});

test("responsive screens keep messenger and settings usable with both themes", () => {
  assert.match(html, /name="viewport"[^>]*width=device-width/);
  assert.match(styles, /:root\s*\{[^}]*color-scheme:\s*dark/s);
  assert.match(styles, /:root\[data-theme="light"\]\s*\{[^}]*color-scheme:\s*light/s);
  assert.match(styles, /@media\s*\(max-width:\s*760px\)[\s\S]*?\.shell\.is-messenger \.talk-layout\s*\{[^}]*display:\s*block[^}]*height:\s*clamp/s);
  assert.match(styles, /@media\s*\(max-width:\s*900px\)[\s\S]*?\.settings-layout\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/s);
  assert.match(styles, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  assert.match(styles, /:root\[data-motion="reduce"\]/);
});

test("mobile messenger keeps the icon sidebar and settings text fields are named", () => {
  const messengerMobile = styles.lastIndexOf("@media (max-width: 820px)");
  const messengerWidthOverride = styles.lastIndexOf(".shell.is-messenger .sidebar", messengerMobile + 500);
  assert.ok(messengerMobile >= 0);
  assert.ok(messengerWidthOverride > messengerMobile, "messenger mobile override should follow the 232px desktop rule");
  assert.match(styles.slice(messengerWidthOverride, messengerWidthOverride + 100), /width:\s*60px/);

  const controls = [
    "telegram-login-phone", "telegram-login-code", "telegram-login-password",
    "search-company-blacklist", "search-title-blacklist", "search-location-blacklist",
    "search-positions", "search-locations", "tgq-keywords", "tgq-stop", "tgq-greeting",
    "tgq-delay-min", "tgq-delay-max", "tgq-hours-start", "tgq-hours-end",
    "tgq-daily-limit", "tg-daily-limit", "tg-hours-start", "tg-hours-end",
  ];
  for (const id of controls) {
    const control = html.match(new RegExp(`<[^>]+\\bid="${id}"[^>]*>`))?.[0] || "";
    assert.match(control, /\baria-label="[^"]+"/, `${id} should have an accessible name`);
  }
});
