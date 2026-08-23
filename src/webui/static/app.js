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
let llmCatalog = { models: {}, api_key_previews: {} };

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

    const badge = document.getElementById("daemon-badge");
    badge.innerHTML = `<span class="badge-dot"></span>${
      status.daemon_running ? "демон работает" : "демон остановлен"
    }`;
    badge.classList.toggle("on", status.daemon_running);
    badge.classList.toggle("off", !status.daemon_running);
    document.getElementById("daemon-start").disabled = status.daemon_running;
    document.getElementById("daemon-stop").disabled = !status.daemon_running;

    const statsRow = document.getElementById("stats-row");
    statsRow.innerHTML = `
      <div class="stat-card"><div class="value" data-target="${stats.day}">0</div><div class="label">Сегодня</div></div>
      <div class="stat-card"><div class="value" data-target="${stats.week}">0</div><div class="label">За неделю</div></div>
      <div class="stat-card"><div class="value" data-target="${stats.month}">0</div><div class="label">За месяц</div></div>
    `;
    statsRow.querySelectorAll(".value").forEach((el) => {
      countUp(el, parseInt(el.dataset.target, 10));
    });

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
            <input type="checkbox" class="run-now-check" value="${s.name}" title="Выбрать для запуска сейчас" />
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

    overviewLoaded = true;
    await render.runNowStatus();
  },

  async runNowStatus() {
    const status = await api("/api/run-now/status");
    const el = document.getElementById("run-now-status");
    const btn = document.getElementById("run-now");
    if (status.running) {
      el.textContent = `Выполняется сейчас: ${status.sources
        .map(sourceLabel)
        .join(", ")}`;
      btn.disabled = true;
    } else {
      el.textContent = "";
      btn.disabled = false;
    }
    return status.running;
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
    tbody.innerHTML = skeletonRows(6, 6);

    const entries = await api(`/api/applications?${params}`);
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
        <td>${e.status}</td>
        <td>${e.score ?? ""}</td>
      </tr>`
      )
      .join("");
    observeReveal(tbody);
  },

  async replies() {
    const tbody = document.getElementById("replies-rows");
    tbody.innerHTML = skeletonRows(3, 4);

    const entries = await api("/api/replies");
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
      </div>`
      )
      .join("");
  },

  async settings() {
    const status = await api("/api/status");

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
      document.getElementById("search-telegram-channels").value = (
        search.telegram_channels || []
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
    });

    const tbody = document.getElementById("settings-rows");
    tbody.innerHTML = status.sources
      .map(
        (s, i) => `
      <tr data-source="${s.name}" class="reveal" style="transition-delay:${staggerDelay(i, 25)}">
        <td>${sourceLabel(s.name)}</td>
        <td title="${s.readiness && s.readiness.missing.length ? "Не хватает: " + s.readiness.missing.join(", ") : "Данных для подключения достаточно"}">${s.readiness && s.readiness.ready ? "✅" : "⚠️"}</td>
        <td><input type="checkbox" class="s-schedule" ${s.schedule_enabled ? "checked" : ""} /></td>
        <td><input type="number" class="s-interval" min="1" value="${s.interval_hours ?? 3}" /></td>
        <td><input type="checkbox" class="s-auto" ${s.auto_apply ? "checked" : ""} /></td>
        <td><input type="text" class="s-resume-id" value="${s.resume_id || ""}" placeholder="id резюме на площадке" /></td>
        <td><input type="number" class="s-max-applications" min="1" value="${s.job_max_applications}" /></td>
        <td><input type="number" class="s-daily-limit" min="1" value="${s.daily_limit}" /></td>
        <td><button class="btn btn-secondary s-save">Сохранить</button></td>
      </tr>`
      )
      .join("");
    observeReveal(tbody);

    tbody.querySelectorAll(".s-save").forEach((btn) => {
      btn.addEventListener("click", async (ev) => {
        const row = ev.target.closest("tr");
        const source = row.dataset.source;
        const body = {
          source,
          schedule_enabled: row.querySelector(".s-schedule").checked,
          interval_hours: parseInt(row.querySelector(".s-interval").value, 10),
          auto_apply: row.querySelector(".s-auto").checked,
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
  },

  async logs() {
    const source = document.getElementById("log-source").value;
    const params = new URLSearchParams({ lines: "300" });
    if (source) params.set("source", source);
    const pre = document.getElementById("log-output");
    pre.innerHTML = `<div class="skeleton" style="height:14px;width:90%;margin-bottom:8px"></div><div class="skeleton" style="height:14px;width:75%;margin-bottom:8px"></div><div class="skeleton" style="height:14px;width:85%"></div>`;

    const data = await api(`/api/logs?${params}`);
    if (data.note) {
      pre.textContent = data.note;
      return;
    }
    pre.textContent = data.lines.join("\n") || "(пусто)";
  },
};

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

  document.getElementById("run-now").addEventListener("click", async () => {
    const sources = Array.from(
      document.querySelectorAll(".run-now-check:checked")
    ).map((c) => c.value);
    if (!sources.length) {
      alert("Выберите хотя бы одну площадку.");
      return;
    }
    await api("/api/run-now", {
      method: "POST",
      body: JSON.stringify({ sources }),
    });
    render.overview();
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
            telegram_channels: linesOf("search-telegram-channels"),
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
  setInterval(() => {
    const active = document.querySelector("nav.tabs button.active")?.dataset.tab;
    if (active === "overview") render.overview();
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
