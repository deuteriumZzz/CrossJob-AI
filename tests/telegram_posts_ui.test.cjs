const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = readFileSync(join(__dirname, "../src/webui/static/app.js"), "utf8");
const postsCode = source.slice(source.indexOf("let tgPostsData ="), source.indexOf("function closeTelegramPost()"));
const closeCode = source.slice(source.indexOf("function closeTelegramPost()"), source.indexOf("function tgPostContact("));
const repliesCode = source.slice(source.indexOf("  async replies() {"), source.indexOf("  async analytics() {"));
const contactCode = source.slice(source.indexOf("function tgPostContact("), source.indexOf("function tgPostResumeChoice("));
const panelCode = source.slice(source.indexOf("function tgPostPanelHtml("), source.indexOf("function tgPostContextHtml("));
const actionCode = source.slice(source.indexOf("async function tgPostAction("), source.indexOf("async function blockContact("));
const extrasCode = source.slice(source.indexOf("function initTalkExtras()"));

function setup() {
  const elements = Object.fromEntries(
    ["tg-posts-block", "tg-posts-count", "tg-posts-list", "tg-chat-posts-list", "tg-posts-more", "tg-chat-later", "tg-chat-empty", "replies-rows", "tg-post-panel", "talk-context-body"].map(
      (id) => [id, { hidden: true, innerHTML: "", textContent: "", style: {}, listeners: {}, replaceChildren() { this.innerHTML = ""; }, addEventListener(event, callback) { this.listeners[event] = callback; } }]
    )
  );
  const state = { posts: [], inboxError: false };
  const context = vm.createContext({
    document: { getElementById: (id) => elements[id], querySelectorAll: () => [] },
    repliesKind: "",
    repliesLoaded: false,
    lastRepliesCount: 0,
    lastRepliesSnapshot: null,
    lastRepliesEntries: [],
    renderDraftsQueue() {},
    renderHhRemindersQueue() {},
    renderRepliesRows() {},
    updateTalkListCount() {},
    fireConfetti() {},
    showToast() {},
    openTelegramPost() { state.openCount = (state.openCount || 0) + 1; },
    async refreshTelegramPost() {},
    tgPostResumeChoice: () => "",
    escapeHtml: (value) => String(value),
    emptyStateHtml: (message) => `<p>${message}</p>`,
    plogoHtml: () => "",
    truncate: (value) => value,
    fmtDay: (value) => value,
    api: async (path, options) => {
      if (path.endsWith("/draft")) {
        state.draftRequest = JSON.parse(options.body);
        state.draftedContact = state.draftRequest.contact;
        return {};
      }
      if (path.startsWith("/api/telegram/posts?scope=all&limit=200&offset=")) {
        const offset = Number(path.split("offset=")[1]);
        return { posts: structuredClone(state.posts.slice(offset, offset + 200)), total: state.posts.length, resume_options: [], sent_today: 0, daily_limit: 15 };
      }
      if (path === "/api/inbox") {
        if (state.inboxError) throw new Error("Inbox unavailable");
        return [];
      }
      throw new Error(`Unexpected request: ${path}`);
    },
  });
  vm.runInContext(`${postsCode}\n${closeCode}\n${contactCode}\n${panelCode}\n${actionCode}\n${extrasCode}\nconst render = { ${repliesCode} telegram() {} };`, context);
  const run = async (code) => {
    await vm.runInContext(code, context);
    await new Promise((resolve) => setImmediate(resolve));
  };
  return { elements, state, context, run };
}

test("empty posts remain visible with an explanation on Main and Telegram", async () => {
  const { elements, context, run } = setup();
  for (const kind of ["", "telegram"]) {
    context.repliesKind = kind;
    await run("renderTelegramPosts()");
    assert.equal(elements["tg-posts-block"].hidden, false);
    assert.match(elements["tg-posts-list"].innerHTML, /пока нет/i);
    assert.match(elements["tg-posts-count"].textContent, /0/);
  }
});

test("posts stay hidden for unrelated inbox filters", async () => {
  const { elements, context, run } = setup();
  for (const kind of ["interview", "replied", "rejected"]) {
    context.repliesKind = kind;
    await run("renderTelegramPosts()");
    assert.equal(elements["tg-posts-block"].hidden, true);
  }
});

test("new posts appear and disappear while inbox replies remain unchanged", async () => {
  const { elements, state, run } = setup();
  await run("render.replies()");
  state.posts = [{ id: "post-1", channel: "jobs", title: "Python developer", contacts: [] }];
  await run("render.replies()");
  assert.equal(elements["tg-posts-block"].hidden, false);
  assert.match(elements["tg-posts-list"].innerHTML, /Python developer/);
  assert.match(elements["tg-chat-posts-list"].innerHTML, /Python developer/);
  assert.match(elements["tg-posts-list"].innerHTML, /data-tg-post="post-1"/);
  assert.match(elements["tg-posts-count"].textContent, /1/);
  state.posts = [];
  await run("render.replies()");
  assert.equal(elements["tg-posts-block"].hidden, false);
  assert.doesNotMatch(elements["tg-posts-list"].innerHTML, /Python developer/);
  assert.match(elements["tg-posts-list"].innerHTML, /пока нет/i);
});

