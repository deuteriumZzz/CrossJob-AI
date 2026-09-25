// Применяем сохранённую тему сразу при загрузке скрипта (до
// DOMContentLoaded) — иначе будет видна вспышка тёмной темы перед
// переключением на светлую.
(function initTheme() {
  const saved = localStorage.getItem("cj-theme");
  if (saved === "light" || saved === "dark") {
    document.documentElement.dataset.theme = saved;
  }
})();

const SOURCE_LABELS = {
  headhunter: "HeadHunter",
  geekjob: "geekjob.ru",
  telegram: "Telegram",
  getmatch: "GetMatch",
  linkedin: "LinkedIn",
  habr_career: "Habr Career",
  wellfound: "Wellfound",
  himalayas: "Himalayas",
  djinni: "Djinni",
  direct: "Сайты компаний",
};

// ponytail: настоящие логотипы площадок — товарные знаки, тащить их к себе
// рискованно. Вместо этого — монограмма (1-2 буквы) на цветном бейдже,
// свой цвет на площадку для быстрого узнавания глазами в таблицах/карточках.
const SOURCE_ICON = {
  headhunter: { text: "hh", color: "#d64545" },
  geekjob: { text: "GJ", color: "#3fb37f" },
  telegram: { text: "TG", color: "#35a8e0" },
  getmatch: { text: "GM", color: "#8a6fd1" },
  linkedin: { text: "in", color: "#2f6fed" },
  habr_career: { text: "HC", color: "#e0954a" },
  wellfound: { text: "WF", color: "#c23b6b" },
  himalayas: { text: "HM", color: "#5b7fd6" },
  djinni: { text: "DJ", color: "#2f9e6e" },
  direct: { text: "→", color: "#4f9d8f" },
};

// Площадки, нацеленные на зарубежный рынок — остальные площадки RU.
const OWN_CHANNELS = new Set(["telegram", "direct"]);
const INTL_SOURCES = new Set(["linkedin", "wellfound", "himalayas", "djinni"]);

const STATUS_DOT = {
  ok: "ok",
  error: "error",
  blocked: "blocked",
  never_run: "never_run",
};

function sourceLabel(name) {
  return SOURCE_LABELS[name] || name;
}

function sourceIconHtml(name) {
  const icon = SOURCE_ICON[name];
  if (!icon) return "";
  return `<span class="source-icon" style="background:${icon.color}">${icon.text}</span>`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

// Причины пропуска (fit.gaps) — это полные предложения от LLM, а не
// короткие лейблы, для которых была сделана .readiness-note (110px):
// без обрезки один длинный gap растягивал строку истории на сотни
// пикселей в высоту. Полный текст всё равно доступен через title=.
function truncate(text, maxLength) {
  const s = String(text || "");
  return s.length > maxLength ? s.slice(0, maxLength - 1) + "…" : s;
}

// Тег-инпут поверх textarea со списком "один пункт на строку"
// (должности/локации/чёрные списки, свои должности/локации
// площадки) — textarea остаётся источником правды (просто скрыта),
// поэтому существующие обработчики "Сохранить" (linesOfEl и
// аналоги, читающие .value построчно) не меняются вообще. initTagInput
// идемпотентна: повторный вызов на уже обёрнутой textarea (например
// после programmatic .value = "..." с сервера) просто перерисовывает
// чипы из актуального значения, не создавая обёртку заново.
function tagItemsOf(textarea) {
  return textarea.value
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

function renderTagChips(textarea) {
  const chips = textarea._tagChipsEl;
  if (!chips) return;
  const items = tagItemsOf(textarea);
  chips.innerHTML = items
    .map(
      (item, i) =>
        `<span class="tag-chip">${escapeHtml(item)}<button type="button" class="tag-chip-remove" data-i="${i}" aria-label="Удалить">×</button></span>`
    )
    .join("");
  chips.querySelectorAll(".tag-chip-remove").forEach((btn) => {
    btn.addEventListener("click", () => {
      const current = tagItemsOf(textarea);
      current.splice(parseInt(btn.dataset.i, 10), 1);
      textarea.value = current.join("\n");
      renderTagChips(textarea);
      tagChanged(textarea);
    });
  });
}

// Скрытая textarea меняется кодом — сообщаем об этом, как обычное поле
// (иначе автосохранение настроек не узнает про добавленный тег).
function tagChanged(textarea) {
  textarea.dispatchEvent(new Event("change", { bubbles: true }));
}

function initTagInput(textarea) {
  if (textarea.dataset.tagInputInit) {
    renderTagChips(textarea);
    return;
  }
  textarea.dataset.tagInputInit = "1";
  textarea.style.display = "none";

  const wrap = document.createElement("div");
  wrap.className = "tag-input";
  const chips = document.createElement("div");
  chips.className = "tag-chips";
  const input = document.createElement("input");
  input.type = "text";
  input.className = "tag-input-field";
  // Плейсхолдер textarea рассчитан на несколько строк ("пример1\nпример2")
  // — в однострочном input это слипается в "пример1пример2" без
  // разделителя, если не заменить переносы явно.
  input.placeholder = textarea.placeholder
    ? textarea.placeholder.replace(/\n/g, " · ")
    : "Добавить, Enter";
  wrap.append(chips, input);
  textarea.insertAdjacentElement("afterend", wrap);
  textarea._tagChipsEl = chips;

  function commit() {
    const value = input.value.trim();
    if (!value) return;
    const items = tagItemsOf(textarea);
    if (!items.includes(value)) {
      items.push(value);
      textarea.value = items.join("\n");
      renderTagChips(textarea);
      tagChanged(textarea);
    }
    input.value = "";
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit();
    } else if (e.key === "Backspace" && !input.value) {
      const items = tagItemsOf(textarea);
      items.pop();
      textarea.value = items.join("\n");
      renderTagChips(textarea);
      tagChanged(textarea);
    }
  });
  input.addEventListener("blur", commit);

  renderTagChips(textarea);
}

// last_error теперь {summary, detail} от _classify_error() в api.py —
// короткая фраза для человека + сырой текст исключения под
// сворачиваемой деталью, а не JSON-простыня от LLM-провайдера прямо в
// карточке площадки.
function errorRowHtml(lastError) {
  if (!lastError) return "";
  return `
    <details class="error-row">
      <summary>${escapeHtml(lastError.summary)}</summary>
      <pre>${escapeHtml(lastError.detail)}</pre>
    </details>`;
}

const STATUS_LABELS = {
  applied: "отправлено",
  dry_run: "тестовый прогон",
  skipped_low_fit: "пропущено (слабое совпадение)",
  skipped_easy_apply_failed: "пропущено (форма Easy Apply)",
  skipped_closed_posting: "пропущено (вакансия закрыта)",
  skipped_requirements: "пропущено (не проходит требования)",
};

const REGION_LABELS = {
  us_only: "🇺🇸 только США",
  europe_only: "🇪🇺 только Европа",
  global: "🌍 откуда угодно",
};

const STAGE_LABELS = {
  replied: "ответили",
  interview: "интервью",
  test_task: "тестовое",
  offer: "оффер",
  rejected: "отказ",
};

// Этап — выпадающий список прямо в строке: ставится вручную, пустое
// значение снимает ручную отметку (этап снова считается по ответу hh).
function stageSelectHtml(e) {
  if (!e.external_id) return `<span class="muted small">—</span>`;
  const current = e.effective_stage ?? e.stage ?? "";
  const options = [["", "—"], ...Object.entries(STAGE_LABELS)]
    .map(
      ([value, label]) =>
        `<option value="${value}"${value === current ? " selected" : ""}>${label}</option>`
    )
    .join("");
  return `<select class="stage-select" data-stage-source="${escapeHtml(e.source)}" data-stage-id="${escapeHtml(e.external_id)}" aria-label="Этап">${options}</select>`;
}

function bindStageSelects(container) {
  container.querySelectorAll("[data-stage-id]").forEach((select) => {
    select.addEventListener("change", async () => {
      try {
        await api("/api/applications/stage", {
          method: "POST",
          body: JSON.stringify({
            source: select.dataset.stageSource,
            external_id: select.dataset.stageId,
            stage: select.value,
          }),
        });
        showToast("Этап сохранён", "success");
      } catch (err) {
        showToast(`Не удалось сохранить этап: ${err.message}`, "error");
      }
    });
  });
}

function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString();
}

const REDUCE_MOTION = window.matchMedia(
  "(prefers-reduced-motion: reduce)"
).matches;

function countUp(el, target, duration = 700, start = 0) {
  if (REDUCE_MOTION) {
    el.textContent = target;
    return;
  }
  const startTime = performance.now();
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  function tick(now) {
    const progress = Math.min(1, (now - startTime) / duration);
    const value = Math.round(start + (target - start) * ease(progress));
    el.textContent = value;
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// Цифры на карточках плавно досчитываются с прошлого значения до нового —
// видно, что изменилось. Первый показ — без анимации.
const shownCounts = {};
function animateCounts(root) {
  root.querySelectorAll("[data-count]").forEach((el) => {
    const id = el.dataset.count;
    const value = parseInt(el.textContent, 10) || 0;
    const before = shownCounts[id];
    shownCounts[id] = value;
    if (before !== undefined && before !== value) {
      countUp(el, value, 700, before);
      el.classList.add("count-changed");
      setTimeout(() => el.classList.remove("count-changed"), 1600);
    }
  });
}

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("in-view");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  { threshold: 0.1 }
);

function observeReveal(container) {
  container.querySelectorAll(".reveal").forEach((el) => {
    revealObserver.observe(el);
  });
}

function staggerDelay(index, step = 40) {
  return `${Math.min(index * step, 400)}ms`;
}

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status}: ${body}`);
  }
  return response.json();
}

async function refreshTelegramConnectStatus() {
  const statusEl = document.getElementById("telegram-connect-status");
  if (!statusEl) return true; // элемент есть только внутри вкладки "Настройки"
  try {
    const data = await api("/api/settings/telegram/connect/status");
    if (data.status === "connected") {
      statusEl.innerHTML = `✅ Подключено (chat_id: ${escapeHtml(String(data.chat_id))}) <button type="button" class="copy-btn" title="Скопировать chat_id" aria-label="Скопировать chat_id">${COPY_ICON_SVG}</button>`;
      statusEl.querySelector(".copy-btn").addEventListener("click", (e) => {
        copyToClipboard(String(data.chat_id), e.currentTarget);
      });
      return true;
    }
    if (data.status === "timeout") {
      statusEl.textContent =
        "Не дождались Start за 3 минуты — попробуйте снова.";
      return true;
    }
    if (data.status === "waiting") {
      statusEl.textContent = "Ждём, когда вы нажмёте Start у бота…";
      return false;
    }
    statusEl.textContent = "Ещё не подключено — вставьте токен и нажмите «Подключить».";
  } catch (e) {
    // тихая фоновая проверка — idle/сеть не показываем как ошибку
  }
  return true;
}

// 5 разделов в меню вместо 9 вкладок: подразделы показываются строкой
// над содержимым раздела. Ключ — раздел (data-tab кнопки меню), значение —
// его подразделы (id view-*) с подписями; первый — открывается по клику.
const NAV_GROUPS = {
  overview: [["overview", "Главная"]],
  history: [["history", "Вакансии"]],
  replies: [
    ["replies", "Входящие"],
    ["telegram", "Telegram-парсер"],
  ],
  contacts: [
    ["contacts", "База"],
    ["outreach", "Рассылки"],
  ],
  analytics: [["analytics", "Аналитика"]],
  settings: [
    ["settings", "Настройки"],
    ["resume", "Мои резюме"],
    ["logs", "Логи"],
  ],
};
const VIEW_GROUP = Object.fromEntries(
  Object.entries(NAV_GROUPS).flatMap(([group, views]) =>
    views.map(([view]) => [view, group])
  )
);
let currentView = "overview";

function renderSubnav(group, view) {
  const subnav = document.getElementById("subnav");
  const views = NAV_GROUPS[group] || [];
  if (views.length < 2) {
    subnav.style.display = "none";
    return;
  }
  subnav.style.display = "";
  subnav.innerHTML = views
    .map(
      ([id, label]) =>
        `<button type="button" class="${id === view ? "active" : ""}" data-subview="${id}">${label}<span class="subnav-badge" data-subbadge="${id}"></span></button>`
    )
    .join("");
  subnav.querySelectorAll("[data-subview]").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.subview));
  });
}

function switchTab(name) {
  if (!VIEW_GROUP[name]) name = "overview";
  const prevName = currentView;
  currentView = name;
  const group = VIEW_GROUP[name];
  document
    .querySelectorAll("nav.tabs button")
    .forEach((b) => b.classList.toggle("active", b.dataset.tab === group));
  renderSubnav(group, name);
  applySubnavBadges();
  document
    .querySelectorAll("main .view")
    .forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  if (prevName && prevName !== name) {
    directionalReveal(document.getElementById(`view-${name}`), prevName, name);
  }
  // URL отражает текущую вкладку — иначе обновление страницы (F5) всегда
  // сбрасывает на "Обзор", даже если человек читал длинный тред в Telegram
  // или таблицу в Истории. replaceState, а не location.hash — не плодит
  // отдельную запись в истории браузера на каждый клик по вкладке.
  history.replaceState(null, "", `#${name}`);
  render[name]?.();
  moveTabIndicator(
    document.getElementById("nav-tab-indicator"),
    document.querySelector(`nav.tabs button[data-tab="${group}"]`)
  );
  if (name === "settings") {
    // switchSettingsTab() двигает #settings-tab-indicator только по
    // клику на саб-вкладку — при первом заходе в "Настройки" за сессию
    // активная по умолчанию "Поиск" ни разу не получала позицию
    // индикатора, а .active у самой кнопки специально прозрачный (фон
    // даёт индикатор) — с тёмным текстом поверх это выглядело как
    // пустая таблетка вместо подписи "Поиск".
    moveTabIndicator(
      document.getElementById("settings-tab-indicator"),
      settingsTabAnchor(document.querySelector("#settings-jump button.active"))
    );
  }
}

let overviewLoaded = false;
let lastOverviewSnapshot = null;
let pendingPlatformDrawer = null;
let historyLoaded = false;
let lastHistorySnapshot = null;
let lastHistoryEntries = [];
let repliesLoaded = false;
let lastRepliesSnapshot = null;
let lastRepliesCount = 0;
let lastRepliesEntries = [];
let logsLoaded = false;
let lastLogsSnapshot = null;
let lastLogsLines = [];
let llmCatalog = { models: {}, api_key_previews: {}, provider_base_urls: {} };
// Провайдеры без единого статического эндпоинта — нужен свой
// base_url на аккаунт (сейчас только Cloudflare Workers AI, у
// которого account_id зашит в URL). См. llm_provider.py:
// set_fallback_base_urls().
const PROVIDERS_NEEDING_BASE_URL = new Set(["cloudflare"]);
let activeTelegramContact = null;

function formatChatTime(iso) {
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function providerLabel(provider) {
  const card = document.querySelector(
    `#provider-grid .provider-card[data-provider="${provider}"]`
  );
  return card ? card.querySelector("span").textContent : provider;
}

// Те же страницы, что в таблице docs/GUIDE.md — держать в одном
// месте смысла нет (бэкенд не знает про этот URL), поэтому
// дублируется здесь; при добавлении провайдера обновлять оба места.
const LLM_KEY_PAGE_URLS = {
  openai: "https://platform.openai.com/api-keys",
  groq: "https://console.groq.com/keys",
  gemini: "https://aistudio.google.com/apikey",
  deepseek: "https://platform.deepseek.com/api_keys",
  nvidia: "https://build.nvidia.com",
  openrouter: "https://openrouter.ai/keys",
  mistral: "https://console.mistral.ai/api-keys",
  cohere: "https://dashboard.cohere.com/api-keys",
  huggingface: "https://huggingface.co/settings/tokens",
  ollama_cloud: "https://ollama.com/settings/keys",
  llm7: "https://token.llm7.io",
  cloudflare: "https://dash.cloudflare.com/profile/api-tokens",
  vercel: "https://vercel.com/docs/ai-gateway/authentication-and-byok/api-keys",
};

function applyLLMSelection(provider, currentModel) {
  document
    .querySelectorAll("#provider-grid .provider-card")
    .forEach((card) => {
      card.classList.toggle("active", card.dataset.provider === provider);
      card.classList.toggle(
        "has-key",
        Boolean(llmCatalog.api_key_previews[card.dataset.provider])
      );
    });
  updateProviderVisibility();

  const modelSelect = document.getElementById("llm-model");
  const models = llmCatalog.models[provider] || [];
  modelSelect.innerHTML = models
    .map(
      (m) =>
        `<option value="${m.id}">${m.recommended ? "👑 " : ""}${m.id}${m.free ? " · бесплатно" : ""}</option>`
    )
    .join("");
  const recommended = models.find((m) => m.recommended);
  if (currentModel && models.some((m) => m.id === currentModel)) {
    modelSelect.value = currentModel;
  } else if (recommended) {
    // Свежее переключение провайдера без сохранённой модели — сразу
    // подставляем рекомендованную (👑), а не первую по силе: для
    // наших задач (оценка вакансии, письма) это лучший выбор
    // цена/скорость/качество, не обязательно самая мощная модель.
    modelSelect.value = recommended.id;
  }

  document.getElementById("llm-key-provider-label").textContent =
    providerLabel(provider);
  document.getElementById("llm-key-preview").textContent =
    llmCatalog.api_key_previews[provider] || "—";

  const keyLink = document.getElementById("llm-key-get-link");
  const keyPageUrl = LLM_KEY_PAGE_URLS[provider];
  keyLink.style.display = keyPageUrl ? "" : "none";
  if (keyPageUrl) keyLink.href = keyPageUrl;

  const baseUrlRow = document.getElementById("llm-provider-base-url-row");
  const needsBaseUrl = PROVIDERS_NEEDING_BASE_URL.has(provider);
  baseUrlRow.style.display = needsBaseUrl ? "" : "none";
  if (needsBaseUrl) {
    document.getElementById("llm-provider-base-url-label").textContent =
      providerLabel(provider);
    document.getElementById("llm-provider-base-url-preview").textContent =
      llmCatalog.provider_base_urls[provider] || "—";
  }
}

function relativeTimeRu(iso) {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "только что";
  if (mins < 60) return `${mins} мин назад`;
  return `${Math.round(mins / 60)} ч назад`;
}

function formatElapsed(iso) {
  const mins = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000));
  if (mins < 1) return "только что запущен";
  if (mins < 60) return `${mins} мин`;
  const hours = Math.floor(mins / 60);
  const rest = mins % 60;
  return rest ? `${hours} ч ${rest} мин` : `${hours} ч`;
}

function applyLLMProviderStatus(statusMap) {
  // Свежесть статуса — 15 минут: дальше "сейчас отвечает"/ошибка
  // считаются устаревшими и подсветка гаснет сама, без отдельного
  // запроса на "провайдер снова онлайн".
  const FRESH_MS = 15 * 60 * 1000;
  let liveProvider = null;
  let liveAt = 0;
  for (const [provider, info] of Object.entries(statusMap || {})) {
    const okAt = info.last_ok_at ? new Date(info.last_ok_at).getTime() : 0;
    if (okAt > liveAt) {
      liveAt = okAt;
      liveProvider = provider;
    }
  }
  const liveIsFresh = liveAt && Date.now() - liveAt < FRESH_MS;

  document
    .querySelectorAll("#provider-grid .provider-card")
    .forEach((card) => {
      const provider = card.dataset.provider;
      const info = (statusMap || {})[provider];
      card.classList.toggle(
        "llm-live",
        Boolean(liveIsFresh && provider === liveProvider)
      );

      const okAt = info?.last_ok_at
        ? new Date(info.last_ok_at).getTime()
        : 0;
      const errAt = info?.last_error_at
        ? new Date(info.last_error_at).getTime()
        : 0;
      const showError = errAt > okAt && Date.now() - errAt < FRESH_MS;

      const history = info?.history || [];
      let spark = card.querySelector(".provider-sparkline");
      if (history.length) {
        if (!spark) {
          spark = document.createElement("div");
          spark.className = "provider-sparkline";
          card.appendChild(spark);
        }
        spark.innerHTML = history
          .slice(-10)
          .map(
            (h) =>
              `<span class="spark-dot ${h.ok ? "ok" : "err"}" title="${fmtTime(h.at)}"></span>`
          )
          .join("");
      } else if (spark) {
        spark.remove();
      }

      let note = card.querySelector(".provider-status-note");
      if (showError) {
        if (!note) {
          note = document.createElement("span");
          note.className = "provider-status-note";
          card.appendChild(note);
        }
        note.classList.toggle(
          "rate-limit",
          info.last_error_kind === "rate_limit"
        );
        note.textContent =
          (info.last_error_kind === "rate_limit"
            ? "лимит исчерпан "
            : "недоступен ") + relativeTimeRu(info.last_error_at);
      } else if (note) {
        note.remove();
      }
    });
}

function renderTotalBudget(status, totalLimit) {
  const el = document.getElementById("total-budget-info");
  if (!totalLimit) {
    el.innerHTML =
      '<p class="muted small">Общий лимит не задан — каждая площадка считает свой дневной лимит независимо.</p>';
    return;
  }
  const appliedToday = status.total_applied_today || 0;
  const sumPerPlatform = (status.sources || []).reduce(
    (sum, s) => sum + (s.daily_limit || 0),
    0
  );
  const usedRatio = Math.min(1, appliedToday / totalLimit);
  const usedClass =
    usedRatio >= 1 ? "full" : usedRatio >= 0.7 ? "warn" : "";
  const overBudget = sumPerPlatform > totalLimit;
  const distributionLine = `Распределено по площадкам (сумма лимитов в таблице ниже): ${sumPerPlatform} / ${totalLimit}`;
  el.innerHTML = `
    <p class="muted small">Сегодня отправлено: ${appliedToday} / ${totalLimit} (общий лимит)</p>
    <div class="limit-bar"><div class="limit-bar-fill ${usedClass}" style="width:${Math.round(usedRatio * 100)}%"></div></div>
    ${
      overBudget
        ? `<div class="risk-banner" style="margin-top:10px;margin-bottom:0">⚠️ ${distributionLine} — превышает общий лимит, снизьте лимиты отдельных площадок.</div>`
        : `<p class="muted small" style="margin-top:8px">${distributionLine}</p>`
    }
  `;
}

function skeletonStats() {
  return Array.from(
    { length: 3 },
    () => `<div class="stat-card"><div class="skeleton" style="height:26px;width:40px;margin-bottom:6px"></div><div class="skeleton" style="height:11px;width:70px"></div></div>`
  ).join("");
}

function skeletonSourceGrid(count = 8) {
  return Array.from(
    { length: count },
    () => `<div class="source-card skeleton-card"><div class="skeleton" style="height:100%"></div></div>`
  ).join("");
}

function skeletonRows(rows, cols) {
  const cells = Array.from(
    { length: cols },
    () => `<td><div class="skeleton"></div></td>`
  ).join("");
  return Array.from(
    { length: rows },
    () => `<tr class="skeleton-row">${cells}</tr>`
  ).join("");
}

const CONTACT_KIND = {
  telegram: { icon: "✈️", label: "Telegram" },
  email: { icon: "✉️", label: "Email" },
  linkedin: { icon: "in", label: "LinkedIn" },
};
// Один язык статусов для базы, рассылки и входящих: слово + цвет.
const CONTACT_STATUS = {
  new: "не писали",
  draft: "черновик",
  written: "написали",
  replied: "ответили",
  bounced: "возврат",
  skip: "не писать",
};
const SOURCE_KIND = {
  file: "📄 мой файл",
  telegram: "✈️ Telegram",
  sites: "🏢 сайты компаний",
  dossier: "🔎 найден кнопкой",
  vacancy: "💼 вакансия",
};
let lastContacts = [];
let focusContactKey = null;
const baseState = { status: "", sort: "last", dir: -1, selected: new Set(), open: new Set(), page: 0, size: 50 };
let baseFiltered = [];
let baseSeen = new Map(); // ключ → updated_at с прошлого показа — что подсветить // ключи всех компаний под текущим фильтром — для «Выбрать все по фильтру»

function contactHref(c) {
  if (c.kind === "telegram") return `https://t.me/${encodeURIComponent(c.value)}`;
  if (c.kind === "email") return `mailto:${c.value}`;
  return c.value;
}

// «сегодня 14:30», «вчера», «25 сент.» — вместо 24.09.2026, 23:56:02.
function fmtDay(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 864e5);
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (days === 0) return `сегодня ${time}`;
  if (days === 1) return `вчера ${time}`;
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: days > 300 ? "numeric" : undefined });
}

function statusPill(status) {
  return `<span class="status-pill st-${status}">${CONTACT_STATUS[status] || status}</span>`;
}

