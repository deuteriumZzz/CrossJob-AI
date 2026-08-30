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
  superjob: "SuperJob",
  geekjob: "geekjob.ru",
  rabota_ru: "rabota.ru",
  telegram: "Telegram",
  getmatch: "GetMatch",
  linkedin: "LinkedIn",
  habr_career: "Habr Career",
};

const STATUS_DOT = {
  ok: "ok",
  error: "error",
  blocked: "blocked",
  never_run: "never_run",
};

function sourceLabel(name) {
  return SOURCE_LABELS[name] || name;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
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
};

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

function countUp(el, target, duration = 700) {
  if (REDUCE_MOTION) {
    el.textContent = target;
    return;
  }
  const start = 0;
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

function switchTab(name) {
  const prevName = document.querySelector("nav.tabs button.active")?.dataset.tab;
  document
    .querySelectorAll("nav.tabs button")
    .forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
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
    document.querySelector(`nav.tabs button[data-tab="${name}"]`)
  );
}

let overviewLoaded = false;
let lastOverviewSnapshot = null;
let historyLoaded = false;
let lastHistorySnapshot = null;
let lastHistoryEntries = [];
let repliesLoaded = false;
let lastRepliesSnapshot = null;
let lastRepliesCount = 0;
let logsLoaded = false;
let lastLogsSnapshot = null;
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

