const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const root = join(__dirname, "../src/webui/static");
const html = readFileSync(join(root, "index.html"), "utf8");
const css = readFileSync(join(root, "style.css"), "utf8");
const source = readFileSync(join(root, "app.js"), "utf8");

test("messenger uses two columns and keeps details in a closed drawer", () => {
  assert.match(css, /\.talk-layout\s*\{[^}]*grid-template-columns:\s*minmax\([^;]+\)\s+minmax\([^;]+\);/s);
  assert.match(html, /id="talk-context"[^>]*hidden/);
  assert.match(html, /id="talk-context-toggle"/);
  assert.match(html, /id="talk-context-close"/);
});

test("right-click menu exposes separate local cleanup and Telegram deletion", () => {
  const start = source.indexOf("function telegramMenuItems(");
  const end = source.indexOf("function initTalkExtras()", start);
  assert.ok(start >= 0 && end > start);
  const context = vm.createContext({});
  vm.runInContext(source.slice(start, end), context);
  const actions = (kind, hasContact) => Array.from(vm.runInContext(`telegramMenuItems(${JSON.stringify(kind)}, ${hasContact})`, context), (item) => item.action);
  assert.deepEqual(actions("post", true), ["open", "info", "remove-post", "remove-contact"]);
  assert.deepEqual(actions("post", false), ["open", "info", "remove-post"]);
  assert.deepEqual(actions("conversation", true), ["open", "info", "remove-contact", "delete-dialog"]);
});

test("switching to vacancies hides chats and selecting chats restores them", () => {
  const start = source.indexOf("function setTalkListTab(");
  const end = source.indexOf("function setTalkContextOpen(", start);
  const buttons = ["chats", "posts"].map((tab) => ({
    dataset: { talkListTab: tab },
    classList: { toggle(name, value) { this[name] = value; } },
    setAttribute(name, value) { this[name] = value; },
  }));
  const elements = {
    "talk-source-tabs": { querySelectorAll: () => buttons },
    "talk-chats-block": { hidden: false },
    "replies-kind": { hidden: false },
    "tg-posts-block": { hidden: true },
  };
  const context = vm.createContext({
    document: { getElementById: (id) => elements[id] },
    talkListTab: "chats",
    lastRepliesEntries: [],
    telegramConversationsCache: [],
    updateTalkListCount() {},
  });
  vm.runInContext(source.slice(start, end), context);
  vm.runInContext('setTalkListTab("posts", false)', context);
  assert.equal(elements["talk-chats-block"].hidden, true);
  assert.equal(elements["tg-posts-block"].hidden, false);
  assert.equal(buttons[1]["aria-selected"], "true");
  vm.runInContext('setTalkListTab("chats", false)', context);
  assert.equal(elements["talk-chats-block"].hidden, false);
  assert.equal(elements["tg-posts-block"].hidden, true);
});

test("Telegram counter includes a new outbound conversation without an inbox reply", () => {
  const start = source.indexOf("function telegramConversationCount(");
  const end = source.indexOf("function renderRepliesRows(", start);
  assert.ok(start >= 0 && end > start);
  const context = vm.createContext({});
  vm.runInContext(source.slice(start, end), context);
  const count = vm.runInContext(`telegramConversationCount(
    [{ contact: "nextbit_hr" }],
    [{ channel: "telegram_dm", contact: "NEXTBIT_HR" }]
  )`, context);
  assert.equal(count, 1);
  assert.equal(vm.runInContext("telegramConversationCount([{ contact: 'nextbit_hr' }], [])", context), 1);
});

test("messenger keeps parser controls in the filter panel and exposes a visible resume attachment", () => {
  assert.match(html, /id="talk-tools-toggle"/);
  assert.match(html, /id="talk-tools-panel"/);
  assert.match(html, /id="parser-open-base"/);
  assert.match(source, /post-attachment/);
  assert.match(source, /data-post-action="resume-menu"/);
  assert.match(source, /data-post-action="send"/);
});

test("conversation list includes unsent vacancy threads without losing the separate vacancies tab", () => {
  assert.match(html, /id="talk-chats-block"[\s\S]*id="tg-chat-posts-list"[\s\S]*id="replies-rows"/);
  assert.match(source, /tg-chat-posts-list/);
  assert.match(source, /#tg-posts-list \.talk-row, #tg-chat-posts-list \.talk-row/);
});