function renderContactsList() {
  const el = document.getElementById("contacts-list");
  const source = document.getElementById("contacts-filter-source").value;
  const contactFilter = document.getElementById("contacts-filter-contact").value;
  const query = document.getElementById("contacts-filter-query").value.trim().toLowerCase();
  fillFileOptions();

  // Счётчики — они же фильтры по статусу.
  const counts = {};
  lastContacts.forEach((c) => (counts[c.status] = (counts[c.status] || 0) + 1));
  const chips = [["", "Все", lastContacts.length], ...Object.entries(CONTACT_STATUS).map(([k, t]) => [k, t, counts[k] || 0])]
    .filter(([k, , n]) => !k || n);
  const chipBox = document.getElementById("base-chips");
  chipBox.innerHTML = chips
    .map(([k, label, n]) => `<button type="button" class="chip${k === baseState.status ? " active" : ""}" data-status="${k}">${label} <b>${n}</b></button>`)
    .join("");
  chipBox.querySelectorAll("[data-status]").forEach((b) =>
    b.addEventListener("click", () => {
      baseState.status = b.dataset.status;
      baseState.page = 0;
      renderContactsList();
    })
  );

  if (!lastContacts.length) {
    el.innerHTML = `<tr><td colspan="7">${emptyStateHtml("База пока пуста. Загрузите свой список компаний кнопкой «📥 Загрузить файл» — или включите Telegram-парсер: он сам добавляет HR из постов.")}</td></tr>`;
    renderBaseBulk();
    return;
  }
  const filtered = lastContacts.filter((card) => {
    if (baseState.status && card.status !== baseState.status) return false;
    if (source.startsWith("file:") ? !card.files.includes(source.slice(5)) : source && !card.source_kinds.includes(source)) return false;
    if (contactFilter === "email" && !card.contacts.some((c) => c.kind === "email")) return false;
    if (contactFilter === "none" && card.contacts.length) return false;
    if (!query) return true;
    return [card.company, card.hr, card.website, ...card.contacts.map((c) => c.value), ...card.vacancies.map((v) => v.title)]
      .filter(Boolean)
      .some((v) => v.toLowerCase().includes(query));
  });
  const key = {
    company: (c) => (c.company || c.primary?.value || "").toLowerCase(),
    status: (c) => Object.keys(CONTACT_STATUS).indexOf(c.status),
    added: (c) => c.created_at || "",
    last: (c) => c.last?.at || "",
  }[baseState.sort];
  filtered.sort((a, b) => (key(a) > key(b) ? 1 : key(a) < key(b) ? -1 : 0) * baseState.dir);
  document.querySelectorAll("#base-table th[data-sort]").forEach((th) => {
    th.classList.toggle("sorted", th.dataset.sort === baseState.sort);
    th.dataset.dir = th.dataset.sort === baseState.sort ? (baseState.dir > 0 ? "↑" : "↓") : "";
  });
  baseFiltered = filtered.map((c) => c.key);
  const pages = Math.max(1, Math.ceil(filtered.length / baseState.size));
  const focusIndex = focusContactKey ? baseFiltered.indexOf(focusContactKey) : -1;
  if (focusIndex >= 0) baseState.page = Math.floor(focusIndex / baseState.size);
  baseState.page = Math.min(baseState.page, pages - 1);
  renderBasePager(filtered.length, pages);
  if (!filtered.length) {
    el.innerHTML = `<tr><td colspan="7">${emptyStateHtml("Ничего не найдено.")}</td></tr>`;
    renderBaseBulk();
    return;
  }
  const rows = filtered.slice(baseState.page * baseState.size, (baseState.page + 1) * baseState.size);
  // Новые и обновлённые с прошлого показа компании — мягкая подсветка.
  const fresh = new Set();
  if (baseSeen.size) {
    lastContacts.forEach((c) => {
      if (baseSeen.get(c.key) !== c.updated_at) fresh.add(c.key);
    });
  }
  baseSeen = new Map(lastContacts.map((c) => [c.key, c.updated_at]));
  el.innerHTML =
    rows
      .map((card) => {
        const p = card.primary;
        const more = card.contacts.length - 1;
        const open = baseState.open.has(card.key) || card.key === focusContactKey;
        return `
      <tr class="base-row${fresh.has(card.key) ? " row-fresh" : ""}${open ? " is-open" : ""}${card.key === focusContactKey ? " is-focused" : ""}" data-card-key="${escapeHtml(card.key)}" tabindex="0" aria-expanded="${open}">
        <td class="base-check"><input type="checkbox" data-select="${escapeHtml(card.key)}" aria-label="Выбрать" ${baseState.selected.has(card.key) ? "checked" : ""} /></td>
        <td><strong>${escapeHtml(card.company || p?.value || "Без названия")}</strong>
          ${card.website ? `<div class="muted small">${escapeHtml(card.website.replace(/^https?:\/\//, "").replace(/\/$/, ""))}</div>` : ""}</td>
        <td>${p ? `${CONTACT_KIND[p.kind]?.icon || "•"} ${escapeHtml(p.kind === "telegram" ? "@" + p.value : p.value)}` : "—"}${more > 0 ? ` <span class="muted small">+${more}</span>` : ""}
          ${card.hr ? `<div class="muted small">${escapeHtml(card.hr)}</div>` : ""}</td>
        <td class="small col-source">${card.source_kinds.map((k) => SOURCE_KIND[k]).join("<br>")}</td>
        <td>${statusPill(card.status)}</td>
        <td class="small col-last">${card.last ? `${escapeHtml(truncate(card.last.text, 60))}<div class="muted">${fmtDay(card.last.at)}</div>` : "—"}</td>
        <td class="base-toggle" aria-hidden="true">${open ? "▾" : "▸"}</td>
      </tr>
      ${open ? `<tr class="base-detail"><td colspan="7">${baseDetailHtml(card)}</td></tr>` : ""}`;
      })
      .join("");
  if (focusContactKey) {
    el.querySelector(".base-row.is-focused")?.scrollIntoView({ block: "center", behavior: REDUCE_MOTION ? "auto" : "smooth" });
    baseState.open.add(focusContactKey);
    focusContactKey = null;
  }
  const toggleRow = (row) => {
    const k = row.dataset.cardKey;
    baseState.open.has(k) ? baseState.open.delete(k) : baseState.open.add(k);
    renderContactsList();
    el.querySelector(`.base-row[data-card-key="${CSS.escape(k)}"]`)?.focus();
  };
  el.querySelectorAll(".base-row").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (e.target.closest("input, a, button")) return;
      toggleRow(row);
    });
    // С клавиатуры: Tab до строки, Enter/пробел — раскрыть.
    row.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && e.target === row) {
        e.preventDefault();
        toggleRow(row);
      }
    });
  });
  el.querySelectorAll("[data-select]").forEach((box) =>
    box.addEventListener("change", () => {
      box.checked ? baseState.selected.add(box.dataset.select) : baseState.selected.delete(box.dataset.select);
      renderBaseBulk();
    })
  );
  const all = document.getElementById("base-select-all");
  all.checked = rows.length > 0 && rows.every((c) => baseState.selected.has(c.key));
  all.onchange = () => {
    rows.forEach((c) => (all.checked ? baseState.selected.add(c.key) : baseState.selected.delete(c.key)));
    renderContactsList();
  };
  baseState.pageKeys = rows.map((c) => c.key);
  bindBaseDetail(el);
  renderBaseBulk();
}

function baseDetailHtml(card) {
  return `
    <div class="base-detail-grid">
      <div>
        <h4>Контакты</h4>
        ${card.contacts
          .map(
            (c) => `<div class="contact-row">
              <span>${CONTACT_KIND[c.kind]?.icon || "•"} <a href="${escapeHtml(contactHref(c))}" target="_blank" rel="noopener">${escapeHtml(c.kind === "telegram" ? "@" + c.value : c.value)}</a>
                ${c.name ? `<span class="muted small">${escapeHtml(c.name)}${c.position ? ", " + escapeHtml(c.position) : ""}</span>` : ""}
                <div class="muted small">${escapeHtml(c.source || "")}</div></span>
              <span>${statusPill(c.status)}
                ${(c.kind === "telegram" || c.kind === "email") && c.status === "new" && card.status !== "skip"
                  ? `<button type="button" class="btn btn-secondary btn-small" data-contact-draft data-key="${escapeHtml(card.key)}" data-kind="${c.kind}" data-value="${escapeHtml(c.value)}">✍️ Написать</button>`
                  : ""}</span>
            </div>`
          )
          .join("")}
        ${card.emphasis ? `<p class="small"><b>На что сделать упор:</b> ${escapeHtml(card.emphasis)}</p>` : ""}
        ${card.vacancies.length ? `<h4>Вакансии</h4>${card.vacancies.slice(-3).map((v) => `<div class="small">${sourceIconHtml(v.source)}<a href="${escapeHtml(v.link)}" target="_blank" rel="noopener">${escapeHtml(v.title || v.link)}</a></div>`).join("")}` : ""}
        ${card.company ? `<div class="step-actions">${card.website ? "" : `<input type="text" class="dossier-site" placeholder="сайт компании" aria-label="Сайт компании" />`}
          <button type="button" class="btn btn-ghost btn-small" data-dossier data-key="${escapeHtml(card.key)}" title="Найти контакты на сайте компании и через Hunter">🔎 Найти ещё контакты</button></div>` : ""}
      </div>
      <div>
        <h4>История</h4>
        <ol class="base-history">${card.history
          .slice()
          .reverse()
          .map((h) => `<li><span class="muted small">${fmtDay(h.at)}</span> ${escapeHtml(h.text)}</li>`)
          .join("")}</ol>
      </div>
    </div>`;
}

function bindBaseDetail(el) {
  el.querySelectorAll("[data-dossier]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const site = btn.parentElement.querySelector(".dossier-site");
      btn.disabled = true;
      btn.textContent = "Ищу…";
      try {
        const res = await api("/api/contacts/dossier", {
          method: "POST",
          body: JSON.stringify({ key: btn.dataset.key, website: site ? site.value.trim() : "" }),
        });
        showToast(res.added ? `Найдено новых контактов: ${res.added}` : "Новых контактов на сайте нет", res.added ? "success" : "info");
        render.contacts();
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error", 6000);
        btn.disabled = false;
        btn.textContent = "🔎 Найти ещё контакты";
      }
    });
  });
  el.querySelectorAll("[data-contact-draft]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "Пишу…";
      try {
        await api("/api/contacts/draft", {
          method: "POST",
          body: JSON.stringify({ key: btn.dataset.key, kind: btn.dataset.kind, value: btn.dataset.value }),
        });
        showToast("Черновик готов — проверьте и отправьте в «Общение → Входящие».", "success", 6000);
        render.contacts();
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error");
        btn.disabled = false;
      }
    });
  });
}

// Панель действий над выбранными — появляется, только когда что-то отмечено.
// Страницы: «1–50 из 2 840», стрелки и размер страницы.
function renderBasePager(total, pages) {
  const pager = document.getElementById("base-pager");
  if (total <= 50) {
    pager.innerHTML = total ? `<span class="muted small">${total} ${plural(total, "компания", "компании", "компаний")}</span>` : "";
    return;
  }
  const from = baseState.page * baseState.size + 1;
  const to = Math.min(total, from + baseState.size - 1);
  pager.innerHTML = `
    <button type="button" class="btn btn-ghost btn-small" data-page="-1" ${baseState.page ? "" : "disabled"} aria-label="Предыдущая страница">‹</button>
    <span><b>${from}–${to}</b> из ${total.toLocaleString("ru-RU")}</span>
    <button type="button" class="btn btn-ghost btn-small" data-page="1" ${baseState.page < pages - 1 ? "" : "disabled"} aria-label="Следующая страница">›</button>
    <label class="muted small">по <select id="base-page-size" aria-label="Строк на странице">
      ${[50, 100, 200].map((n) => `<option value="${n}" ${n === baseState.size ? "selected" : ""}>${n}</option>`).join("")}
    </select></label>`;
  pager.querySelectorAll("[data-page]").forEach((b) =>
    b.addEventListener("click", () => {
      baseState.page += Number(b.dataset.page);
      renderContactsList();
      document.getElementById("base-table").scrollIntoView({ block: "start", behavior: REDUCE_MOTION ? "auto" : "smooth" });
    })
  );
  document.getElementById("base-page-size").addEventListener("change", (e) => {
    baseState.size = Number(e.target.value);
    baseState.page = 0;
    renderContactsList();
  });
}

// Каждый загруженный файл — отдельный пункт в фильтре «Источник».
function fillFileOptions() {
  const select = document.getElementById("contacts-filter-source");
  const files = [...new Set(lastContacts.flatMap((c) => c.files || []))].sort();
  const have = [...select.options].filter((o) => o.value.startsWith("file:")).map((o) => o.value.slice(5));
  if (have.join("\n") === files.join("\n")) return;
  const value = select.value;
  select.querySelectorAll('option[value^="file:"]').forEach((o) => o.remove());
  const anchor = select.querySelector('option[value="file"]');
  files.reverse().forEach((f) => anchor.after(new Option(`↳ 📄 ${f}`, `file:${f}`)));
  select.value = [...select.options].some((o) => o.value === value) ? value : "";
}

function renderBaseBulk() {
  const bar = document.getElementById("base-bulk");
  const keys = [...baseState.selected].filter((k) => lastContacts.some((c) => c.key === k));
  baseState.selected = new Set(keys);
  if (!keys.length) {
    bar.hidden = true;
    return;
  }
  bar.hidden = false;
  const byKey = new Map(lastContacts.map((c) => [c.key, c]));
  const skipped = keys.every((k) => byKey.get(k)?.status === "skip");
  // Как в Gmail: выбрана вся страница — предложить все по фильтру.
  const pageAll = (baseState.pageKeys || []).length && baseState.pageKeys.every((k) => baseState.selected.has(k));
  const moreByFilter = pageAll && baseFiltered.length > keys.length;
  bar.innerHTML = `
    <span>Выбрано: <b>${keys.length.toLocaleString("ru-RU")}</b>${
      moreByFilter ? ` · <button type="button" class="link-btn" data-bulk="all">Выбрать все ${baseFiltered.length.toLocaleString("ru-RU")} по фильтру</button>` : ""
    }</span>
    <button type="button" class="btn btn-primary btn-small" data-bulk="write">✉️ Написать выбранным</button>
    <button type="button" class="btn btn-secondary btn-small" data-bulk="${skipped ? "unskip" : "skip"}">${skipped ? "Снова можно писать" : "🚫 Не писать"}</button>
    <button type="button" class="btn btn-ghost btn-small" data-bulk="delete">🗑 Удалить</button>
    <button type="button" class="btn btn-ghost btn-small" data-bulk="clear">Снять выбор</button>`;
  bar.querySelectorAll("[data-bulk]").forEach((b) =>
    b.addEventListener("click", async () => {
      const action = b.dataset.bulk;
      try {
        if (action === "clear" || action === "all") {
          // Только выбор — без запроса к серверу.
          if (action === "clear") baseState.selected.clear();
          else baseFiltered.forEach((k) => baseState.selected.add(k));
          renderContactsList();
          return;
        } else if (action === "write") {
          await api("/api/campaigns", { method: "POST", body: JSON.stringify({ keys }) });
          baseState.selected.clear();
          showToast("Рассылка создана — подготовьте письма", "success");
          switchTab("outreach");
          return;
        } else if (action === "delete") {
          const { removed } = await api("/api/contacts/bulk", { method: "POST", body: JSON.stringify({ keys, action }) });
          baseState.selected.clear();
          showUndo(`Удалено компаний: ${removed.length}`, async () => {
            await api("/api/contacts/restore", { method: "POST", body: JSON.stringify({ cards: removed }) });
            render.contacts();
          });
        } else {
          await api("/api/contacts/bulk", { method: "POST", body: JSON.stringify({ keys, action }) });
        }
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error");
      }
      render.contacts();
    })
  );
}

// Удаление без «Вы уверены?»: сразу, но 10 секунд можно «Отменить».
function showUndo(text, undo) {
  document.getElementById("undo-bar")?.remove();
  const bar = document.createElement("div");
  bar.id = "undo-bar";
  bar.className = "undo-bar";
  bar.innerHTML = `<span>${escapeHtml(text)}</span><button type="button" class="btn btn-secondary btn-small">Отменить</button>`;
  document.body.appendChild(bar);
  const timer = setTimeout(() => bar.remove(), 10000);
  bar.querySelector("button").addEventListener("click", async () => {
    clearTimeout(timer);
    bar.remove();
    await undo();
  });
}

// «Что сделать сейчас» — первое, что видно на Главной. Заодно раздаёт
// счётчики в строку подразделов «Общения».
let lastTodoBadges = {};

// Главная цифра — ответы и интервью за 7 дней, откуда они пришли.
async function renderResults() {
  const el = document.getElementById("results-panel");
  let r;
  try {
    r = await api("/api/results");
  } catch (e) {
    return;
  }
  const w = r.week;
  const delta = w.replies - r.prev.replies;
  const deltaHtml = delta
    ? `<span class="${delta > 0 ? "ok-text" : "err-text"}">${delta > 0 ? "↑" : "↓"} ${Math.abs(delta)} к прошлой неделе</span>`
    : `<span class="muted">как на прошлой неделе</span>`;
  const label = (s) => (s === "email_campaign" ? "✉️ Рассылка по почте" : `${sourceIconHtml(s)}${escapeHtml(sourceLabel(s))}`);
  const rate = (row) => (row.applied ? `${Math.round((100 * row.replies) / row.applied)}%` : "—");
  el.innerHTML = `
    <div class="results-head">
      <h3>Результат за 7 дней</h3>
      <span class="muted small">${deltaHtml}</span>
    </div>
    <div class="results-numbers">
      <div><span class="results-big">${w.replies}</span><span class="muted">ответов</span></div>
      <div><span class="results-big accent">${w.interviews}</span><span class="muted">интервью</span></div>
      <div><span class="results-big muted">${w.applied}</span><span class="muted">отправлено</span></div>
    </div>
    ${
      r.by_source.length
        ? `<div class="table-wrap"><table class="results-table">
            <thead><tr><th>Откуда</th><th>Отправлено</th><th>Ответы</th><th>Интервью</th><th title="Доля ответов от отправленного">Отклик</th></tr></thead>
            <tbody>${r.by_source
              .map((row) => `<tr><td>${label(row.source)}</td><td>${row.applied}</td><td><b>${row.replies}</b></td><td>${row.interviews}</td><td>${rate(row)}</td></tr>`)
              .join("")}</tbody></table></div>
          <p class="muted small">Источники с низким откликом можно выключить — бот потратит лимиты на те, что приносят ответы.</p>`
        : `<p class="muted small">За неделю пока ничего не отправлено — запустите бота или рассылку.</p>`
    }`;
}

// 1 письмо, 2 письма, 5 писем.
function plural(n, one, few, many) {
  const m = Math.abs(n) % 100;
  if (m > 10 && m < 20) return many;
  return m % 10 === 1 ? one : m % 10 >= 2 && m % 10 <= 4 ? few : many;
}

// «Свои каналы» на Главной: Telegram-парсер и рассылка по почте —
// не площадки с откликами, а свои способы выйти на работодателя.
let lastOwnChannels = "";
async function renderOwnChannels() {
  let w, c, d;
  try {
    [w, c, d] = await Promise.all([api("/api/settings/telegram-watch"), api("/api/campaigns"), api("/api/direct/summary")]);
  } catch (e) {
    return;
  }
  const snapshot = JSON.stringify([w, c, d]);
  if (snapshot === lastOwnChannels) return;
  lastOwnChannels = snapshot;
  const el = document.getElementById("own-channels");
  const tgState = w.running ? "ok" : w.enabled ? "never_run" : "error";
  const tgText = w.running
    ? "работает — посты приходят за секунды"
    : w.enabled
      ? w.daemon_running ? "подключается…" : "включён — заработает после «▶ Запустить»"
      : "выключен";
  const weekAgo = Date.now() - 7 * 864e5;
  const items = c.campaigns.flatMap((x) => x.items);
  const sentWeek = items.filter((i) => i.sent_at && Date.parse(i.sent_at) >= weekAgo).length;
  const replied = items.filter((i) => i.status === "replied").length;
  const drafts = items.filter((i) => i.status === "draft").length;
  const followUps = items.filter((i) => i.follow_up_text).length;
  const ms = c.mail_status;
  const mailText = !c.email_connected
    ? "Gmail не подключён"
    : ms
      ? ms.text
      : c.campaigns.some((x) => x.progress)
        ? "пишу письма…"
        : drafts
          ? `${drafts} ${plural(drafts, "письмо ждёт", "письма ждут", "писем ждут")} — нажмите «Начать отправку»`
          : "готово к рассылке";
  const mailDot = !c.email_connected || ms?.state === "stopped" ? "error" : ms?.state === "active" ? "ok running" : ms ? "never_run" : "ok";
  el.innerHTML = `
    <div class="source-card own-card">
      <h3>
        <input type="checkbox" class="switch" id="own-tg-toggle" title="Включить или выключить парсер" ${w.enabled ? "checked" : ""} />
        <span class="dot ${tgState}"></span> ${sourceIconHtml("telegram")}Telegram-парсер
      </h3>
      <div class="row"><span>Состояние</span><span>${tgText}</span></div>
      <div class="row"><span>Каналов</span><span>${w.channels}</span></div>
      <div class="row"><span>Вакансий найдено с запуска</span><span>${w.matched}</span></div>
      <div class="row"><span>Контактов HR в базе</span><span>${w.contacts_collected}</span></div>
      <div class="row"><span>Ответы HR в диалогах</span><span>${w.running ? "ловит сразу" : "проверяет каждые 30 мин"}</span></div>
      <div class="own-card-actions">
        <button type="button" class="btn btn-secondary btn-small" data-own-go="telegram">Открыть</button>
        <button type="button" class="btn btn-ghost btn-small" data-own-settings="settings-tg-quick">Настроить</button>
      </div>
    </div>
    <div class="source-card own-card">
      <h3><span class="dot ${mailDot}"></span> ✉️ Отправка почты</h3>
      <div class="row${ms?.state === "stopped" ? " row-alert" : ""}"><span>Сейчас</span><span>${escapeHtml(mailText)}</span></div>
      ${ms ? `<div class="row"><span>Сегодня</span><span><span data-count="mail-today">${ms.sent_today}</span> из ${ms.limit}</span></div>` : ""}
      ${ms?.last ? `<div class="row"><span>Последнее письмо</span><span>${fmtDay(ms.last.at)} → ${escapeHtml(ms.last.company)}</span></div>` : ""}
      <div class="row"><span>Можно написать</span><span>${c.available} ${plural(c.available, "компании", "компаниям", "компаниям")}</span></div>
      <div class="row"><span>Отправлено за неделю</span><span data-count="mail-week">${sentWeek}</span></div>
      <div class="row"><span>Ответили</span><span>${replied}${followUps ? ` · ⏳ напоминаний готово: ${followUps}` : ""}</span></div>
      <div class="row"><span>Ответы и возвраты</span><span>${c.email_connected ? "проверяет каждый час" : "—"}</span></div>
      <div class="own-card-actions">
        <button type="button" class="btn btn-secondary btn-small" data-own-go="outreach">Открыть рассылку</button>
        ${!c.email_connected ? `<button type="button" class="btn btn-ghost btn-small" data-own-settings="settings-outreach">Подключить Gmail</button>`
          : ms?.state === "stopped"
            ? ms.goto.startsWith("settings-")
              ? `<button type="button" class="btn btn-ghost btn-small" data-own-settings="${ms.goto}">Что делать</button>`
              : `<button type="button" class="btn btn-ghost btn-small" data-own-go="${ms.goto}">Проверить адреса</button>`
            : ""}
      </div>
    </div>
    <div class="source-card own-card">
      <h3>
        <input type="checkbox" class="switch" id="own-direct-toggle" title="Включить или выключить поиск на сайтах компаний" ${d.enabled ? "checked" : ""} />
        <span class="dot ${d.enabled ? "ok" : "error"}"></span> 🏢 Сайты компаний
      </h3>
      <div class="row"><span>Состояние</span><span>${d.enabled ? "собирает компании в Базу" : "выключено"}</span></div>
      <div class="row"><span>Где ищет</span><span>${[d.companies && `${d.companies} ${plural(d.companies, "компанию", "компании", "компаний")}`, d.wwr && "We Work Remotely", d.hn && "HN"].filter(Boolean).join(" + ") || "ничего — добавьте компании"}</span></div>
      <div class="row"><span>Добавлено в Базу за неделю</span><span data-count="sites-week">${d.added_week}</span></div>
      <div class="row"><span>С email — готовы к рассылке</span><span data-count="sites-ready">${d.ready}</span></div>
      <div class="own-card-actions">
        <button type="button" class="btn btn-secondary btn-small" data-own-go="contacts" data-base-source="sites">Открыть Базу</button>
        ${d.ready ? `<button type="button" class="btn btn-secondary btn-small" data-own-go="outreach">Разослать →</button>` : ""}
        <button type="button" class="btn btn-ghost btn-small" data-own-settings="settings-direct">Настроить</button>
      </div>
    </div>`;
  animateCounts(el);
  el.querySelectorAll("[data-own-go]").forEach((b) =>
    b.addEventListener("click", () => {
      if (b.dataset.baseSource) {
        document.getElementById("contacts-filter-source").value = b.dataset.baseSource;
        baseState.page = 0;
      }
      switchTab(b.dataset.ownGo);
    })
  );
  el.querySelectorAll("[data-own-settings]").forEach((b) =>
    b.addEventListener("click", () => {
      switchTab("settings");
      switchSettingsTab(b.dataset.ownSettings);
      if (b.dataset.ownSettings === "settings-tg-quick") loadTelegramWatch();
    })
  );
  document.getElementById("own-direct-toggle").addEventListener("change", async (e) => {
    e.target.disabled = true;
    try {
      await api("/api/settings", { method: "POST", body: JSON.stringify({ source: "direct", schedule_enabled: e.target.checked }) });
      showToast(e.target.checked ? "Поиск на сайтах компаний включён" : "Поиск на сайтах компаний выключен", "success");
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
    lastOwnChannels = "";
    renderOwnChannels();
  });
  document.getElementById("own-tg-toggle").addEventListener("change", async (e) => {
    e.target.disabled = true;
    try {
      // Один переключатель на весь Telegram: парсер + поиск по расписанию.
      await Promise.all([
        api("/api/settings/telegram-watch", { method: "POST", body: JSON.stringify({ enabled: e.target.checked }) }),
        api("/api/settings", { method: "POST", body: JSON.stringify({ source: "telegram", schedule_enabled: e.target.checked }) }),
      ]);
      showToast(e.target.checked ? "Telegram-парсер включён" : "Telegram-парсер выключен", "success");
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
    lastOwnChannels = "";
    renderOwnChannels();
  });
}

async function renderTodo() {
  const el = document.getElementById("todo-panel");
  let todo;
  try {
    todo = await api("/api/todo");
  } catch (e) {
    return;
  }
  lastTodoBadges = todo.badges || {};
  applySubnavBadges();
  const setup = todo.setup || [];
  const missing = setup.filter((c) => !c.ok);
  // Мастер настройки — пока что-то не подключено. Шаги идут по порядку,
  // «Следующий шаг» — одна главная кнопка.
  const next = missing[0];
  const done = setup.length - missing.length;
  const setupHtml = next
    ? `<div class="setup">
        <div class="setup-head">
          <h3 style="margin:0">Настройка: ${done} из ${setup.length}</h3>
          <div class="progress setup-progress"><div style="width:${Math.round((100 * done) / setup.length)}%"></div></div>
        </div>
        <div class="setup-next">
          <div><span class="muted small">Следующий шаг</span><div><b>${escapeHtml(next.label)}</b> — ${escapeHtml(next.hint)}</div></div>
          ${next.goto === "start-bot"
            ? `<span class="muted small">Кнопка «▶ Запустить» — в меню слева</span>`
            : next.goto ? `<button type="button" class="btn btn-primary" data-setup-goto="${escapeHtml(next.goto)}">Сделать →</button>` : ""}
        </div>
        <ol class="setup-steps">${setup
          .map(
            (c, i) => `<li class="${c.ok ? "is-done" : c === next ? "is-next" : ""}">
              <button type="button" class="setup-step" data-setup-goto="${escapeHtml(c.goto)}" ${c.goto && !c.ok && c.goto !== "start-bot" ? "" : "disabled"}>
                <span class="setup-step-mark">${c.ok ? "✓" : i + 1}</span>${escapeHtml(c.label)}
              </button></li>`
          )
          .join("")}</ol>
      </div>`
    : "";
  const bindSetup = () =>
    el.querySelectorAll("[data-setup-goto]").forEach((btn) =>
      btn.addEventListener("click", () => {
        const goto = btn.dataset.setupGoto;
        if (goto === "start-bot") {
          document.getElementById("daemon-toggle").click();
        } else if (goto.startsWith("settings-")) {
          switchTab("settings");
          switchSettingsTab(goto);
          if (goto === "settings-tg-quick") loadTelegramWatch();
        } else if (goto) {
          switchTab(goto);
        }
      })
    );
  if (!todo.items.length) {
    el.innerHTML = setupHtml + `<div class="todo-calm">✓ Сейчас ничего не ждёт вашего решения${missing.length ? "" : " — бот работает сам"}.</div>`;
    bindSetup();
    return;
  }
  el.innerHTML = `${setupHtml}
    <h3 style="margin:0 0 10px">Что сделать сейчас</h3>
    ${todo.items
      .map(
        (i) => `
      <button type="button" class="todo-item" data-todo-view="${i.view}">
        <span class="todo-count">${i.count}</span>
        <span class="todo-text">${escapeHtml(i.text)}</span>
        <span class="todo-go" aria-hidden="true">→</span>
      </button>`
      )
      .join("")}`;
  el.querySelectorAll("[data-todo-view]").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.todoView));
  });  bindSetup();
}

function applySubnavBadges() {
  document.querySelectorAll("[data-subbadge]").forEach((badge) => {
    const n = lastTodoBadges[badge.dataset.subbadge];
    badge.textContent = n ? String(n) : "";
  });
}

// Каналы и правила Telegram — в Настройках → Telegram-парсер. Пока поля
// не заполнены с сервера, автосохранение этого блока выключено: иначе
// пустое поле могло бы затереть ваши каналы.
function fillTelegramRules(settings) {
  document.getElementById("tg-channels").value = (settings.channels || []).join("\n");
  document.getElementById("tg-max-age").value = settings.max_post_age_days ?? "";
  document.getElementById("tg-daily-limit").value = settings.daily_message_limit ?? "";
  document.getElementById("tg-auto-message").checked = !!settings.auto_message;
  document.getElementById("tg-hours-start").value = settings.active_hours_start ?? "";
  document.getElementById("tg-hours-end").value = settings.active_hours_end ?? "";
  document.getElementById("tg-rules-panel").dataset.loaded = "1";
}

async function loadTelegramWatch() {
  api("/api/settings/telegram").then(fillTelegramRules).catch(() => {});
  const w = await api("/api/settings/telegram-watch");
  // Строка статуса во вкладке «Общение → Telegram».
  const line = document.getElementById("tg-quick-line-status");
  if (line) {
    const state = w.running ? "on" : w.enabled ? "wait" : "off";
    line.className = `parser-state is-${state}`;
    line.textContent = {
      on: "● Парсер работает",
      wait: w.daemon_running ? "● Парсер подключается…" : "● Парсер включён — заработает после «▶ Запустить»",
      off: "● Парсер выключен — включите в «Настроить»",
    }[state];
    document.getElementById("parser-numbers").innerHTML = [
      [w.channels, w.running ? "каналов слушаю" : "каналов в списке"],
      [w.matched, "вакансий найдено с запуска"],
      [w.contacts_collected, "контактов HR в базе"],
    ]
      .map(([n, t]) => `<div><span class="results-big">${n}</span><span class="muted">${t}</span></div>`)
      .join("");
  }
  const pane = document.getElementById("settings-tg-quick");
  if (!pane) return w;
  document.getElementById("tgq-enabled").checked = w.enabled;
  const status = document.getElementById("tgq-status");
  status.className = `tgq-status ${w.running ? "is-on" : w.enabled ? "is-wait" : "is-off"}`;
  status.textContent = w.running
    ? `Работает — слушаю ${w.channels} каналов, подходящих постов с запуска: ${w.matched}`
    : w.enabled
      ? w.daemon_running
        ? "Подключаюсь к Telegram…"
        : "Включено — заработает, когда нажмёте «Запустить» слева"
      : "Выключено";
  const keywords = document.getElementById("tgq-keywords");
  keywords.value = w.keywords.join("\n");
  initTagInput(keywords);
  document.getElementById("tgq-keywords-hint").textContent = w.keywords.length
    ? ""
    : `Пусто — ищу по словам из ваших должностей: ${w.default_keywords.join(", ") || "—"}`;
  const stop = document.getElementById("tgq-stop");
  stop.value = w.stop_words.join("\n");
  initTagInput(stop);
  const greeting = document.getElementById("tgq-greeting");
  greeting.value = w.greeting;
  updateGreetingPreview();
  renderTelegramResumes(w.resumes);
  document.getElementById("tgq-bot-state").innerHTML = w.bot_connected
    ? "✅ В ваш CrossJob-бот — с кнопками быстрого ответа."
    : `⚠️ Бот уведомлений не подключён — <a href="#" data-goto-settings="settings-notifications">подключить</a> (1 минута), иначе кнопок не будет.`;
  bindGotoSettings(document.getElementById("tgq-bot-state"));
  return w;
}

function updateGreetingPreview() {
  const text = document.getElementById("tgq-greeting").value || "";
  document.getElementById("tgq-greeting-preview").textContent = text
    .replaceAll("{role}", "Python-разработчик")
    .replaceAll("{link}", "https://t.me/канал/123");
}

// «Мои резюме» — одна таблица: какое резюме, где используется, файл, действие.
function renderTelegramResumes() {
  renderResumes();
}

async function renderResumes() {
  const el = document.getElementById("resume-table");
  if (!el) return;
  let r;
  try {
    r = await api("/api/resumes");
  } catch (e) {
    return;
  }
  const fileCell = (f, missing) =>
    f.exists
      ? `<span class="resume-file" title="${escapeHtml(f.name)}">📄 <span class="resume-name">${escapeHtml(f.name)}</span></span>
         <span class="muted small">${Math.max(1, Math.round(f.size / 1024))} КБ · ${fmtDay(f.updated_at)}</span>`
      : `<span class="${missing === "err" ? "err-text" : "muted"} small">${missing === "err" ? "не загружено" : "не загружено — берётся основное"}</span>`;
  const row = (title, where, file, action) => `
    <div class="resume-row" role="row">
      <div role="cell"><b>${title}</b></div>
      <div role="cell" class="muted small">${where}</div>
      <div role="cell" class="resume-file-cell">${file}</div>
      <div role="cell" class="resume-action">${action}</div>
    </div>`;
  el.innerHTML = `
    <div class="resume-row resume-head" role="row">
      <div role="columnheader">Резюме</div><div role="columnheader">Где используется</div><div role="columnheader">Файл</div><div role="columnheader"></div>
    </div>
    ${row("Основное", "hh, geekjob, GetMatch, Хабр Карьера, Telegram; письма на русском",
      fileCell(r.primary, "err"),
      `<button type="button" class="btn btn-${r.primary.exists ? "ghost" : "primary"} btn-small" data-upload="primary">${r.primary.exists ? "Заменить" : "Загрузить"}</button>`)}
    ${row("Для международных", "LinkedIn, Wellfound, Himalayas; письма на английском",
      fileCell(r.linkedin, "soft"),
      `<button type="button" class="btn btn-ghost btn-small" data-upload="linkedin">${r.linkedin.exists ? "Заменить" : "Загрузить"}</button>`)}
    ${r.extra
      .map((f) =>
        row("Дополнительное", "своя кнопка «+ 📎» под вакансией в Telegram; можно выбрать в рассылке",
          fileCell(f),
          `<button type="button" class="btn btn-ghost btn-small" data-delete-extra="${escapeHtml(f.name)}" aria-label="Удалить ${escapeHtml(f.name)}">Удалить</button>`)
      )
      .join("")}
    ${r.extra.length ? "" : `<div class="resume-row resume-empty"><div class="muted small">Дополнительных пока нет — например, резюме под другую роль. Кнопка «📎 Добавить дополнительное» выше.</div></div>`}`;
  el.querySelectorAll("[data-upload]").forEach((b) =>
    b.addEventListener("click", () => document.getElementById(`resume-upload-${b.dataset.upload}`).click())
  );
  el.querySelectorAll("[data-delete-extra]").forEach((b) =>
    b.addEventListener("click", async () => {
      await api(`/api/telegram/resumes/${encodeURIComponent(b.dataset.deleteExtra)}`, { method: "DELETE" });
      renderResumes();
    })
  );
}

async function uploadTelegramResumes(files) {
  const status = document.getElementById("tgq-resume-status");
  for (const file of files) {
    status.textContent = `Загружаю ${file.name}…`;
    const form = new FormData();
    form.append("file", file);
    const response = await fetch("/api/telegram/resumes", { method: "POST", body: form });
    if (!response.ok) {
      status.textContent = `${file.name}: ${(await response.json()).detail || "ошибка"}`;
      return;
    }
    renderTelegramResumes((await response.json()).resumes);
  }
  status.textContent = "✅ Сохранено";
}

async function saveTelegramWatch() {
  const status = document.getElementById("tgq-save-status");
  try {
    await api("/api/settings/telegram-watch", {
      method: "POST",
      body: JSON.stringify({
        enabled: document.getElementById("tgq-enabled").checked,
        keywords: tagItemsOf(document.getElementById("tgq-keywords")),
        stop_words: tagItemsOf(document.getElementById("tgq-stop")),
        greeting: document.getElementById("tgq-greeting").value,
      }),
    });
    status.textContent = "✅ Сохранено — применяется сразу.";
    loadTelegramWatch();
  } catch (err) {
    status.textContent = err.message;
  }
}

function bindGotoSettings(root) {
  root.querySelectorAll("[data-goto-settings]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      switchTab("settings");
      switchSettingsTab(el.dataset.gotoSettings);
      if (el.dataset.gotoSettings === "settings-tg-quick") loadTelegramWatch();
    });
  });
}

const CAMPAIGN_STATUS = {
  pending: "ждёт письма",
  draft: "письмо готово",
  sent: "отправлено",
  failed: "ошибка",
  bounced: "возврат",
  replied: "ответили",
  skipped: "пропущено",
  followed_up: "напомнили",
};
let campaignPoll = null;

async function importPreview(file) {
  const el = document.getElementById("import-preview");
  const fail = (msg) => (el.innerHTML = `<p class="import-error">${escapeHtml(msg || "Не удалось разобрать файл")}</p>`);
  el.innerHTML = `<p class="muted small">Загружаю ${escapeHtml(file.name)}…</p>`;
  const form = new FormData();
  form.append("file", file);
  let data;
  try {
    const response = await fetch("/api/import/preview", { method: "POST", body: form });
    data = await response.json();
    if (!response.ok) return fail(data.detail);
    // Большой файл разбирается в фоне — показываем, что происходит.
    while (data.state === "running") {
      const pct = data.total ? Math.round((100 * data.done) / data.total) : 0;
      el.innerHTML = `<div class="import-progress">
          <p class="small"><b>${escapeHtml(file.name)}</b>: ${escapeHtml(data.stage)}${data.total ? ` — часть ${data.done} из ${data.total}` : "…"}</p>
          <div class="progress"><div style="width:${data.total ? pct : 15}%"></div></div>
          <p class="muted small">Большой PDF разбирается частями, это может занять несколько минут. Можно переключиться на другую вкладку и вернуться.</p>
        </div>`;
      await new Promise((r) => setTimeout(r, 1500));
      const poll = await fetch(`/api/import/preview/${data.token}`);
      data = await poll.json();
      if (!poll.ok) return fail(data.detail);
    }
  } catch (err) {
    return fail(`Нет связи с ботом: ${err.message}`);
  }
  if (data.state === "error") return fail(data.detail);
  const s = data.stats;
  const CHECK = { ok: "✓", unknown: "?", bad: "✗", duplicate: "дубль", written: "писали" };
  el.innerHTML = `
    <div class="import-summary">
      <strong>${escapeHtml(data.filename)}</strong>: строк ${s.total} ·
      <span class="ok-text">адрес в порядке ${s.ok}</span> ·
      не проверен ${s.unknown} · <span class="err-text">с ошибкой ${s.bad}</span> ·
      дублей ${s.duplicate} · уже писали ${s.already_written}
    </div>
    <div class="table-wrap import-table"><table>
      <thead><tr><th>#</th><th>Компания</th><th>Email</th><th>Контакт</th><th>Упор</th><th>Проверка</th></tr></thead>
      <tbody>${data.items
        .slice(0, 50)
        .map(
          (i) => `<tr class="check-${i.check}">
            <td>${i.row}</td><td>${escapeHtml(i.company)}</td><td>${escapeHtml(i.email)}</td>
            <td>${escapeHtml(i.name)}</td><td>${escapeHtml(truncate(i.emphasis || "", 60))}</td>
            <td>${CHECK[i.check] || ""} <span class="muted small">${escapeHtml(i.note)}</span></td></tr>`
        )
        .join("")}</tbody></table></div>
    ${data.items.length > 50 ? `<p class="muted small">…и ещё ${data.items.length - 50}</p>` : ""}
    <div class="filters">
      <label class="checkbox-row"><input type="checkbox" id="import-unverified" checked /> Добавлять адреса, домен которых не удалось проверить</label>
      <button type="button" class="btn btn-primary" id="import-commit">Добавить в базу</button>
      <button type="button" class="btn btn-ghost" id="import-cancel">Отмена</button>
    </div>`;
  document.getElementById("import-cancel").addEventListener("click", () => (el.innerHTML = ""));
  document.getElementById("import-commit").addEventListener("click", async () => {
    try {
      const res = await api("/api/import/commit", {
        method: "POST",
        body: JSON.stringify({ token: data.token, include_unverified: document.getElementById("import-unverified").checked }),
      });
      el.innerHTML = `<p class="ok-text">✅ Добавлено: компаний ${res.companies}, контактов ${res.contacts} из ${escapeHtml(res.filename)}. </p>
        <button type="button" class="btn btn-primary btn-small" data-goto-outreach>✉️ Перейти к рассылке →</button>`;
      el.querySelector("[data-goto-outreach]").addEventListener("click", () => switchTab("outreach"));
      showToast(`База обновлена: +${res.companies} ${plural(res.companies, "компания", "компании", "компаний")}`, "success");
      // Сразу показать новое: фильтр по этому файлу, подсветка строк.
      document.getElementById("contacts-filter-source").value = `file:${res.filename}`;
      baseState.page = 0;
      render.contacts();
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
  });
}

function stepHead(n, title, state) {
  return `<div class="step-head"><span class="step-num ${state}">${state === "done" ? "✓" : n}</span><h3>${title}</h3></div>`;
}

async function loadCampaigns() {
  const [data, watch] = await Promise.all([api("/api/campaigns"), api("/api/settings/telegram-watch")]);
  const resumes = watch.resumes || [];
  const sources = Object.entries(data.sources);
  // Текущая рассылка — самая свежая; остальные — история.
  const [current, ...past] = data.campaigns;
  const cur = current && (current.progress || current.stats.pending || current.stats.draft) ? current : null;
  const history = cur ? past : data.campaigns;

  // ① База
  const base = document.getElementById("step-base");
  base.innerHTML = `
    ${stepHead(1, "База", data.available || cur ? "done" : "active")}
    ${
      data.available
        ? `<p>Можно написать <b>${data.available}</b> ${plural(data.available, "компании", "компаниям", "компаниям")} с email, которым вы ещё не писали:</p>
           <div class="campaign-stats">${sources.map(([s, n]) => `<span class="stat-pill">${escapeHtml(s)} <b>${n}</b></span>`).join("")}</div>`
        : `<p class="muted">${cur ? "Все новые адреса уже в текущей рассылке." : "Пока некому писать — загрузите свой список или подождите, пока бот соберёт контакты из Telegram и вакансий."}</p>`
    }
    <div class="step-actions">
      <button type="button" class="btn btn-ghost btn-small" data-base-open>Открыть базу и загрузить свой файл →</button>
    </div>`;
  base.querySelector("[data-base-open]").addEventListener("click", () => switchTab("contacts"));

  // ② Письма
  const letters = document.getElementById("step-letters");
  const drafts = cur ? cur.items.filter((i) => i.status === "draft") : [];
  let body;
  if (cur?.progress?.kind === "prepare") {
    body = progressHtml("Пишу письма", cur.progress, cur.id);
  } else if (cur?.stats.pending) {
    // Порциями по дневному лимиту — см. start_campaign_job("prepare").
    const batch = Math.min(cur.stats.pending, Math.max(0, data.daily_limit - drafts.length));
    const days = Math.ceil((cur.stats.pending + drafts.length) / Math.max(1, data.daily_limit));
    body = batch
      ? `<p>В очереди: <b>${cur.stats.pending}</b>. Письма пишутся порциями по дневному лимиту (${data.daily_limit}), следующие — сами на следующий день, придут в бот.</p>
         <button type="button" class="btn btn-primary" data-campaign="${cur.id}" data-action="prepare">✍️ Написать ${batch} ${plural(batch, "письмо", "письма", "писем")}</button>`
      : `<p class="muted">Ещё в очереди: <b>${cur.stats.pending}</b> — следующая порция будет готова завтра, когда эти письма уйдут${days > 1 ? ` (≈ ${days} ${plural(days, "день", "дня", "дней")} на всю рассылку)` : ""}.</p>`;
  } else if (!cur && data.available) {
    const days = data.days_needed;
    body = `<p class="muted small">Для каждой компании — своё письмо: обращение по имени, почему именно она, 2–3 ваших достижения под её профиль, 150–180 слов, тема «[Должность] Application — Имя Фамилия».</p>
      ${days > 1 ? `<p class="muted small">Сейчас можно ${data.daily_limit} писем в день${data.mail_plan.warmup && data.daily_limit < data.mail_plan.daily_limit ? ` (разогрев ящика — дальше больше, до ${data.mail_plan.daily_limit})` : ""}: вся база — ≈ ${days} ${plural(days, "день", "дня", "дней")} отправки. Письма пишутся порциями, каждый день новая порция приходит в бот. Быстрее — выберите нужные компании в Базе фильтрами и «✉️ Написать выбранным».</p>` : ""}
      <div class="step-actions">
        ${sources.length > 1 ? `<select id="campaign-source" aria-label="Кому писать">
          <option value="">всем (${data.available})</option>
          ${sources.map(([s, n]) => `<option value="${escapeHtml(s)}">${escapeHtml(s)} (${n})</option>`).join("")}
        </select>` : ""}
        <button type="button" class="btn btn-primary" id="campaign-create">✍️ Подготовить письма</button>
      </div>`;
  } else {
    body = drafts.length ? "" : `<p class="muted">Появится, когда в базе будут адреса.</p>`;
  }
  if (drafts.length) {
    body += `<p>Готово писем: <b>${drafts.length}</b>. Пролистайте — можно поправить текст или убрать письмо.</p>
      <div class="letters">${drafts
        .map(
          (i) => `<details class="letter">
            <summary><strong>${escapeHtml(i.company || i.email)}</strong> <span class="muted small">${escapeHtml(i.email)}</span></summary>
            <div class="muted small">Тема: ${escapeHtml(i.subject)}</div>
            <textarea rows="9" data-letter="${escapeHtml(i.code)}" aria-label="Текст письма">${escapeHtml(i.text)}</textarea>
            <div class="step-actions"><button type="button" class="btn btn-ghost btn-small" data-letter-skip="${escapeHtml(i.code)}">Убрать из рассылки</button></div>
          </details>`
        )
        .join("")}</div>`;
  }
  letters.innerHTML = stepHead(2, "Письма", drafts.length ? "done" : data.available || cur ? "active" : "locked") + body;

  // ③ Отправка
  const send = document.getElementById("step-send");
  let sendBody;
  if (!data.email_connected) {
    sendBody = `<p class="warn-text">Почта Gmail не подключена — <a href="#" data-goto-settings="settings-outreach">подключить</a> (пароль приложения Google, 2 минуты).</p>`;
  } else if (cur?.progress?.kind === "send" || cur?.progress?.kind === "followups") {
    sendBody = progressHtml(cur.progress.kind === "send" ? "Отправляю" : "Отправляю напоминания", cur.progress, cur.id);
  } else if (drafts.length && cur.sending) {
    // Отправка включена, но сейчас ждёт: вечер/выходные, лимит, возвраты.
    sendBody = `<p>⏸ Отправка идёт по расписанию — ждут ещё <b>${drafts.length}</b>. ${escapeHtml(data.mail_plan.reason || "Следующее письмо — в течение 15 минут.")}</p>
      <div class="step-actions"><button type="button" class="btn btn-ghost btn-small" data-campaign="${cur.id}" data-action="stop">Остановить рассылку</button></div>
      <p class="small">🛡 ${escapeHtml(mailPlanText(data.mail_plan))} · <a href="#" data-goto-settings="settings-outreach">настроить</a></p>`;
  } else if (drafts.length) {
    sendBody = `<div class="step-actions">
        <label class="muted small">Резюме во вложении
          <select data-campaign-resume="${cur.id}" aria-label="Резюме во вложении">
            <option value="">основное резюме</option>
            ${resumes.map((r) => `<option value="${escapeHtml(r.name)}">${escapeHtml(r.name)}</option>`).join("")}
          </select>
        </label>
        <button type="button" class="btn btn-primary" data-campaign="${cur.id}" data-action="send">🚀 Начать отправку (${drafts.length})</button>
      </div>
      <p class="muted small">Бот отправляет по одному, со случайными паузами в течение рабочего дня — как человек. Что не уйдёт сегодня, продолжит сам в следующее время отправки. Можно закрыть окно.</p>
      <p class="small">🛡 ${escapeHtml(mailPlanText(data.mail_plan))} · <a href="#" data-goto-settings="settings-outreach">настроить</a></p>`;
  } else {
    sendBody = `<p class="muted">Когда письма будут готовы — здесь одна кнопка отправки.</p>`;
  }
  const statsFor = (c) => `
    <div class="campaign-card">
      <div class="campaign-title"><strong>${escapeHtml(c.name)}</strong> <span class="muted small">${fmtTime(c.created_at).split(",")[0]}</span>
        ${c.progress ? "" : `<button type="button" class="btn btn-ghost btn-small" data-campaign="${c.id}" data-action="delete" title="Удалить рассылку и её неотправленные письма">Удалить</button>`}</div>
      <div class="campaign-stats">
        ${["total", "sent", "followed_up", "replied", "failed", "bounced", "skipped"]
          .filter((k) => k === "total" || c.stats[k])
          .map((k) => `<span class="stat-pill ${k}"><b>${c.stats[k]}</b> ${k === "total" ? "всего" : CAMPAIGN_STATUS[k]}</span>`)
          .join("")}
      </div>
      ${(() => {
        const due = c.items.filter((i) => i.follow_up_text);
        if (!due.length) return "";
        return `<div class="followups">
          <p><b>⏳ Молчат больше недели: ${due.length}</b> — короткое напоминание уйдёт в ту же ветку письма, без вложения.</p>
          <div class="letters">${due
            .map(
              (i) => `<details class="letter">
                <summary><strong>${escapeHtml(i.company || i.email)}</strong> <span class="muted small">${escapeHtml(i.email)}</span></summary>
                <textarea rows="4" data-letter="${escapeHtml(i.follow_up_code)}" aria-label="Текст напоминания">${escapeHtml(i.follow_up_text)}</textarea>
                <div class="step-actions"><button type="button" class="btn btn-ghost btn-small" data-letter-skip="${escapeHtml(i.follow_up_code)}">Не напоминать</button></div>
              </details>`
            )
            .join("")}</div>
          ${c.progress ? "" : `<div class="step-actions"><button type="button" class="btn btn-primary btn-small" data-campaign="${c.id}" data-action="followups">⏳ Отправить напоминания (${due.length})</button></div>`}
        </div>`;
      })()}
      ${(() => {
        const failed = c.items.filter((i) => ["failed", "bounced"].includes(i.status));
        return failed.length
          ? `<details class="muted small"><summary>Не дошло и почему (${failed.length})</summary>
              ${failed.map((i) => `<div>${escapeHtml(i.company)} — ${escapeHtml(i.email)}: ${escapeHtml(i.reason || CAMPAIGN_STATUS[i.status])}</div>`).join("")}
            </details>`
          : "";
      })()}
    </div>`;
  const all = (cur ? [cur] : []).concat(history);
  send.innerHTML =
    stepHead(3, "Отправка и результат", drafts.length && data.email_connected ? "active" : all.some((c) => c.stats.sent) ? "done" : "locked") +
    sendBody +
    (all.length ? `<h4 class="muted small">Рассылки</h4>${all.map(statsFor).join("")}` : "");

  const view = document.getElementById("view-outreach");
  bindGotoSettings(view);
  document.getElementById("campaign-create")?.addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      const c = await api("/api/campaigns", {
        method: "POST",
        body: JSON.stringify({ source: document.getElementById("campaign-source")?.value || "" }),
      });
      await api(`/api/campaigns/${c.id}/prepare`, { method: "POST", body: JSON.stringify({ resume: "" }) });
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
    loadCampaigns();
  });
  view.querySelectorAll("[data-letter]").forEach((ta) =>
    ta.addEventListener("change", async () => {
      try {
        await api(`/api/hr-drafts/${ta.dataset.letter}`, { method: "PUT", body: JSON.stringify({ text: ta.value }) });
        showToast("Письмо сохранено");
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error");
      }
    })
  );
  view.querySelectorAll("[data-letter-skip]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await api(`/api/hr-drafts/${btn.dataset.letterSkip}/skip`, { method: "POST" });
      loadCampaigns();
    })
  );
  view.querySelectorAll("[data-campaign]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.campaign;
      const action = btn.dataset.action;
      if (action === "send" && !confirm("Отправить письма через Gmail с резюме во вложении?")) return;
      if (action === "followups" && !confirm("Отправить напоминания через Gmail в те же ветки писем?")) return;
      if (action === "delete" && !confirm("Удалить рассылку? Неотправленные письма тоже удалятся.")) return;
      btn.disabled = true;
      try {
        if (action === "delete") {
          await api(`/api/campaigns/${id}`, { method: "DELETE" });
        } else {
          const resume = view.querySelector(`[data-campaign-resume="${id}"]`)?.value || "";
          await api(`/api/campaigns/${id}/${action}`, { method: "POST", body: JSON.stringify({ resume }) });
        }
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error");
      }
      loadCampaigns();
    });
  });
  // Пока идёт работа — обновляем прогресс.
  clearTimeout(campaignPoll);
  if (data.campaigns.some((c) => c.progress) && currentView === "outreach") {
    campaignPoll = setTimeout(loadCampaigns, 4000);
  }
}

function progressHtml(label, progress, id) {
  const pct = Math.round((100 * progress.done) / Math.max(progress.total, 1));
  return `<p>${label}: <b>${progress.done}</b> из ${progress.total}</p>
    <div class="progress"><div style="width:${pct}%"></div></div>
    <div class="step-actions"><button type="button" class="btn btn-ghost btn-small" data-campaign="${id}" data-action="stop">Остановить</button></div>`;
}

const render = {
  async contacts() {
    lastContacts = await api("/api/contacts");
    renderContactsList();
  },

  outreach() {
    loadCampaigns();
  },

  resume() {
    renderResumes();
  },

  async overview() {
    renderTodo();
    renderOwnChannels();
    if (!overviewLoaded) {
      document.getElementById("stats-row").innerHTML = skeletonStats();
      document.getElementById("source-grid-ru").innerHTML = skeletonSourceGrid(5);
      document.getElementById("source-grid-intl").innerHTML = skeletonSourceGrid(3);
    }

    const [status, stats, runNow] = await Promise.all([
      api("/api/status"),
      api("/api/stats"),
      api("/api/run-now/status"),
    ]);

    // ponytail: без этой проверки весь блок ниже (счётчики со
    // start-anew анимацией, карточки площадок, чекбоксы) пересобирался
    // на каждый опрос раз в 7с даже когда ничего не изменилось — визуально
    // это и есть "мерцание", о котором сообщил пользователь.
    const snapshot = JSON.stringify({ status, stats, runNow });
    const unchanged = overviewLoaded && snapshot === lastOverviewSnapshot;
    lastOverviewSnapshot = snapshot;

    const badge = document.getElementById("daemon-badge");
    const runningLabel = status.daemon_started_at
      ? `бот работает · ${formatElapsed(status.daemon_started_at)}`
      : "бот работает";
    badge.innerHTML = `<span class="badge-dot"></span><span class="btn-label">${
      status.daemon_running ? runningLabel : "бот остановлен"
    }</span>`;
    badge.classList.toggle("on", status.daemon_running);
    badge.classList.toggle("off", !status.daemon_running);
    // Одна кнопка вместо двух (Старт/Пауза): демон не запущен — это
    // "Запустить"; запущен и активен — "Пауза"; запущен и на паузе —
    // "Возобновить". is-pause-action переключает play/pause-иконку
    // (см. style.css), is-paused — только цвет в состоянии "на паузе"
    // (тот же класс/приём, что был у отдельной кнопки-паузы).
    const toggleBtn = document.getElementById("daemon-toggle");
    const isPauseAction = status.daemon_running && !status.daemon_paused;
    toggleBtn.classList.toggle("is-pause-action", isPauseAction);
    toggleBtn.classList.toggle("is-paused", !!status.daemon_paused);
    // Одна кнопка: «Запустить» ↔ «Остановить». Пауза и отдельный «Стоп»
    // для человека — одно и то же, лишний выбор только путал.
    toggleBtn.querySelector(".btn-label").textContent = !status.daemon_running
      ? "Запустить"
      : status.daemon_paused
        ? "Возобновить"
        : "Остановить";
    toggleBtn.title = !status.daemon_running
      ? "Запустить бота: площадки по расписанию, Telegram-парсер, проверка ответов"
      : status.daemon_paused
        ? "Возобновить работу бота"
        : "Остановить бота";

    // Проблемные площадки видно только зайдя на "Обзор" — бейдж на
    // самой вкладке (как непрочитанные в Telegram) сигналит о них,
    // даже если человек сейчас смотрит Историю или Настройки.
    const errorCount = status.sources.filter(
      (s) => s.status === "error" || s.status === "blocked"
    ).length;
    const overviewBadge = document.getElementById("overview-error-badge");
    if (errorCount > 0) {
      overviewBadge.textContent = String(errorCount);
      overviewBadge.style.display = "";
    } else {
      overviewBadge.style.display = "none";
    }

    if (!unchanged) {

      const statsRow = document.getElementById("stats-row");
      statsRow.classList.remove("content-fade-in");
      void statsRow.offsetWidth;
      statsRow.classList.add("content-fade-in");
      statsRow.innerHTML = `
        <div class="stat-card"><div class="value" data-target="${stats.day}">0</div><div class="label">откликов сегодня</div></div>
        <div class="stat-card"><div class="value" data-target="${stats.week}">0</div><div class="label">за неделю</div></div>
        <div class="stat-card"><div class="value" data-target="${stats.month}">0</div><div class="label">за месяц</div></div>
      `;
      statsRow.querySelectorAll(".value").forEach((el) => {
        countUp(el, parseInt(el.dataset.target, 10));
      });

      // ponytail: чекбокс теперь ЕСТЬ schedule_enabled этой площадки —
      // единственный переключатель "площадка участвует в демоне", вместо
      // отдельной кнопки "Запустить выбранные" поверх отдельного тумблера
      // в "Настройках". checked всегда берётся из свежих данных сервера
      // (s.schedule_enabled), а не сохраняется вручную между опросами —
      // рендер и так пропускается, пока status не изменится (см. unchanged
      // выше), так что раньше поставленная галочка не мигает.
      // Telegram и «Сайты компаний» — отдельными карточками в «Свои каналы».
      const ruSources = status.sources.filter((s) => !INTL_SOURCES.has(s.name) && !OWN_CHANNELS.has(s.name));
      const intlSources = status.sources.filter((s) => INTL_SOURCES.has(s.name));
      const renderSourceCard = (s, i) => {
          const dot = STATUS_DOT[s.status] || "never_run";
          const ratio = s.daily_limit
            ? Math.min(1, s.applied_today / s.daily_limit)
            : 0;
          const barClass =
            ratio >= 1 ? "full" : ratio >= 0.7 ? "warn" : "";
          const ringC = 2 * Math.PI * 13;
          const ringOffset = ringC * (1 - ratio);
          // telegram отправляет (пишет контакту) только при
          // auto_message; остальные площадки — при auto_apply. Раньше
          // в режиме "только поиск" счётчик "Откликов сегодня" вообще
          // пропадал с карточки (заменялся строкой "Режим") — снаружи
          // это выглядело как будто лимит нигде не виден. Теперь
          // счётчик остаётся всегда (он и так 0/N, пока автоотклик
          // выключен, — не вводит в заблуждение), а "только поиск"
          // идёт отдельной строкой поверх него как пояснение.
          const isSearchOnly =
            s.name === "telegram" ? !s.auto_message : !s.auto_apply;
          const isRunning = runNow.running && runNow.current_source === s.name;
          // Один понятный выбор вместо «расписание» + «автоотклик» + «только поиск».
          // Вкл/выкл — переключатель, как у Telegram-парсера; что делать, когда
          // включена, — две кнопки: откликаться самому или только искать.
          // Режим меняют редко — на карточке спокойная метка, по клику
          // окно площадки с пояснением (случайно включить автоотклик нельзя).
          const modeRow = `<div class="row"><span>Режим</span>${
            s.schedule_enabled
              ? `<button type="button" class="mode-chip${isSearchOnly ? "" : " is-apply"}" data-open-platform="${s.name}" title="Изменить режим и фильтры">${isSearchOnly ? "🔍 только ищет" : "✉️ откликается сам"}</button>`
              : `<span class="muted">выключена</span>`
          }</div>`;
          const responseRow = `<div class="row"><span>Откликов сегодня</span>
              <span class="limit-ring-wrap">
                <svg width="18" height="18" viewBox="0 0 32 32">
                  <circle class="limit-ring-bg" cx="16" cy="16" r="13"></circle>
                  <circle class="limit-ring-fill ${barClass}" cx="16" cy="16" r="13" style="stroke-dasharray:${ringC.toFixed(2)};stroke-dashoffset:${ringOffset.toFixed(2)}"></circle>
                </svg>
                ${s.applied_today}/${s.daily_limit}
              </span></div>`;
          return `
          <div class="source-card stagger-item${isRunning ? " is-running" : ""}" data-source="${s.name}" draggable="true" style="animation-delay:${staggerDelay(i)}">
            <div class="source-card-actions">
              <button type="button" class="src-run-now${isRunning ? " is-stop" : ""}" data-source="${s.name}" data-running="${isRunning ? "1" : "0"}" title="${isRunning ? "Остановить (текущая заявка досылается, следующая не начнётся)" : "Запустить эту площадку прямо сейчас, не дожидаясь расписания"}" aria-label="${isRunning ? "Остановить" : "Запустить сейчас"} ${sourceLabel(s.name)}">
                ${isRunning
                  ? `<svg viewBox="0 0 20 20" fill="none"><rect x="5.5" y="5.5" width="9" height="9" rx="1.5" fill="currentColor"/></svg>`
                  : `<svg viewBox="0 0 20 20" fill="none"><path d="M7 5.2v9.6l8-4.8-8-4.8Z" fill="currentColor"/></svg>`}
              </button>
              <button type="button" class="src-goto-history" data-source="${s.name}" title="История откликов этой площадки" aria-label="История откликов ${sourceLabel(s.name)}">
                <svg viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="7.3" stroke="currentColor" stroke-width="1.6"/><path d="M10 5.8V10l3 2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
              </button>
              <button type="button" class="src-goto-logs" data-source="${s.name}" title="Логи этой площадки" aria-label="Логи ${sourceLabel(s.name)}">
                <svg viewBox="0 0 20 20" fill="none"><rect x="2.5" y="3.5" width="15" height="13" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M5.5 7.5 8 10l-2.5 2.5M9.8 12.5h4.7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
            </div>
            <h3>
              <input type="checkbox" class="switch platform-toggle" data-source="${s.name}" title="Включить или выключить площадку" aria-label="Включить ${sourceLabel(s.name)}" ${s.schedule_enabled ? "checked" : ""} />
              <span class="dot ${isRunning ? "running" : dot}"></span> ${sourceIconHtml(s.name)}${sourceLabel(s.name)}
            </h3>
            ${modeRow}
            <div class="row" title="Следующая проверка: ${escapeHtml(fmtTime(s.next_run))}"><span>Последняя проверка</span><span>${s.schedule_enabled ? fmtDay(s.last_run) : "—"}</span></div>
            ${responseRow}
            ${errorRowHtml(s.last_error)}
          </div>`;
      };
      document.getElementById("source-grid-ru").innerHTML = applySourceOrder(ruSources, "name", "cj-source-order-ru")
        .map(renderSourceCard)
        .join("");
      document.getElementById("source-grid-intl").innerHTML = applySourceOrder(intlSources, "name", "cj-source-order-intl")
        .map(renderSourceCard)
        .join("");
      const chatGrid = document.getElementById("chat-checks-grid");
      if (chatGrid) chatGrid.innerHTML = applySourceOrder(status.chat_checks, "name", "cj-source-order")
        .map((c, i) => {
          const dot = STATUS_DOT[c.status] || "never_run";
          return `
          <div class="source-card stagger-item" data-source="${c.name}" draggable="true" style="animation-delay:${staggerDelay(i)}">
            <div class="source-card-actions">
              <button type="button" class="src-goto-history" data-source="${c.name}" title="История откликов этой площадки" aria-label="История откликов ${escapeHtml(c.label)}">
                <svg viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="7.3" stroke="currentColor" stroke-width="1.6"/><path d="M10 5.8V10l3 2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
              </button>
              <button type="button" class="src-goto-logs" data-source="${c.name}" title="Логи этой площадки" aria-label="Логи ${escapeHtml(c.label)}">
                <svg viewBox="0 0 20 20" fill="none"><rect x="2.5" y="3.5" width="15" height="13" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M5.5 7.5 8 10l-2.5 2.5M9.8 12.5h4.7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
            </div>
            <h3>
              <input type="checkbox" class="schedule-toggle switch" data-source="${c.name}" title="Бот проверяет по расписанию" ${c.schedule_enabled ? "checked" : ""} />
              <span class="dot ${dot}"></span> ${c.label}
            </h3>
            <div class="row"><span>Расписание</span><span>${c.schedule_enabled ? `каждые ${c.interval_hours}ч` : "выключено"}</span></div>
            <div class="row"><span>Последняя проверка</span><span>${fmtTime(c.last_run)}</span></div>
            <div class="row"><span>Следующая проверка</span><span>${fmtTime(c.next_run)}</span></div>
            <p class="muted small" style="margin:6px 0 0">${c.note}</p>
            ${errorRowHtml(c.last_error)}
          </div>`;
        })
        .join("");

      const savePlatform = async (source, body, label) => {
        try {
          await api("/api/settings", { method: "POST", body: JSON.stringify({ source, ...body }) });
          showToast(`${sourceLabel(source)}: ${label}`, "success");
        } catch (err) {
          showToast(err.message.replace(/^\d+: /, ""), "error");
        }
        lastOverviewSnapshot = "";
        render.overview();
      };
      document.querySelectorAll(".platform-toggle").forEach((box) =>
        box.addEventListener("change", () => {
          box.disabled = true;
          savePlatform(box.dataset.source, { schedule_enabled: box.checked }, box.checked ? "включена" : "выключена");
        })
      );
      document.querySelectorAll("[data-open-platform]").forEach((btn) =>
        btn.addEventListener("click", () => {
          pendingPlatformDrawer = btn.dataset.openPlatform;
          switchTab("settings");
        })
      );
      document.querySelectorAll(".schedule-toggle").forEach((box) => {
        box.addEventListener("change", async () => {
          box.disabled = true;
          try {
            await api("/api/settings", {
              method: "POST",
              body: JSON.stringify({
                source: box.dataset.source,
                schedule_enabled: box.checked,
              }),
            });
          } finally {
            box.disabled = false;
          }
        });
      });
    }

    overviewLoaded = true;
  },

  async history() {
    const source = document.getElementById("filter-source").value;
    const status = document.getElementById("filter-status").value;
    const q = document.getElementById("filter-query").value;
    const params = new URLSearchParams();
    if (source) params.set("source", source);
    if (status) params.set("status", status);
    if (q) params.set("q", q);

    const tbody = document.getElementById("history-rows");
    if (!historyLoaded) tbody.innerHTML = skeletonRows(6, 7);

    // Отказы по умолчанию скрыты — на виду живые отклики.
    const showRejected = document.getElementById("filter-show-rejected").checked;
    const entries = (await api(`/api/applications?${params}`)).filter(
      (e) => showRejected || e.effective_stage !== "rejected"
    );
    historyLoaded = true;

    // ponytail: тот же фикс мерцания, что и на "Обзоре" — без этого
    // таблица (и её fade-in анимация строк через observeReveal)
    // пересобиралась с нуля на каждом опросе раз в 7с, даже если ни
    // одной новой строки не появилось.
    const historySnapshot = JSON.stringify({ params: params.toString(), entries });
    if (historySnapshot === lastHistorySnapshot) return;
    lastHistorySnapshot = historySnapshot;

    lastHistoryEntries = entries;
    if (!entries.length) {
      tbody.innerHTML = `<tr><td colspan="8">${emptyStateHtml("Ничего не найдено.")}</td></tr>`;
      return;
    }
    const reversed = entries.slice().reverse();
    tbody.innerHTML = reversed
      .map(
        (e, i) => `
      <tr class="reveal" style="transition-delay:${staggerDelay(i, 25)}">
        <td>${fmtTime(e.applied_at)}</td>
        <td>${sourceIconHtml(e.source)}${sourceLabel(e.source)}</td>
        <td>${escapeHtml(e.company)}</td>
        <td><a href="${escapeHtml(e.link)}" target="_blank" rel="noopener">${escapeHtml(e.title)}</a>${rowActionsHtml(e, i)}</td>
        <td>${statusLabel(e.status)}${e.remote_region ? `<div class="muted small">${REGION_LABELS[e.remote_region] || ""}</div>` : ""}</td>
        <td>${e.status === "applied" ? stageSelectHtml(e) : `<span class="muted small">—</span>`}</td>
        <td title="${e.gaps && e.gaps.length ? escapeHtml(e.gaps.join("; ")) : ""}">
          ${e.score ?? ""}
          ${
            e.gaps && e.gaps.length
              ? `<div class="readiness-note">${escapeHtml(truncate(e.gaps[0], 70))}${e.gaps.length > 1 ? ` (+${e.gaps.length - 1})` : ""}</div>`
              : ""
          }
        </td>
        <td>
          ${
            e.cover_letter
              ? `<button type="button" class="btn btn-secondary btn-small" data-cover-letter-btn data-row-index="${i}">📄 Читать письмо</button>`
              : `<span class="muted small">—</span>`
          }

        </td>
      </tr>`
      )
      .join("");
    tbody.querySelectorAll("[data-cover-letter-btn]").forEach((btn) => {
      btn.addEventListener("click", () => {
        openCoverLetterModal(reversed[parseInt(btn.dataset.rowIndex, 10)]);
      });
    });
    tbody.querySelectorAll("[data-prep-btn]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const e = reversed[parseInt(btn.dataset.rowIndex, 10)];
        btn.disabled = true;
        btn.textContent = "Готовлю…";
        try {
          const { prep } = await api("/api/applications/prep", {
            method: "POST",
            body: JSON.stringify({ source: e.source, external_id: e.external_id }),
          });
          openTextModal(`Подготовка: ${e.company} — ${e.title}`, "Справка к интервью", prep.replace(/\*\*/g, ""));
        } catch (err) {
          showToast(err.message, "error");
        } finally {
          btn.disabled = false;
          btn.textContent = "🎯 Подготовка";
        }
      });
    });
    tbody.querySelectorAll("[data-find-hr]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const e = reversed[parseInt(btn.dataset.rowIndex, 10)];
        btn.disabled = true;
        btn.textContent = "Ищу контакты…";
        try {
          const res = await api("/api/contacts/from-application", {
            method: "POST",
            body: JSON.stringify({ source: e.source, external_id: e.external_id }),
          });
          showToast(
            res.message ||
              (res.added ? `Найдено контактов: ${res.added}` : "Компания добавлена в «Контакты» — публичных контактов на сайте нет"),
            res.added ? "success" : "info",
            7000
          );
          focusContactKey = res.key;
          switchTab("contacts");
        } catch (err) {
          showToast(err.message.replace(/^\d+: /, ""), "error");
          btn.disabled = false;
          btn.textContent = "👤 Найти HR этой компании";
        }
      });
    });
    tbody.querySelectorAll("[data-calendar-btn]").forEach((btn) => {
      btn.addEventListener("click", () =>
        openCalendarOverlay(reversed[parseInt(btn.dataset.rowIndex, 10)])
      );
    });
    tbody.querySelectorAll("[data-trainer-btn]").forEach((btn) => {
      btn.addEventListener("click", () =>
        openTrainer(reversed[parseInt(btn.dataset.rowIndex, 10)])
      );
    });
    tbody.querySelectorAll("[data-prefill-btn]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const e = reversed[parseInt(btn.dataset.rowIndex, 10)];
        btn.disabled = true;
        try {
          const { filled } = await api("/api/direct/prefill", {
            method: "POST",
            body: JSON.stringify({ source: e.source, external_id: e.external_id }),
          });
          showToast(
            filled.length
              ? `Форма открыта в Chrome, заполнено: ${filled.join(", ")}. Ответьте на вопросы компании и нажмите Submit.`
              : "Форма открыта в Chrome — эту разметку заполнить не удалось, заполните вручную.",
            "success",
            8000
          );
        } catch (err) {
          showToast(err.message, "error");
        } finally {
          btn.disabled = false;
        }
      });
    });
    bindStageSelects(tbody);
    observeReveal(tbody);
  },

  async replies() {
    const tbody = document.getElementById("replies-rows");
    if (!repliesLoaded) tbody.innerHTML = `<div class="skeleton" style="height:90px;margin-bottom:10px"></div>`.repeat(3);

    renderDraftsQueue();
    const entries = await api("/api/inbox");
    // Конфетти — только на реально новый ответ, появившийся после
    // первой загрузки за сессию, не на каждое открытие вкладки с уже
    // существующими данными.
    if (repliesLoaded && entries.length > lastRepliesCount) {
      fireConfetti();
      showToast("Новый ответ от работодателя!", "success");
    }
    lastRepliesCount = entries.length;
    repliesLoaded = true;

    const repliesSnapshot = JSON.stringify(entries);
    if (repliesSnapshot === lastRepliesSnapshot) return;
    lastRepliesSnapshot = repliesSnapshot;
    lastRepliesEntries = entries;
    renderRepliesRows();
  },

  async analytics() {
    renderResults();
    renderActivityHeatmap();
    const gapsEl = document.getElementById("gaps-list");
    const candidatesEl = document.getElementById("blacklist-candidates");
    gapsEl.innerHTML = Array.from({ length: 3 }, () => `<li><div class="skeleton" style="height:14px"></div></li>`).join("");
    candidatesEl.innerHTML = Array.from({ length: 2 }, () => `<div class="skeleton" style="height:20px;margin-bottom:6px"></div>`).join("");

    const [gaps, candidates, funnel, market] = await Promise.all([
      api("/api/analytics/gaps"),
      api("/api/analytics/blacklist-candidates"),
      api("/api/analytics/funnel"),
      api("/api/analytics/market"),
    ]);
    renderFunnel(funnel);
    renderMarket(market);
    renderOffers();

    gapsEl.innerHTML = gaps.length
      ? gaps
          .map(
            ([gap, count], i) =>
              `<li class="stagger-item" style="animation-delay:${staggerDelay(i)}">${escapeHtml(gap)} — ${count}</li>`
          )
          .join("")
      : `<li>${emptyStateHtml("Пока нет данных.")}</li>`;

    if (!candidates.length) {
      candidatesEl.innerHTML = emptyStateHtml("Нет кандидатов на чёрный список.");
      return;
    }
    candidatesEl.innerHTML = candidates
      .map(
        (c, i) => `
      <div class="candidate-row stagger-item" style="animation-delay:${staggerDelay(i)}">
        <input type="checkbox" value="${escapeHtml(c)}" class="blacklist-check" />
        <span>${escapeHtml(c)}</span>
        <button class="btn btn-secondary btn-small block-hh-employer" data-company="${escapeHtml(c)}" title="Заблокировать работодателя на hh.ru (серверный бан, только для HeadHunter)">🔒 hh.ru</button>
      </div>`
      )
      .join("");
  },

  async settings() {
    loadOutreachSettings(); // заполняет и сводку, и фильтры удалёнки на других вкладках
    loadAccounts();
    const [status, salary, limits] = await Promise.all([
      api("/api/status"),
      api("/api/settings/salary"),
      api("/api/settings/limits"),
    ]);
    renderAutoAll(status);

    api("/api/settings/search").then((search) => {
      const fields = [
        ["search-positions", search.positions],
        ["search-locations", search.locations],
        ["search-company-blacklist", search.company_blacklist],
        ["search-title-blacklist", search.title_blacklist],
        ["search-location-blacklist", search.location_blacklist],
      ];
      fields.forEach(([id, list]) => {
        const el = document.getElementById(id);
        el.value = (list || []).join("\n");
        initTagInput(el);
      });
    });

    api("/api/settings/llm").then((llm) => {
      llmCatalog = {
        models: llm.models || {},
        api_key_previews: llm.api_key_previews || {},
        provider_base_urls: llm.provider_base_urls || {},
      };
      applyLLMSelection(llm.provider, llm.model);
      document.getElementById("llm-base-url").value = llm.base_url || "";
      document.getElementById("llm-mode").value = llm.mode || "auto";
      document.getElementById("llm-fallback-enabled").checked =
        llm.fallback_enabled !== false;
    });

    api("/api/settings/llm/status").then(applyLLMProviderStatus);
    refreshTelegramConnectStatus();

    api("/api/settings/autostart").then((autostart) => {
      const toggle = document.getElementById("autostart-toggle");
      const note = document.getElementById("autostart-status");
      toggle.checked = autostart.enabled;
      toggle.disabled = !autostart.supported;
      note.textContent = autostart.supported
        ? ""
        : "Не поддерживается на этой ОС.";
    });

    api("/api/settings/daemon_service").then((svc) => {
      const toggle = document.getElementById("daemon-service-toggle");
      const note = document.getElementById("daemon-service-status");
      toggle.checked = svc.enabled;
      toggle.disabled = !svc.supported;
      note.textContent = svc.supported
        ? ""
        : "Не поддерживается на этой ОС (или в собранном приложении).";
    });

    document.getElementById("limit-total").value =
      limits.total_daily_application_limit || "";
    document.getElementById("limit-daily").value =
      limits.daily_application_limit;
    document.getElementById("limit-linkedin").value =
      limits.linkedin_daily_application_limit;
    document.getElementById("limit-per-run").value =
      limits.job_max_applications;
    document.getElementById("limit-min-score").value = limits.job_min_score;
    document.getElementById("limit-suitability-score").value =
      limits.job_suitability_score;
    document.getElementById("limit-history-retention").value = String(
      limits.application_retention_days || 0
    );
    renderTotalBudget(status, limits.total_daily_application_limit);
    if (limits.llm_daily_cost_alert_usd != null) {
      document.getElementById("llm-alert-usd").value =
        limits.llm_daily_cost_alert_usd;
    }

    api("/api/usage").then((usage) => {
      const fmtTokens = (n) => n.toLocaleString("ru-RU");
      const fmtCost = (c) =>
        c === null ? "" : ` (~$${c.toFixed(3)})`;
      document.getElementById("usage-summary").textContent =
        `Сегодня: ${fmtTokens(usage.today_tokens)} токенов` +
        `${fmtCost(usage.today_cost_usd)} · Всего: ` +
        `${fmtTokens(usage.total_tokens)} токенов` +
        `${fmtCost(usage.total_cost_usd)}`;
      document.getElementById("usage-note").textContent = usage.partial
        ? "$-оценка неполная: часть моделей не в прайс-листе (только некоторые модели OpenAI)."
        : usage.total_cost_usd === null && usage.total_tokens > 0
          ? "$-оценка недоступна для используемой модели/провайдера — показаны только токены."
          : "";
      document.getElementById("llm-exhausted-banner").style.display = usage
        .llm_exhausted_today
        ? ""
        : "none";
    });

    // Карточка на площадку (тот же язык, что у "Обзора") + клик на
    // "Настроить" открывает боковую панель со всеми полями — вместо
    // одной широкой таблицы на 9 колонок, которая на узком окне не
    // читалась (см. Stripe/Linear/Vercel: список карточек со статусом
    // и быстрым тумблером снаружи, drawer с деталями по клику).
    const platformCards = document.getElementById("platform-cards");
    platformCards.innerHTML = status.sources
      .map((s, i) => {
        const missing = (s.readiness && s.readiness.missing) || [];
        const ready = s.readiness && s.readiness.ready;
        const readinessTitle = missing.length
          ? "Не хватает: " + missing.join(", ")
          : s.readiness && s.readiness.resume && s.readiness.resume.warning
            ? s.readiness.resume.warning
            : "Данных для подключения достаточно";
        return `
      <div class="source-card stagger-item" data-source="${s.name}" style="animation-delay:${staggerDelay(i, 25)}">
        <h3 title="${readinessTitle}">${ready ? "✅" : "⚠️"} ${sourceIconHtml(s.name)}${sourceLabel(s.name)}</h3>
        ${missing.length ? `<p class="muted small" style="margin:-6px 0 8px">${missing.join(", ")}</p>` : ""}
        <div class="row"><span>Расписание</span><span>${s.schedule_enabled ? `каждые ${s.interval_hours}ч` : "выключено"}</span></div>
        <div class="row"><span>Автоотклик</span><span>${s.auto_apply ? "включён" : "выключен"}</span></div>
        <div class="platform-card-quick">
          <label title="Бот проверяет по расписанию"><input type="checkbox" class="p-schedule-quick switch" data-source="${s.name}" ${s.schedule_enabled ? "checked" : ""} /> в расписании</label>
          <button type="button" class="btn btn-secondary btn-small p-open-drawer" data-source="${s.name}">⚙ Настроить</button>
        </div>
      </div>`;
      })
      .join("");

    platformCards.querySelectorAll(".p-schedule-quick").forEach((box) => {
      box.addEventListener("change", async () => {
        box.disabled = true;
        try {
          await api("/api/settings", {
            method: "POST",
            body: JSON.stringify({
              source: box.dataset.source,
              schedule_enabled: box.checked,
            }),
          });
          flashSaved(document.getElementById("settings-table"), null);
        } finally {
          box.disabled = false;
        }
      });
    });

    const linesOfEl = (el) =>
      el.value
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);

    function renderDrawerBody(s) {
      return `
        <div class="drawer-section">
          <h4>Расписание и отклик</h4>
          <div class="limits-grid">
            <label class="limit-field" style="justify-content:flex-end">
              <span style="display:flex;align-items:center;gap:8px"><input type="checkbox" class="d-schedule switch" ${s.schedule_enabled ? "checked" : ""} />Включена</span>
            </label>
            <label class="limit-field">
              <span>Интервал, ч</span>
              <input type="number" class="d-interval" min="1" value="${s.interval_hours ?? 3}" />
            </label>
            <label class="limit-field" style="justify-content:flex-end">
              <span style="display:flex;align-items:center;gap:8px"><input type="checkbox" class="d-auto switch" ${s.auto_apply ? "checked" : ""} />Откликается сам</span>
              <span class="muted small">Включено — бот сам отправляет отклики, до дневного лимита. Выключено — только ищет: вакансии появляются в «Вакансиях», откликаетесь вы.</span>
            </label>
            <label class="limit-field">
              <span>Resume ID</span>
              <input type="text" class="d-resume-id" value="${s.resume_id || ""}" placeholder="id резюме на площадке" />
            </label>
          </div>
        </div>

        <div class="drawer-section">
          <h4>Лимиты — своё значение для этой площадки</h4>
          <div class="limits-grid">
            <div class="override-field">
              <input type="number" class="d-max-applications" min="1"
                value="${s.job_max_applications_override ? s.job_max_applications : ""}"
                placeholder="${limits.job_max_applications}"
                ${s.job_max_applications_override ? "" : "disabled"} />
              <label class="override-toggle" title="Своё значение только для этой площадки — иначе используется дефолт из панели «Лимиты откликов»">
                <input type="checkbox" class="d-max-applications-override" ${s.job_max_applications_override ? "checked" : ""} /> за один заход
              </label>
            </div>
            <div class="override-field">
              <input type="number" class="d-daily-limit" min="1"
                value="${s.daily_limit_override ? s.daily_limit : ""}"
                placeholder="${s.name === "linkedin" ? limits.linkedin_daily_application_limit : limits.daily_application_limit}"
                ${s.daily_limit_override ? "" : "disabled"} />
              <label class="override-toggle" title="Своё значение только для этой площадки — иначе используется дефолт из панели «Лимиты откликов»">
                <input type="checkbox" class="d-daily-limit-override" ${s.daily_limit_override ? "checked" : ""} /> дневной лимит
              </label>
            </div>
          </div>
        </div>

        <div class="drawer-section">
          <h4>Фильтры</h4>
          <div class="limits-grid">
            <label class="limit-field">
              <span>Свои должности (пусто — общие из «Что ищу»)</span>
              <textarea class="d-positions" rows="2" placeholder="оставить пустым — использовать общие">${(s.positions_override || []).join("\n")}</textarea>
            </label>
            <label class="limit-field">
              <span>Свои локации (пусто — общие из «Что ищу»)</span>
              <textarea class="d-locations" rows="2" placeholder="оставить пустым — использовать общие">${(s.locations_override || []).join("\n")}</textarea>
            </label>
            ${
              s.name === "headhunter"
                ? `<label class="limit-field" style="justify-content:flex-end">
                <span style="display:flex;align-items:center;gap:8px"><input type="checkbox" class="d-auto-reply switch" ${s.auto_reply ? "checked" : ""} />Автоответ в чате HH</span>
              </label>
              <label class="limit-field" style="justify-content:flex-end">
                <span style="display:flex;align-items:center;gap:8px"><input type="checkbox" class="d-auto-bump switch" ${s.auto_bump_resume ? "checked" : ""} />Бамп резюме на HH</span>
              </label>
              <label class="limit-field">
                <span>Зарплата для автоответа в чате HH</span>
                <input type="text" class="d-hh-salary" value="${salary.hh_salary_expectations || ""}" placeholder="250000-300000 RUR" />
              </label>`
                : s.name === "djinni"
                  ? `<label class="limit-field" style="justify-content:flex-end">
                <span style="display:flex;align-items:center;gap:8px"><input type="checkbox" class="d-auto-bump switch" ${s.auto_bump_resume ? "checked" : ""} />Поднимать профиль раз в 7 дней</span>
                <span class="muted small">Кнопка «Bump My Profile» на Djinni — профиль снова наверху у рекрутеров. Бот нажимает её сам, как только Djinni разрешит.</span>
              </label>`
                  : ""
            }
            ${
              s.name === "linkedin"
                ? `<label class="limit-field">
                <span>Зарплата для скрининга LinkedIn (USD/год)</span>
                <input type="text" class="d-linkedin-salary" value="${salary.linkedin_salary_range_usd || ""}" placeholder="60000-80000" />
              </label>`
                : ""
            }
          </div>
          <p class="muted small">Сейчас реально ищет по: «${(s.effective_positions || []).join("», «") || "—"}»${
        s.name === "linkedin"
          ? " · локации LinkedIn настраиваются отдельно (linkedin.locations)"
          : `, локации: «${(s.effective_locations || []).join("», «") || "любые"}»`
      }.</p>
        </div>

        <div class="filters">
          <button class="btn btn-primary" id="platform-drawer-save">Сохранить</button>
          <span id="platform-drawer-status" class="muted small"></span>
        </div>`;
    }

    // Пришли с карточки на Главной (метка режима) — сразу открываем окно площадки.
    if (pendingPlatformDrawer) {
      const source = pendingPlatformDrawer;
      pendingPlatformDrawer = null;
      switchSettingsTab("settings-table");
      setTimeout(() => openPlatformDrawer(source));
    }
    function openPlatformDrawer(sourceName) {
      const s = status.sources.find((x) => x.name === sourceName);
      if (!s) return;
      document.getElementById("platform-drawer-title").innerHTML =
        `${sourceIconHtml(s.name)}${sourceLabel(s.name)}`;
      const drawerBody = document.getElementById("platform-drawer-body");
      drawerBody.innerHTML = renderDrawerBody(s);
      drawerBody
        .querySelectorAll(".d-positions, .d-locations")
        .forEach(initTagInput);
      // Тот же паттерн inherited/override, что в Stripe/AWS для
      // лимитов бюджета: чекбокс "своё" выключен → инпут задизейблен
      // и показывает дефолт как placeholder, не как значение.
      drawerBody
        .querySelectorAll(
          ".d-max-applications-override, .d-daily-limit-override"
        )
        .forEach((cb) => {
          cb.addEventListener("change", () => {
            const input = cb
              .closest(".override-field")
              .querySelector("input[type=number]");
            input.disabled = !cb.checked;
            if (cb.checked) input.focus();
          });
        });
      drawerBody
        .querySelector("#platform-drawer-save")
        .addEventListener("click", async () => {
          const jobMaxOverride = drawerBody.querySelector(
            ".d-max-applications-override"
          ).checked;
          const dailyOverride = drawerBody.querySelector(
            ".d-daily-limit-override"
          ).checked;
          const statusEl = drawerBody.querySelector("#platform-drawer-status");
          const autoReplyEl = drawerBody.querySelector(".d-auto-reply");
          const autoBumpEl = drawerBody.querySelector(".d-auto-bump");
          await api("/api/settings", {
            method: "POST",
            body: JSON.stringify({
              source: sourceName,
              schedule_enabled: drawerBody.querySelector(".d-schedule").checked,
              interval_hours: parseInt(
                drawerBody.querySelector(".d-interval").value,
                10
              ),
              auto_apply: drawerBody.querySelector(".d-auto").checked,
              resume_id: drawerBody.querySelector(".d-resume-id").value.trim(),
              // "своё" выключено → clear_* удаляет override в YAML,
              // площадка возвращается к общему дефолту (см.
              // unset_source_field на бэкенде); включено → пишем
              // введённое число как явное значение этой площадки.
              clear_job_max_applications: !jobMaxOverride,
              clear_daily_application_limit: !dailyOverride,
              positions: linesOfEl(drawerBody.querySelector(".d-positions")),
              locations: linesOfEl(drawerBody.querySelector(".d-locations")),
              ...(autoReplyEl ? { auto_reply: autoReplyEl.checked } : {}),
              ...(autoBumpEl ? { auto_bump_resume: autoBumpEl.checked } : {}),
              ...(jobMaxOverride
                ? {
                    job_max_applications: parseInt(
                      drawerBody.querySelector(".d-max-applications").value,
                      10
                    ),
                  }
                : {}),
              ...(dailyOverride
                ? {
                    daily_application_limit: parseInt(
                      drawerBody.querySelector(".d-daily-limit").value,
                      10
                    ),
                  }
                : {}),
            }),
          });
          const hhSalaryEl = drawerBody.querySelector(".d-hh-salary");
          const liSalaryEl = drawerBody.querySelector(".d-linkedin-salary");
          if (hhSalaryEl || liSalaryEl) {
            await api("/api/settings/salary", {
              method: "POST",
              body: JSON.stringify({
                ...(hhSalaryEl
                  ? { hh_salary_expectations: hhSalaryEl.value.trim() }
                  : {}),
                ...(liSalaryEl
                  ? { linkedin_salary_range_usd: liSalaryEl.value.trim() }
                  : {}),
              }),
            });
          }
          statusEl.textContent = "Сохранено";
          setTimeout(() => {
            closePlatformDrawer();
            render.settings();
          }, 500);
        });
      const overlay = document.getElementById("platform-drawer-overlay");
      overlay.style.display = "flex";
      trapFocus(document.getElementById("platform-drawer"));
    }

    platformCards.querySelectorAll(".p-open-drawer").forEach((btn) => {
      btn.addEventListener("click", () => openPlatformDrawer(btn.dataset.source));
    });
  },

  async telegram() {
    loadTelegramWatch();
    const [status, settings, conversations] = await Promise.all([
      api("/api/telegram/status"),
      api("/api/settings/telegram"),
      api("/api/telegram/conversations"),
    ]);

    const badge = document.getElementById("telegram-status-badge");
    const note = document.getElementById("telegram-status-note");
    // Ключи уже есть — поля не показываем, чтобы не путали.
    if (status.configured) {
      document.getElementById("tg-keys-row").outerHTML = `<div id="tg-keys-row" class="ok-text small">✓ Ключи сохранены</div>`;
    }
    if (!status.configured) {
      badge.className = "badge off";
      badge.innerHTML = '<span class="badge-dot"></span>не настроено';
      note.textContent =
        "Сначала шаг 1: вставьте api_id и api_hash ниже.";
    } else if (status.connected) {
      // Вход нужен один раз — дальше блок подключения свёрнут.
      document.getElementById("tg-connect-panel").open = false;
      badge.className = "badge on";
      badge.innerHTML = '<span class="badge-dot"></span>подключено';
      note.textContent = "";
    } else {
      badge.className = "badge off";
      badge.innerHTML = '<span class="badge-dot"></span>не авторизовано';
      note.textContent = "Введите номер телефона и код ниже.";
    }
    // Форма входа (телефон/код/пароль) нужна только пока не
    // подключено — если уже авторизовано, незачем занимать место и
    // сбивать с толку полем для повторного ввода номера.
    document.getElementById("telegram-login-row").style.display =
      status.connected ? "none" : "";
    if (status.connected) {
      document.getElementById("telegram-login-code-row").style.display =
        "none";
      document.getElementById("telegram-login-password-row").style.display =
        "none";
      document.getElementById("telegram-login-status").textContent = "";
    }

    fillTelegramRules(settings);

    const unreadCount = conversations.filter((c) => c.unread).length;
    const navBadge = document.getElementById("telegram-unread-badge");
    if (unreadCount > 0) {
      navBadge.textContent = String(unreadCount);
      navBadge.style.display = "";
    } else {
      navBadge.style.display = "none";
    }

    const list = document.getElementById("tg-conv-list");
    if (!conversations.length) {
      list.innerHTML = '<p class="muted small">Пока нет диалогов.</p>';
    } else {
      list.innerHTML = conversations
        .map(
          (c) => `
        <div class="conv-item${c.contact === activeTelegramContact ? " active" : ""}" data-contact="${c.contact}">
          <span class="conv-contact">${c.unread ? '<span class="conv-unread-dot"></span>' : ""}@${c.contact}</span>
          <span class="conv-preview">${c.last_message ? c.last_message.text : ""}</span>
        </div>`
        )
        .join("");
      list.querySelectorAll(".conv-item").forEach((el) => {
        el.addEventListener("click", () =>
          openTelegramConversation(el.dataset.contact)
        );
      });
    }

    if (activeTelegramContact) {
      await openTelegramConversation(activeTelegramContact);
    }
  },

  async logs() {
    const source = document.getElementById("log-source").value;
    const params = new URLSearchParams({ lines: "300" });
    if (source) params.set("source", source);
    const pre = document.getElementById("log-output");
    if (!logsLoaded) {
      pre.innerHTML = `<div class="skeleton" style="height:14px;width:90%;margin-bottom:8px"></div><div class="skeleton" style="height:14px;width:75%;margin-bottom:8px"></div><div class="skeleton" style="height:14px;width:85%"></div>`;
    }

    const data = await api(`/api/logs?${params}`);
    logsLoaded = true;

    // ponytail: тот же фикс — иначе pre.textContent сбрасывал
    // прокрутку и мигал на каждом опросе, даже если новых строк лога
    // не появилось.
    const logsSnapshot = JSON.stringify(data);
    if (logsSnapshot === lastLogsSnapshot) return;
    lastLogsSnapshot = logsSnapshot;

    if (data.note) {
      lastLogsLines = [];
      pre.textContent = data.note;
      return;
    }
    lastLogsLines = data.lines || [];
    renderLogLines();
  },
};

// Фильтр по тексту — чисто на клиенте: сервер и так уже отдаёт не
// больше 300 строк за раз, дозапрашивать их под каждую букву поиска
// незачем. Позиция прокрутки сохраняется при автообновлении раз в
// 7с, кроме случая "уже был внизу" — тогда новые строки уезжают вниз
// вместе с прокруткой, как ожидается от live-хвоста лога.
function renderLogLines() {
  const pre = document.getElementById("log-output");
  const query = document.getElementById("log-search").value.trim().toLowerCase();
  const lines = query
    ? lastLogsLines.filter((l) => l.toLowerCase().includes(query))
    : lastLogsLines;
  const wasAtBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 20;
  const prevScrollTop = pre.scrollTop;
  pre.textContent =
    lines.join("\n") || (query ? "(совпадений нет)" : "(пусто)");
  pre.scrollTop = wasAtBottom ? pre.scrollHeight : prevScrollTop;
}

// Фильтр чисто на клиенте, тот же подход, что и у "Логов" — список
// ответов работодателей не настолько большой, чтобы гонять фильтр на
// сервер под каждую букву поиска.
// Что произошло — человеческими словами, по этапу заявки.
const INBOX_KIND = {
  interview: { title: "🎉 Приглашение на интервью", group: "interview" },
  test_task: { title: "📝 Тестовое задание", group: "interview" },
  offer: { title: "💼 Оффер", group: "interview" },
  replied: { title: "💬 Ответили", group: "replied" },
  rejected: { title: "Отказ", group: "rejected" },
};
let repliesKind = "";

function renderRepliesRows() {
  const list = document.getElementById("replies-rows");
  const query = document.getElementById("replies-filter-query").value.trim().toLowerCase();
  const groupOf = (e) => (INBOX_KIND[e.stage] || INBOX_KIND.replied).group;
  const counts = { interview: 0, replied: 0, rejected: 0 };
  lastRepliesEntries.forEach((e) => counts[groupOf(e)]++);
  // По умолчанию — «Главное»: отказы не заслоняют приглашения и вопросы HR.
  const chips = [["", "Главное", counts.interview + counts.replied], ["interview", "Интервью и офферы", counts.interview], ["replied", "Ответили", counts.replied], ["rejected", "Отказы", counts.rejected]];
  const chipBox = document.getElementById("replies-kind");
  chipBox.innerHTML = chips
    .map(([k, label, n]) => `<button type="button" class="chip${k === repliesKind ? " active" : ""}" data-kind="${k}">${label} <b>${n}</b></button>`)
    .join("");
  chipBox.querySelectorAll("[data-kind]").forEach((b) =>
    b.addEventListener("click", () => {
      repliesKind = b.dataset.kind;
      renderRepliesRows();
    })
  );

  const entries = lastRepliesEntries.filter((e) => {
    if (repliesKind ? groupOf(e) !== repliesKind : groupOf(e) === "rejected") return false;
    if (!query) return true;
    return [e.company, e.title, e.text, e.contact].filter(Boolean).some((v) => v.toLowerCase().includes(query));
  });
  if (!lastRepliesEntries.length) {
    list.innerHTML = emptyStateHtml("Пока нет ответов. Как только работодатель ответит на отклик, в Telegram или на письмо — он появится здесь, а бот пришлёт уведомление.");
    return;
  }
  if (!entries.length) {
    list.innerHTML = emptyStateHtml(
      query ? "Ничего не найдено." : repliesKind ? "Здесь пока пусто." : "Сейчас нет новых приглашений и вопросов — бот сообщит, как только появятся. Отказы — в фильтре «Отказы»."
    );
    return;
  }
  const where = (e) =>
    e.channel === "telegram_dm" ? `${sourceIconHtml("telegram")}Telegram @${escapeHtml(e.contact)}`
    : e.channel === "email" ? `✉️ Письмо · ${escapeHtml(e.contact)}`
    : `${sourceIconHtml(e.source)}${escapeHtml(sourceLabel(e.source))}`;
  list.innerHTML = entries
    .map((e) => {
      const kind = INBOX_KIND[e.stage] || INBOX_KIND.replied;
      // Статус hh («Приглашение», «Отказ») уже сказан заголовком — не дублируем.
      const text = e.channel === "telegram_dm" || e.channel === "email" ? e.text : "";
      const who = [e.company, e.title].filter(Boolean).join(" — ");
      return `
      <div class="inbox-item inbox-${kind.group}${e.unread ? " is-unread" : ""}">
        <div class="inbox-top">
          <strong>${kind.title}</strong>
          <span class="muted small">${fmtTime(e.at)}${e.unread ? ` <span class="tab-badge">новое</span>` : ""}</span>
        </div>
        <div class="inbox-who">${e.link ? `<a href="${escapeHtml(e.link)}" target="_blank" rel="noopener">${escapeHtml(who || "Открыть")}</a>` : escapeHtml(who)}</div>
        <div class="muted small">${where(e)}${e.label ? ` · ${escapeHtml(e.label)}` : ""}</div>
        ${text ? `<p class="inbox-text">${escapeHtml(truncate(text, 280))}</p>` : ""}
        ${e.draft ? `<div class="ok-text small">✍️ Черновик ответа готов — вверху, в «Ждут вашего решения»</div>` : ""}
        <div class="inbox-actions">
          ${e.channel === "telegram_dm" ? `<button type="button" class="btn btn-secondary btn-small" data-open-dialog="${escapeHtml(e.contact)}">Открыть диалог</button>` : ""}
          ${e.channel === "email" ? `<a class="btn btn-secondary btn-small" href="${escapeHtml(e.link)}" target="_blank" rel="noopener">Открыть в Gmail</a>` : ""}
          ${kind.group === "interview" && e.external_id ? `<button type="button" class="btn btn-secondary btn-small" data-prep-source="${escapeHtml(e.source)}" data-prep-id="${escapeHtml(e.external_id)}" data-prep-title="${escapeHtml(who)}">🎯 Подготовиться к интервью</button>` : ""}
          ${e.external_id ? `<label class="muted small inbox-stage">Этап ${stageSelectHtml({ ...e, effective_stage: e.stage })}</label>` : ""}
        </div>
      </div>`;
    })
    .join("");
  list.querySelectorAll("[data-open-dialog]").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab("telegram");
      openTelegramConversation(btn.dataset.openDialog);
    });
  });
  list.querySelectorAll("[data-prep-id]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "Готовлю справку…";
      try {
        const { prep } = await api("/api/applications/prep", {
          method: "POST",
          body: JSON.stringify({ source: btn.dataset.prepSource, external_id: btn.dataset.prepId }),
        });
        openTextModal(`Подготовка: ${btn.dataset.prepTitle}`, "Справка к интервью", prep.replace(/\*\*/g, ""));
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error");
      } finally {
        btn.disabled = false;
        btn.textContent = "🎯 Подготовиться к интервью";
      }
    })
  );
  bindStageSelects(list);
}

async function openTelegramConversation(contact) {
  activeTelegramContact = contact;
  document
    .querySelectorAll("#tg-conv-list .conv-item")
    .forEach((el) =>
      el.classList.toggle("active", el.dataset.contact === contact)
    );

  const conv = await api(`/api/telegram/conversations/${contact}`);
  document.getElementById("tg-chat-empty").style.display = "none";
  document.getElementById("tg-chat-panel").style.display = "";
  document.getElementById("tg-chat-contact").textContent = `@${contact}`;

  const messages = document.getElementById("tg-chat-messages");
  messages.innerHTML = conv.messages
    .map(
      (m) => `
    <div class="chat-bubble ${m.direction}">
      ${m.text.replace(/</g, "&lt;")}
      <span class="chat-bubble-time">${formatChatTime(m.at)}</span>
    </div>`
    )
    .join("");
  messages.scrollTop = messages.scrollHeight;

  // Открытие треда гасит бейдж "непрочитано" на бэкенде (см.
  // get_telegram_conversation) — обновляем счётчик в шапке вкладки,
  // не дожидаясь следующего полного render.telegram().
  const navBadge = document.getElementById("telegram-unread-badge");
  const remaining = document.querySelectorAll(
    "#tg-conv-list .conv-unread-dot"
  ).length;
  const dot = document.querySelector(
    `#tg-conv-list .conv-item[data-contact="${contact}"] .conv-unread-dot`
  );
  if (dot) {
    dot.remove();
    const left = remaining - 1;
    if (left > 0) {
      navBadge.textContent = String(left);
    } else {
      navBadge.style.display = "none";
    }
  }
}

async function pollGenerateStatus() {
  const statusEl = document.getElementById("gen-status");
  const downloadEl = document.getElementById("gen-download");
  const progressEl = document.getElementById("gen-progress");
  for (;;) {
    const result = await api("/api/generate/status");
    if (!result.running) {
      progressEl.classList.remove("active");
      if (result.error) {
        statusEl.textContent = `Ошибка: ${result.error}`;
        downloadEl.style.display = "none";
        showToast("Не удалось сгенерировать документ", "error");
      } else if (result.ready) {
        statusEl.textContent = "Готово.";
        downloadEl.style.display = "";
        showToast("Документ готов", "success");
      }
      return;
    }
    statusEl.textContent = "Генерация (может занять до минуты)…";
    progressEl.classList.add("active");
    await new Promise((r) => setTimeout(r, 2000));
  }
}

async function startGenerate(kind) {
  const statusEl = document.getElementById("gen-status");
  const downloadEl = document.getElementById("gen-download");
  const progressEl = document.getElementById("gen-progress");
  const styleName = document.getElementById("gen-style").value || null;
  const jobUrl = document.getElementById("gen-job-url").value.trim() || null;
  if (kind !== "resume" && !jobUrl) {
    showToast("Укажите ссылку на вакансию.", "error");
    return;
  }
  downloadEl.style.display = "none";
  statusEl.textContent = "Запуск…";
  progressEl.classList.add("active");
  try {
    await api(`/api/generate/${kind}`, {
      method: "POST",
      body: JSON.stringify({ style_name: styleName, job_url: jobUrl }),
    });
  } catch (e) {
    statusEl.textContent = `Ошибка: ${e.message}`;
    progressEl.classList.remove("active");
    return;
  }
  pollGenerateStatus();
}

async function pollResumeAuditStatus() {
  const statusEl = document.getElementById("gen-status");
  const progressEl = document.getElementById("gen-progress");
  for (;;) {
    const result = await api("/api/generate/status");
    if (!result.running) {
      progressEl.classList.remove("active");
      if (result.error) {
        statusEl.textContent = `Ошибка: ${result.error}`;
        showToast("Не удалось выполнить аудит резюме", "error");
      } else if (result.ready && result.result) {
        statusEl.textContent = "Готово.";
        showToast("Аудит резюме готов", "success");
        openResumeAuditModal(result.result);
      }
      return;
    }
    statusEl.textContent = "Аудит резюме (3 шага, может занять до минуты)…";
    progressEl.classList.add("active");
    await new Promise((r) => setTimeout(r, 2000));
  }
}

async function startResumeAudit() {
  const statusEl = document.getElementById("gen-status");
  const downloadEl = document.getElementById("gen-download");
  const progressEl = document.getElementById("gen-progress");
  const jobUrl = document.getElementById("gen-job-url").value.trim() || null;
  if (!jobUrl) {
    showToast("Укажите ссылку на вакансию.", "error");
    return;
  }
  downloadEl.style.display = "none";
  statusEl.textContent = "Запуск…";
  progressEl.classList.add("active");
  try {
    await api("/api/generate/resume-audit", {
      method: "POST",
      body: JSON.stringify({ job_url: jobUrl }),
    });
  } catch (e) {
    statusEl.textContent = `Ошибка: ${e.message}`;
    progressEl.classList.remove("active");
    return;
  }
  pollResumeAuditStatus();
}

function resumeAuditScoreClass(score) {
  if (score >= 75) return "ok";
  if (score >= 50) return "warn";
  return "err";
}

function resumeAuditScoreLabel(score) {
  if (score >= 75) return "Сильное совпадение";
  if (score >= 50) return "Среднее совпадение";
  return "Слабое совпадение";
}

function setResumeAuditBadge(el, text, cls) {
  el.className = `badge ${cls}`;
  el.innerHTML = `<span class="badge-dot"></span>${escapeHtml(text)}`;
}

function renderResumeAuditList(el, items) {
  el.innerHTML = (items || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
}

function renderResumeAuditChips(el, items) {
  el.innerHTML = (items || [])
    .map((item) => `<span class="chip">${escapeHtml(item)}</span>`)
    .join("");
}

function openResumeAuditModal(result) {
  document.getElementById("resume-audit-meta").textContent =
    document.getElementById("gen-job-url").value.trim();

  const audit = result.audit || {};
  const ats = result.ats_hiring_manager || {};
  const score = audit.match_score ?? 0;
  const scoreClass = resumeAuditScoreClass(score);

  document.getElementById("resume-audit-score-value").textContent = score;
  document.getElementById("resume-audit-score-label").textContent =
    resumeAuditScoreLabel(score);
  const meterFill = document.getElementById("resume-audit-meter-fill");
  meterFill.className = `meter-fill ${scoreClass}`;
  meterFill.style.width = `${Math.max(0, Math.min(100, score))}%`;

  setResumeAuditBadge(
    document.getElementById("resume-audit-ats-badge"),
    ats.ats_pass ? "Пройдёт ATS" : "Не пройдёт ATS",
    ats.ats_pass ? "ok" : "err"
  );
  const bucketClass =
    ats.hiring_manager_bucket === "да"
      ? "ok"
      : ats.hiring_manager_bucket === "возможно"
        ? "warn"
        : "err";
  setResumeAuditBadge(
    document.getElementById("resume-audit-bucket-badge"),
    `Менеджер по найму: ${ats.hiring_manager_bucket || "—"}`,
    bucketClass
  );

  document.getElementById("resume-audit-comparison-note").textContent =
    audit.comparison_note || "";
  renderResumeAuditList(
    document.getElementById("resume-audit-red-flags"),
    audit.red_flags
  );
  renderResumeAuditChips(
    document.getElementById("resume-audit-missing-keywords"),
    audit.missing_keywords
  );
  renderResumeAuditList(
    document.getElementById("resume-audit-strong-sections"),
    audit.strong_sections
  );
  renderResumeAuditList(
    document.getElementById("resume-audit-weak-sections"),
    audit.weak_sections
  );
  renderResumeAuditList(
    document.getElementById("resume-audit-formatting-issues"),
    ats.formatting_issues
  );
  document.getElementById("resume-audit-rewrite-body").textContent =
    result.rewritten_experience || "";

  const overlay = document.getElementById("resume-audit-overlay");
  overlay.style.display = "flex";
  trapFocus(overlay);
}

function closeResumeAuditModal() {
  const overlay = document.getElementById("resume-audit-overlay");
  if (overlay.style.display === "none") return;
  overlay.style.display = "none";
  releaseFocusTrap(overlay);
}

function isResumeAuditModalOpen() {
  return document.getElementById("resume-audit-overlay").style.display !== "none";
}

// Настройки → «Сайты компаний»: переключатели и список компаний.
async function loadDirectSettings() {
  const d = await api("/api/direct/summary");
  document.getElementById("direct-wwr").checked = d.wwr;
  document.getElementById("direct-hn").checked = d.hn;
  loadDirectCompanies();
}

async function saveDirectSetting(e) {
  const field = { "direct-wwr": "wwr", "direct-hn": "hn" }[e.target.id];
  if (!field) return;
  try {
    await api("/api/direct/settings", { method: "POST", body: JSON.stringify({ [field]: e.target.checked }) });
    showToast("Сохранено", "success");
  } catch (err) {
    e.target.checked = !e.target.checked;
    showToast(err.message.replace(/^\d+: /, ""), "error");
  }
}

async function loadDirectCompanies() {
  const list = document.getElementById("direct-companies");
  const companies = await api("/api/direct/companies");
  list.innerHTML = companies.length
    ? companies
        .map(
          (c) => `
      <div class="company-row">
        <span><strong>${escapeHtml(c.name)}</strong> <span class="muted small">${escapeHtml(c.ats)} / ${escapeHtml(c.slug)}</span></span>
        <button type="button" class="btn btn-ghost btn-small" data-company-delete="${escapeHtml(c.slug)}">Удалить</button>
      </div>`
        )
        .join("")
    : emptyStateHtml("Пока нет компаний — добавьте сайт компании выше.");
  list.querySelectorAll("[data-company-delete]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api(`/api/direct/companies/${encodeURIComponent(btn.dataset.companyDelete)}`, { method: "DELETE" });
      loadDirectCompanies();
    });
  });
}

async function addDirectCompany() {
  const status = document.getElementById("direct-company-status");
  const website = document.getElementById("direct-company-website").value.trim();
  const name = document.getElementById("direct-company-name").value.trim();
  if (!website) return;
  status.textContent = "Ищу систему найма на сайте…";
  try {
    const c = await api("/api/direct/companies", {
      method: "POST",
      body: JSON.stringify({ website, name }),
    });
    status.textContent = `✓ ${c.name}: ${c.ats}, открытых вакансий ${c.jobs}`;
    document.getElementById("direct-company-website").value = "";
    document.getElementById("direct-company-name").value = "";
    loadDirectCompanies();
  } catch (err) {
    status.textContent = err.message.replace(/^\d+: /, "");
  }
}

function switchSettingsTab(paneId) {
  if (paneId === "settings-direct") loadDirectSettings().catch(() => {});
  document
    .querySelectorAll("#settings-jump button")
    .forEach((b) => b.classList.toggle("active", b.dataset.settingsTab === paneId));
  document.querySelectorAll(".settings-pane").forEach((pane) => {
    const isTarget = pane.id === paneId;
    pane.classList.toggle("active", isTarget);
    if (isTarget && window.gsap && !REDUCE_MOTION) {
      gsap.fromTo(
        pane,
        { opacity: 0, y: 6 },
        { opacity: 1, y: 0, duration: 0.28, ease: "power2.out" }
      );
    }
  });
  moveTabIndicator(
    document.getElementById("settings-tab-indicator"),
    settingsTabAnchor(document.querySelector(`#settings-jump button[data-settings-tab="${paneId}"]`))
  );
}

// Вкладка из меню «Ещё» — подсвечиваем само «Ещё» и закрываем меню.
function settingsTabAnchor(btn) {
  const more = btn?.closest(".settings-more");
  if (!more) {
    document.querySelector(".settings-more > summary")?.classList.remove("active");
    return btn;
  }
  more.open = false;
  const summary = more.querySelector("summary");
  summary.classList.add("active");
  return summary;
}

// Провайдеров стало 14 — большинство пользователей смотрят только на
// активный + уже настроенные с ключом, остальные шумят на экране.
// Сворачиваем неактивные/без ключа за кнопку "Показать все", если
// пользователь сам не развернул список.
function updateProviderVisibility() {
  const grid = document.getElementById("provider-grid");
  const toggle = document.getElementById("provider-grid-toggle");
  if (!grid || !toggle) return;
  let hiddenCount = 0;
  grid.querySelectorAll(".provider-card").forEach((card) => {
    const keep = card.classList.contains("active") || card.classList.contains("has-key");
    card.classList.toggle("provider-hideable", !keep);
    if (!keep) hiddenCount += 1;
  });
  if (hiddenCount === 0) {
    toggle.style.display = "none";
    grid.classList.remove("collapsed");
    return;
  }
  toggle.style.display = "";
  if (toggle.dataset.expanded !== "1") {
    toggle.textContent = `Показать все провайдеры (+${hiddenCount})`;
  }
}

// Тот же концентрический мотив, что в лого (brand-mark) — приглушённый
// и без ядра, чтобы empty-state читался как "эхо" бренда, а не
// дженерик-иконка пустой коробки, как раньше.
function emptyStateHtml(message) {
  return `<div class="empty-state">
    <svg viewBox="0 0 40 40" fill="none" width="36" height="36">
      <circle cx="20" cy="20" r="17" stroke="currentColor" stroke-width="1.6" stroke-dasharray="3 4" opacity="0.3"/>
      <circle cx="20" cy="20" r="10" stroke="currentColor" stroke-width="1.6" opacity="0.35"/>
    </svg>
    <p>${escapeHtml(message)}</p>
  </div>`;
}

function showToast(message, type = "info", duration = 3500) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="toast-dot"></span><span>${escapeHtml(message)}</span>`;
  container.appendChild(el);
  if (window.gsap && !REDUCE_MOTION) {
    gsap.fromTo(el, { opacity: 0, x: 24 }, { opacity: 1, x: 0, duration: 0.3, ease: "power2.out" });
  }
  setTimeout(() => {
    if (window.gsap && !REDUCE_MOTION) {
      gsap.to(el, { opacity: 0, x: 24, duration: 0.25, ease: "power2.in", onComplete: () => el.remove() });
    } else {
      el.remove();
    }
  }, duration);
}

// Общий плавающий индикатор для sidebar-nav и вкладок настроек — вместо
// мгновенной смены фона у активной кнопки, полоска физически едет к ней.
// CSS transition, не GSAP — двигать плоский прямоугольник по позиции
// умеет сам браузер без тикера requestAnimationFrame, а motion-reduce
// уже глобально обнулён через prefers-reduced-motion в style.css.
function moveTabIndicator(indicator, btn) {
  if (!indicator || !btn) return;
  // Относительно контейнера самого индикатора — кнопка может быть
  // вложена глубже (меню «Ещё» в настройках).
  const parentRect = indicator.parentElement.getBoundingClientRect();
  const btnRect = btn.getBoundingClientRect();
  const x = btnRect.left - parentRect.left;
  const y = btnRect.top - parentRect.top;
  indicator.style.transform = `translate(${x}px, ${y}px)`;
  indicator.style.width = `${btnRect.width}px`;
  indicator.style.height = `${btnRect.height}px`;
  indicator.style.opacity = "1";
}

function repositionTabIndicators() {
  moveTabIndicator(
    document.getElementById("nav-tab-indicator"),
    document.querySelector("nav.tabs button.active")
  );
  moveTabIndicator(
    document.getElementById("settings-tab-indicator"),
    settingsTabAnchor(document.querySelector("#settings-jump button.active"))
  );
}

// Вкладки без понятия "сохранить" — не размечаем как "не сохранено",
// там нет настройки, которая могла бы потеряться. Сейчас пусто:
// «Резюме на hh.ru» переехало в раздел «Резюме» (вне #view-settings,
// эта система его не касается), а «Площадки» теперь редактируются
// через drawer, который сам управляет своим статусом сохранения.
const SETTINGS_PANES_WITHOUT_SAVE = new Set();

function markSettingsDirty(pane) {
  if (!pane || SETTINGS_PANES_WITHOUT_SAVE.has(pane.id)) return;
  const tab = document.querySelector(`#settings-jump button[data-settings-tab="${pane.id}"]`);
  if (tab) tab.classList.add("dirty");
}

function flashSaved(pane, btn) {
  if (!pane) return;
  const tab = document.querySelector(`#settings-jump button[data-settings-tab="${pane.id}"]`);
  if (tab) tab.classList.remove("dirty");
  if (!btn) return;
  btn.classList.remove("save-flash");
  void btn.offsetWidth;
  btn.classList.add("save-flash");
}

// Автосохранение: любое изменение в разделе сохраняется само через
// секунду — кнопкой «Сохранить» этого раздела. Ключи и пароли (ИИ,
// Telegram) — с явной кнопкой, их вводят один раз и ждут подтверждения.
const AUTOSAVE = [
  ["settings-search", "search-save"],
  ["settings-limits", "limits-save"],
  ["settings-tg-quick", "tgq-save"],
  ["settings-outreach", "outreach-save"],
  ["tg-rules-panel", "tg-settings-save"],
];

function initAutosave() {
  AUTOSAVE.forEach(([paneId, btnId]) => {
    const pane = document.getElementById(paneId);
    const btn = document.getElementById(btnId);
    if (!pane || !btn) return;
    btn.hidden = true;
    const note = document.createElement("span");
    note.className = "muted small autosave-note";
    note.textContent = "Изменения сохраняются сами";
    btn.after(note);
    let timer = null;
    pane.addEventListener("change", (e) => {
      if (e.target.type === "file") return;
      if (pane.dataset.needsLoad && pane.dataset.loaded !== "1") return; // ещё не загрузили
      clearTimeout(timer);
      note.textContent = "Сохраняю…";
      timer = setTimeout(() => {
        btn.click();
        setTimeout(() => (note.textContent = "✓ Сохранено"), 700);
      }, 900);
    });
  });
}

function initSettingsDirtyTracking() {
  const settingsView = document.getElementById("view-settings");
  if (!settingsView) return;
  ["input", "change"].forEach((evt) => {
    settingsView.addEventListener(evt, (e) => {
      markSettingsDirty(e.target.closest(".settings-pane"));
    });
  });
  settingsView.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const isSaveBtn = btn.id.includes("save") || btn.classList.contains("s-save");
    if (!isSaveBtn) return;
    const pane = btn.closest(".settings-pane");
    btn.classList.add("is-loading");
    setTimeout(() => btn.classList.remove("is-loading"), 350);
    flashSaved(pane, btn);
    // Клик снимает "не сохранено" сразу — отзывчивее, чем ждать ответ
    // сервера. Но если рядом всё же выскочило "Ошибка: …", честно
    // возвращаем метку "не сохранено" вместо того чтобы соврать об успехе.
    setTimeout(() => {
      const statusEl = pane?.querySelector('[id$="-status"]');
      if (statusEl && /ошибка/i.test(statusEl.textContent || "")) {
        markSettingsDirty(pane);
      }
    }, 800);
  });
}

