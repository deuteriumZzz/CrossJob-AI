const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const root = join(__dirname, "../src/webui/static");
const css = readFileSync(join(root, "style.css"), "utf8");
const source = readFileSync(join(root, "app.js"), "utf8");

test("first load fades inbox content in after its skeleton without replaying on refresh", () => {
  assert.match(source, /const firstRepliesLoad = !repliesLoaded/);
  assert.match(source, /renderRepliesRows\(\{ animateContent: firstRepliesLoad \}\)/);
  assert.match(source, /function renderRepliesRows\(\{ animateContent = false \} = \{\}\)/);
  assert.match(css, /\.talk-list-content-arrive\s*\{[^}]*animation:\s*talk-content-arrive/s);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)[\s\S]*?\.talk-list-content-arrive/);
});

test("only genuinely new Telegram messages receive an entrance animation", () => {
  assert.match(source, /function newerTelegramMessageKeys\(previous, next\)/);
  assert.match(source, /function syncTelegramMessageBubbles\(container, messages, animateKeys = new Set\(\)\)/);
  assert.match(source, /animateKeys\.has\(key\)/);
  assert.match(source, /newerTelegramMessageKeys\(previouslyLoadedMessages, conv\.messages\)/);
  assert.match(source, /newerTelegramMessageKeys\(previous, page\.messages\)/);
  assert.match(css, /\.chat-bubble--enter\s*\{[^}]*animation:\s*rise/s);
  assert.doesNotMatch(css, /\.chat-bubble\s*\{[^}]*animation:\s*rise/s);
});

test("animated panel visibility remains accessible and is instant for keyboard and reduced-motion input", () => {
  const start = source.indexOf("const talkMotionVisibilityAnimations = new WeakMap()");
  const end = source.indexOf("function setTalkContextOpen(", start);
  assert.ok(start >= 0 && end > start);
  const context = vm.createContext({
    REDUCE_MOTION: false,
    document: { documentElement: {} },
    getComputedStyle: () => ({
      getPropertyValue(name) {
        return name === "--motion-enter" ? "180ms"
          : name === "--motion-exit" ? "140ms"
            : name === "--motion-ease-out" ? "cubic-bezier(0.23, 1, 0.32, 1)"
              : "";
      },
    }),
  });
  vm.runInContext(source.slice(start, end), context);
  const element = {
    hidden: true,
    inert: false,
    attrs: {},
    animations: [],
    setAttribute(name, value) { this.attrs[name] = value; },
    animate(frames, options) {
      const animation = { frames, options, cancelled: false, cancel() { this.cancelled = true; } };
      this.animations.push(animation);
      return animation;
    },
  };
  context.element = element;
  vm.runInContext('setTalkMotionVisibility(element, true, true)', context);
  assert.equal(element.hidden, false);
  assert.equal(element.inert, false);
  assert.equal(element.attrs["aria-hidden"], "false");
  assert.equal(element.animations[0].options.duration, 180);
  assert.match(element.animations[0].frames[0].transform, /translate/);

  vm.runInContext('setTalkMotionVisibility(element, false, true)', context);
  assert.equal(element.hidden, false);
  assert.equal(element.inert, true);
  assert.equal(element.attrs["aria-hidden"], "true");
  assert.equal(element.animations[1].options.duration, 140);
  element.animations[1].onfinish();
  assert.equal(element.hidden, true);

  element.animations.length = 0;
  vm.runInContext('setTalkMotionVisibility(element, true, false)', context);
  assert.equal(element.hidden, false);
  assert.equal(element.animations.length, 0);
  context.REDUCE_MOTION = true;
  vm.runInContext('setTalkMotionVisibility(element, false, true)', context);
  assert.equal(element.hidden, true);
  assert.equal(element.animations.length, 0);
});

test("context history reveals only on a deliberate conversation change", () => {
  assert.match(source, /function animateTalkTimeline\(body\)/);
  assert.match(source, /function showTalkContext\(e, animate = false\)/);
  assert.match(source, /if \(animate\) animateTalkTimeline\(body\)/);
  assert.match(source, /showTalkContext\(e, true\)/);
  assert.match(source, /showTalkContext\(match, contactChanged\)/);
  assert.match(css, /\.talk-timeline li\.is-entering\s*\{[^}]*animation:\s*talk-timeline-enter/s);
});

test("message indicator, details panels, tools panel, and resume menu have reversible motion states", () => {
  assert.match(source, /setTalkMotionVisibility\(drawer, open, animate, "x"\)/);
  assert.match(source, /setTalkMotionVisibility\(panel, open, animate\)/);
  assert.match(source, /setTalkMotionVisibility\(menu, open, e\.detail > 0\)/);
  assert.match(source, /setTalkMotionVisibility\(button, visible, animate && visible\)/);
  assert.match(source, /setTalkMotionVisibility\(more, visible, visible\)/);
  assert.match(css, /\.post-recipient\s*\{[^}]*transition:[^}]*background-color/s);
  assert.match(css, /\.post-recipient-check\s*\{[^}]*transition:/s);
});

test("mobile pane movement animates for pointer use and is immediate for keyboard selection", () => {
  assert.match(source, /function setTalkMobilePane\(pane, animate = false\)/);
  assert.match(source, /layout\.classList\.toggle\("is-motion-disabled", !animate \|\| REDUCE_MOTION\)/);
  assert.match(source, /selectInboxItem\(Number\(btn\.dataset\.inboxIndex\), event\.detail > 0\)/);
  assert.match(source, /setTalkMobilePane\("list", event\.detail > 0\)/);
  assert.match(css, /\.talk-layout\.is-motion-disabled \.talk-list,[\s\S]*?transition:\s*none !important/);
});
