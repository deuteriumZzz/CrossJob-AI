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
    const tbody = document.getElementById("settings-rows");
    tbody.innerHTML = status.sources
      .map(
        (s, i) => `
      <tr data-source="${s.name}" class="reveal" style="transition-delay:${staggerDelay(i, 25)}">
        <td>${sourceLabel(s.name)}</td>
        <td><input type="checkbox" class="s-schedule" ${s.schedule_enabled ? "checked" : ""} /></td>
        <td><input type="number" class="s-interval" min="1" value="${s.interval_hours ?? 3}" /></td>
        <td><input type="checkbox" class="s-auto" ${s.auto_apply ? "checked" : ""} /></td>
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

document.addEventListener("DOMContentLoaded", () => {
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

  switchTab("overview");
  setInterval(() => {
    const active = document.querySelector("nav.tabs button.active")?.dataset.tab;
    if (active === "overview") render.overview();
  }, 7000);
});