function toggleSidebarCollapse() {
  const sidebar = document.querySelector(".sidebar");
  const collapsed = sidebar.classList.toggle("collapsed");
  localStorage.setItem("cj-sidebar-collapsed", collapsed ? "1" : "0");
  requestAnimationFrame(repositionTabIndicators);
}

function initSidebarCollapse() {
  const sidebar = document.querySelector(".sidebar");
  if (localStorage.getItem("cj-sidebar-collapsed") === "1") {
    sidebar.classList.add("collapsed");
  }
  document
    .getElementById("sidebar-collapse-toggle")
    .addEventListener("click", toggleSidebarCollapse);
}

// ---------- Командная палитра ----------

let commandActiveIndex = 0;

function collectCommandItems(query) {
  const items = [];
  Object.values(NAV_GROUPS)
    .flat()
    .forEach(([view, label]) => {
      items.push({ label, hint: "Раздел", action: () => switchTab(view) });
    });
  document.querySelectorAll("#settings-jump button[data-settings-tab]").forEach((btn) => {
    items.push({
      label: `Настройки → ${btn.textContent}`,
      hint: "Вкладка",
      action: () => {
        switchTab("settings");
        switchSettingsTab(btn.dataset.settingsTab);
      },
    });
  });
  // Записи Истории ищем только когда уже что-то введено — иначе список
  // из сотен вакансий забивал бы палитру при открытии пустой.
  const q = (query || "").trim().toLowerCase();
  if (q.length >= 2) {
    lastHistoryEntries
      .filter(
        (e) =>
          e.company.toLowerCase().includes(q) || e.title.toLowerCase().includes(q)
      )
      .slice(0, 8)
      .forEach((e) => {
        items.push({
          label: `${e.company} — ${e.title}`,
          hint: sourceLabel(e.source),
          action: () => {
            document.getElementById("filter-source").value = "";
            document.getElementById("filter-query").value = e.company;
            switchTab("history");
          },
        });
      });
  }
  return items;
}