test("deletion of the last source post closes its stale conversation pane", async () => {
  const { elements, state, run } = setup();
  state.posts = [{ id: "post-deleted", channel: "jobs", title: "Old job", contacts: [] }];
  await run("renderTelegramPosts(); activeTgPostId = 'post-deleted'");
  elements["tg-post-panel"].hidden = false;
  state.posts = [];
  await run("renderTelegramPosts()");
  assert.equal(elements["tg-post-panel"].hidden, true);
  assert.equal(elements["tg-post-panel"].innerHTML, "");
});

test("history includes undated legacy and sent posts with a delivery receipt", async () => {
  const { elements, state, context, run } = setup();
  state.posts = [
    { id: "legacy", channel: "jobs", title: "Older vacancy", contacts: [] },
    { id: "sent", channel: "jobs", title: "Sent vacancy", status: "sent", contact: "anna_hr", sent_at: "2026-10-01T10:00:00Z", contacts: [{ kind: "telegram", value: "anna_hr" }] },
  ];
  await run("renderTelegramPosts()");
  assert.match(elements["tg-posts-list"].innerHTML, /Older vacancy/);
  assert.match(elements["tg-posts-list"].innerHTML, /Sent vacancy/);
  assert.match(elements["tg-posts-list"].innerHTML, /отправлено/i);
  const sentPanel = vm.runInContext("tgPostPanelHtml(tgPostsData.posts[1])", context);
  assert.match(sentPanel, /отправлено/i);
  assert.doesNotMatch(sentPanel, /data-post-action="send"/);
});

test("older vacancies remain available beyond the first history page", async () => {
  const { elements, state, run } = setup();
  state.posts = Array.from({ length: 201 }, (_, i) => ({
    id: `post-${i}`, channel: "jobs", title: `Vacancy ${i}`, contacts: [],
  }));
  await run("renderTelegramPosts()");
  assert.equal(elements["tg-posts-more"].hidden, false);
  assert.doesNotMatch(elements["tg-posts-list"].innerHTML, /Vacancy 200/);
  await run("initTalkExtras()");
  elements["tg-posts-more"].listeners.click();
  await new Promise((resolve) => setImmediate(resolve));
  assert.match(elements["tg-posts-list"].innerHTML, /Vacancy 200/);
  assert.equal(elements["tg-posts-more"].hidden, true);
});

test("an inbox error does not prevent posts from loading", async () => {
  const { elements, state, run } = setup();
  state.inboxError = true;
  state.posts = [{ id: "post-2", channel: "jobs", title: "Designer", contacts: [] }];
  await assert.rejects(run("render.replies()"), /Inbox unavailable/);
  assert.equal(elements["tg-posts-block"].hidden, false);
  assert.match(elements["tg-posts-list"].innerHTML, /Designer/);
});

test("polling retains the chosen recipient when requesting a draft", async () => {
  const { elements, state, run } = setup();
  state.posts = [{
    id: "post-1", channel: "jobs", title: "Developer",
    contacts: [{ kind: "telegram", value: "first_hr" }, { kind: "telegram", value: "second_hr" }],
    draft: { code: "draft-1", contact: "first_hr", text: "Hello" },
  }];
  await run("render.replies()");
  await run("activeTgPostId = 'post-1'; initTalkExtras()");
  elements["tg-post-panel"].listeners.click({ target: {
    closest: (selector) => selector === "[data-post-contact]"
      ? { dataset: { postContact: "second_hr" } } : null,
  } });
  await run("render.replies()");
  await run("tgPostAction('draft', {})");
  assert.equal(state.draftedContact, "second_hr");
  elements["tg-post-panel"].listeners.click({ target: {
    closest: (selector) => selector === "[data-post-contact]"
      ? { dataset: { postContact: "second_hr" } } : null,
  } });
  assert.equal(state.openCount, 1, "clicking the selected contact must not reset the composer");
});

test("chosen contact survives refreshed post data and hides stale draft", async () => {
  const { context } = setup();
  const result = vm.runInContext(
    `(() => {
      const post = {
        id: "post-3",
        channel: "jobs",
        title: "Python",
        text: "Vacancy",
        link: "https://t.me/jobs/3",
        contacts: [
          { kind: "telegram", value: "anna_hr" },
          { kind: "telegram", value: "bob_hr" },
        ],
        draft: { code: "draft-1", contact: "anna_hr", text: "Hello Anna" },
      };
      tgPostsData = { posts: [post], resume_options: [], sent_today: 0, daily_limit: 15 };
      tgPostContactChoice = { "post-3": "bob_hr" };
      return {
        contact: tgPostContact(post).value,
        draft: tgPostDraft(post),
        html: tgPostPanelHtml(post),
      };
    })()`,
    context
  );
  assert.equal(result.contact, "bob_hr");
  assert.equal(result.draft, null);
  assert.match(result.html, /Черновика пока нет/);
  assert.doesNotMatch(result.html, /Hello Anna/);
});