function skeletonSourceGrid() {
  return Array.from(
    { length: 8 },
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

const render = {
  async overview() {
    if (!overviewLoaded) {
      document.getElementById("stats-row").innerHTML = skeletonStats();
      document.getElementById("source-grid").innerHTML =
        skeletonSourceGrid();
    }

    const [status, stats] = await Promise.all([
      api("/api/status"),
      api("/api/stats"),
    ]);

    // ponytail: без этой проверки весь блок ниже (счётчики со
    // start-anew анимацией, карточки площадок, чекбоксы) пересобирался
    // на каждый опрос раз в 7с даже когда ничего не изменилось — визуально
    // это и есть "мерцание", о котором сообщил пользователь.
    const snapshot = JSON.stringify({ status, stats });
    const unchanged = overviewLoaded && snapshot === lastOverviewSnapshot;
    lastOverviewSnapshot = snapshot;

    const badge = document.getElementById("daemon-badge");
    const runningLabel = status.daemon_started_at
      ? `демон работает · ${formatElapsed(status.daemon_started_at)}`
      : "демон работает";
    badge.innerHTML = `<span class="badge-dot"></span><span class="btn-label">${
      status.daemon_running ? runningLabel : "демон остановлен"
    }</span>`;
    badge.classList.toggle("on", status.daemon_running);
    badge.classList.toggle("off", !status.daemon_running);
    document.getElementById("daemon-start").disabled = status.daemon_running;
    document.getElementById("daemon-stop").disabled = !status.daemon_running;

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
        <div class="stat-card"><div class="value" data-target="${stats.day}">0</div><div class="label">Сегодня</div></div>
        <div class="stat-card"><div class="value" data-target="${stats.week}">0</div><div class="label">За неделю</div></div>
        <div class="stat-card"><div class="value" data-target="${stats.month}">0</div><div class="label">За месяц</div></div>
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
      document.getElementById("source-grid").innerHTML = applySourceOrder(status.sources, "name")
        .map((s, i) => {
          const dot = STATUS_DOT[s.status] || "never_run";
          const ratio = s.daily_limit
            ? Math.min(1, s.applied_today / s.daily_limit)
            : 0;
          const barClass =
            ratio >= 1 ? "full" : ratio >= 0.7 ? "warn" : "";
          const ringC = 2 * Math.PI * 13;
          const ringOffset = ringC * (1 - ratio);
          // telegram отправляет (пишет контакту) только при
          // auto_message; остальные площадки — при auto_apply. Без
          // этого "Откликов сегодня 0/N" выглядит как площадка не
          // работает, хотя она специально настроена только искать и
          // класть найденное в Историю, ничего не отправляя.
          const isSearchOnly =
            s.name === "telegram" ? !s.auto_message : !s.auto_apply;
          const responseRow = isSearchOnly
            ? `<div class="row"><span>Режим</span><span>🔍 только поиск</span></div>`
            : `<div class="row"><span>Откликов сегодня</span>
              <span class="limit-ring-wrap">
                <svg width="18" height="18" viewBox="0 0 32 32">
                  <circle class="limit-ring-bg" cx="16" cy="16" r="13"></circle>
                  <circle class="limit-ring-fill ${barClass}" cx="16" cy="16" r="13" style="stroke-dasharray:${ringC.toFixed(2)};stroke-dashoffset:${ringOffset.toFixed(2)}"></circle>
                </svg>
                ${s.applied_today}/${s.daily_limit}
              </span></div>`;
          return `
          <div class="source-card stagger-item" data-source="${s.name}" draggable="true" style="animation-delay:${staggerDelay(i)}">
            <div class="source-card-actions">
              <button type="button" class="src-goto-history" data-source="${s.name}" title="История откликов этой площадки" aria-label="История откликов ${sourceLabel(s.name)}">
                <svg viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="7.3" stroke="currentColor" stroke-width="1.6"/><path d="M10 5.8V10l3 2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
              </button>
              <button type="button" class="src-goto-logs" data-source="${s.name}" title="Логи этой площадки" aria-label="Логи ${sourceLabel(s.name)}">
                <svg viewBox="0 0 20 20" fill="none"><rect x="2.5" y="3.5" width="15" height="13" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M5.5 7.5 8 10l-2.5 2.5M9.8 12.5h4.7" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
            </div>
            <h3>
              <input type="checkbox" class="schedule-toggle switch" data-source="${s.name}" title="В расписании демона" ${s.schedule_enabled ? "checked" : ""} />
              <span class="dot ${dot}"></span> ${sourceLabel(s.name)}
            </h3>
            <div class="row"><span>Расписание</span><span>${s.schedule_enabled ? `каждые ${s.interval_hours}ч` : "выключено"}</span></div>
            <div class="row"><span>Последний запуск</span><span>${fmtTime(s.last_run)}</span></div>
            <div class="row"><span>Следующий запуск</span><span>${fmtTime(s.next_run)}</span></div>
            ${responseRow}
            ${errorRowHtml(s.last_error)}
          </div>`;
        })
        .join("");
      document.getElementById("chat-checks-grid").innerHTML = applySourceOrder(status.chat_checks, "name")
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
              <input type="checkbox" class="schedule-toggle switch" data-source="${c.name}" title="В расписании демона" ${c.schedule_enabled ? "checked" : ""} />
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
    if (!historyLoaded) tbody.innerHTML = skeletonRows(6, 6);

    const entries = await api(`/api/applications?${params}`);
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
      tbody.innerHTML = `<tr><td colspan="6">${emptyStateHtml("Ничего не найдено.")}</td></tr>`;
      document.getElementById("history-timeline").innerHTML = emptyStateHtml("Ничего не найдено.");
      return;
    }
    const reversed = entries.slice().reverse();
    tbody.innerHTML = reversed
      .map(
        (e, i) => `
      <tr class="reveal" style="transition-delay:${staggerDelay(i, 25)}">
        <td>${fmtTime(e.applied_at)}</td>
        <td>${sourceLabel(e.source)}</td>
        <td>${escapeHtml(e.company)}</td>
        <td><a href="${escapeHtml(e.link)}" target="_blank" rel="noopener">${escapeHtml(e.title)}</a></td>
        <td>${statusLabel(e.status)}</td>
        <td>${e.score ?? ""}</td>
      </tr>`
      )
      .join("");
    observeReveal(tbody);
    renderHistoryTimeline(reversed);
  },

  async replies() {
    const tbody = document.getElementById("replies-rows");
    if (!repliesLoaded) tbody.innerHTML = skeletonRows(3, 4);

    const entries = await api("/api/replies");
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

    if (!entries.length) {
      tbody.innerHTML = `<tr><td colspan="4">${emptyStateHtml("Пока нет ответов.")}</td></tr>`;
      return;
    }
    tbody.innerHTML = entries
      .map(
        (e, i) => `
      <tr class="reveal" style="transition-delay:${staggerDelay(i, 25)}">
        <td>${fmtTime(e.applied_at)}</td>
        <td>${sourceLabel(e.source)}</td>
        <td><a href="${escapeHtml(e.link)}" target="_blank" rel="noopener">${escapeHtml(e.company)} — ${escapeHtml(e.title)}</a></td>
        <td>${escapeHtml(e.last_known_state)}</td>
      </tr>`
      )
      .join("");
    observeReveal(tbody);
  },

  async analytics() {
    renderActivityHeatmap();
    const gapsEl = document.getElementById("gaps-list");
    const candidatesEl = document.getElementById("blacklist-candidates");
    gapsEl.innerHTML = Array.from({ length: 3 }, () => `<li><div class="skeleton" style="height:14px"></div></li>`).join("");
    candidatesEl.innerHTML = Array.from({ length: 2 }, () => `<div class="skeleton" style="height:20px;margin-bottom:6px"></div>`).join("");

    const [gaps, candidates] = await Promise.all([
      api("/api/analytics/gaps"),
      api("/api/analytics/blacklist-candidates"),
    ]);

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
    const [status, salary] = await Promise.all([
      api("/api/status"),
      api("/api/settings/salary"),
    ]);

    api("/api/settings/search").then((search) => {
      document.getElementById("search-positions").value = (
        search.positions || []
      ).join("\n");
      document.getElementById("search-locations").value = (
        search.locations || []
      ).join("\n");
      document.getElementById("search-company-blacklist").value = (
        search.company_blacklist || []
      ).join("\n");
      document.getElementById("search-title-blacklist").value = (
        search.title_blacklist || []
      ).join("\n");
      document.getElementById("search-location-blacklist").value = (
        search.location_blacklist || []
      ).join("\n");
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

    api("/api/settings/limits").then((limits) => {
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
      renderTotalBudget(status, limits.total_daily_application_limit);
      if (limits.llm_daily_cost_alert_usd != null) {
        document.getElementById("llm-alert-usd").value =
          limits.llm_daily_cost_alert_usd;
      }
    });

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

    const tbody = document.getElementById("settings-rows");
    tbody.innerHTML = status.sources
      .map(
        (s, i) => `
      <tr data-source="${s.name}" class="reveal" style="transition-delay:${staggerDelay(i, 25)}">
        <td>${sourceLabel(s.name)}</td>
        <td title="${
          s.readiness && s.readiness.missing.length
            ? "Не хватает: " + s.readiness.missing.join(", ")
            : s.readiness && s.readiness.resume && s.readiness.resume.warning
              ? s.readiness.resume.warning
              : "Данных для подключения достаточно"
        }">${s.readiness && s.readiness.ready ? "✅" : "⚠️"}</td>
        <td><input type="checkbox" class="s-schedule switch" ${s.schedule_enabled ? "checked" : ""} /></td>
        <td><input type="number" class="s-interval" min="1" value="${s.interval_hours ?? 3}" /></td>
        <td><input type="checkbox" class="s-auto switch" ${s.auto_apply ? "checked" : ""} /></td>
        <td>${
          s.name === "headhunter"
            ? `<input type="checkbox" class="s-auto-reply switch" ${s.auto_reply ? "checked" : ""} />`
            : "—"
        }</td>
        <td>${
          s.name === "headhunter"
            ? `<input type="checkbox" class="s-auto-bump switch" ${s.auto_bump_resume ? "checked" : ""} />`
            : "—"
        }</td>
        <td><input type="text" class="s-resume-id" value="${s.resume_id || ""}" placeholder="id резюме на площадке" /></td>
        <td><input type="number" class="s-max-applications" min="1" value="${s.job_max_applications}" /></td>
        <td><input type="number" class="s-daily-limit" min="1" value="${s.daily_limit}" /></td>
        <td><button class="btn btn-secondary s-save">Сохранить</button></td>
        <td><button class="btn btn-ghost btn-small s-filters-toggle" title="Свои должности/локации/зарплата для этой площадки">⚙ Фильтры</button></td>
      </tr>
      <tr class="filters-detail" data-source="${s.name}" style="display:none">
        <td colspan="12">
          <div class="limits-grid" style="margin:10px 0">
            <label class="limit-field">
              <span>Свои должности для ${sourceLabel(s.name)} (пусто — общие из "Поиск")</span>
              <textarea class="f-positions" rows="2" placeholder="оставить пустым — использовать общие">${(s.positions_override || []).join("\n")}</textarea>
            </label>
            <label class="limit-field">
              <span>Свои локации для ${sourceLabel(s.name)} (пусто — общие из "Поиск")</span>
              <textarea class="f-locations" rows="2" placeholder="оставить пустым — использовать общие">${(s.locations_override || []).join("\n")}</textarea>
            </label>
            ${
              s.name === "headhunter"
                ? `<label class="limit-field">
                <span>Зарплата для автоответа в чате HH</span>
                <input type="text" class="f-hh-salary" value="${salary.hh_salary_expectations || ""}" placeholder="250000-300000 RUR" />
              </label>`
                : ""
            }
            ${
              s.name === "linkedin"
                ? `<label class="limit-field">
                <span>Зарплата для скрининга LinkedIn (USD/год)</span>
                <input type="text" class="f-linkedin-salary" value="${salary.linkedin_salary_range_usd || ""}" placeholder="60000-80000" />
              </label>`
                : ""
            }
          </div>
          <p class="muted small">Сейчас реально ищет по: «${(s.effective_positions || []).join("», «") || "—"}»${
          s.name === "linkedin"
            ? " · локации LinkedIn настраиваются отдельно (linkedin.locations)"
            : `, локации: «${(s.effective_locations || []).join("», «") || "любые"}»`
        }.</p>
          <div class="filters">
            <button class="btn btn-secondary f-save">Сохранить фильтры</button>
            <span class="f-status muted small"></span>
          </div>
        </td>
      </tr>`
      )
      .join("");
    observeReveal(tbody);

    tbody.querySelectorAll(".s-save").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        const row = ev.target.closest("tr");
        const source = row.dataset.source;
        const autoReplyEl = row.querySelector(".s-auto-reply");
        const autoBumpEl = row.querySelector(".s-auto-bump");
        const body = {
          source,
          schedule_enabled: row.querySelector(".s-schedule").checked,
          interval_hours: parseInt(row.querySelector(".s-interval").value, 10),
          auto_apply: row.querySelector(".s-auto").checked,
          ...(autoReplyEl ? { auto_reply: autoReplyEl.checked } : {}),
          ...(autoBumpEl ? { auto_bump_resume: autoBumpEl.checked } : {}),
          resume_id: row.querySelector(".s-resume-id").value.trim(),
          job_max_applications: parseInt(
            row.querySelector(".s-max-applications").value,
            10
          ),
          daily_application_limit: parseInt(
            row.querySelector(".s-daily-limit").value,
            10
          ),
        };
        await api("/api/settings", {
          method: "POST",
          body: JSON.stringify(body),
        });
        btn.textContent = "Сохранено";
        setTimeout(() => (btn.textContent = "Сохранить"), 1500);
      });
    });

    tbody.querySelectorAll(".s-filters-toggle").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        const detail = ev.target.closest("tr").nextElementSibling;
        if (detail && detail.classList.contains("filters-detail")) {
          detail.style.display =
            detail.style.display === "none" ? "" : "none";
        }
      });
    });

    const linesOfEl = (el) =>
      el.value
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);

    tbody.querySelectorAll(".f-save").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        const row = ev.target.closest("tr.filters-detail");
        const source = row.dataset.source;
        const statusEl = row.querySelector(".f-status");
        await api("/api/settings", {
          method: "POST",
          body: JSON.stringify({
            source,
            positions: linesOfEl(row.querySelector(".f-positions")),
            locations: linesOfEl(row.querySelector(".f-locations")),
          }),
        });
        const hhSalaryEl = row.querySelector(".f-hh-salary");
        const liSalaryEl = row.querySelector(".f-linkedin-salary");
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
        await render.settings();
      });
    });
  },

  async telegram() {
    const [status, settings, conversations] = await Promise.all([
      api("/api/telegram/status"),
      api("/api/settings/telegram"),
      api("/api/telegram/conversations"),
    ]);

    const badge = document.getElementById("telegram-status-badge");
    const note = document.getElementById("telegram-status-note");
    if (!status.configured) {
      badge.className = "badge off";
      badge.innerHTML = '<span class="badge-dot"></span>не настроено';
      note.textContent =
        "Впишите telegram.api_id/api_hash в secrets.yaml (см. подсказку выше).";
    } else if (status.connected) {
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

    document.getElementById("tg-channels").value = (
      settings.channels || []
    ).join("\n");
    document.getElementById("tg-max-age").value =
      settings.max_post_age_days ?? "";
    document.getElementById("tg-daily-limit").value =
      settings.daily_message_limit ?? "";
    document.getElementById("tg-auto-message").checked = !!settings.auto_message;
    document.getElementById("tg-hours-start").value =
      settings.active_hours_start ?? "";
    document.getElementById("tg-hours-end").value =
      settings.active_hours_end ?? "";
    document.getElementById("tg-intro-template").value =
      settings.intro_message_template || "";

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
      pre.textContent = data.note;
      return;
    }
    pre.textContent = data.lines.join("\n") || "(пусто)";
  },
};

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