function updateCommandActive(results) {
  results.querySelectorAll(".command-item").forEach((el, i) => {
    el.classList.toggle("active", i === commandActiveIndex);
  });
}

function renderCommandResults(query) {
  const results = document.getElementById("command-results");
  const items = collectCommandItems(query).filter((it) =>
    it.label.toLowerCase().includes(query.toLowerCase())
  );
  commandActiveIndex = 0;
  results.__items = items;
  if (!items.length) {
    results.innerHTML = `<div class="command-empty">Ничего не найдено</div>`;
    return;
  }
  results.innerHTML = items
    .map(
      (it, i) =>
        `<div class="command-item${i === 0 ? " active" : ""}" data-index="${i}"><span>${escapeHtml(it.label)}</span><span class="muted">${it.hint}</span></div>`
    )
    .join("");
  results.querySelectorAll(".command-item").forEach((el, i) => {
    el.addEventListener("click", () => {
      items[i].action();
      closeCommandPalette();
    });
  });
}

// Общий focus trap для модалок-оверлеев — Tab не должен уводить
// фокус на затемнённый фон позади, а закрытие возвращает фокус туда,
// откуда открыли (иначе клавиатурный пользователь теряет место).
const _focusTrapRelease = new WeakMap();

function trapFocus(container) {
  const focusableSelector =
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  const previouslyFocused = document.activeElement;
  const getFocusable = () =>
    Array.from(container.querySelectorAll(focusableSelector)).filter(
      (el) => el.offsetParent !== null
    );

  function onKeydown(e) {
    if (e.key !== "Tab") return;
    const focusable = getFocusable();
    if (!focusable.length) {
      e.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  container.addEventListener("keydown", onKeydown);
  const focusable = getFocusable();
  (focusable[0] || container).focus();

  const release = () => {
    container.removeEventListener("keydown", onKeydown);
    if (previouslyFocused && typeof previouslyFocused.focus === "function") {
      previouslyFocused.focus();
    }
  };
  _focusTrapRelease.set(container, release);
  return release;
}

function releaseFocusTrap(container) {
  const release = _focusTrapRelease.get(container);
  if (release) {
    _focusTrapRelease.delete(container);
    release();
  }
}

function openCommandPalette() {
  const overlay = document.getElementById("command-overlay");
  const input = document.getElementById("command-input");
  overlay.style.display = "flex";
  input.value = "";
  renderCommandResults("");
  trapFocus(overlay);
  input.focus();
}

function closeCommandPalette() {
  const overlay = document.getElementById("command-overlay");
  overlay.style.display = "none";
  releaseFocusTrap(overlay);
}

function isCommandPaletteOpen() {
  return document.getElementById("command-overlay").style.display !== "none";
}

// Свой modal вместо нативного confirm() — та же причина, что и с
// alert(): системный диалог браузера ломает визуальный язык
// приложения. Промис резолвится true/false, вызывающий код просто
// делает await вместо if(confirm(...)).
function showConfirm(message) {
  const overlay = document.getElementById("confirm-overlay");
  document.getElementById("confirm-message").textContent = message;
  overlay.style.display = "flex";
  return new Promise((resolve) => {
    const okBtn = document.getElementById("confirm-ok");
    const cancelBtn = document.getElementById("confirm-cancel");
    const cleanup = (result) => {
      overlay.style.display = "none";
      releaseFocusTrap(overlay);
      okBtn.removeEventListener("click", onOk);
      cancelBtn.removeEventListener("click", onCancel);
      overlay.removeEventListener("click", onOverlay);
      document.removeEventListener("keydown", onKey);
      resolve(result);
    };
    const onOk = () => cleanup(true);
    const onCancel = () => cleanup(false);
    const onOverlay = (e) => {
      if (e.target === overlay) cleanup(false);
    };
    const onKey = (e) => {
      if (e.key === "Escape") cleanup(false);
      if (e.key === "Enter") cleanup(true);
    };
    okBtn.addEventListener("click", onOk);
    cancelBtn.addEventListener("click", onCancel);
    overlay.addEventListener("click", onOverlay);
    document.addEventListener("keydown", onKey);
    trapFocus(overlay);
  });
}

function initCommandPalette() {
  const overlay = document.getElementById("command-overlay");
  const input = document.getElementById("command-input");
  input.addEventListener("input", () => renderCommandResults(input.value));
  input.addEventListener("keydown", (e) => {
    const results = document.getElementById("command-results");
    const items = results.__items || [];
    if (e.key === "ArrowDown") {
      e.preventDefault();
      commandActiveIndex = Math.min(commandActiveIndex + 1, items.length - 1);
      updateCommandActive(results);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      commandActiveIndex = Math.max(commandActiveIndex - 1, 0);
      updateCommandActive(results);
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (items[commandActiveIndex]) {
        items[commandActiveIndex].action();
        closeCommandPalette();
      }
    } else if (e.key === "Escape") {
      closeCommandPalette();
    }
  });
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) closeCommandPalette();
  });

  const shortcutsOverlay = document.getElementById("shortcuts-overlay");
  shortcutsOverlay.addEventListener("click", (e) => {
    if (e.target === shortcutsOverlay) closeShortcutsOverlay();
  });
  document.getElementById("shortcuts-close").addEventListener("click", closeShortcutsOverlay);

  const coverLetterOverlay = document.getElementById("cover-letter-overlay");
  coverLetterOverlay.addEventListener("click", (e) => {
    if (e.target === coverLetterOverlay) closeCoverLetterModal();
  });
  document
    .getElementById("cover-letter-close")
    .addEventListener("click", closeCoverLetterModal);

  const resumeAuditOverlay = document.getElementById("resume-audit-overlay");
  resumeAuditOverlay.addEventListener("click", (e) => {
    if (e.target === resumeAuditOverlay) closeResumeAuditModal();
  });
  document
    .getElementById("resume-audit-close")
    .addEventListener("click", closeResumeAuditModal);
  document
    .getElementById("resume-audit-copy-rewrite")
    .addEventListener("click", (e) => {
      const text = document.getElementById("resume-audit-rewrite-body").textContent;
      copyToClipboard(text, e.currentTarget);
    });

  const platformDrawerOverlay = document.getElementById("platform-drawer-overlay");
  platformDrawerOverlay.addEventListener("click", (e) => {
    if (e.target === platformDrawerOverlay) closePlatformDrawer();
  });
  document
    .getElementById("platform-drawer-close")
    .addEventListener("click", closePlatformDrawer);
}

