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

const render = {
  async overview() {
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

    document.getElementById("stats-row").innerHTML = `
      <div class="stat-card"><div class="value">${stats.day}</div><div class="label">Сегодня</div></div>
      <div class="stat-card"><div class="value">${stats.week}</div><div class="label">За неделю</div></div>
      <div class="stat-card"><div class="value">${stats.month}</div><div class="label">За месяц</div></div>
    `;

    document.getElementById("source-grid").innerHTML = status.sources
      .map((s) => {
        const dot = STATUS_DOT[s.status] || "never_run";
        const ratio = s.daily_limit
          ? Math.min(1, s.applied_today / s.daily_limit)
          : 0;
        const barClass =
          ratio >= 1 ? "full" : ratio >= 0.7 ? "warn" : "";
        return `
        <div class="source-card">
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

    const entries = await api(`/api/applications?${params}`);
    const tbody = document.getElementById("history-rows");
    tbody.innerHTML = entries
      .slice()
      .reverse()
      .map(
        (e) => `
      <tr>
        <td>${fmtTime(e.applied_at)}</td>
        <td>${sourceLabel(e.source)}</td>
        <td>${e.company}</td>
        <td><a href="${e.link}" target="_blank" rel="noopener">${e.title}</a></td>
        <td>${e.status}</td>
        <td>${e.score ?? ""}</td>
      </tr>`
      )
      .join("");
  },

  async replies() {
    const entries = await api("/api/replies");
    const tbody = document.getElementById("replies-rows");
    if (!entries.length) {
      tbody.innerHTML = `<tr><td colspan="4" class="muted">Пока нет ответов.</td></tr>`;
      return;
    }
    tbody.innerHTML = entries
      .map(
        (e) => `
      <tr>
        <td>${fmtTime(e.applied_at)}</td>
        <td>${sourceLabel(e.source)}</td>
        <td><a href="${e.link}" target="_blank" rel="noopener">${e.company} — ${e.title}</a></td>
        <td>${e.last_known_state}</td>
      </tr>`
      )
      .join("");
  },

  async analytics() {
    const [gaps, candidates] = await Promise.all([
      api("/api/analytics/gaps"),
      api("/api/analytics/blacklist-candidates"),
    ]);

    const gapsEl = document.getElementById("gaps-list");
    gapsEl.innerHTML = gaps.length
      ? gaps.map(([gap, count]) => `<li>${gap} — ${count}</li>`).join("")
      : `<li class="muted">Пока нет данных.</li>`;

    const candidatesEl = document.getElementById("blacklist-candidates");
    if (!candidates.length) {
      candidatesEl.innerHTML = `<div class="muted">Нет кандидатов на чёрный список.</div>`;
      return;
    }
    candidatesEl.innerHTML = candidates
      .map(
        (c) => `
      <div class="candidate-row">
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
        (s) => `
      <tr data-source="${s.name}">
        <td>${sourceLabel(s.name)}</td>
        <td><input type="checkbox" class="s-schedule" ${s.schedule_enabled ? "checked" : ""} /></td>
        <td><input type="number" class="s-interval" min="1" value="${s.interval_hours ?? 3}" /></td>
        <td><input type="checkbox" class="s-auto" ${s.auto_apply ? "checked" : ""} /></td>
        <td><button class="btn btn-secondary s-save">Сохранить</button></td>
      </tr>`
      )
      .join("");

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
    const data = await api(`/api/logs?${params}`);
    const pre = document.getElementById("log-output");
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
