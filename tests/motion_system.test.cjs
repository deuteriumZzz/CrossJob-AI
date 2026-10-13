const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const app = readFileSync(join(__dirname, "../src/webui/static/app.js"), "utf8");
const css = readFileSync(join(__dirname, "../src/webui/static/style.css"), "utf8");
const plan = readFileSync(join(__dirname, "../docs/PLAN.md"), "utf8");

test("motion system defines shared enter, exit, and movement tokens", () => {
  assert.match(css, /--motion-enter:\s*\d+ms/);
  assert.match(css, /--motion-exit:\s*\d+ms/);
  assert.match(css, /--motion-move:\s*\d+ms/);
  assert.match(css, /--motion-ease-out:\s*cubic-bezier\(/);
  assert.match(css, /--motion-ease-in-out:\s*cubic-bezier\(/);
  assert.match(css, /\.content-fade-in\s*\{[^}]*var\(--motion-enter\)/s);
  assert.match(css, /\.view\.slide-right\s*\{[^}]*var\(--motion-enter\)/s);
});

test("pointer sorting uses a guarded FLIP transition for retained company rows", () => {
  assert.match(app, /function captureBaseRowPositions\(animate\)/);
  assert.match(app, /function animateBaseRowReorder\(positions\)/);
  assert.match(app, /const animation = row\.animate\(\s*\[\s*\{ transform: `translateY\(\$\{delta\}px\)` \}/s);
  assert.match(app, /REDUCE_MOTION[\s\S]*?matchMedia\("\(hover: hover\) and \(pointer: fine\)"\)/);
  assert.match(app, /captureBaseRowPositions\(event\.detail > 0\)/);
  assert.match(app, /animateBaseRowReorder\(sortPositions\)/);
});

test("FLIP moves retained rows and skips reduced-motion sessions", () => {
  const start = app.indexOf("function captureBaseRowPositions(animate)");
  const end = app.indexOf("function contactHref(", start);
  assert.ok(start >= 0 && end > start);
  const row = {
    dataset: { cardKey: "company-a" },
    top: 100,
    animations: [],
    getBoundingClientRect() { return { top: this.top }; },
    animate(frames, options) {
      this.animations.push({ frames, options });
      return { cancel() {}, onfinish: null };
    },
  };
  const context = vm.createContext({
    REDUCE_MOTION: false,
    window: { matchMedia: () => ({ matches: true }) },
    document: {
      documentElement: {},
      querySelectorAll: () => [row],
    },
    Element: { prototype: { animate() {} } },
    requestAnimationFrame(callback) { callback(); },
    getComputedStyle: () => ({
      getPropertyValue(name) {
        return name === "--motion-move" ? "220ms" : "cubic-bezier(0.4, 0, 0.2, 1)";
      },
    }),
  });
  vm.runInContext(app.slice(start, end), context);
  const positions = context.captureBaseRowPositions(true);
  row.top = 145;
  context.animateBaseRowReorder(positions);
  assert.equal(row.animations.length, 1);
  assert.equal(row.animations[0].frames[0].transform, "translateY(-45px)");
  assert.equal(row.animations[0].options.duration, 220);

  context.REDUCE_MOTION = true;
  assert.equal(context.captureBaseRowPositions(true), null);
  context.animateBaseRowReorder(positions);
  assert.equal(row.animations.length, 1);
});

test("native conversation disclosures reveal content subtly when supported", () => {
  assert.match(css, /@supports selector\(details::details-content\)/);
  assert.match(css, /details\.row-actions::details-content\s*\{[^}]*opacity:\s*0/s);
  assert.match(css, /details\.row-actions\[open\]::details-content\s*\{[^}]*opacity:\s*1/s);
  assert.match(css, /data-motion="reduce"[^}]*details::details-content|details::details-content[^}]*transition:\s*none/s);
});

test("keyboard navigation changes views without directional entrance motion", () => {
  const start = app.indexOf("let navigationInputModality");
  const end = app.indexOf("function switchTab(", start);
  assert.ok(start >= 0 && end > start);
  const listeners = {};
  const context = vm.createContext({
    document: {
      addEventListener(type, listener) { listeners[type] = listener; },
    },
  });
  vm.runInContext(app.slice(start, end), context);
  assert.equal(context.shouldAnimateNavigation(), true);
  listeners.keydown({ type: "keydown" });
  assert.equal(context.shouldAnimateNavigation(), false);
  listeners.pointerdown({ type: "pointerdown" });
  assert.equal(context.shouldAnimateNavigation(), true);

  const switchStart = app.indexOf("function switchTab(");
  const switchEnd = app.indexOf("function ", switchStart + 10);
  assert.match(app.slice(switchStart, switchEnd), /prevName !== name && shouldAnimateNavigation\(\)/);
});

test("motion guide preserves scenario hierarchy and keyboard/reduced-motion rules", () => {
  assert.match(plan, /### Motion-гайд/);
  assert.match(plan, /клавиатуры происходят сразу/);
  assert.match(plan, /фоновые обновления не повторяют входные эффекты/);
  assert.match(plan, /сортировка перемещает оставшиеся на экране строки/);
});