function closePlatformDrawer() {
  const overlay = document.getElementById("platform-drawer-overlay");
  if (overlay.style.display === "none") return;
  overlay.style.display = "none";
  releaseFocusTrap(document.getElementById("platform-drawer"));
}

function isPlatformDrawerOpen() {
  return document.getElementById("platform-drawer-overlay").style.display !== "none";
}

// Дополнительные действия строки "Истории" — в одном выпадающем меню,
// а не 4-5 кнопок в ячейке.
function rowActionsHtml(e, i) {
  const actions = [];
  if (e.effective_stage === "interview") {
    actions.push(
      `<button type="button" data-prep-btn data-row-index="${i}">🎯 Подготовка к интервью</button>`,
      `<button type="button" data-trainer-btn data-row-index="${i}">🎤 Тренажёр</button>`,
      `<button type="button" data-calendar-btn data-row-index="${i}">📅 В календарь</button>`
    );
  }
  if (e.source === "direct" && e.status === "dry_run" && /greenhouse\.io|lever\.co/.test(e.link)) {
    actions.push(`<button type="button" data-prefill-btn data-row-index="${i}">✍️ Заполнить форму отклика</button>`);
  }
  if (e.company) {
    actions.push(`<button type="button" data-find-hr data-row-index="${i}">👤 Найти HR этой компании</button>`);
  }
  if (e.contacts && e.contacts.length) {
    actions.push(
      ...e.contacts.map((c) => `<a href="mailto:${escapeHtml(c)}">✉️ ${escapeHtml(c)}</a>`)
    );
  }
  if (!actions.length) return "";
  return `<details class="row-actions"><summary>Действия ▾</summary><div class="row-actions-menu">${actions.join("")}</div></details>`;
}