function switchSettingsTab(paneId) {
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
    document.querySelector(`#settings-jump button[data-settings-tab="${paneId}"]`)
  );
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
  const parentRect = btn.parentElement.getBoundingClientRect();
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
    document.querySelector("#settings-jump button.active")
  );
}

// Вкладки без понятия "сохранить" (генерация резюме через Selenium,
// ручные best-effort клики на hh.ru) — не размечаем как "не сохранено",
// там нет настройки, которая могла бы потеряться.
const SETTINGS_PANES_WITHOUT_SAVE = new Set(["settings-resume", "settings-hh-resume"]);

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
  document.querySelectorAll("nav.tabs button[data-tab]").forEach((btn) => {
    items.push({
      label: btn.querySelector("span")?.textContent || btn.dataset.tab,
      hint: "Раздел",
      action: () => switchTab(btn.dataset.tab),
    });
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
    if (/^[1-7]$/.test(e.key)) {
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

const NAV_ORDER = ["overview", "history", "replies", "telegram", "analytics", "settings", "logs"];

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
  { tab: "overview", text: "«Обзор» — статус всех площадок и дневная статистика откликов сразу на входе." },
  { tab: "history", text: "«История» — что уже отправлено, с фильтрами и таймлайном." },
  { tab: "telegram", text: "«Telegram» — поиск по каналам вакансий и переписка с контактами." },
  { tab: "settings", text: "«Настройки» — расписание, LLM-провайдер, лимиты откликов и всё остальное по вкладкам." },
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
  }

  function finish() {
    localStorage.setItem("cj-seen-tour", "1");
    overlay.remove();
  }

  document.body.appendChild(overlay);
  renderStep();
}

function renderHistoryTimeline(reversedEntries) {
  const el = document.getElementById("history-timeline");
  if (!reversedEntries.length) return;
  el.innerHTML = reversedEntries
    .map(
      (e, i) => `
    <div class="timeline-item reveal" style="transition-delay:${staggerDelay(i, 20)}">
      <div class="timeline-date">${fmtTime(e.applied_at)}</div>
      <div class="timeline-title"><a href="${escapeHtml(e.link)}" target="_blank" rel="noopener">${escapeHtml(e.company)} — ${escapeHtml(e.title)}</a></div>
      <div class="timeline-meta">${sourceLabel(e.source)} · ${statusLabel(e.status)}${e.score != null ? ` · балл ${e.score}` : ""}</div>
    </div>`
    )
    .join("");
  observeReveal(el);
}

function initHistoryViewToggle() {
  const tableBtn = document.getElementById("history-view-table");
  const timelineBtn = document.getElementById("history-view-timeline");
  const tableWrap = document.getElementById("history-table-wrap");
  const timelineWrap = document.getElementById("history-timeline");
  tableBtn.addEventListener("click", () => {
    tableBtn.classList.add("active");
    timelineBtn.classList.remove("active");
    tableWrap.style.display = "";
    timelineWrap.style.display = "none";
  });
  timelineBtn.addEventListener("click", () => {
    timelineBtn.classList.add("active");
    tableBtn.classList.remove("active");
    tableWrap.style.display = "none";
    timelineWrap.style.display = "";
  });
}

// 13 недель x 7 дней, как в GitHub contributions — считаем прямо на
// клиенте по уже существующему /api/applications, отдельного
// backend-эндпоинта для этого заводить незачем.
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

function loadSourceOrder() {
  try {
    return JSON.parse(localStorage.getItem("cj-source-order") || "[]");
  } catch {
    return [];
  }
}

function saveSourceOrder(order) {
  localStorage.setItem("cj-source-order", JSON.stringify(order));
}

function applySourceOrder(items, key) {
  const order = loadSourceOrder();
  if (!order.length) return items;
  const rank = new Map(order.map((name, i) => [name, i]));
  return items
    .slice()
    .sort((a, b) => (rank.get(a[key]) ?? 999) - (rank.get(b[key]) ?? 999));
}

function initDragReorder(gridId) {
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
    saveSourceOrder(order);
  });
}

