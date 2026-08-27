const SOURCE_LABELS = {
  headhunter: "HeadHunter",
  superjob: "SuperJob",
  zarplata: "Zarplata.ru",
  geekjob: "geekjob.ru",
  rabota_ru: "rabota.ru",
  telegram: "Telegram",
  getmatch: "GetMatch",
  linkedin: "LinkedIn",
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

function switchTab(name) {
  document
    .querySelectorAll("nav.tabs button")
    .forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document
    .querySelectorAll("main .view")
    .forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  render[name]?.();
}

let overviewLoaded = false;
let lastOverviewSnapshot = null;
let historyLoaded = false;
let lastHistorySnapshot = null;
let repliesLoaded = false;
let lastRepliesSnapshot = null;
let logsLoaded = false;
let lastLogsSnapshot = null;
let llmCatalog = { models: {}, api_key_previews: {} };
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
  el.innerHTML = `
    <p class="muted small">Сегодня отправлено: ${appliedToday} / ${totalLimit} (общий лимит)</p>
    <div class="limit-bar"><div class="limit-bar-fill ${usedClass}" style="width:${Math.round(usedRatio * 100)}%"></div></div>
    <p class="muted small" style="margin-top:8px${overBudget ? ";color:var(--err)" : ""}">
      ${overBudget ? "⚠️ " : ""}Распределено по площадкам (сумма лимитов в таблице ниже): ${sumPerPlatform} / ${totalLimit}
      ${overBudget ? " — превышает общий лимит, снизьте лимиты отдельных площадок." : ""}
    </p>
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
    badge.innerHTML = `<span class="badge-dot"></span>${
      status.daemon_running ? "демон работает" : "демон остановлен"
    }`;
    badge.classList.toggle("on", status.daemon_running);
    badge.classList.toggle("off", !status.daemon_running);
    document.getElementById("daemon-start").disabled = status.daemon_running;
    document.getElementById("daemon-stop").disabled = !status.daemon_running;

    if (!unchanged) {
      const statsRow = document.getElementById("stats-row");
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
      document.getElementById("source-grid").innerHTML = status.sources
        .map((s, i) => {
          const dot = STATUS_DOT[s.status] || "never_run";
          const ratio = s.daily_limit
            ? Math.min(1, s.applied_today / s.daily_limit)
            : 0;
          const barClass =
            ratio >= 1 ? "full" : ratio >= 0.7 ? "warn" : "";
          return `
          <div class="source-card stagger-item" style="animation-delay:${staggerDelay(i)}">
            <h3>
              <input type="checkbox" class="schedule-toggle" data-source="${s.name}" title="В расписании демона" ${s.schedule_enabled ? "checked" : ""} />
              <span class="dot ${dot}"></span> ${sourceLabel(s.name)}
            </h3>
            <div class="row"><span>Расписание</span><span>${s.schedule_enabled ? `каждые ${s.interval_hours}ч` : "выключено"}</span></div>
            <div class="row"><span>Последний запуск</span><span>${fmtTime(s.last_run)}</span></div>
            <div class="row"><span>Следующий запуск</span><span>${fmtTime(s.next_run)}</span></div>
            <div class="row"><span>Откликов сегодня</span><span>${s.applied_today}/${s.daily_limit}</span></div>
            <div class="limit-bar"><div class="limit-bar-fill ${barClass}" style="width:${Math.round(ratio * 100)}%"></div></div>
            ${s.last_error ? `<div class="error-row">${s.last_error}</div>` : ""}
          </div>`;
        })
        .join("");
      document.getElementById("chat-checks-grid").innerHTML = status.chat_checks
        .map((c, i) => {
          const dot = STATUS_DOT[c.status] || "never_run";
          return `
          <div class="source-card stagger-item" style="animation-delay:${staggerDelay(i)}">
            <h3>
              <input type="checkbox" class="schedule-toggle" data-source="${c.name}" title="В расписании демона" ${c.schedule_enabled ? "checked" : ""} />
              <span class="dot ${dot}"></span> ${c.label}
            </h3>
            <div class="row"><span>Расписание</span><span>${c.schedule_enabled ? `каждые ${c.interval_hours}ч` : "выключено"}</span></div>
            <div class="row"><span>Последняя проверка</span><span>${fmtTime(c.last_run)}</span></div>
            <div class="row"><span>Следующая проверка</span><span>${fmtTime(c.next_run)}</span></div>
            <p class="muted small" style="margin:6px 0 0">${c.note}</p>
            ${c.last_error ? `<div class="error-row">${c.last_error}</div>` : ""}
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

    if (!entries.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="muted">Ничего не найдено.</td></tr>`;
      return;
    }
    tbody.innerHTML = entries
      .slice()
      .reverse()
      .map(
        (e, i) => `
      <tr class="reveal" style="transition-delay:${staggerDelay(i, 25)}">
        <td>${fmtTime(e.applied_at)}</td>
        <td>${sourceLabel(e.source)}</td>
        <td>${e.company}</td>
        <td><a href="${e.link}" target="_blank" rel="noopener">${e.title}</a></td>
        <td>${statusLabel(e.status)}</td>
        <td>${e.score ?? ""}</td>
      </tr>`
      )
      .join("");
    observeReveal(tbody);
  },

  async replies() {
    const tbody = document.getElementById("replies-rows");
    if (!repliesLoaded) tbody.innerHTML = skeletonRows(3, 4);

    const entries = await api("/api/replies");
    repliesLoaded = true;

    const repliesSnapshot = JSON.stringify(entries);
    if (repliesSnapshot === lastRepliesSnapshot) return;
    lastRepliesSnapshot = repliesSnapshot;

    if (!entries.length) {
      tbody.innerHTML = `<tr><td colspan="4" class="muted">Пока нет ответов.</td></tr>`;
      return;
    }
    tbody.innerHTML = entries
      .map(
        (e, i) => `
      <tr class="reveal" style="transition-delay:${staggerDelay(i, 25)}">
        <td>${fmtTime(e.applied_at)}</td>
        <td>${sourceLabel(e.source)}</td>
        <td><a href="${e.link}" target="_blank" rel="noopener">${e.company} — ${e.title}</a></td>
        <td>${e.last_known_state}</td>
      </tr>`
      )
      .join("");
    observeReveal(tbody);
  },

  async analytics() {
    const [gaps, candidates] = await Promise.all([
      api("/api/analytics/gaps"),
      api("/api/analytics/blacklist-candidates"),
    ]);

    const gapsEl = document.getElementById("gaps-list");
    gapsEl.innerHTML = gaps.length
      ? gaps
          .map(
            ([gap, count], i) =>
              `<li class="stagger-item" style="animation-delay:${staggerDelay(i)}">${gap} — ${count}</li>`
          )
          .join("")
      : `<li class="muted">Пока нет данных.</li>`;

    const candidatesEl = document.getElementById("blacklist-candidates");
    if (!candidates.length) {
      candidatesEl.innerHTML = `<div class="muted">Нет кандидатов на чёрный список.</div>`;
      return;
    }
    candidatesEl.innerHTML = candidates
      .map(
        (c, i) => `
      <div class="candidate-row stagger-item" style="animation-delay:${staggerDelay(i)}">
        <input type="checkbox" value="${c}" class="blacklist-check" />
        <span>${c}</span>
        <button class="btn btn-secondary btn-small block-hh-employer" data-company="${c}" title="Заблокировать работодателя на hh.ru (серверный бан, только для HeadHunter)">🔒 hh.ru</button>
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
      };
      applyLLMSelection(llm.provider, llm.model);
      document.getElementById("llm-base-url").value = llm.base_url || "";
      document.getElementById("llm-mode").value = llm.mode || "auto";
      document.getElementById("llm-fallback-enabled").checked =
        llm.fallback_enabled !== false;
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
        <td><input type="checkbox" class="s-schedule" ${s.schedule_enabled ? "checked" : ""} /></td>
        <td><input type="number" class="s-interval" min="1" value="${s.interval_hours ?? 3}" /></td>
        <td><input type="checkbox" class="s-auto" ${s.auto_apply ? "checked" : ""} /></td>
        <td>${
          s.name === "headhunter"
            ? `<input type="checkbox" class="s-auto-reply" ${s.auto_reply ? "checked" : ""} />`
            : "—"
        }</td>
        <td>${
          s.name === "headhunter"
            ? `<input type="checkbox" class="s-auto-bump" ${s.auto_bump_resume ? "checked" : ""} />`
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
      note.textContent =
        "Запустите поиск по Telegram один раз вручную (--auto telegram) и введите код входа в консоли.";
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
  for (;;) {
    const result = await api("/api/generate/status");
    if (!result.running) {
      if (result.error) {
        statusEl.textContent = `Ошибка: ${result.error}`;
        downloadEl.style.display = "none";
      } else if (result.ready) {
        statusEl.textContent = "Готово.";
        downloadEl.style.display = "";
      }
      return;
    }
    statusEl.textContent = "Генерация (может занять до минуты)...";
    await new Promise((r) => setTimeout(r, 2000));
  }
}

async function startGenerate(kind) {
  const statusEl = document.getElementById("gen-status");
  const downloadEl = document.getElementById("gen-download");
  const styleName = document.getElementById("gen-style").value || null;
  const jobUrl = document.getElementById("gen-job-url").value.trim() || null;
  if (kind !== "resume" && !jobUrl) {
    alert("Укажите ссылку на вакансию.");
    return;
  }
  downloadEl.style.display = "none";
  statusEl.textContent = "Запуск...";
  try {
    await api(`/api/generate/${kind}`, {
      method: "POST",
      body: JSON.stringify({ style_name: styleName, job_url: jobUrl }),
    });
  } catch (e) {
    statusEl.textContent = `Ошибка: ${e.message}`;
    return;
  }
  pollGenerateStatus();
}

function initDashboard() {
  document.querySelectorAll("nav.tabs button").forEach((b) => {
    b.addEventListener("click", () => switchTab(b.dataset.tab));
  });

  document.getElementById("notif-test").addEventListener("click", async () => {
    const status = document.getElementById("notif-test-status");
    status.textContent = "Отправка...";
    try {
      await api("/api/notifications/test", { method: "POST" });
      status.textContent = "Отправлено, проверьте Telegram.";
    } catch (e) {
      status.textContent = `Ошибка: ${e.message}`;
    }
  });

  document.getElementById("daemon-start").addEventListener("click", async () => {
    await api("/api/daemon/start", { method: "POST" });
    render.overview();
  });
  document.getElementById("daemon-stop").addEventListener("click", async () => {
    await api("/api/daemon/stop", { method: "POST" });
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
      if (!confirm(`Заблокировать "${company}" на hh.ru? Это серверная блокировка, отменить её сложнее, чем локальный чёрный список.`)) {
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
      status.textContent = "Обновление...";
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
    status.textContent = "Сохранение...";
    try {
      await api("/api/settings/limits", {
        method: "POST",
        body: JSON.stringify({
          daily_application_limit: daily,
          linkedin_daily_application_limit: linkedin,
          total_daily_application_limit: total,
          job_max_applications: perRun,
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
      status.textContent = "Распределение...";
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
      status.textContent = "Сохранение...";
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
      status.textContent = "Сохранение...";
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
      status.textContent = "Сохранение...";
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
      status.textContent = "Читаем резюме...";
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
    .getElementById("tg-settings-save")
    .addEventListener("click", async () => {
      const status = document.getElementById("tg-settings-status");
      status.textContent = "Сохранение...";
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
    status.textContent = "Отправка...";
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
      status.textContent = "Отправка резюме...";
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
      if (
        !confirm(
          `Удалить всю переписку с @${activeTelegramContact}? Это не архив — история удаляется без возможности восстановить, а контакт перестаёт считаться "уже написанным" (бот может написать ему заново при следующем совпадении).`
        )
      )
        return;
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
      status.textContent = "Сохранение...";
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
      status.textContent = "Сохранение...";
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

  switchTab("overview");
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
  setInterval(() => {
    const active = document.querySelector("nav.tabs button.active")?.dataset.tab;
    if (active && LIVE_TABS.has(active)) render[active]();
  }, 7000);
}

function initSetupScreen() {
  document
    .getElementById("setup-init")
    .addEventListener("click", async () => {
      const status = document.getElementById("setup-status");
      const apiKey = document.getElementById("setup-api-key").value.trim();
      status.textContent = "Создание...";
      try {
        const result = await api("/api/setup/init", {
          method: "POST",
          body: JSON.stringify({ api_key: apiKey || null }),
        });
        if (result.ready) {
          status.textContent = "Готово, открываю дашборд...";
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