// Очередь "Ждут вашего решения" — все черновики (ответы и напоминания в
// Telegram, письма HR): правка текста, отправить или пропустить.
async function renderDraftsQueue() {
  const el = document.getElementById("drafts-queue");
  const drafts = await api("/api/hr-drafts");
  if (!drafts.length) {
    el.style.display = "none";
    return;
  }
  const KIND = { reply: "Ответ HR", follow_up: "Напоминание", email: "Письмо HR" };
  el.style.display = "";
  el.innerHTML = `
    <h3 style="margin-top:0">Ждут вашего решения · ${drafts.length}</h3>
    ${drafts
      .map(
        (d) => `
      <div class="hr-draft" data-draft-code="${escapeHtml(d.code)}">
        <div class="muted small">
          ${d.channel === "email" ? "✉️" : "✈️"} ${KIND[d.kind] || "Сообщение"} →
          ${d.channel === "email" ? escapeHtml(d.contact) : "@" + escapeHtml(d.contact)}
          ${d.company ? ` · ${escapeHtml(d.company)}${d.title ? " — " + escapeHtml(d.title) : ""}` : ""}
          ${d.job_link ? ` · <a href="${escapeHtml(d.job_link)}" target="_blank" rel="noopener">вакансия</a>` : ""}
        </div>
        <textarea rows="4" aria-label="Текст черновика">${escapeHtml(d.text)}</textarea>
        <div>
          <button type="button" class="btn btn-primary btn-small" data-draft-send>Отправить</button>
          <button type="button" class="btn btn-ghost btn-small" data-draft-skip>Пропустить</button>
        </div>
      </div>`
      )
      .join("")}`;
  el.querySelectorAll("[data-draft-code]").forEach((box) => {
    const code = box.dataset.draftCode;
    box.querySelector("[data-draft-send]").addEventListener("click", async (ev) => {
      ev.target.disabled = true;
      try {
        const res = await api(`/api/hr-drafts/${code}/send`, {
          method: "POST",
          body: JSON.stringify({ text: box.querySelector("textarea").value }),
        });
        showToast(res.message, "success");
        renderDraftsQueue();
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error");
        ev.target.disabled = false;
      }
    });
    box.querySelector("[data-draft-skip]").addEventListener("click", async () => {
      await api(`/api/hr-drafts/${code}/skip`, { method: "POST" });
      renderDraftsQueue();
    });
  });
}

// «Сегодня: 12 из 25 · разогрев, день 3 · отправка будни 9–19».
function mailPlanText(p) {
  if (!p) return "";
  const warm = p.warmup && p.limit < p.daily_limit ? ` (разогрев, день ${p.warmup_day} — до ${p.daily_limit} дойдёт постепенно)` : "";
  const when = `${p.weekdays_only ? "будни" : "каждый день"} ${p.send_from}:00–${p.send_to}:00`;
  return `Сегодня отправлено ${p.sent_today} из ${p.limit}${warm} · отправка: ${when}${p.can_send ? "" : ` · ⏸ ${p.reason}`}`;
}

async function loadOutreachSettings() {
  const s = await api("/api/settings/outreach");
  document.getElementById("outreach-email").value = s.email_address;
  document.getElementById("outreach-app-password").value = "";
  document.getElementById("outreach-app-password").placeholder = s.email_connected
    ? "Пароль сохранён — введите новый, чтобы заменить"
    : "Пароль приложения (16 символов)";
  document.getElementById("outreach-email-status").textContent = s.email_connected
    ? `✅ Почта подключена: ${s.email_address}`
    : "Почта не подключена — письма HR будут только черновиками для ручной отправки.";
  document.getElementById("outreach-hunter-status").textContent = s.hunter_preview
    ? `сохранён: ${s.hunter_preview}`
    : "не задан";
  document.getElementById("outreach-email-limit").value = s.email_daily_limit;
  document.getElementById("outreach-send-from").value = s.send_from;
  document.getElementById("outreach-send-to").value = s.send_to;
  document.getElementById("outreach-weekdays").checked = s.weekdays_only;
  document.getElementById("outreach-warmup").checked = s.warmup;
  document.getElementById("outreach-guard-status").textContent = mailPlanText(s.mail_plan);
  document.getElementById("outreach-follow-up").value = s.follow_up_days;
  document.getElementById("outreach-digest").checked = s.digest_enabled;
  document.getElementById("outreach-digest-hour").value = s.digest_hour;
  document.getElementById("digest-quiet").checked = s.digest_quiet;
  document.getElementById("outreach-skip-us").checked = s.skip_us_only;
  document.getElementById("outreach-skip-eu").checked = s.skip_europe_only;
}

async function saveOutreachSettings() {
  const status = document.getElementById("outreach-save-status");
  const num = (id) => parseInt(document.getElementById(id).value, 10);
  const body = {
    email_address: document.getElementById("outreach-email").value.trim(),
    email_daily_limit: num("outreach-email-limit"),
    send_from: num("outreach-send-from"),
    send_to: num("outreach-send-to"),
    weekdays_only: document.getElementById("outreach-weekdays").checked,
    warmup: document.getElementById("outreach-warmup").checked,
    follow_up_days: num("outreach-follow-up"),
    digest_enabled: document.getElementById("outreach-digest").checked,
    digest_hour: num("outreach-digest-hour"),
    skip_us_only: document.getElementById("outreach-skip-us").checked,
    skip_europe_only: document.getElementById("outreach-skip-eu").checked,
  };
  const password = document.getElementById("outreach-app-password").value.trim();
  if (password) body.email_app_password = password;
  const hunter = document.getElementById("outreach-hunter").value.trim();
  if (hunter) body.hunter_api_key = hunter;
  try {
    await api("/api/settings/outreach", { method: "POST", body: JSON.stringify(body) });
    document.getElementById("outreach-hunter").value = "";
    status.textContent = "Сохранено";
    loadOutreachSettings();
  } catch (err) {
    status.textContent = err.message;
  }
}

// Что бот делает прямо сейчас — видно с любой страницы, клик ведёт туда.
async function updateActivity() {
  if (document.visibilityState !== "visible") return;
  let items;
  try {
    items = await api("/api/activity");
  } catch (e) {
    return;
  }
  const el = document.getElementById("activity");
  // state: нет/active — крутится; waiting — ⏸ спокойно; stopped — красным, нужны вы.
  const icon = (a) =>
    a.state === "waiting" ? `<span class="activity-icon" aria-hidden="true">⏸</span>`
      : a.state === "stopped" ? `<span class="activity-icon" aria-hidden="true">⛔</span>`
      : `<span class="activity-spin" aria-hidden="true"></span>`;
  el.innerHTML = items
    .map(
      (a) => `<button type="button" class="activity-item${a.state ? ` is-${a.state}` : ""}" data-activity-view="${a.goto || a.view}">
        ${icon(a)}
        <span>${escapeHtml(a.text)}${a.source ? " " + escapeHtml(sourceLabel(a.source)) : ""}${a.total ? ` · ${a.done}/${a.total}` : ""}${a.state === "stopped" ? " — что делать →" : ""}</span>
      </button>`
    )
    .join("");
  el.querySelectorAll("[data-activity-view]").forEach((b) =>
    b.addEventListener("click", () => {
      const to = b.dataset.activityView;
      if (to.startsWith("settings-")) {
        switchTab("settings");
        switchSettingsTab(to);
      } else {
        switchTab(to);
      }
    })
  );
}

// «Откликаться автоматически» разом для всех включённых площадок —
// большинству не нужно настраивать режим каждой отдельно.
function renderAutoAll(status) {
  const on = status.sources.filter((s) => s.schedule_enabled && s.name !== "telegram");
  const auto = on.filter((s) => s.auto_apply);
  const box = document.getElementById("search-auto-all");
  box.checked = on.length > 0 && auto.length === on.length;
  box.indeterminate = auto.length > 0 && auto.length < on.length;
  document.getElementById("search-auto-note").textContent = on.length
    ? `сейчас сами откликаются: ${auto.length} из ${on.length}`
    : "ни одна площадка не включена";
  box.onchange = async () => {
    const enable = box.checked;
    if (enable && !confirm(`Бот начнёт сам отправлять отклики на ${on.length} ${plural(on.length, "площадке", "площадках", "площадках")} — до дневного лимита каждой. Включить?`)) {
      renderAutoAll(status);
      return;
    }
    box.disabled = true;
    try {
      for (const s of on) {
        await api("/api/settings", { method: "POST", body: JSON.stringify({ source: s.name, auto_apply: enable }) });
      }
      showToast(enable ? "Автоотклик включён на всех площадках" : "Площадки только ищут, откликаетесь вы", "success");
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    } finally {
      box.disabled = false;
      renderAutoAll(await api("/api/status"));
      lastOverviewSnapshot = "";
    }
  };
}

// «Подключения»: сервисы (то же, что «Готовность» на Главной) и
// площадки — вход, пауза после капчи, последняя ошибка.
async function loadAccounts() {
  const [todo, status] = await Promise.all([api("/api/todo"), api("/api/status")]);
  const row = (ok, title, hint, action) => `
    <div class="account-row ${ok ? "is-ok" : "is-missing"}">
      <span class="account-mark">${ok ? "✓" : "✗"}</span>
      <span class="account-text"><b>${escapeHtml(title)}</b>${hint ? `<span class="muted small">${escapeHtml(hint)}</span>` : ""}</span>
      ${action || ""}`;
  const services = (todo.setup || []).filter((c) => !["schedule", "salary", "daemon"].includes(c.id));
  document.getElementById("accounts-services").innerHTML = services
    .map((c) => row(c.ok, c.label, c.hint, c.ok || !c.goto ? "</div>" : `<button type="button" class="btn btn-secondary btn-small" data-account-goto="${escapeHtml(c.goto)}">Подключить</button></div>`))
    .join("");
  const outreach = await api("/api/settings/outreach").catch(() => null);
  if (outreach) {
    document.getElementById("accounts-services").insertAdjacentHTML(
      "beforeend",
      `<div class="account-row ${outreach.hunter_preview ? "is-ok" : "is-optional"}">
        <span class="account-mark">${outreach.hunter_preview ? "✓" : "○"}</span>
        <span class="account-text"><b>Hunter — поиск email HR (необязательно)</b><span class="muted small">${outreach.hunter_preview ? `ключ ${escapeHtml(outreach.hunter_preview)}` : "без ключа контакты ищутся только на сайте компании"}</span></span>
        ${outreach.hunter_preview ? "" : `<button type="button" class="btn btn-ghost btn-small" data-account-goto="settings-outreach" data-anchor="hunter-block">Добавить ключ</button>`}
      </div>`
    );
  }
  const platforms = status.sources.filter((s) => s.schedule_enabled && s.name !== "telegram");
  document.getElementById("accounts-platforms").innerHTML = platforms.length
    ? platforms
        .map((s) => {
          const blocked = s.paused || s.status === "blocked";
          const error = s.last_error?.summary || "";
          const ok = !blocked && s.status !== "error";
          const hint = blocked
            ? "на паузе после капчи — пройдите её в браузере и отправьте боту /resume"
            : error || (s.status === "never_run" ? "ещё не запускалась — вход попросит при первом запуске" : "работает");
          return row(ok, sourceLabel(s.name), hint, "</div>");
        })
        .join("")
    : `<p class="muted small">Ни одна площадка не включена — выберите режим на карточке площадки на Главной.</p>`;
  document.querySelectorAll("[data-account-goto]").forEach((b) =>
    b.addEventListener("click", () => {
      const goto = b.dataset.accountGoto;
      if (goto.startsWith("settings-")) {
        switchSettingsTab(goto);
        if (b.dataset.anchor) document.getElementById(b.dataset.anchor)?.scrollIntoView({ block: "center" });
        if (goto === "settings-tg-quick") loadTelegramWatch();
      } else {
        switchTab(goto);
      }
    })
  );
}

// Сводка живёт в «Уведомлениях», сохраняется сразу — без кнопки.
async function saveDigest() {
  if (document.getElementById("digest-quiet").checked) document.getElementById("outreach-digest").checked = true;
  try {
    await api("/api/settings/outreach", {
      method: "POST",
      body: JSON.stringify({
        // Тихий режим без сводки не работает — включаем сводку вместе с ним.
        digest_enabled: document.getElementById("outreach-digest").checked || document.getElementById("digest-quiet").checked,
        digest_hour: parseInt(document.getElementById("outreach-digest-hour").value, 10) || 9,
        digest_quiet: document.getElementById("digest-quiet").checked,
      }),
    });
    showToast("Сводка сохранена", "success");
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
  }
}

async function testOutreachEmail() {
  const status = document.getElementById("outreach-email-status");
  await saveOutreachSettings();
  status.textContent = "Отправляю письмо себе…";
  try {
    await api("/api/settings/outreach/test-email", { method: "POST" });
    status.textContent = "✅ Письмо отправлено — проверьте почту. Всё работает.";
  } catch (err) {
    status.textContent = `❌ ${err.message.replace(/^\d+: /, "")}`;
  }
}

function showOverlay(id) {
  const overlay = document.getElementById(id);
  overlay.style.display = "flex";
  trapFocus(overlay);
}

function hideOverlay(overlay) {
  overlay.style.display = "none";
  releaseFocusTrap(overlay);
}

// .ics собирается на сервере по введённому времени — ссылка на скачивание
// обновляется при каждом изменении полей.
function openCalendarOverlay(e) {
  document.getElementById("calendar-meta").textContent = `${e.company} — ${e.title}`;
  const start = document.getElementById("calendar-start");
  const duration = document.getElementById("calendar-duration");
  const link = document.getElementById("calendar-download");
  const update = () => {
    const params = new URLSearchParams({
      source: e.source,
      external_id: e.external_id,
      start: start.value,
      duration: duration.value || "60",
    });
    link.href = start.value ? `/api/applications/ics?${params}` : "#";
    link.classList.toggle("disabled", !start.value);
  };
  start.oninput = update;
  duration.oninput = update;
  update();
  showOverlay("calendar-overlay");
  start.focus();
}

let trainer = null;

async function openTrainer(e) {
  trainer = { entry: e, questions: [], index: 0 };
  document.getElementById("trainer-title").textContent = `Тренажёр: ${e.company} — ${e.title}`;
  document.getElementById("trainer-question").textContent = "Готовлю вопросы…";
  document.getElementById("trainer-progress").textContent = "";
  document.getElementById("trainer-answer").value = "";
  document.getElementById("trainer-feedback").textContent = "";
  showOverlay("trainer-overlay");
  try {
    const { questions } = await api("/api/interview/questions", {
      method: "POST",
      body: JSON.stringify({ source: e.source, external_id: e.external_id }),
    });
    trainer.questions = questions;
    showTrainerQuestion();
  } catch (err) {
    document.getElementById("trainer-question").textContent = err.message;
  }
}

