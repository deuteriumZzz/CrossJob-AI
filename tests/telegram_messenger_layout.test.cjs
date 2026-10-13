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

test("mobile messenger provides a back-to-list action and keeps both panes in one viewport", () => {
  assert.match(html, /id="talk-thread-back"[^>]*aria-label="Вернуться к списку разговоров"/);
  assert.match(css, /\.shell\.is-messenger \.talk-layout\.is-mobile-thread-open \.talk-list\s*\{[^}]*visibility:\s*hidden/s);
  assert.match(css, /\.shell\.is-messenger \.talk-layout\.is-mobile-thread-open \.talk-thread\s*\{[^}]*visibility:\s*visible/s);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  assert.match(source, /function setTalkMobilePane\(pane, animate = false\)/);
  assert.match(source, /setTalkMobilePane\("thread", animatePane\)/);
  assert.match(source, /setTalkMobilePane\("list", event\.detail > 0\)/);
  assert.match(source, /openTelegramConversation\(activeTelegramContact, false, true, true, false, true\)/);
  assert.match(source, /if \(!preservePane\) setTalkMobilePane\("thread", animatePane\)/);
  assert.match(source, /function setTalkMobilePane\(pane, animate = false\)[\s\S]*?\.talk-list[\s\S]*?\.talk-thread[\s\S]*?aria-hidden/);
});