test("composer names the selected recipient and the sending account", () => {
  const { context } = setup();
  const html = vm.runInContext(`tgPostPanelHtml({
    id: "post-4", channel: "jobs_it", title: "AI developer", text: "Write to @nextbit_hr",
    link: "https://t.me/jobs_it/4", status: "new", contacts: [
      { kind: "telegram", value: "nextbit_hr" }, { kind: "email", value: "hr@example.com" }
    ], draft: { code: "draft-4", contact: "nextbit_hr", text: "Здравствуйте" }
  })`, context);
  assert.match(html, /Источник.*@jobs_it/s);
  assert.match(html, /Кому отправить/);
  assert.match(html, /@nextbit_hr/);
  assert.match(html, /hr@example\.com/);
  assert.match(html, /С вашего Telegram.*@nextbit_hr/s);
  assert.match(html, /Отправить в Telegram/);
  assert.match(html, /Переписка/);
});

test("a missing recipient offers an address field and no send button", () => {
  const { context } = setup();
  const html = vm.runInContext(`tgPostPanelHtml({
    id: "post-5", channel: "jobs_it", title: "AI developer", text: "Apply on website",
    link: "https://t.me/jobs_it/5", status: "new", contacts: []
  })`, context);
  assert.match(html, /Добавить адресата/);
  assert.match(html, /data-post-action="add-contact"/);
  assert.doesNotMatch(html, /data-post-action="send"/);
});

test("a Hirify vacancy offers contact retrieval without a recipient", () => {
  const { context } = setup();
  const html = vm.runInContext(`tgPostPanelHtml({
    id: "hirify-1", source: "hirify", channel: "Hirify", title: "Developer",
    text: "Apply on Hirify", link: "https://hirify.me/jobs/7-python-dev",
    status: "new", contacts: []
  })`, context);
  assert.doesNotMatch(html, /data-post-action="login-hirify"/);
  assert.match(html, /data-post-action="sync-hirify"/);
  assert.match(html, /Получить контакты из Hirify/);
  assert.doesNotMatch(html, /data-post-action="send"/);
});

test("Hirify sign-in is offered only after the saved session expires", () => {
  const { context } = setup();
  const html = vm.runInContext(`(() => {
    hirifyLoginRequired.add("hirify-1");
    return tgPostPanelHtml({
      id: "hirify-1", source: "hirify", channel: "Hirify", title: "Developer",
      text: "Apply on Hirify", link: "https://hirify.me/jobs/7-python-dev",
      status: "new", contacts: []
    });
  })()`, context);
  assert.match(html, /data-post-action="login-hirify"/);
  assert.match(html, /Повторить вход в Hirify/);
});

test("ambiguous mentions are not silently selected as delivery addresses", () => {
  const { context } = setup();
  const html = vm.runInContext(`tgPostPanelHtml({
    id: "post-ambiguous", channel: "jobs", title: "Developer", text: "@channel_one @channel_two",
    link: "https://t.me/jobs/7", status: "new",
    contacts: [{kind: "telegram", value: "channel_one"}, {kind: "telegram", value: "channel_two"}],
    recipient_options: []
  })`, context);
  assert.match(html, /Адресат не найден/);
  assert.doesNotMatch(html, /data-post-action="send"/);
});

test("multiple explicit recipients require the user to choose one", () => {
  const { context } = setup();
  const result = vm.runInContext(`(() => {
    const post = { id: "post-many", channel: "jobs", title: "Developer", text: "Contact both HRs",
      link: "https://t.me/jobs/8", status: "new", contacts: [
        {kind: "telegram", value: "first_hr"}, {kind: "telegram", value: "second_hr"}
      ], recipient_options: [
        {kind: "telegram", value: "first_hr"}, {kind: "telegram", value: "second_hr"}
      ] };
    return { selected: tgPostContact(post), html: tgPostPanelHtml(post) };
  })()`, context);
  assert.equal(result.selected, undefined);
  assert.match(result.html, /Выберите адресата/);
  assert.doesNotMatch(result.html, /data-post-action="send"/);
});

test("AI rewrite sends rewrite flag for the selected recipient", async () => {
  const { state, run } = setup();
  state.posts = [{ id: "post-6", channel: "jobs", title: "Developer",
    contacts: [{ kind: "telegram", value: "hr" }],
    draft: { code: "draft-6", contact: "hr", text: "Old text" } }];
  await run("renderTelegramPosts()");
  await run("activeTgPostId = 'post-6'; tgPostAction('rewrite', { disabled: false, textContent: '' })");
  assert.equal(state.draftRequest.contact, "hr");
  assert.equal(state.draftRequest.rewrite, true);
});