function showTrainerQuestion() {
  const { questions, index } = trainer;
  document.getElementById("trainer-progress").textContent = `Вопрос ${index + 1} из ${questions.length}`;
  document.getElementById("trainer-question").textContent = questions[index];
  document.getElementById("trainer-answer").value = "";
  document.getElementById("trainer-feedback").textContent = "";
  document.getElementById("trainer-answer").focus();
}

async function checkTrainerAnswer() {
  const btn = document.getElementById("trainer-check");
  const feedback = document.getElementById("trainer-feedback");
  btn.disabled = true;
  feedback.textContent = "Оцениваю…";
  try {
    const res = await api("/api/interview/feedback", {
      method: "POST",
      body: JSON.stringify({
        source: trainer.entry.source,
        external_id: trainer.entry.external_id,
        question: trainer.questions[trainer.index],
        answer: document.getElementById("trainer-answer").value,
      }),
    });
    feedback.textContent = res.feedback.replace(/\*\*/g, "");
  } catch (err) {
    feedback.textContent = err.message.replace(/^\d+: /, "");
  } finally {
    btn.disabled = false;
  }
}

function openTextModal(title, meta, body) {
  document.getElementById("cover-letter-title").textContent = title;
  document.getElementById("cover-letter-meta").textContent = meta;
  document.getElementById("cover-letter-body").textContent = body;
  const overlay = document.getElementById("cover-letter-overlay");
  overlay.style.display = "flex";
  trapFocus(overlay);
}

async function renderOffers() {
  const el = document.getElementById("offers");
  const offers = await api("/api/offers");
  const fmt = (n) => n.toLocaleString("ru-RU");
  el.innerHTML = offers.length
    ? `<table>
        <thead><tr><th>Компания</th><th>В месяц</th><th>К рынку</th><th>Удалённо</th><th>Заметки</th><th></th></tr></thead>
        <tbody>${offers
          .map(
            (o) => `<tr>
              <td>${escapeHtml(o.company)}</td>
              <td>${fmt(o.amount)} ${escapeHtml(o.currency)}</td>
              <td>${o.vs_market === null ? "—" : `${o.vs_market > 0 ? "+" : ""}${o.vs_market}%`}</td>
              <td>${o.remote ? "да" : "нет"}</td>
              <td>${escapeHtml(o.notes || "")}</td>
              <td><button type="button" class="btn btn-ghost btn-small" data-offer-delete="${escapeHtml(o.id)}">Удалить</button></td>
            </tr>`
          )
          .join("")}</tbody>
      </table>`
    : emptyStateHtml("Офферов пока нет — добавьте, когда появятся.");
  el.querySelectorAll("[data-offer-delete]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await api(`/api/offers/${btn.dataset.offerDelete}`, { method: "DELETE" });
      renderOffers();
    });
  });
}

async function addOffer() {
  const company = document.getElementById("offer-company").value.trim();
  const amount = parseInt(document.getElementById("offer-amount").value, 10);
  if (!company || !amount) {
    showToast("Укажите компанию и сумму", "error");
    return;
  }
  await api("/api/offers", {
    method: "POST",
    body: JSON.stringify({
      company,
      amount,
      currency: document.getElementById("offer-currency").value,
      remote: document.getElementById("offer-remote").checked,
      notes: document.getElementById("offer-notes").value.trim(),
    }),
  });
  ["offer-company", "offer-amount", "offer-notes"].forEach((id) => {
    document.getElementById(id).value = "";
  });
  renderOffers();
}

function openCoverLetterModal(entry) {
  document.getElementById("cover-letter-title").textContent =
    `${entry.company} — ${entry.title}`;
  document.getElementById("cover-letter-meta").textContent =
    `${sourceLabel(entry.source)} · ${fmtTime(entry.applied_at)}`;
  document.getElementById("cover-letter-body").textContent =
    entry.cover_letter || "Письмо не сохранено (могло истечь по сроку хранения).";
  const overlay = document.getElementById("cover-letter-overlay");
  overlay.style.display = "flex";
  trapFocus(overlay);
}

function closeCoverLetterModal() {
  const overlay = document.getElementById("cover-letter-overlay");
  if (overlay.style.display === "none") return;
  overlay.style.display = "none";
  releaseFocusTrap(overlay);
}

function isCoverLetterModalOpen() {
  return document.getElementById("cover-letter-overlay").style.display !== "none";
}

function openShortcutsOverlay() {
  const overlay = document.getElementById("shortcuts-overlay");
  overlay.style.display = "flex";
  trapFocus(overlay);
}

function closeShortcutsOverlay() {
  const overlay = document.getElementById("shortcuts-overlay");
  if (overlay.style.display === "none") return;
  overlay.style.display = "none";
  releaseFocusTrap(overlay);
}

function initKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    const tag = (e.target.tagName || "").toLowerCase();
    const isTyping = tag === "input" || tag === "textarea" || e.target.isContentEditable;

    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      openCommandPalette();
      return;
    }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
      e.preventDefault();
      toggleSidebarCollapse();
      return;
    }
    if (isCommandPaletteOpen()) return;

    if (isCoverLetterModalOpen()) {
      if (e.key === "Escape") closeCoverLetterModal();
      return;
    }
    if (isResumeAuditModalOpen()) {
      if (e.key === "Escape") closeResumeAuditModal();
      return;
    }
    if (isPlatformDrawerOpen()) {
      if (e.key === "Escape") closePlatformDrawer();
      return;
    }

    if (e.key === "Escape") {
      closeShortcutsOverlay();
      return;
    }
    if (isTyping) return;
    if (e.key === "?") {
      e.preventDefault();
      const overlay = document.getElementById("shortcuts-overlay");
      if (overlay.style.display === "none") openShortcutsOverlay();
      else closeShortcutsOverlay();
      return;
    }
    if (/^[1-8]$/.test(e.key)) {
      const buttons = document.querySelectorAll("nav.tabs button[data-tab]");
      const idx = parseInt(e.key, 10) - 1;
      if (buttons[idx]) switchTab(buttons[idx].dataset.tab);
    }
  });
}

// ---------- Cursor-spotlight + magnetic primary buttons ----------
// Один делегированный слушатель на весь документ вместо одного на
// карточку — дешевле при десятках карточек на Обзоре.
function initPointerEffects() {
  if (REDUCE_MOTION) return;
  document.addEventListener("mousemove", (e) => {
    const card = e.target.closest(".source-card, .provider-card");
    if (card) {
      const rect = card.getBoundingClientRect();
      card.style.setProperty("--spot-x", `${e.clientX - rect.left}px`);
      card.style.setProperty("--spot-y", `${e.clientY - rect.top}px`);
    }
    const btn = e.target.closest(".btn-primary:not(:disabled)");
    document.querySelectorAll(".btn-primary.is-magnetic").forEach((el) => {
      if (el !== btn) {
        el.style.transform = "";
        el.classList.remove("is-magnetic");
      }
    });
    if (btn) {
      btn.classList.add("is-magnetic");
      const rect = btn.getBoundingClientRect();
      const dx = (e.clientX - (rect.left + rect.width / 2)) * 0.15;
      const dy = (e.clientY - (rect.top + rect.height / 2)) * 0.25;
      btn.style.transform = `translate(${dx}px, ${dy}px)`;
    }
  });
}

// ---------- Directional переходы между вкладками ----------

const NAV_ORDER = Object.values(NAV_GROUPS).flat().map(([view]) => view);

function directionalReveal(viewEl, fromName, toName) {
  if (REDUCE_MOTION || !viewEl) return;
  const fromIdx = NAV_ORDER.indexOf(fromName);
  const toIdx = NAV_ORDER.indexOf(toName);
  if (fromIdx === -1 || toIdx === -1 || fromIdx === toIdx) return;
  const cls = toIdx > fromIdx ? "slide-right" : "slide-left";
  viewEl.classList.remove("slide-right", "slide-left");
  void viewEl.offsetWidth;
  viewEl.classList.add(cls);
}

// ---------- Спиннер загрузки на кнопке во время async-действия ----------

async function withButtonLoading(btn, fn) {
  if (!btn) return fn();
  btn.classList.add("is-loading");
  try {
    return await fn();
  } finally {
    btn.classList.remove("is-loading");
  }
}

// ---------- Confetti на реальное достижение (первый ответ работодателя) ----------

function fireConfetti() {
  if (REDUCE_MOTION) return;
  const colors = ["#7ab8ff", "#6fdc8c", "#e0c05a", "#e08787"];
  for (let i = 0; i < 24; i++) {
    const piece = document.createElement("div");
    piece.className = "confetti-piece";
    piece.style.left = `${Math.random() * 100}vw`;
    piece.style.background = colors[i % colors.length];
    piece.style.animationDuration = `${1.4 + Math.random() * 1.2}s`;
    piece.style.animationDelay = `${Math.random() * 0.3}s`;
    document.body.appendChild(piece);
    piece.addEventListener("animationend", () => piece.remove());
  }
}

// ---------- Онбординг-тур (только при первом запуске) ----------

const TOUR_STEPS = [
  { tab: "overview", text: "«Главная» — что готово к работе, что ждёт вашего решения, площадки, Telegram-парсер и рассылка." },
  { tab: "history", text: "«Вакансии» — куда бот откликнулся, этап по каждой и действия: подготовка к интервью, найти HR." },
  { tab: "replies", text: "«Общение» — ответы работодателей и переписка в Telegram, черновики ответов на подтверждение." },
  { tab: "contacts", text: "«Компании» — ваша база компаний и HR (из файла, Telegram, вакансий) и рассылки им через Gmail." },
  { tab: "analytics", text: "«Аналитика» — ответы и интервью за неделю по каждому источнику, воронка, рынок." },
  { tab: "settings", text: "«Настройки» — поиск, площадки, почта, Telegram-парсер и резюме." },
];

function initOnboardingTour() {
  if (localStorage.getItem("cj-seen-tour") === "1") return;
  let step = 0;
  const overlay = document.createElement("div");
  overlay.className = "tour-overlay";
  const highlight = document.createElement("div");
  highlight.className = "tour-highlight";
  const tooltip = document.createElement("div");
  tooltip.className = "tour-tooltip";
  overlay.append(highlight, tooltip);

  function renderStep() {
    const { tab, text } = TOUR_STEPS[step];
    const btn = document.querySelector(`nav.tabs button[data-tab="${tab}"]`);
    if (!btn) return finish();
    const rect = btn.getBoundingClientRect();
    Object.assign(highlight.style, {
      top: `${rect.top - 4}px`,
      left: `${rect.left - 4}px`,
      width: `${rect.width + 8}px`,
      height: `${rect.height + 8}px`,
    });
    const isLast = step === TOUR_STEPS.length - 1;
    tooltip.innerHTML = `
      <button type="button" class="tour-skip" id="tour-skip" title="Пропустить" aria-label="Пропустить">✕</button>
      <p>${escapeHtml(text)}</p>
      <div class="tour-actions">
        <span class="tour-step">${step + 1} / ${TOUR_STEPS.length}</span>
        <button type="button" class="btn btn-primary btn-small" id="tour-next">${isLast ? "Готово" : "Дальше"}</button>
      </div>`;
    tooltip.style.top = `${Math.min(rect.top, window.innerHeight - 160)}px`;
    tooltip.style.left = `${Math.min(rect.right + 16, window.innerWidth - 280)}px`;
    document.getElementById("tour-next").addEventListener("click", () => {
      step += 1;
      if (step >= TOUR_STEPS.length) finish();
      else renderStep();
    });
    document.getElementById("tour-skip").addEventListener("click", finish);
  }

  function finish() {
    localStorage.setItem("cj-seen-tour", "1");
    overlay.remove();
  }

  document.body.appendChild(overlay);
  renderStep();
}


// 13 недель x 7 дней, как в GitHub contributions — считаем прямо на
// клиенте по уже существующему /api/applications, отдельного
// backend-эндпоинта для этого заводить незачем.
// Воронка — один ряд величин по этапам: горизонтальные полосы одного
// цвета (--accent), число подписано у каждой полосы, ширина — доля от
// числа реальных откликов; подсказка при наведении — title.
function renderFunnel(funnel) {
  const el = document.getElementById("funnel");
  if (!funnel.applied) {
    el.innerHTML = emptyStateHtml("Пока нет реальных откликов.");
    return;
  }
  const rows = [["applied", "Отклики"], ...Object.entries(STAGE_LABELS).map(([k, v]) => [k, v[0].toUpperCase() + v.slice(1)])];
  el.innerHTML = rows
    .map(([key, label]) => {
      const value = funnel[key] ?? 0;
      const pct = (value / funnel.applied) * 100;
      const share = key === "applied" ? "" : ` · ${pct.toFixed(1)}%`;
      return `
      <div class="funnel-row" title="${label}: ${value}${share}">
        <span class="funnel-label">${label}</span>
        <span class="funnel-track"><span class="funnel-bar" style="width:${Math.max(pct, value ? 1 : 0)}%"></span></span>
        <span class="funnel-value">${value}<span class="muted small">${share}</span></span>
      </div>`;
    })
    .join("");
}

// Спрос на навыки — тот же вид, что воронка (одна величина, один цвет),
// плюс отметка "есть в резюме"; зарплаты — таблица по валютам.
function renderMarket(market) {
  const skillsEl = document.getElementById("skill-demand");
  skillsEl.innerHTML = market.skills.length
    ? market.skills
        .map(
          (s) => `
      <div class="funnel-row" title="${escapeHtml(s.skill)}: ${s.count} вакансий, ${s.share}%${s.in_resume ? "" : " — нет в резюме"}">
        <span class="funnel-label">${escapeHtml(s.skill)}</span>
        <span class="funnel-track"><span class="funnel-bar" style="width:${s.share}%"></span></span>
        <span class="funnel-value">${s.share}% ${s.in_resume ? "✓" : "✗"}</span>
      </div>`
        )
        .join("")
    : emptyStateHtml("Появится после новых откликов — навыки извлекаются из текста вакансий с этого обновления.");

  const fmt = (n) => n.toLocaleString("ru-RU");
  const salaryEl = document.getElementById("salary-stats");
  salaryEl.innerHTML = market.salaries.length
    ? `<table>
        <thead><tr><th>Валюта</th><th>Вакансий</th><th>Медиана «от»</th><th>Медиана «до»</th></tr></thead>
        <tbody>${market.salaries
          .map(
            (r) =>
              `<tr><td>${escapeHtml(r.currency)}</td><td>${r.count}</td><td>${fmt(r.median_min)}</td><td>${fmt(r.median_max)}</td></tr>`
          )
          .join("")}</tbody>
      </table>`
    : emptyStateHtml("Пока нет вакансий с указанной зарплатой.");
}

async function renderActivityHeatmap() {
  const el = document.getElementById("activity-heatmap");
  if (!el) return;
  const entries = await api("/api/applications");
  const counts = new Map();
  entries.forEach((e) => {
    const day = (e.applied_at || "").slice(0, 10);
    if (day) counts.set(day, (counts.get(day) || 0) + 1);
  });
  const days = 91;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const cells = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    const count = counts.get(key) || 0;
    const level = count === 0 ? 0 : count >= 5 ? 3 : count >= 2 ? 2 : 1;
    cells.push(
      `<div class="heatmap-cell" data-level="${level}" title="${key}: ${count} откл."></div>`
    );
  }
  el.innerHTML = cells.join("");
}