// ---------- Changelog popover ----------

const CHANGELOG_VERSION = "2026-08-29-motion";
const CHANGELOG_ITEMS = [
  "Плавающий индикатор вкладок, toggle-переключатели, toast-уведомления",
  "Ctrl/⌘+K — командная палитра, цифры 1–7 — переход по разделам",
  "Кольцевой прогресс и цветные акценты площадок на Обзоре",
  "Таймлайн и heatmap-активность в Истории/Аналитике",
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
  initSettingsDirtyTracking();
  initCommandPalette();
  initKeyboardShortcuts();
  initHistoryViewToggle();

  document.getElementById("llm-key-toggle").addEventListener("click", () => {
    const input = document.getElementById("llm-key-input");
    input.type = input.type === "password" ? "text" : "password";
  });
  initDragReorder("source-grid");
  initDragReorder("chat-checks-grid");
  initChangelogPopover();
  initPointerEffects();
  initOnboardingTour();

  function handleSourceCardActionClick(e) {
    const historyBtn = e.target.closest(".src-goto-history");
    const logsBtn = e.target.closest(".src-goto-logs");
    if (historyBtn) {
      document.getElementById("filter-source").value = historyBtn.dataset.source;
      switchTab("history");
    } else if (logsBtn) {
      document.getElementById("log-source").value = logsBtn.dataset.source;
      switchTab("logs");
    }
  }
  document.getElementById("source-grid").addEventListener("click", handleSourceCardActionClick);
  document.getElementById("chat-checks-grid").addEventListener("click", handleSourceCardActionClick);
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

  document.getElementById("daemon-start").addEventListener("click", async (ev) => {
    await withButtonLoading(ev.currentTarget, () => api("/api/daemon/start", { method: "POST" }));
    showToast("Демон запущен", "success");
    render.overview();
  });
  document.getElementById("daemon-stop").addEventListener("click", async (ev) => {
    await withButtonLoading(ev.currentTarget, () => api("/api/daemon/stop", { method: "POST" }));
    showToast("Демон остановлен", "info");
    render.overview();
  });

  document
    .getElementById("history-apply-filters")
    .addEventListener("click", () => render.history());
  document
    .getElementById("log-source")
    .addEventListener("change", () => render.logs());

  document
    .getElementById("blacklist-add")
    .addEventListener("click", async () => {
      const companies = Array.from(
        document.querySelectorAll(".blacklist-check:checked")
      ).map((c) => c.value);
      if (!companies.length) return;
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

  document
    .getElementById("hh-resume-clone")
    .addEventListener("click", async () => {
      const resumeId = document
        .getElementById("hh-resume-clone-id")
        .value.trim();
      if (!resumeId) return;
      const statusEl = document.getElementById("hh-resume-status");
      statusEl.textContent = "Запущено — откроется браузер…";
      await api("/api/headhunter/clone-resume", {
        method: "POST",
        body: JSON.stringify({ resume_id: resumeId }),
      });
      statusEl.textContent = "Запрошено, результат — в логах/уведомлениях.";
    });

  document
    .getElementById("hh-resume-create-draft")
    .addEventListener("click", async () => {
      const statusEl = document.getElementById("hh-resume-status");
      statusEl.textContent = "Запущено — откроется браузер…";
      await api("/api/headhunter/create-resume-draft", { method: "POST" });
      statusEl.textContent = "Запрошено, ссылка на черновик — в логах/уведомлениях.";
    });

  api("/api/generate/styles").then((styles) => {
    document.getElementById("gen-style").innerHTML = styles
      .map((s) => `<option value="${s}">${s}</option>`)
      .join("");
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
    .getElementById("refresh-plain-text")
    .addEventListener("click", async () => {
      const status = document.getElementById("refresh-plain-text-status");
      status.textContent = "Обновление…";
      try {
        await api("/api/resume/refresh-plain-text", { method: "POST" });
        status.textContent = "Готово.";
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
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

  document
    .getElementById("limits-reset-recommended")
    .addEventListener("click", async () => {
      const status = document.getElementById("limits-status");
      status.textContent = "Сохранение…";
      try {
        await api("/api/settings/limits", {
          method: "POST",
          body: JSON.stringify({
            daily_application_limit: 15,
            linkedin_daily_application_limit: 8,
            job_max_applications: 5,
          }),
        });
        status.textContent = "Готово.";
        await render.settings();
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  document
    .getElementById("llm-alert-save")
    .addEventListener("click", async () => {
      const status = document.getElementById("llm-alert-status");
      const raw = document.getElementById("llm-alert-usd").value;
      const value = raw ? parseFloat(raw) : null;
      if (value === null) {
        status.textContent = "Введите значение.";
        return;
      }
      status.textContent = "Сохранение…";
      try {
        await api("/api/settings/limits", {
          method: "POST",
          body: JSON.stringify({ llm_daily_cost_alert_usd: value }),
        });
        status.textContent = "Сохранено.";
        setTimeout(() => (status.textContent = ""), 2000);
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
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
            intro_message_template: document
              .getElementById("tg-intro-template")
              .value.trim(),
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

  const knownTabs = new Set(
    Array.from(document.querySelectorAll("nav.tabs button")).map(
      (b) => b.dataset.tab
    )
  );
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
    const active = document.querySelector("nav.tabs button.active")?.dataset.tab;
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
});