test("Telegram refresh preserves a reader's scroll position and offers a new-message jump", () => {
  assert.match(html, /id="tg-chat-new-messages"[^>]*hidden/);
  assert.match(source, /preserveScroll = false/);
  assert.match(source, /openTelegramConversation\(activeTelegramContact, false, true, true, false, true\)/);
  assert.match(source, /shouldStickToBottom\(/);
  assert.match(source, /Показать новые сообщения/);
  assert.match(source, /behavior: REDUCE_MOTION \? "auto" : "smooth"/);
  assert.match(source, /syncTelegramMessageBubbles\(messages, visibleMessages, newlyReceivedKeys\)/);
});

test("old Telegram history does not inflate the new-message counter", () => {
  const start = source.indexOf("function telegramMessageKey(message)");
  const end = source.indexOf("function providerLabel(", start);
  const context = vm.createContext({});
  vm.runInContext(source.slice(start, end), context);
  const count = vm.runInContext(`countNewerTelegramMessages(
    [{ id: 8, at: "2026-10-12T10:00:00Z" }, { id: 9, at: "2026-10-12T10:01:00Z" }],
    [{ id: 2, at: "2026-10-12T09:00:00Z" }, { id: 8, at: "2026-10-12T10:00:00Z" }, { id: 9, at: "2026-10-12T10:01:00Z" }, { id: 10, at: "2026-10-12T10:02:00Z" }]
  )`, context);
  assert.equal(count, 1);
});

test("context panel orders recorded application, message, and reply events", () => {
  const start = source.indexOf("function talkTimelineHtml(entry)");
  const end = source.indexOf("function talkContextHtml(", start);
  const context = vm.createContext({
    escapeHtml: (value) => String(value),
    fmtTime: (value) => value,
    INBOX_KIND: { replied: { title: "Ответили" } },
  });
  vm.runInContext(source.slice(start, end), context);
  const html = vm.runInContext(`talkTimelineHtml({
    channel: "email",
    applied_at: "2026-01-01T00:00:00Z",
    sent_at: "2026-01-02T00:00:00Z",
    replied_at: "2026-01-03T00:00:00Z"
  })`, context);
  assert.ok(html.indexOf("Отклик отправлен") < html.indexOf("Письмо отправлено"));
  assert.ok(html.indexOf("Письмо отправлено") < html.indexOf("Ответ работодателя"));
});

test("refresh keeps the selected inbox row tied to its record when new rows arrive", () => {
  assert.match(source, /function inboxEntryKey\(entry\)/);
  assert.match(source, /inboxEntryKey\(e\) === selectedInboxKey/);
});

test("mobile pane and near-bottom helpers behave without changing the current pane on desktop", () => {
  const start = source.indexOf("function setTalkMobilePane(");
  const end = source.indexOf("function setTalkListTab(", start);
  const classes = new Set();
  const layout = {
    classList: {
      toggle(name, value) { value ? classes.add(name) : classes.delete(name); },
      contains(name) { return classes.has(name); },
    },
  };
  const context = vm.createContext({
    document: { querySelector: () => layout },
    window: { matchMedia: () => ({ matches: false }) },
  });
  vm.runInContext(source.slice(start, end), context);
  vm.runInContext('setTalkMobilePane("thread")', context);
  assert.equal(classes.has("is-mobile-thread-open"), true);
  vm.runInContext('setTalkMobilePane("list")', context);
  assert.equal(classes.has("is-mobile-thread-open"), false);
  assert.equal(vm.runInContext("shouldStickToBottom({ scrollTop: 400, clientHeight: 200, scrollHeight: 590 })", context), true);
  assert.equal(vm.runInContext("shouldStickToBottom({ scrollTop: 100, clientHeight: 200, scrollHeight: 590 })", context), false);
});

test("conversation sending has explicit busy and recipient feedback", () => {
  assert.match(html, /id="tg-chat-status"[^>]*aria-live="polite"/);
  assert.match(html, /id="tg-chat-retry"[^>]*hidden/);
  assert.match(source, /sendingTelegramMessage/);
  assert.match(source, /aria-busy/);
  assert.match(source, /retry\.hidden = false/);
  assert.match(source, /@\$\{contact\}/);
});

test("background Telegram polling does not repeatedly steal keyboard focus", () => {
  const start = source.indexOf("function setTalkMobilePane(");
  const end = source.indexOf("function setTalkListTab(", start);
  const classes = new Set();
  let focusCount = 0;
  const layout = {
    classList: {
      toggle(name, value) { value ? classes.add(name) : classes.delete(name); },
      contains(name) { return classes.has(name); },
    },
    querySelector: () => ({ focus() { focusCount++; } }),
  };
  const context = vm.createContext({
    document: { querySelector: () => layout },
    window: { matchMedia: () => ({ matches: true }) },
  });
  vm.runInContext(source.slice(start, end), context);
  vm.runInContext('setTalkMobilePane("thread")', context);
  vm.runInContext('setTalkMobilePane("thread")', context);
  assert.equal(focusCount, 1);
});

test("mobile pane hides the inactive conversation from keyboard and assistive technology", () => {
  const start = source.indexOf("function setTalkMobilePane(");
  const end = source.indexOf("function shouldStickToBottom(", start);
  const classes = new Set();
  const makePane = () => ({
    inert: false,
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
    focus() {},
  });
  const list = makePane();
  const thread = makePane();
  let mobile = true;
  const layout = {
    classList: {
      toggle(name, value) { value ? classes.add(name) : classes.delete(name); },
      contains(name) { return classes.has(name); },
    },
    querySelector(selector) { return selector === ".talk-list" ? list : thread; },
  };
  const context = vm.createContext({
    document: { querySelector: () => layout },
    window: { matchMedia: () => ({ matches: mobile }) },
  });
  vm.runInContext(source.slice(start, end), context);
  vm.runInContext('setTalkMobilePane("thread")', context);
  assert.equal(list.inert, true);
  assert.equal(list.attributes["aria-hidden"], "true");
  assert.equal(thread.inert, false);
  assert.equal(thread.attributes["aria-hidden"], "false");
  vm.runInContext('setTalkMobilePane("list")', context);
  assert.equal(list.inert, false);
  assert.equal(list.attributes["aria-hidden"], "false");
  assert.equal(thread.inert, true);
  assert.equal(thread.attributes["aria-hidden"], "true");
  mobile = false;
  vm.runInContext("syncTalkMobilePaneAccessibility()", context);
  assert.equal(list.inert, false);
  assert.equal(list.attributes["aria-hidden"], "false");
  assert.equal(thread.inert, false);
  assert.equal(thread.attributes["aria-hidden"], "false");
});

test("mobile pane accessibility is synchronized on initial messenger setup", () => {
  const initStart = source.indexOf("function initTalkExtras()");
  const initEnd = source.indexOf('document.getElementById("talk-tools-toggle")', initStart);
  const init = source.slice(initStart, initEnd);
  assert.ok(initStart >= 0 && initEnd > initStart);
  const initialSync = init.indexOf("syncTalkMobilePaneAccessibility()");
  const resizeListener = init.indexOf("window.matchMedia");
  assert.ok(initialSync >= 0 && resizeListener >= 0);
  assert.ok(initialSync < resizeListener, "initial pane sync must run before installing the resize listener");
});

test("changing Telegram conversations hides a stale retry action", () => {
  const start = source.indexOf("async function openTelegramConversation(");
  const end = source.indexOf("\n}", start) + 2;
  const conversation = source.slice(start, end);
  assert.ok(start >= 0 && end > start);
  const changedStart = conversation.indexOf("if (contactChanged) {");
  const changedEnd = conversation.indexOf("\n  }", changedStart) + 4;
  const changedState = conversation.slice(changedStart, changedEnd);
  assert.ok(changedStart >= 0 && changedEnd > changedStart);
  assert.match(changedState, /tg-chat-retry[\s\S]*?retry\.hidden = true/);
});