function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    btn.classList.add("copied");
    const original = btn.innerHTML;
    btn.innerHTML = `<svg viewBox="0 0 20 20" fill="none"><path d="m4 10.5 4 4 8-9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    setTimeout(() => {
      btn.classList.remove("copied");
      btn.innerHTML = original;
    }, 1400);
  });
}

const COPY_ICON_SVG = `<svg viewBox="0 0 20 20" fill="none"><rect x="7" y="7" width="10" height="10" rx="1.5" stroke="currentColor" stroke-width="1.6"/><path d="M4.5 13V4.5a1 1 0 0 1 1-1H13" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>`;

// ---------- Drag-to-reorder карточек площадок ----------

function loadSourceOrder(storageKey) {
  try {
    return JSON.parse(localStorage.getItem(storageKey) || "[]");
  } catch {
    return [];
  }
}

function saveSourceOrder(storageKey, order) {
  localStorage.setItem(storageKey, JSON.stringify(order));
}

function applySourceOrder(items, key, storageKey) {
  const order = loadSourceOrder(storageKey);
  if (!order.length) return items;
  const rank = new Map(order.map((name, i) => [name, i]));
  return items
    .slice()
    .sort((a, b) => (rank.get(a[key]) ?? 999) - (rank.get(b[key]) ?? 999));
}

function initDragReorder(gridId, storageKey) {
  const grid = document.getElementById(gridId);
  let dragged = null;
  grid.addEventListener("dragstart", (e) => {
    const card = e.target.closest(".source-card");
    if (!card) return;
    dragged = card;
    e.dataTransfer.effectAllowed = "move";
  });
  grid.addEventListener("dragover", (e) => {
    if (!dragged) return;
    e.preventDefault();
    const target = e.target.closest(".source-card");
    if (!target || target === dragged) return;
    const rect = target.getBoundingClientRect();
    const before = e.clientX < rect.left + rect.width / 2;
    target.parentElement.insertBefore(dragged, before ? target : target.nextSibling);
  });
  grid.addEventListener("dragend", () => {
    if (!dragged) return;
    dragged = null;
    const order = [...grid.querySelectorAll(".source-card")].map((c) => c.dataset.source);
    saveSourceOrder(storageKey, order);
  });
}

// ---------- Changelog popover ----------

const CHANGELOG_VERSION = "2026-09-24-tg-quick";
const CHANGELOG_ITEMS = [
  "✈️ Telegram-парсер: вакансия из каналов через секунды в вашем боте — кнопки «Здравствуйте», «+ резюме», «сопроводительное под вакансию»; контакты HR из постов — сразу в «Базу компаний». Настройки → «Telegram-парсер»",
  "Меню стало проще: 5 разделов — Главная, Вакансии, Общение, Аналитика, Настройки",
  "На Главной — «Что сделать сейчас»: черновики, новые ответы, интервью, контакты HR",
  "У любой вакансии «Действия» → «Найти HR этой компании»",
  "«Входящие»: ответы hh и HR из Telegram в одном месте + черновики ответов на подтверждение",
  "Этап у каждого отклика и воронка до оффера в Аналитике",
  "Настройки → «Контакты и письма»: почта Gmail, Hunter, сводка, напоминания HR",
  "🏢 «Сайты компаний» в «Свои каналы»: сами собирают компании с email HR в Базу — дальше рассылка одной кнопкой",
  "У интервью в Истории → «Действия»: подготовка, тренажёр, событие в календарь",
  "Аналитика: спрос на навыки, зарплаты на рынке, сравнение офферов",
];

function initChangelogPopover() {
  if (localStorage.getItem("cj-seen-changelog") === CHANGELOG_VERSION) return;
  // Не показываем поверх онбординг-тура на самом первом запуске —
  // одновременно два оверлея это перегруз, а не "круто". Чейнджлог
  // подождёт следующего открытия, когда тур уже пройден.
  if (localStorage.getItem("cj-seen-tour") !== "1") return;
  const el = document.createElement("div");
  el.className = "changelog-popover";
  el.innerHTML = `
    <h4>✨ Что нового</h4>
    <ul>${CHANGELOG_ITEMS.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>
    <button class="btn btn-primary" type="button">Понятно</button>
  `;
  document.body.appendChild(el);
  el.querySelector("button").addEventListener("click", () => {
    localStorage.setItem("cj-seen-changelog", CHANGELOG_VERSION);
    el.remove();
  });
}

function initDashboard() {
  document.querySelectorAll("nav.tabs button").forEach((b) => {
    b.addEventListener("click", () => switchTab(b.dataset.tab));
  });

  document.getElementById("theme-toggle").addEventListener("click", (ev) => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    const apply = () => {
      document.documentElement.dataset.theme = next;
      localStorage.setItem("cj-theme", next);
    };
    const rect = ev.currentTarget.getBoundingClientRect();
    document.documentElement.style.setProperty("--theme-toggle-x", `${rect.left + rect.width / 2}px`);
    document.documentElement.style.setProperty("--theme-toggle-y", `${rect.top + rect.height / 2}px`);
    if (document.startViewTransition && !REDUCE_MOTION) {
      document.startViewTransition(apply);
    } else {
      apply();
    }
  });

  document.querySelectorAll("#settings-jump button").forEach((b) => {
    b.addEventListener("click", () => switchSettingsTab(b.dataset.settingsTab));
  });

  initSidebarCollapse();
  // Справка «Как пользоваться» — нативный <dialog>: Esc и фокус из коробки.
  const help = document.getElementById("help-dialog");
  document.getElementById("help-open").addEventListener("click", () => help.showModal());
  document.getElementById("help-close").addEventListener("click", () => help.close());
  help.addEventListener("click", (e) => {
    if (e.target === help) help.close(); // клик мимо окна
  });
  updateActivity();
  setInterval(updateActivity, 4000);
  initSettingsDirtyTracking();
  initAutosave();
  initCommandPalette();
  initKeyboardShortcuts();

  document.getElementById("llm-key-toggle").addEventListener("click", () => {
    const input = document.getElementById("llm-key-input");
    input.type = input.type === "password" ? "text" : "password";
  });
  initDragReorder("source-grid-ru", "cj-source-order-ru");
  initDragReorder("source-grid-intl", "cj-source-order-intl");
  initChangelogPopover();
  initPointerEffects();
  initOnboardingTour();

  function handleSourceCardActionClick(e) {
    const runBtn = e.target.closest(".src-run-now");
    const historyBtn = e.target.closest(".src-goto-history");
    const logsBtn = e.target.closest(".src-goto-logs");
    if (runBtn) {
      if (runBtn.dataset.running === "1") {
        stopSourceNow(runBtn);
      } else {
        runSourceNow(runBtn);
      }
    } else if (historyBtn) {
      document.getElementById("filter-source").value = historyBtn.dataset.source;
      switchTab("history");
    } else if (logsBtn) {
      document.getElementById("log-source").value = logsBtn.dataset.source;
      switchTab("logs");
    }
  }

  // Запускает одну конкретную площадку прямо сейчас (реальный прогон, с
  // её собственным auto_apply — не форсированный dry-run, как у общей
  // кнопки "Тестовый прогон") — чтобы не ждать next_run при отладке/
  // ручной проверке. Переиспользует тот же /api/run-now, что и общая
  // кнопка, просто с одним источником в списке.
  //
  // ponytail: раньше withButtonLoading держал is-loading на кнопке на
  // ВСЁ время прогона (иногда минуты), пока рядом отдельный опрос
  // overview (render.overview, раз в 7с) параллельно перерисовывал ту
  // же карточку по server-side isRunning — два независимых источника
  // правды дрались за один DOM-узел, и после пересборки innerHTML
  // ссылка btn протухала, а visible-состояние "зависало". Теперь
  // is-loading висит только на быстром POST-запуске, а "идёт/не идёт"
  // всегда только из уже существующего опроса overview (пульс точки +
  // свечение карточки) — второго индикатора больше нет.
  async function runSourceNow(btn) {
    const name = btn.dataset.source;
    if (
      !(await showConfirm(
        `Запустить ${sourceLabel(name)} прямо сейчас? Это реальный прогон, ` +
          `не тест — если у площадки включён автоотклик, заявки уйдут по-настоящему.`
      ))
    ) {
      return;
    }
    try {
      await withButtonLoading(btn, () =>
        api("/api/run-now", {
          method: "POST",
          body: JSON.stringify({ sources: [name] }),
        })
      );
    } catch (e) {
      showToast(`Не удалось запустить ${sourceLabel(name)}: ${e.message}`, "error");
      return;
    }
    render.overview();
    watchSourceRunCompletion(name);
  }

  async function watchSourceRunCompletion(name) {
    for (;;) {
      await new Promise((r) => setTimeout(r, 3000));
      const runStatus = await api("/api/run-now/status");
      if (!runStatus.running || runStatus.current_source !== name) break;
    }
    showToast(`${sourceLabel(name)}: прогон завершён — см. Историю`, "success");
    render.overview();
  }

  // Мягкий стоп: текущая уже начатая заявка досылается (см. main.py —
  // stop_event проверяется между вакансиями, не посреди клика
  // "Откликнуться"), следующая не начинается.
  async function stopSourceNow(btn) {
    const name = btn.dataset.source;
    try {
      await withButtonLoading(btn, () => api("/api/run-now/stop", { method: "POST" }));
      showToast(`${sourceLabel(name)}: остановка запрошена`, "success");
    } catch (e) {
      showToast(`Не удалось остановить ${sourceLabel(name)}: ${e.message}`, "error");
    }
  }
  document.getElementById("source-grid-ru").addEventListener("click", handleSourceCardActionClick);
  document.getElementById("source-grid-intl").addEventListener("click", handleSourceCardActionClick);
  requestAnimationFrame(repositionTabIndicators);
  window.addEventListener("resize", repositionTabIndicators);

  const providerToggle = document.getElementById("provider-grid-toggle");
  const providerGrid = document.getElementById("provider-grid");
  providerGrid.classList.add("collapsed");
  providerToggle.addEventListener("click", () => {
    const expanded = providerToggle.dataset.expanded === "1";
    providerToggle.dataset.expanded = expanded ? "" : "1";
    if (expanded) {
      providerGrid.classList.add("collapsed");
      updateProviderVisibility();
      return;
    }
    providerToggle.textContent = "Свернуть";
    const hidden = providerGrid.querySelectorAll(".provider-hideable");
    providerGrid.classList.remove("collapsed");
    if (window.gsap && !REDUCE_MOTION) {
      gsap.from(hidden, {
        opacity: 0,
        y: -6,
        scale: 0.96,
        duration: 0.3,
        stagger: 0.03,
        ease: "power2.out",
      });
    }
  });

  refreshTelegramConnectStatus();

  document
    .getElementById("telegram-connect-btn")
    .addEventListener("click", async () => {
      const tokenInput = document.getElementById("telegram-bot-token");
      const statusEl = document.getElementById("telegram-connect-status");
      const token = tokenInput.value.trim();
      if (!token) {
        statusEl.textContent = "Вставьте токен бота.";
        return;
      }
      statusEl.textContent = "Проверяю токен…";
      try {
        const { connect_url } = await api("/api/settings/telegram/token", {
          method: "POST",
          body: JSON.stringify({ bot_token: token }),
        });
        window.open(connect_url, "_blank");
        statusEl.textContent = "Открылся чат с ботом — нажмите там Start…";
        await api("/api/settings/telegram/connect", { method: "POST" });
        const timer = setInterval(async () => {
          const done = await refreshTelegramConnectStatus();
          if (done) clearInterval(timer);
        }, 3000);
      } catch (e) {
        statusEl.textContent = `Ошибка: ${e.message}`;
      }
    });

  document
    .getElementById("autostart-toggle")
    .addEventListener("change", async (ev) => {
      const toggle = ev.target;
      const note = document.getElementById("autostart-status");
      const wanted = toggle.checked;
      toggle.disabled = true;
      note.textContent = "Сохранение…";
      try {
        const result = await api("/api/settings/autostart", {
          method: "POST",
          body: JSON.stringify({ enabled: wanted }),
        });
        toggle.checked = result.enabled;
        note.textContent = result.enabled
          ? "✅ Будет запускаться при входе в систему."
          : "Автозапуск выключен.";
      } catch (e) {
        toggle.checked = !wanted;
        note.textContent = `Ошибка: ${e.message}`;
      } finally {
        toggle.disabled = false;
      }
    });

  document
    .getElementById("daemon-service-toggle")
    .addEventListener("change", async (ev) => {
      const toggle = ev.target;
      const note = document.getElementById("daemon-service-status");
      const wanted = toggle.checked;
      toggle.disabled = true;
      note.textContent = "Сохранение…";
      try {
        const result = await api("/api/settings/daemon_service", {
          method: "POST",
          body: JSON.stringify({ enabled: wanted }),
        });
        toggle.checked = result.enabled;
        note.textContent = result.enabled
          ? "✅ Бот работает в фоне, даже когда окно закрыто."
          : "Фоновый сервис выключен.";
      } catch (e) {
        toggle.checked = !wanted;
        note.textContent = `Ошибка: ${e.message}`;
      } finally {
        toggle.disabled = false;
      }
    });

  document.getElementById("notif-test").addEventListener("click", async () => {
    const status = document.getElementById("notif-test-status");
    status.textContent = "Отправка…";
    try {
      await api("/api/notifications/test", { method: "POST" });
      status.textContent = "Отправлено, проверьте Telegram.";
    } catch (e) {
      status.textContent = `Ошибка: ${e.message}`;
    }
  });

  document.getElementById("daemon-toggle").addEventListener("click", async (ev) => {
    const btn = ev.currentTarget;
    // Три исхода зависят от текущего состояния кнопки (см. render.overview):
    // не запущен -> start; запущен и активен (is-pause-action) -> pause;
    // запущен и на паузе -> resume.
    const endpoint = !btn.classList.contains("is-pause-action") && !btn.classList.contains("is-paused")
      ? "start"
      : btn.classList.contains("is-paused")
        ? "resume"
        : "stop";
    const messages = {
      start: ["Бот запущен", "success"],
      stop: ["Бот остановлен", "info"],
      resume: ["Бот продолжает работу", "info"],
    };
    await withButtonLoading(btn, () => api(`/api/daemon/${endpoint}`, { method: "POST" }));
    showToast(...messages[endpoint]);
    render.overview();
  });

  // Прогоняет площадки из расписания сейчас же, но с auto_apply/
  // auto_message, форсированно выключенными на сервере (см. dry_run в
  // run_selected_sources, main.py) — сам work_preferences.yaml не
  // трогается, реальный отклик не уходит никуда.
  document.getElementById("dry-run-button").addEventListener("click", async (ev) => {
    const status = await api("/api/status");
    const sources = status.sources
      .filter((s) => s.schedule_enabled)
      .map((s) => s.name);
    if (!sources.length) {
      showToast(
        "Ни одна площадка не включена — выберите режим на карточке площадки на Главной",
        "info"
      );
      return;
    }
    try {
      await withButtonLoading(ev.currentTarget, async () => {
        await api("/api/run-now", {
          method: "POST",
          body: JSON.stringify({ sources, dry_run: true }),
        });
        for (;;) {
          const runStatus = await api("/api/run-now/status");
          if (!runStatus.running) break;
          await new Promise((r) => setTimeout(r, 3000));
        }
      });
      showToast(
        "Проверка закончена — что нашлось, смотрите в «Вакансиях» (статус «тестовый прогон»), ничего не отправлено",
        "success"
      );
      loadAccounts();
    } catch (e) {
      showToast(`Не удалось запустить проверку: ${e.message}`, "error");
    }
  });

  document
    .getElementById("history-apply-filters")
    .addEventListener("click", () => render.history());
  // Согласовано с "Логи" ниже: смена площадки/статуса фильтрует
  // сразу, а не только по клику "Применить" — раньше эти два похожих
  // выпадающих списка в одном приложении вели себя по-разному.
  document
    .getElementById("filter-source")
    .addEventListener("change", () => render.history());
  document
    .getElementById("filter-status")
    .addEventListener("change", () => render.history());
  document.getElementById("filter-show-rejected").addEventListener("change", () => render.history());
  document.getElementById("filter-query").addEventListener("keydown", (e) => {
    if (e.key === "Enter") render.history();
  });
  document
    .getElementById("log-source")
    .addEventListener("change", () => render.logs());
  document
    .getElementById("log-search")
    .addEventListener("input", () => renderLogLines());
  document
    .getElementById("replies-filter-query")
    .addEventListener("input", () => renderRepliesRows());

  document
    .getElementById("blacklist-add")
    .addEventListener("click", async () => {
      const companies = Array.from(
        document.querySelectorAll(".blacklist-check:checked")
      ).map((c) => c.value);
      if (!companies.length) return;
      // Тот же showConfirm, что уже стоит перед серверной блокировкой
      // на hh.ru ниже — локальный чёрный список отменить проще
      // (просто убрать из списка в "Поиск"), но сама компания сразу
      // перестаёт попадаться в поиске на всех площадках, отмена не
      // мгновенная, стоит спросить перед массовым добавлением.
      const list = companies.join(", ");
      if (
        !(await showConfirm(
          `Добавить в чёрный список: ${list}? Эти компании перестанут попадаться в поиске на всех площадках.`
        ))
      ) {
        return;
      }
      await api("/api/blacklist", {
        method: "POST",
        body: JSON.stringify({ companies }),
      });
      render.analytics();
    });

  // Делегирование клика: список кандидатов перерисовывается на каждый
  // render.analytics(), поэтому слушатель вешаем на постоянный
  // родительский элемент, а не на кнопки напрямую.
  document
    .getElementById("blacklist-candidates")
    .addEventListener("click", async (ev) => {
      const btn = ev.target.closest(".block-hh-employer");
      if (!btn) return;
      const company = btn.dataset.company;
      if (!(await showConfirm(`Заблокировать "${company}" на hh.ru? Это серверная блокировка, отменить её сложнее, чем локальный чёрный список.`))) {
        return;
      }
      btn.disabled = true;
      btn.textContent = "…";
      await api("/api/headhunter/block-employer", {
        method: "POST",
        body: JSON.stringify({ company }),
      });
      btn.textContent = "Запрошено";
    });

  Promise.all([
    api("/api/generate/styles"),
    api("/api/generate/styles/ats-report"),
  ]).then(([styles, atsReport]) => {
    const select = document.getElementById("gen-style");
    const note = document.getElementById("gen-style-ats-note");
    select.innerHTML = styles
      .map((s) => {
        const risks = atsReport[s] || [];
        const warn = risks.length ? "⚠️ " : "";
        const title = risks.length ? ` title="${escapeHtml(risks.join(" "))}"` : "";
        return `<option value="${s}"${title}>${warn}${escapeHtml(s)}</option>`;
      })
      .join("");
    const updateNote = () => {
      const risks = atsReport[select.value] || [];
      note.innerHTML = risks.length
        ? `⚠️ Возможные проблемы с ATS у стиля «${escapeHtml(select.value)}»: ${risks.map(escapeHtml).join(" ")}`
        : `✅ У стиля «${escapeHtml(select.value)}» известных проблем с ATS не найдено (проверка эвристическая, не гарантия).`;
    };
    select.addEventListener("change", updateNote);
    if (styles.length) updateNote();
  });
  document
    .getElementById("gen-resume")
    .addEventListener("click", () => startGenerate("resume"));
  document
    .getElementById("gen-resume-tailored")
    .addEventListener("click", () => startGenerate("resume-tailored"));
  document
    .getElementById("gen-cover-letter")
    .addEventListener("click", () => startGenerate("cover-letter"));
  document
    .getElementById("gen-resume-audit")
    .addEventListener("click", startResumeAudit);

  ["primary", "linkedin"].forEach((kind) => {
    const input = document.getElementById(`resume-upload-${kind}`);
    const status = document.getElementById("tgq-resume-status");
    input.addEventListener("change", async () => {
      const file = input.files[0];
      if (!file) return;
      status.textContent = `Загружаю ${file.name}…`;
      const formData = new FormData();
      formData.append("file", file);
      try {
        await api(`/api/resume/upload?kind=${kind}`, { method: "POST", headers: {}, body: formData });
        renderResumes();
        if (kind === "primary") {
          // ИИ перечитывает новое резюме — из него берутся имя, опыт и навыки для писем.
          status.textContent = "✅ Загружено. ИИ перечитывает резюме…";
          api("/api/resume/refresh-plain-text", { method: "POST" })
            .then(() => (status.textContent = "✅ Резюме обновлено — письма пойдут уже по нему"))
            .catch((e) => (status.textContent = `Загружено, но ИИ не смог его прочитать: ${e.message.replace(/^\d+: /, "")}`));
        } else {
          status.textContent = "✅ Резюме обновлено";
        }
      } catch (e) {
        status.textContent = `Ошибка: ${e.message.replace(/^\d+: /, "")}`;
      } finally {
        input.value = "";
      }
    });
  });


  document.getElementById("limits-save").addEventListener("click", async () => {
    const status = document.getElementById("limits-status");
    const daily = parseInt(document.getElementById("limit-daily").value, 10);
    const linkedin = parseInt(
      document.getElementById("limit-linkedin").value,
      10
    );
    const perRun = parseInt(
      document.getElementById("limit-per-run").value,
      10
    );
    // Пустое поле — не трогаем сохранённое значение на сервере
    // (POST игнорирует null), а не пытаемся его "снять": у
    // set_source_field() нет удаления поля из YAML, только запись.
    const totalRaw = document.getElementById("limit-total").value.trim();
    const total = totalRaw ? parseInt(totalRaw, 10) : null;
    const minScore = parseFloat(
      document.getElementById("limit-min-score").value
    );
    const suitabilityScore = parseFloat(
      document.getElementById("limit-suitability-score").value
    );
    const llmAlertRaw = document.getElementById("llm-alert-usd").value;
    const llmAlert = llmAlertRaw ? parseFloat(llmAlertRaw) : null;
    const retentionDays = parseInt(
      document.getElementById("limit-history-retention").value,
      10
    );
    status.textContent = "Сохранение…";
    try {
      await api("/api/settings/limits", {
        method: "POST",
        body: JSON.stringify({
          daily_application_limit: daily,
          linkedin_daily_application_limit: linkedin,
          total_daily_application_limit: total,
          job_max_applications: perRun,
          job_min_score: Number.isFinite(minScore) ? minScore : null,
          job_suitability_score: Number.isFinite(suitabilityScore)
            ? suitabilityScore
            : null,
          application_retention_days: Number.isFinite(retentionDays)
            ? retentionDays
            : 0,
          ...(llmAlert !== null ? { llm_daily_cost_alert_usd: llmAlert } : {}),
        }),
      });
      status.textContent = "Сохранено.";
      setTimeout(() => (status.textContent = ""), 2000);
    } catch (e) {
      status.textContent = `Ошибка: ${e.message}`;
    }
  });

  document
    .getElementById("limits-distribute")
    .addEventListener("click", async () => {
      const status = document.getElementById("limits-status");
      status.textContent = "Распределение…";
      try {
        await api("/api/settings/limits/distribute", { method: "POST" });
        status.textContent = "Готово.";
        await render.settings();
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  // Профили риска: одним кликом задают общий дефолт (daily/linkedin/
  // per-run) И снимают "своё значение" (override) со всех площадок в
  // таблице ниже, плюс выставляют интервал между прогонами — иначе
  // площадки, у которых уже есть явное число, остались бы на нём,
  // кнопка ничего бы для них не меняла. Эта функция живёт в
  // initDashboard(), не в render.settings() — своего "status" с
  // .sources в области видимости нет, поэтому список площадок
  // запрашивается заново, а не через внешнюю переменную.
  async function applyRiskPreset(daily, linkedin, perRun, intervalHours) {
    const statusEl = document.getElementById("limits-status");
    statusEl.textContent = "Сохранение…";
    try {
      const status = await api("/api/status");
      await api("/api/settings/limits", {
        method: "POST",
        body: JSON.stringify({
          daily_application_limit: daily,
          linkedin_daily_application_limit: linkedin,
          job_max_applications: perRun,
        }),
      });
      // Последовательно, не Promise.all: set_source_field/
      // unset_source_field в config_patch.py читают и переписывают
      // весь YAML-файл без блокировки — несколько параллельных
      // запросов гонятся за одним файлом и портят его (поймано здесь
      // же при проверке: ConfigError "expected <block end>, but
      // found <scalar>" после параллельной записи по всем площадкам).
      for (const s of status.sources) {
        await api("/api/settings", {
          method: "POST",
          body: JSON.stringify({
            source: s.name,
            clear_daily_application_limit: true,
            clear_job_max_applications: true,
            interval_hours: intervalHours,
          }),
        });
      }
      statusEl.textContent = "Готово.";
      await render.settings();
    } catch (e) {
      statusEl.textContent = `Ошибка: ${e.message}`;
    }
  }

  document
    .getElementById("limits-preset-cautious")
    .addEventListener("click", () => applyRiskPreset(8, 4, 3, 4));
  document
    .getElementById("limits-preset-standard")
    .addEventListener("click", () => applyRiskPreset(15, 8, 5, 3));
  document
    .getElementById("limits-preset-aggressive")
    .addEventListener("click", () => applyRiskPreset(25, 12, 8, 2));

  // Строгость подбора — просто подставляет значения в те же два
  // числовых поля (min-score/suitability-score), которые и так уже
  // выше в этой панели, ничего сама не сохраняет — жмут "Сохранить"
  // как и при ручном вводе чисел. Не переиспользует applyRiskPreset:
  // тот шлёт запрос и трогает лимиты откликов, а не балл фита.
  const FIT_PRESETS = {
    soft: [2, 5],
    standard: [4, 7],
    strict: [6, 8],
  };
  document
    .getElementById("limit-fit-preset")
    .addEventListener("change", (e) => {
      const preset = FIT_PRESETS[e.target.value];
      if (!preset) return;
      document.getElementById("limit-min-score").value = preset[0];
      document.getElementById("limit-suitability-score").value = preset[1];
    });

  document.querySelectorAll("#provider-grid .provider-card").forEach((card) => {
    card.addEventListener("click", () => {
      // Модель и ключ привязаны к провайдеру — переключение карточки
      // сразу подставляет список моделей и превью ключа именно этого
      // провайдера, а не оставляет значения от предыдущего (иначе,
      // например, gpt-4o-mini тихо отправился бы в запрос к Groq).
      applyLLMSelection(card.dataset.provider, null);
    });
  });

  function linesOf(id) {
    return document
      .getElementById(id)
      .value.split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  document
    .getElementById("search-save")
    .addEventListener("click", async () => {
      const status = document.getElementById("search-status");
      status.textContent = "Сохранение…";
      try {
        await api("/api/settings/search", {
          method: "POST",
          body: JSON.stringify({
            positions: linesOf("search-positions"),
            locations: linesOf("search-locations"),
            company_blacklist: linesOf("search-company-blacklist"),
            title_blacklist: linesOf("search-title-blacklist"),
            location_blacklist: linesOf("search-location-blacklist"),
          }),
        });
        status.textContent = "Сохранено.";
        setTimeout(() => (status.textContent = ""), 2000);
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  document
    .getElementById("search-generate-positions")
    .addEventListener("click", async () => {
      const status = document.getElementById("search-generate-status");
      status.textContent = "Читаем резюме…";
      try {
        const result = await api("/api/settings/generate-positions", {
          method: "POST",
        });
        document.getElementById("search-positions").value = (
          result.positions || []
        ).join("\n");
        status.textContent = "Готово — проверьте список и Сохраните.";
        setTimeout(() => (status.textContent = ""), 3500);
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  document
    .getElementById("telegram-status-refresh")
    .addEventListener("click", () => render.telegram());

  document
    .getElementById("telegram-login-send-code")
    .addEventListener("click", async () => {
      const status = document.getElementById("telegram-login-status");
      const phone = document.getElementById("telegram-login-phone").value.trim();
      if (!phone) {
        status.textContent = "Введите номер телефона.";
        return;
      }
      status.textContent = "Отправляю код…";
      try {
        await api("/api/telegram/login/start", {
          method: "POST",
          body: JSON.stringify({ phone }),
        });
        status.textContent = "Код отправлен в Telegram — введите его ниже.";
        document.getElementById("telegram-login-code-row").style.display = "";
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  document
    .getElementById("telegram-login-submit-code")
    .addEventListener("click", async () => {
      const status = document.getElementById("telegram-login-status");
      const code = document.getElementById("telegram-login-code").value.trim();
      if (!code) {
        status.textContent = "Введите код.";
        return;
      }
      status.textContent = "Проверяю код…";
      try {
        const result = await api("/api/telegram/login/code", {
          method: "POST",
          body: JSON.stringify({ code }),
        });
        if (result.needs_password) {
          status.textContent = "Включена двухфакторка — введите пароль.";
          document.getElementById(
            "telegram-login-password-row"
          ).style.display = "";
        } else {
          status.textContent = "✅ Вход выполнен.";
          document.getElementById("telegram-login-code-row").style.display =
            "none";
          await render.telegram();
        }
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  document
    .getElementById("telegram-login-submit-password")
    .addEventListener("click", async () => {
      const status = document.getElementById("telegram-login-status");
      const password = document.getElementById(
        "telegram-login-password"
      ).value;
      if (!password) {
        status.textContent = "Введите пароль.";
        return;
      }
      status.textContent = "Проверяю пароль…";
      try {
        await api("/api/telegram/login/password", {
          method: "POST",
          body: JSON.stringify({ password }),
        });
        status.textContent = "✅ Вход выполнен.";
        document.getElementById("telegram-login-password-row").style.display =
          "none";
        await render.telegram();
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  document
    .getElementById("tg-settings-save")
    .addEventListener("click", async () => {
      const status = document.getElementById("tg-settings-status");
      status.textContent = "Сохранение…";
      const numOrNull = (id) => {
        const v = document.getElementById(id).value.trim();
        return v === "" ? null : Number(v);
      };
      try {
        await api("/api/settings/telegram", {
          method: "POST",
          body: JSON.stringify({
            channels: linesOf("tg-channels"),
            max_post_age_days: numOrNull("tg-max-age"),
            daily_message_limit: numOrNull("tg-daily-limit"),
            auto_message: document.getElementById("tg-auto-message").checked,
            active_hours_start: numOrNull("tg-hours-start"),
            active_hours_end: numOrNull("tg-hours-end"),
          }),
        });
        status.textContent = "Сохранено.";
        setTimeout(() => (status.textContent = ""), 2000);
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  async function sendTelegramMessage() {
    if (!activeTelegramContact) return;
    const input = document.getElementById("tg-chat-input");
    const text = input.value.trim();
    if (!text) return;
    const status = document.getElementById("tg-chat-status");
    status.textContent = "Отправка…";
    try {
      await api(
        `/api/telegram/conversations/${activeTelegramContact}/send`,
        { method: "POST", body: JSON.stringify({ text }) }
      );
      input.value = "";
      status.textContent = "";
      await openTelegramConversation(activeTelegramContact);
    } catch (e) {
      status.textContent = `Ошибка: ${e.message}`;
    }
  }

  document
    .getElementById("tg-chat-send")
    .addEventListener("click", sendTelegramMessage);
  document.getElementById("tg-chat-input").addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") sendTelegramMessage();
  });

  document
    .getElementById("tg-chat-attach-resume")
    .addEventListener("click", async () => {
      if (!activeTelegramContact) return;
      const status = document.getElementById("tg-chat-status");
      status.textContent = "Отправка резюме…";
      try {
        await api(
          `/api/telegram/conversations/${activeTelegramContact}/send-resume`,
          { method: "POST" }
        );
        status.textContent = "";
        await openTelegramConversation(activeTelegramContact);
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  document
    .getElementById("tg-chat-delete")
    .addEventListener("click", async () => {
      if (!activeTelegramContact) return;
      const ok = await showConfirm(
        `Удалить всю переписку с @${activeTelegramContact}? Это не архив — история удаляется без возможности восстановить, а контакт перестаёт считаться "уже написанным" (бот может написать ему заново при следующем совпадении).`
      );
      if (!ok) return;
      try {
        await api(`/api/telegram/conversations/${activeTelegramContact}`, {
          method: "DELETE",
        });
        activeTelegramContact = null;
        document.getElementById("tg-chat-panel").style.display = "none";
        document.getElementById("tg-chat-empty").style.display = "";
        await render.telegram();
      } catch (e) {
        document.getElementById("tg-chat-status").textContent = `Ошибка: ${e.message}`;
      }
    });

  document
    .getElementById("llm-provider-save")
    .addEventListener("click", async () => {
      const status = document.getElementById("llm-provider-status");
      const active = document.querySelector(
        "#provider-grid .provider-card.active"
      );
      if (!active) {
        status.textContent = "Выберите провайдера.";
        return;
      }
      const model = document.getElementById("llm-model").value.trim();
      const baseUrl = document.getElementById("llm-base-url").value.trim();
      const mode = document.getElementById("llm-mode").value;
      const fallbackEnabled = document.getElementById(
        "llm-fallback-enabled"
      ).checked;
      status.textContent = "Сохранение…";
      try {
        await api("/api/settings/llm", {
          method: "POST",
          body: JSON.stringify({
            provider: active.dataset.provider,
            model: model || null,
            base_url: baseUrl || null,
            mode,
            fallback_enabled: fallbackEnabled,
          }),
        });
        status.textContent = "Сохранено — применено сразу.";
        setTimeout(() => (status.textContent = ""), 2500);
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  document
    .getElementById("llm-key-save")
    .addEventListener("click", async () => {
      const status = document.getElementById("llm-key-status");
      const input = document.getElementById("llm-key-input");
      const active = document.querySelector(
        "#provider-grid .provider-card.active"
      );
      const key = input.value.trim();
      if (!active) {
        status.textContent = "Выберите провайдера.";
        return;
      }
      if (!key) {
        status.textContent = "Вставьте ключ.";
        return;
      }
      status.textContent = "Сохранение…";
      try {
        const result = await api("/api/settings/llm-key", {
          method: "POST",
          body: JSON.stringify({
            provider: active.dataset.provider,
            api_key: key,
          }),
        });
        llmCatalog.api_key_previews[result.provider] =
          result.api_key_preview;
        document.getElementById("llm-key-preview").textContent =
          result.api_key_preview;
        active.classList.add("has-key");
        input.value = "";
        status.textContent = "Ключ сохранён.";
        setTimeout(() => (status.textContent = ""), 2500);
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  document
    .getElementById("llm-provider-base-url-save")
    .addEventListener("click", async () => {
      const status = document.getElementById("llm-provider-base-url-status");
      const input = document.getElementById("llm-provider-base-url-input");
      const active = document.querySelector(
        "#provider-grid .provider-card.active"
      );
      const url = input.value.trim();
      if (!active) {
        status.textContent = "Выберите провайдера.";
        return;
      }
      if (!url) {
        status.textContent = "Вставьте base URL.";
        return;
      }
      status.textContent = "Сохранение…";
      try {
        const result = await api("/api/settings/llm-provider-base-url", {
          method: "POST",
          body: JSON.stringify({
            provider: active.dataset.provider,
            base_url: url,
          }),
        });
        llmCatalog.provider_base_urls[result.provider] = result.base_url;
        document.getElementById("llm-provider-base-url-preview").textContent =
          result.base_url;
        input.value = "";
        status.textContent = "Base URL сохранён.";
        setTimeout(() => (status.textContent = ""), 2500);
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  const knownTabs = new Set(Object.keys(VIEW_GROUP));
  const initialTab = location.hash.replace("#", "");
  switchTab(knownTabs.has(initialTab) ? initialTab : "overview");
  // ponytail: раньше опрос гонял только вкладку "Обзор" — история
  // откликов/ответы/логи обновлялись только вручную (кнопка "Применить"
  // или смена вкладки), из-за чего прогресс запущенного отклика был не
  // виден без перезапуска программы. Настройки сюда намеренно не
  // включены — иначе несохранённый ввод в полях будет затираться, как
  // чекбоксы на "Обзоре" до фикса выше.
  const LIVE_TABS = new Set([
    "overview",
    "history",
    "replies",
    "logs",
    "telegram",
  ]);
  function refreshActiveTab() {
    const active = currentView;
    if (active && LIVE_TABS.has(active)) render[active]();
    else if (active === "settings") {
      // Только подсветка провайдеров + статус Telegram, не полный
      // render.settings() — тот перезатирал бы несохранённый ввод в
      // полях ключа/модели. telegram-connect-status — отдельный
      // элемент, ничего не перезатирает.
      api("/api/settings/llm/status").then(applyLLMProviderStatus);
      refreshTelegramConnectStatus();
    }
  }
  // ponytail: desktop_app.py pokes this directly via evaluate_js — WKWebView
  // throttles setInterval/focus/visibilitychange alike when the window isn't
  // key, so none of those alone kept this reliable in the packaged app.
  window.__refreshActiveTab = refreshActiveTab;
  setInterval(refreshActiveTab, 7000);
  // Десктопное окно (pywebview/WKWebView) троттлит setInterval, пока
  // не в фокусе — без этого прогресс отклика "зависает" на экране,
  // пока пользователь не кликнет по вкладке вручную. window.focus не
  // всегда всплывает в WKWebView, поэтому дублируем visibilitychange.
  window.addEventListener("focus", refreshActiveTab);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshActiveTab();
  });
}

function initSetupScreen() {
  document
    .getElementById("setup-init")
    .addEventListener("click", async () => {
      const status = document.getElementById("setup-status");
      const apiKey = document.getElementById("setup-api-key").value.trim();
      status.textContent = "Создание…";
      try {
        const result = await api("/api/setup/init", {
          method: "POST",
          body: JSON.stringify({ api_key: apiKey || null }),
        });
        if (result.ready) {
          status.textContent = "Готово, открываю дашборд…";
          setTimeout(() => window.location.reload(), 600);
        } else {
          status.textContent = `Создано, но не готово: ${result.error}`;
        }
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });
}

document.addEventListener("DOMContentLoaded", async () => {
  const setupStatus = await api("/api/setup/status");
  if (setupStatus.needs_setup) {
    document.getElementById("setup-screen").style.display = "";
    initSetupScreen();
    return;
  }
  document.getElementById("app-shell").style.display = "";
  initDashboard();
  document
    .getElementById("direct-company-add")
    .addEventListener("click", addDirectCompany);
  document.getElementById("settings-direct").addEventListener("change", saveDirectSetting);
  document.getElementById("offer-add").addEventListener("click", addOffer);
  document.getElementById("outreach-save").addEventListener("click", saveOutreachSettings);
  document.getElementById("tgq-save").addEventListener("click", saveTelegramWatch);
  document.getElementById("import-btn").addEventListener("click", () => document.getElementById("import-file").click());
  document.getElementById("import-file").addEventListener("change", (e) => {
    if (e.target.files[0]) importPreview(e.target.files[0]);
    e.target.value = "";
  });
  document.getElementById("tgq-greeting").addEventListener("input", updateGreetingPreview);
  document.getElementById("tgq-resume-add").addEventListener("click", () =>
    document.getElementById("tgq-resume-file").click()
  );
  document.getElementById("tgq-resume-file").addEventListener("change", (e) => {
    uploadTelegramResumes([...e.target.files]);
    e.target.value = "";
  });
  document
    .querySelector('[data-settings-tab="settings-tg-quick"]')
    .addEventListener("click", loadTelegramWatch);
  bindGotoSettings(document.getElementById("view-telegram"));
  document.querySelectorAll("[data-goto-view]").forEach((a) =>
    a.addEventListener("click", (e) => {
      e.preventDefault();
      switchTab(a.dataset.gotoView);
    })
  );
  document.getElementById("tg-keys-save").addEventListener("click", async () => {
    try {
      await api("/api/telegram/keys", {
        method: "POST",
        body: JSON.stringify({
          api_id: document.getElementById("tg-api-id").value,
          api_hash: document.getElementById("tg-api-hash").value,
        }),
      });
      showToast("Ключи сохранены — теперь введите номер телефона", "success");
      render.telegram();
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
  });
  document.getElementById("parser-open-base").addEventListener("click", () => {
    document.getElementById("contacts-filter-source").value = "telegram";
    switchTab("contacts");
  });
  document.querySelectorAll("#base-table th[data-sort]").forEach((th) =>
    th.addEventListener("click", () => {
      baseState.dir = baseState.sort === th.dataset.sort ? -baseState.dir : th.dataset.sort === "company" ? 1 : -1;
      baseState.sort = th.dataset.sort;
      renderContactsList();
    })
  );
  const resetPage = () => {
    baseState.page = 0;
    renderContactsList();
  };
  ["contacts-filter-source", "contacts-filter-contact"].forEach((id) =>
    document.getElementById(id).addEventListener("change", resetPage)
  );
  document.getElementById("contacts-filter-query").addEventListener("input", resetPage);
  document.getElementById("outreach-email-test").addEventListener("click", testOutreachEmail);
  ["outreach-digest", "outreach-digest-hour", "digest-quiet"].forEach((id) => document.getElementById(id).addEventListener("change", saveDigest));
  // Фильтры удалёнки — в «Что ищу», сохраняются сразу.
  ["outreach-skip-us", "outreach-skip-eu"].forEach((id) =>
    document.getElementById(id).addEventListener("change", async () => {
      try {
        await api("/api/settings/outreach", {
          method: "POST",
          body: JSON.stringify({
            skip_us_only: document.getElementById("outreach-skip-us").checked,
            skip_europe_only: document.getElementById("outreach-skip-eu").checked,
          }),
        });
        showToast("Сохранено", "success");
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error");
      }
    })
  );
  document.querySelector('[data-settings-tab="settings-notifications"]').addEventListener("click", loadOutreachSettings);
  document
    .querySelector('[data-settings-tab="settings-outreach"]')
    .addEventListener("click", loadOutreachSettings);
  document.getElementById("trainer-check").addEventListener("click", checkTrainerAnswer);
  document.getElementById("trainer-next").addEventListener("click", () => {
    if (!trainer || !trainer.questions.length) return;
    trainer.index = (trainer.index + 1) % trainer.questions.length;
    showTrainerQuestion();
  });
  document.querySelectorAll("[data-close-overlay]").forEach((btn) => {
    btn.addEventListener("click", () => hideOverlay(btn.closest(".command-overlay")));
  });

});
