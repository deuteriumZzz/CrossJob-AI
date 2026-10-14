// Применяем сохранённую тему сразу при загрузке скрипта (до
// DOMContentLoaded) — иначе будет видна вспышка тёмной темы перед
// переключением на светлую.
(function initTheme() {
  const saved = localStorage.getItem("cj-theme");
  if (saved === "light" || saved === "dark") {
    document.documentElement.dataset.theme = saved;
  } else if (window.matchMedia?.("(prefers-color-scheme: light)").matches) {
    // Ни разу не переключал тему сам — раньше первый запуск всегда был
    // тёмным, даже если вся система у человека в светлой теме (:root
    // ниже — это тёмная тема по умолчанию, светлая только явным
    // data-theme="light"). Просто угадываем стартовое состояние из ОС,
    // ничего не сохраняем — свой выбор через тумблер это не трогает.
    document.documentElement.dataset.theme = "light";
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
  avito: "Авито Работа",
  direct: "Сайты компаний",
  talanto: "Talanto",
  hirify: "Hirify",
};

// ponytail: настоящие логотипы площадок — товарные знаки, тащить их к себе
// рискованно. Вместо этого — монограмма (1-2 буквы) на цветном бейдже,
// свой цвет на площадку для быстрого узнавания глазами в таблицах/карточках.
// Цвета подобраны так, чтобы белый текст поверх держал WCAG AA (4.5:1) —
// исходные оттенки (например #35a8e0 для telegram, 2.68:1) были слишком
// светлыми, буквы на них не читались. Тот же оттенок, просто темнее.
const SOURCE_ICON = {
  headhunter: { text: "hh", color: "#d43d3d" },
  geekjob: { text: "GJ", color: "#2e825c" },
  telegram: { text: "TG", color: "#1a7aa9" },
  getmatch: { text: "GM", color: "#7d60cc" },
  linkedin: { text: "in", color: "#2a6ced" },
  habr_career: { text: "HC", color: "#a7621d" },
  wellfound: { text: "WF", color: "#c23b6b" },
  himalayas: { text: "HM", color: "#476fd1" },
  djinni: { text: "DJ", color: "#27825b" },
  avito: { text: "AV", color: "#6b4c9a" },
  direct: { text: "WW", color: "#407e73" },
  mail: { text: "@", color: "#5b6068" },
  talanto: { text: "TL", color: "#b4541f" },
  hirify: { text: "HF", color: "#2f6f5e" },
};

// Площадки, нацеленные на зарубежный рынок — остальные площадки RU.
const OWN_CHANNELS = new Set(["telegram", "direct", "talanto", "hirify"]);
// "Расписание" звучит как редкий цикл раз в день — площадка на деле
// проверяется почти непрерывно (следующий заход сразу после конца
// предыдущего + этот интервал), просто с паузой, чтобы не выглядеть
// ботом. Ниже часа показываем минуты — "0.05ч" человеку не читается.
function intervalLabel(hours) {
  return hours < 1 ? `каждые ${Math.round(hours * 60)} мин` : `каждые ${hours}ч`;
}
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
  // Декоративная аббревиатура (hh/in/GM…) всегда стоит рядом с полным
  // названием площадки (sourceLabel) — без aria-hidden скринридер
  // объявлял бы его дважды подряд.
  return `<span class="source-icon" aria-hidden="true" style="background:${icon.color}">${icon.text}</span>`;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

function highlightText(value, query) {
  const text = String(value ?? "");
  const needle = String(query ?? "").trim();
  if (!needle) return escapeHtml(text);
  const source = text.toLocaleLowerCase();
  const search = needle.toLocaleLowerCase();
  let cursor = 0;
  let result = "";
  let match = source.indexOf(search, cursor);
  while (match !== -1) {
    result += `${escapeHtml(text.slice(cursor, match))}<mark class="search-highlight">${escapeHtml(text.slice(match, match + needle.length))}</mark>`;
    cursor = match + needle.length;
    match = source.indexOf(search, cursor);
  }
  return result + escapeHtml(text.slice(cursor));
}

const htmlSnapshots = new WeakMap();
const contentFadeCleanups = new WeakMap();
function setHtmlIfChanged(element, html) {
  if (htmlSnapshots.get(element) === html) return false;
  const replacesSkeleton = Boolean(element.querySelector(".skeleton"));
  element.innerHTML = html;
  htmlSnapshots.set(element, html);
  if (replacesSkeleton && !REDUCE_MOTION) {
    contentFadeCleanups.get(element)?.();
    element.classList.remove("content-fade-in");
    void element.offsetWidth;
    element.classList.add("content-fade-in");
    let onAnimationEnd;
    const clearFade = () => {
      element.removeEventListener("animationend", onAnimationEnd);
      element.removeEventListener("animationcancel", onAnimationEnd);
      if (contentFadeCleanups.get(element) === clearFade) contentFadeCleanups.delete(element);
      element.classList.remove("content-fade-in");
    };
    onAnimationEnd = (event) => {
      if (event.target === element) clearFade();
    };
    contentFadeCleanups.set(element, clearFade);
    element.addEventListener("animationend", onAnimationEnd);
    element.addEventListener("animationcancel", onAnimationEnd);
  }
  return true;
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

function renderTagChips(textarea, motion = null) {
  const chips = textarea._tagChipsEl;
  if (!chips) return;
  const items = tagItemsOf(textarea);
  chips.innerHTML = items
    .map(
      (item, i) => {
        const enterClass = motion?.phase === "enter" && motion.item === item ? " tag-chip-enter" : "";
        return `<span class="tag-chip${enterClass}">${escapeHtml(item)}<button type="button" class="tag-chip-remove" data-i="${i}" aria-label="Удалить">×</button></span>`;
      }
    )
    .join("");
  chips.querySelectorAll(".tag-chip-remove").forEach((btn) => {
    btn.addEventListener("click", () => {
      const index = Number.parseInt(btn.dataset.i, 10);
      const valueAtClick = textarea.value;
      const item = tagItemsOf(textarea)[index];
      if (!item) return;
      const remove = () => {
        if (textarea.value !== valueAtClick) return;
        const current = tagItemsOf(textarea);
        current.splice(index, 1);
        textarea.value = current.join("\n");
        renderTagChips(textarea);
        tagChanged(textarea);
      };
      const chip = btn.closest(".tag-chip");
      if (REDUCE_MOTION || typeof chip?.animate !== "function") return remove();
      btn.disabled = true;
      chip.animate(
        [{ opacity: 1, transform: "scale(1)" }, { opacity: 0, transform: "scale(.94)" }],
        { duration: 130, easing: "cubic-bezier(0.23, 1, 0.32, 1)" }
      ).finished.then(remove, remove);
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
      renderTagChips(textarea, { phase: "enter", item: value });
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
  us_only: "только США",
  europe_only: "только Европа",
  global: "откуда угодно",
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
  if (Number.isNaN(d.getTime())) return "—";
  // Русский формат всегда, независимо от языка браузера/окна.
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: d.getFullYear() === new Date().getFullYear() ? undefined : "2-digit", hour: "2-digit", minute: "2-digit" });
}

// «Уменьшить движение»: из системы или Настройки → Вид → «Анимации: выключить».
const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
let REDUCE_MOTION = motionQuery.matches;
(function applyLookPrefs() {
  try {
    const density = localStorage.getItem("cj-density");
    const motion = localStorage.getItem("cj-motion");
    if (density === "compact") document.documentElement.dataset.density = "compact";
    if (motion === "reduce") {
      document.documentElement.dataset.motion = "reduce";
      REDUCE_MOTION = true;
    }
  } catch (e) {}
})();

function syncReducedMotionPreference(preference = null) {
  let manuallyReduced = preference === "reduce";
  if (preference === null) {
    try {
      manuallyReduced = localStorage.getItem("cj-motion") === "reduce";
    } catch (e) {}
  }
  REDUCE_MOTION = manuallyReduced || motionQuery.matches;
  if (REDUCE_MOTION) clearPointerEffects();
}

if (typeof motionQuery.addEventListener === "function") {
  motionQuery.addEventListener("change", syncReducedMotionPreference);
} else if (typeof motionQuery.addListener === "function") {
  motionQuery.addListener(syncReducedMotionPreference);
}

const countAnimationFrames = new WeakMap();
function countUp(el, target, duration = 700, start = 0) {
  const previousFrame = countAnimationFrames.get(el);
  if (previousFrame) cancelAnimationFrame(previousFrame);
  countAnimationFrames.delete(el);
  if (REDUCE_MOTION) {
    el.textContent = target;
    return;
  }
  const startTime = performance.now();
  const ease = (t) => 1 - Math.pow(1 - t, 3);
  function tick(now) {
    if (REDUCE_MOTION) {
      el.textContent = target;
      countAnimationFrames.delete(el);
      return;
    }
    const progress = Math.min(1, (now - startTime) / duration);
    const value = Math.round(start + (target - start) * ease(progress));
    el.textContent = value;
    if (progress < 1) countAnimationFrames.set(el, requestAnimationFrame(tick));
    else countAnimationFrames.delete(el);
  }
  countAnimationFrames.set(el, requestAnimationFrame(tick));
}

const shownCounts = {};
function animateCountValue(el, id, target) {
  const value = Number.parseInt(target, 10) || 0;
  const before = shownCounts[id];
  shownCounts[id] = value;
  if (before !== undefined && before !== value) {
    const visible = Number.parseInt(el.textContent, 10);
    countUp(el, value, 520, Number.isFinite(visible) ? visible : before);
    el.classList.add("count-changed");
    setTimeout(() => el.classList.remove("count-changed"), 1100);
  } else if (before === undefined) el.textContent = String(value);
}

// Цифры на карточках плавно досчитываются с прошлого значения до нового —
// видно, что изменилось. Первый показ — без анимации.
function animateCounts(root) {
  root.querySelectorAll("[data-count]").forEach((el) => {
    animateCountValue(el, el.dataset.count, el.textContent);
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
      statusEl.innerHTML = `Подключено (chat_id: ${escapeHtml(String(data.chat_id))}) <button type="button" class="copy-btn" title="Скопировать chat_id" aria-label="Скопировать chat_id">${COPY_ICON_SVG}</button>`;
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

async function refreshTelegramGroupConnectStatus() {
  const statusEl = document.getElementById("telegram-connect-group-status");
  if (!statusEl) return true;
  try {
    const data = await api("/api/settings/telegram/connect-group/status");
    if (data.status === "connected") {
      statusEl.innerHTML = `Группа подключена (chat_id: ${escapeHtml(String(data.chat_id))}) <button type="button" class="copy-btn" title="Скопировать chat_id" aria-label="Скопировать chat_id">${COPY_ICON_SVG}</button> — теперь включите «Темы» в настройках группы и сделайте бота админом с правом «Управление темами».`;
      statusEl.querySelector(".copy-btn").addEventListener("click", (e) => {
        copyToClipboard(String(data.chat_id), e.currentTarget);
      });
      return true;
    }
    if (data.status === "timeout") {
      statusEl.textContent =
        "Группа не была выбрана за 3 минуты — попробуйте снова.";
      return true;
    }
    if (data.status === "waiting") {
      statusEl.textContent = "Ждём, когда вы выберете группу в Telegram…";
      return false;
    }
    statusEl.textContent = "";
  } catch (e) {
    // тихая фоновая проверка
  }
  return true;
}

// 5 разделов в меню вместо 9 вкладок: подразделы показываются строкой
// над содержимым раздела. Ключ — раздел (data-tab кнопки меню), значение —
// его подразделы (id view-*) с подписями; первый — открывается по клику.
const NAV_GROUPS = {
  overview: [["overview", "Главная"]],
  // "Вакансии" и "Логи" — один и тот же архив действий бота на двух
  // уровнях детализации (человеческая сводка / сырые строки
  // исполнения), а не два разных раздела — были в разных местах меню
  // (топ-навигация против "Настройки"), хотя отвечают на один и тот же
  // вопрос "что бот сейчас делает и сделал".
  history: [
    ["history", "Отклики"],
    ["logs", "Журнал бота"],
  ],
  // Входящие и Telegram-диалоги — одно окно «Общение»; старый адрес
  // #telegram ведёт туда же (см. switchTab).
  replies: [["replies", "Общение"]],
  contacts: [
    ["contacts", "База"],
    ["outreach", "Рассылка"],
  ],
  analytics: [["analytics", "Аналитика"]],
  settings: [
    ["settings", "Настройки"],
    ["resume", "Мои резюме"],
  ],
};
const VIEW_GROUP = Object.fromEntries(
  Object.entries(NAV_GROUPS).flatMap(([group, views]) =>
    views.map(([view]) => [view, group])
  )
);
const NAV_GROUP_LABELS = {
  overview: "Главная",
  history: "Вакансии",
  replies: "Общение",
  contacts: "Компании",
  analytics: "Аналитика",
  settings: "Настройки",
};
const VALID_VIEWS = new Set(Object.keys(VIEW_GROUP));
const FAVORITE_VIEWS_KEY = "cj-favorite-views";
let favoriteViews = readFavoriteViews();
let currentView = "overview";

function readFavoriteViews() {
  try {
    const stored = JSON.parse(localStorage.getItem("cj-favorite-views") || "[]");
    return Array.isArray(stored) ? [...new Set(stored.filter((view) => VALID_VIEWS.has(view)))] : [];
  } catch (e) {
    return [];
  }
}

function toggleFavoriteView(view) {
  if (!VALID_VIEWS.has(view)) return;
  favoriteViews = favoriteViews.includes(view)
    ? favoriteViews.filter((item) => item !== view)
    : [...favoriteViews, view];
  try {
    localStorage.setItem(FAVORITE_VIEWS_KEY, JSON.stringify(favoriteViews));
  } catch (e) {}
  renderFavoriteViews();
  renderPageFavorites();
}

function renderFavoriteViews() {
  const container = document.getElementById("favorite-nav");
  if (!container) return;
  container.innerHTML = favoriteViews.length
    ? `<span class="favorite-nav-label">Избранное</span>${favoriteViews.map((view) => {
        const label = NAV_GROUPS[VIEW_GROUP[view]].find(([id]) => id === view)?.[1] || NAV_GROUP_LABELS[VIEW_GROUP[view]];
        return `<button type="button" class="favorite-nav-item${view === currentView ? " active" : ""}" data-favorite-view="${view}" aria-label="Открыть раздел: ${escapeHtml(label)}" aria-current="${view === currentView ? "page" : "false"}" title="${escapeHtml(label)}"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m8 1.8 1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.6l-3.8 2 .7-4.3-3.1-3 4.3-.6L8 1.8Z"/></svg><span>${escapeHtml(label)}</span></button>`;
      }).join("")}`
    : "";
  container.querySelectorAll("[data-favorite-view]").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.favoriteView));
  });
}

function renderPageFavorites() {
  document.querySelectorAll("main .view").forEach((view) => {
    const heading = view.querySelector(".page-title h2");
    if (!heading) return;
    let button = heading.parentElement.querySelector(":scope > [data-favorite-toggle]");
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.className = "page-favorite";
      button.setAttribute("data-favorite-toggle", "");
      button.innerHTML = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="m8 1.8 1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.6l-3.8 2 .7-4.3-3.1-3 4.3-.6L8 1.8Z"/></svg>';
      heading.insertAdjacentElement("afterend", button);
      button.addEventListener("click", () => toggleFavoriteView(view.id.replace(/^view-/, "")));
    }
    const viewId = view.id.replace(/^view-/, "");
    const active = favoriteViews.includes(viewId);
    const label = heading.textContent.trim();
    button.classList.toggle("is-favorite", active);
    button.setAttribute("aria-pressed", String(active));
    button.setAttribute("aria-label", active ? `Убрать «${label}» из избранного` : `Добавить «${label}» в избранное`);
    button.title = active ? "Убрать из избранного" : "Добавить в избранное";
  });
}

function renderPageBreadcrumb(view) {
  const group = VIEW_GROUP[view];
  const views = NAV_GROUPS[group] || [];
  const pageTitle = document.querySelector(`#view-${view} .page-title`);
  if (!pageTitle) return;
  let breadcrumb = pageTitle.querySelector(":scope > .page-breadcrumbs");
  if (views.length < 2 || views[0][0] === view) {
    breadcrumb?.remove();
    return;
  }
  if (!breadcrumb) {
    breadcrumb = document.createElement("nav");
    breadcrumb.className = "page-breadcrumbs";
    breadcrumb.setAttribute("aria-label", "Путь раздела");
    pageTitle.prepend(breadcrumb);
  }
  const groupLabel = NAV_GROUP_LABELS[group];
  breadcrumb.innerHTML = `<details class="breadcrumb-parent"><summary>${escapeHtml(groupLabel)}</summary><div class="breadcrumb-menu">${views.map(([id, label]) => `<button type="button" data-breadcrumb-view="${id}"${id === view ? ' aria-current="page"' : ""}>${escapeHtml(label)}</button>`).join("")}</div></details><span class="breadcrumb-separator" aria-hidden="true">›</span><span aria-current="page">${escapeHtml(views.find(([id]) => id === view)?.[1] || "")}</span>`;
  breadcrumb.querySelectorAll("[data-breadcrumb-view]").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.breadcrumbView));
  });
}

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

function showViewRenderFailure(name, error) {
  const view = document.getElementById(`view-${name}`);
  if (!view) return;
  let host = view.querySelector(":scope > .view-load-error");
  if (!host) {
    host = document.createElement("div");
    host.className = "view-load-error";
    view.prepend(host);
  }
  renderRetryState(host, `Не удалось загрузить раздел: ${error.message}`, async () => {
    try {
      await render[name]?.();
      host.remove();
    } catch (retryError) {
      showViewRenderFailure(name, retryError);
    }
  });
}

function clearViewRenderFailure(name) {
  document.getElementById(`view-${name}`)
    ?.querySelector(":scope > .view-load-error")
    ?.remove();
}

let navigationInputModality = "pointer";
function setNavigationInputModality(event) {
  navigationInputModality = event.type === "pointerdown" ? "pointer" : "keyboard";
}
document.addEventListener("pointerdown", setNavigationInputModality, true);
document.addEventListener("keydown", setNavigationInputModality, true);

function shouldAnimateNavigation() {
  return navigationInputModality === "pointer";
}

function switchTab(name) {
  if (name === "telegram") {
    name = "replies";
    repliesKind = "telegram";
  }
  if (!VIEW_GROUP[name]) name = "overview";
  const prevName = currentView;
  currentView = name;
  renderFavoriteViews();
  renderPageFavorites();
  renderPageBreadcrumb(name);
  const group = VIEW_GROUP[name];
  document
    .querySelectorAll("nav.tabs button")
    .forEach((b) => b.classList.toggle("active", b.dataset.tab === group));
  renderSubnav(group, name);
  applySubnavBadges();
  document
    .querySelectorAll("main .view")
    .forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  document.getElementById("app-shell")?.classList.toggle("is-messenger", name === "replies");
  if (prevName && prevName !== name && shouldAnimateNavigation()) {
    directionalReveal(document.getElementById(`view-${name}`), prevName, name);
  }
  // URL отражает текущую вкладку — иначе обновление страницы (F5) всегда
  // сбрасывает на "Обзор", даже если человек читал длинный тред в Telegram
  // или таблицу в Истории. replaceState, а не location.hash — не плодит
  // отдельную запись в истории браузера на каждый клик по вкладке.
  history.replaceState(null, "", `#${name}`);
  try {
    const pendingRender = render[name]?.();
    if (pendingRender && typeof pendingRender.catch === "function") {
      pendingRender.then(
        () => clearViewRenderFailure(name),
        (error) => {
          console.error(`Не удалось загрузить раздел ${name}`, error);
          showViewRenderFailure(name, error);
        }
      );
    } else clearViewRenderFailure(name);
  } catch (error) {
    console.error(`Не удалось загрузить раздел ${name}`, error);
    showViewRenderFailure(name, error);
  }
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
let historyLoaded = false;
let lastHistorySnapshot = null;
let lastHistoryEntries = [];
let repliesLoaded = false;
let lastRepliesSnapshot = null;
let lastRepliesCount = 0;
let lastRepliesEntries = [];
let hhReminderBatchSummary = "";
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
let sendingTelegramMessage = false;
let telegramLoadedHistory = { contact: null, messages: [], hasMore: false };
let telegramConversationsCache = [];

function updateTelegramComposerState() {
  const input = document.getElementById("tg-chat-input");
  const button = document.getElementById("tg-chat-send");
  if (!input || !button) return;
  input.style.height = "auto";
  input.style.height = `${Math.min(132, input.scrollHeight)}px`;
  input.style.overflowY = input.scrollHeight > 132 ? "auto" : "hidden";
  const disabled = !activeTelegramContact || !input.value.trim() || sendingTelegramMessage;
  button.disabled = disabled;
  button.title = disabled && !sendingTelegramMessage
    ? activeTelegramContact ? "Введите сообщение" : "Сначала выберите диалог"
    : "Отправить сообщение";
}

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

function telegramMessageKey(message) {
  return String(message.id ?? `${message.at || ""}|${message.direction || "in"}|${message.text || ""}`);
}

function newerTelegramMessageKeys(previous, next) {
  if (!previous.length) return new Set();
  const known = new Set(previous.map(telegramMessageKey));
  const numericIds = previous.map((message) => Number(message.id)).filter(Number.isFinite);
  const latestId = numericIds.length ? Math.max(...numericIds) : null;
  const latestAt = Math.max(...previous.map((message) => Date.parse(message.at) || 0));
  return new Set(next.filter((message) => {
    if (known.has(telegramMessageKey(message))) return false;
    const id = Number(message.id);
    if (latestId !== null && Number.isFinite(id)) return id > latestId;
    return (Date.parse(message.at) || 0) > latestAt;
  }).map(telegramMessageKey));
}

function countNewerTelegramMessages(previous, next) {
  return newerTelegramMessageKeys(previous, next).size;
}

function mergeTelegramMessages(primary, secondary) {
  const merged = new Map(primary.map((message) => [telegramMessageKey(message), message]));
  secondary.forEach((message) => {
    if (!merged.has(telegramMessageKey(message))) merged.set(telegramMessageKey(message), message);
  });
  return Array.from(merged.values()).sort((a, b) => {
    const timeDifference = (Date.parse(a.at) || 0) - (Date.parse(b.at) || 0);
    if (timeDifference) return timeDifference;
    const aId = Number(a.id);
    const bId = Number(b.id);
    return Number.isFinite(aId) && Number.isFinite(bId) ? aId - bId : 0;
  });
}

function syncTelegramMessageBubbles(container, messages, animateKeys = new Set()) {
  const existing = new Map(Array.from(container.children, (node) => [node.dataset.messageKey, node]));
  const wanted = new Set();
  let cursor = container.firstElementChild;
  for (const message of messages) {
    const key = telegramMessageKey(message);
    wanted.add(key);
    let node = existing.get(key);
    const messageText = String(message.text || "");
    const messageTime = formatChatTime(message.at);
    if (node) {
      node.classList.toggle("out", message.direction === "out");
      node.classList.toggle("in", message.direction !== "out");
      if (node.dataset.messageText !== messageText || node.dataset.messageTime !== messageTime) {
        const time = node.querySelector(".chat-bubble-time") || document.createElement("span");
        time.className = "chat-bubble-time";
        time.textContent = messageTime;
        node.replaceChildren(document.createTextNode(messageText), time);
        node.dataset.messageText = messageText;
        node.dataset.messageTime = messageTime;
      }
    }
    if (node && node === cursor) {
      existing.delete(key);
      cursor = cursor.nextElementSibling;
      continue;
    }
    if (!node) {
      const template = document.createElement("template");
      template.innerHTML = `<div class="chat-bubble ${message.direction === "out" ? "out" : "in"}${animateKeys.has(key) ? " chat-bubble--enter" : ""}" data-message-key="${escapeHtml(key)}">${escapeHtml(messageText)}<span class="chat-bubble-time">${escapeHtml(messageTime)}</span></div>`;
      node = template.content.firstElementChild;
      node.dataset.messageText = messageText;
      node.dataset.messageTime = messageTime;
    }
    container.insertBefore(node, cursor);
    cursor = node.nextElementSibling;
    existing.delete(key);
  }
  for (const node of Array.from(container.children)) {
    if (!node.dataset.messageKey || !wanted.has(node.dataset.messageKey)) node.remove();
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
        `<option value="${m.id}">${m.id}${m.recommended ? " · рекомендуем" : ""}${m.free ? " · бесплатно" : ""}</option>`
    )
    .join("");
  const recommended = models.find((m) => m.recommended);
  if (currentModel && models.some((m) => m.id === currentModel)) {
    modelSelect.value = currentModel;
  } else if (recommended) {
    // Свежее переключение провайдера без сохранённой модели — сразу
    // подставляем рекомендованную («рекомендуем»), а не первую по силе: для
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
        ? `<div class="risk-banner" style="margin-top:10px;margin-bottom:0">${distributionLine} — превышает общий лимит, снизьте лимиты отдельных площадок.</div>`
        : `<p class="muted small" style="margin-top:8px">${distributionLine}</p>`
    }
  `;
}

// "16" само по себе не говорит, хорошо это или плохо — сравнение с тем
// же по длительности предыдущим окном (вчера/предыдущие 7д/предыдущие
// 30д, см. count_in_previous_period) отвечает на этот вопрос сразу под
// цифрой, тем же языком, что уже есть в "Результат за 7 дней" в Аналитике.
function statTrendHtml(curr, prev) {
  const delta = curr - prev;
  if (!delta) return "";
  const cls = delta > 0 ? "ok-text" : "err-text";
  return `<div class="stat-trend small ${cls}">${delta > 0 ? "↑" : "↓"} ${Math.abs(delta)}</div>`;
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
  telegram: { icon: "TG", label: "Telegram" },
  email: { icon: "@", label: "Email" },
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
// Статусы "возврат"/"не писать" сами по себе не объясняют, что
// произошло и что теперь с этим делать — добавляем как title у чипа
// фильтра в "База компаний" (см. renderContactsList).
const CONTACT_STATUS_HINT = {
  bounced: "Письмо вернулось — адрес не существует или ящик недоступен.",
  skip: "Помечено вручную «не писать» — бот пропускает эту компанию в рассылке.",
};
const SOURCE_KIND = {
  file: "мой файл",
  telegram: "Telegram",
  sites: "сайты компаний",
  talanto: "Talanto",
  hirify: "Hirify",
  dossier: "найден кнопкой",
  vacancy: "вакансия",
};
let lastContacts = [];
let focusContactKey = null;
const baseState = { status: "", sort: "last", dir: -1, selected: new Set(), open: new Set(), page: 0, size: 50 };
let baseFiltered = [];
let pendingBaseSortPositions = null;
let baseSeen = new Map(); // ключ → updated_at с прошлого показа — что подсветить // ключи всех компаний под текущим фильтром — для «Выбрать все по фильтру»

function captureBaseRowPositions(animate) {
  if (!animate || REDUCE_MOTION || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) return null;
  return new Map(
    [...document.querySelectorAll("#contacts-list .base-row")]
      .map((row) => [row.dataset.cardKey, row.getBoundingClientRect().top])
  );
}

function animateBaseRowReorder(positions) {
  if (!positions?.size || REDUCE_MOTION || typeof Element.prototype.animate !== "function") return;
  requestAnimationFrame(() => {
    const styles = getComputedStyle(document.documentElement);
    const duration = Number.parseFloat(styles.getPropertyValue("--motion-move")) || 220;
    const easing = styles.getPropertyValue("--motion-ease-in-out").trim() || "ease-in-out";
    document.querySelectorAll("#contacts-list .base-row").forEach((row) => {
      const previousTop = positions.get(row.dataset.cardKey);
      if (previousTop == null) return;
      const delta = previousTop - row.getBoundingClientRect().top;
      if (Math.abs(delta) < 1) return;
      const animation = row.animate(
        [{ transform: `translateY(${delta}px)` }, { transform: "translateY(0)" }],
        { duration, easing }
      );
      animation.onfinish = () => animation.cancel();
    });
  });
}

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

function renderActiveFilters(view) {
  const isHistory = view === "history";
  const container = document.getElementById(isHistory ? "history-active-filters" : "contacts-active-filters");
  if (!container) return;
  const filters = isHistory
    ? [
        { id: "source", label: "Площадка", value: document.getElementById("filter-source").selectedOptions[0]?.textContent, active: !!document.getElementById("filter-source").value },
        { id: "query", label: "Поиск", value: document.getElementById("filter-query").value.trim(), active: !!document.getElementById("filter-query").value.trim() },
      ]
    : [
        { id: "source", label: "Источник", value: document.getElementById("contacts-filter-source").selectedOptions[0]?.textContent, active: !!document.getElementById("contacts-filter-source").value },
        { id: "contact", label: "Контакт", value: document.getElementById("contacts-filter-contact").selectedOptions[0]?.textContent, active: !!document.getElementById("contacts-filter-contact").value },
        { id: "query", label: "Поиск", value: document.getElementById("contacts-filter-query").value.trim(), active: !!document.getElementById("contacts-filter-query").value.trim() },
      ];
  const active = filters.filter((filter) => filter.active);
  container.innerHTML = active.length
    ? `${active.map((filter) => `<button type="button" class="active-filter-chip" data-remove-filter="${filter.id}" aria-label="Убрать фильтр ${escapeHtml(filter.label)}: ${escapeHtml(filter.value)}"><span>${escapeHtml(filter.label)}: ${escapeHtml(filter.value)}</span><span aria-hidden="true">×</span></button>`).join("")}<button type="button" class="active-filters-clear" data-clear-filters>Сбросить</button>`
    : "";
  container.querySelectorAll("[data-remove-filter]").forEach((button) => {
    button.addEventListener("click", (event) => {
      const fields = isHistory
        ? { source: "filter-source", query: "filter-query" }
        : { source: "contacts-filter-source", contact: "contacts-filter-contact", query: "contacts-filter-query" };
      const field = document.getElementById(fields[button.dataset.removeFilter]);
      if (field) field.value = "";
      if (isHistory) {
        lastHistorySnapshot = "";
        render.history({ animateRows: event.detail > 0 });
      } else {
        baseState.page = 0;
        renderContactsList();
      }
    });
  });
  container.querySelector("[data-clear-filters]")?.addEventListener("click", (event) => {
    filters.forEach(({ id }) => {
      const fields = isHistory
        ? { source: "filter-source", query: "filter-query" }
        : { source: "contacts-filter-source", contact: "contacts-filter-contact", query: "contacts-filter-query" };
      const field = document.getElementById(fields[id]);
      if (field) field.value = "";
    });
    if (isHistory) {
      lastHistorySnapshot = "";
      render.history({ animateRows: event.detail > 0 });
    } else {
      baseState.page = 0;
      renderContactsList();
    }
  });
}

function renderContactsList() {
  const el = document.getElementById("contacts-list");
  const sortPositions = pendingBaseSortPositions;
  pendingBaseSortPositions = null;
  const source = document.getElementById("contacts-filter-source").value;
  const contactFilter = document.getElementById("contacts-filter-contact").value;
  const query = document.getElementById("contacts-filter-query").value.trim().toLowerCase();
  fillFileOptions();
  renderActiveFilters("contacts");

  // Счётчики — они же фильтры по статусу.
  const counts = {};
  lastContacts.forEach((c) => (counts[c.status] = (counts[c.status] || 0) + 1));
  const chips = [["", "Все", lastContacts.length], ...Object.entries(CONTACT_STATUS).map(([k, t]) => [k, t, counts[k] || 0])]
    .filter(([k, , n]) => !k || n);
  const chipBox = document.getElementById("base-chips");
  chipBox.innerHTML = chips
    .map(([k, label, n]) => `<button type="button" class="chip${k === baseState.status ? " active" : ""}" data-status="${k}"${CONTACT_STATUS_HINT[k] ? ` title="${escapeHtml(CONTACT_STATUS_HINT[k])}"` : ""}>${label} <b>${n}</b></button>`)
    .join("");
  chipBox.querySelectorAll("[data-status]").forEach((b) =>
    b.addEventListener("click", () => {
      baseState.status = b.dataset.status;
      baseState.page = 0;
      renderContactsList();
    })
  );

  if (!lastContacts.length) {
    // База пуста — ровно момент, когда нужен вопрос «где взять список»:
    // обе кнопки прямо в пустом состоянии.
    el.innerHTML = `<tr><td colspan="5"><div class="empty-state"><p>База пока пуста. Загрузите свой список компаний — Excel, CSV, PDF или Word — или включите Telegram-парсер: он сам добавляет HR из постов.</p>
      <div class="fix-actions"><button type="button" class="btn btn-primary btn-small" data-empty-import>Загрузить файл</button><button type="button" class="btn btn-small" data-empty-prompt>Где взять список?</button></div></div></td></tr>`;
    el.querySelector("[data-empty-import]").addEventListener("click", () => document.getElementById("import-file").click());
    el.querySelector("[data-empty-prompt]").addEventListener("click", openPromptDrawer);
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
    th.setAttribute(
      "aria-sort",
      th.dataset.sort !== baseState.sort ? "none" : baseState.dir > 0 ? "ascending" : "descending"
    );
  });
  baseFiltered = filtered.map((c) => c.key);
  const pages = Math.max(1, Math.ceil(filtered.length / baseState.size));
  const focusIndex = focusContactKey ? baseFiltered.indexOf(focusContactKey) : -1;
  if (focusIndex >= 0) baseState.page = Math.floor(focusIndex / baseState.size);
  baseState.page = Math.min(baseState.page, pages - 1);
  renderBasePager(filtered.length, pages);
  if (!filtered.length) {
    el.innerHTML = `<tr><td colspan="5">${emptyStateHtml("Ничего не найдено.")}</td></tr>`;
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
  el.innerHTML = rows
    .map((card) => {
      const p = card.primary;
      const more = card.contacts.length - 1;
      return `
      <tr class="base-row${fresh.has(card.key) ? " row-fresh" : ""}${card.key === focusContactKey ? " is-focused" : ""}" data-card-key="${escapeHtml(card.key)}">
        <td class="base-check"><input type="checkbox" data-select="${escapeHtml(card.key)}" aria-label="Выбрать компанию ${escapeHtml(card.company || p?.value || "Без названия")}" ${baseState.selected.has(card.key) ? "checked" : ""} /></td>
        <td><button type="button" class="base-row-open" aria-label="Открыть карточку компании: ${escapeHtml(card.company || p?.value || "Без названия")}"><span class="row-title">${highlightText(card.company || p?.value || "Без названия", query)}</span>
          <span class="row-sub">${p ? `${highlightText(p.kind === "telegram" ? "@" + p.value : p.value, query)}${more > 0 ? ` · +${more}` : ""}` : "контакта нет"}${card.hr ? ` · ${highlightText(card.hr, query)}` : ""}</span></button></td>
        <td class="small col-source muted">${card.source_kinds.map((k) => SOURCE_KIND[k]).join(", ")}</td>
        <td>${statusPill(card.status)}</td>
        <td class="small col-last">${card.last ? `${escapeHtml(truncate(card.last.text, 60))}<div class="muted">${fmtDay(card.last.at)}</div>` : "—"}</td>
      </tr>`;
    })
    .join("");
  animateBaseRowReorder(sortPositions);
  const openKey = focusContactKey;
  focusContactKey = null;
  el.querySelectorAll(".base-row").forEach((row) => {
    row.addEventListener("click", (e) => {
      if (e.target.closest("input, a, button")) return;
      openCompanyDrawer(row.dataset.cardKey);
    });
  });
  el.querySelectorAll(".base-row-open").forEach((button) => {
    button.addEventListener("click", () => {
      openCompanyDrawer(button.closest(".base-row").dataset.cardKey);
    });
  });
  if (openKey) {
    el.querySelector(".base-row.is-focused")?.scrollIntoView({ block: "center", behavior: REDUCE_MOTION ? "auto" : "smooth" });
    openCompanyDrawer(openKey);
  }
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
  renderBaseBulk();
}

// Карточка компании — шторка справа: контакты, вакансии, история и
// действия, вместо строки, раскрывающейся посреди таблицы.
function openCompanyDrawer(key) {
  const card = lastContacts.find((c) => c.key === key);
  if (!card) return;
  const skipped = card.status === "skip";
  const written = card.status === "written" || card.status === "replied";
  const body = openSideDrawer({
    title: `<span>${escapeHtml(card.company || card.primary?.value || "Без названия")}</span>`,
    sub: `${statusPill(card.status)}<span>${escapeHtml(card.source_kinds.map((k) => SOURCE_KIND[k]).join(", "))}</span>`,
    body: `${written ? `<div class="fix is-warn"><span class="dot warn"></span><div class="fix-body">Этой компании уже писали${card.last ? " " + fmtDay(card.last.at) : ""}. Второй раз бот не напишет, даже на другой адрес.</div></div>` : ""}
      ${card.website ? `<div class="field-hint"><a href="${escapeHtml(/^https?:/.test(card.website) ? card.website : "https://" + card.website)}" target="_blank" rel="noopener">${escapeHtml(card.website.replace(/^https?:\/\//, ""))} ↗</a></div>` : ""}
      ${baseDetailHtml(card)}`,
    foot: `${skipped || written ? "" : `<button type="button" class="btn btn-primary" data-company-action="write" data-ui="companies.detail.contacts">Написать письмо</button>`}
      <button type="button" class="btn btn-ghost" data-company-action="${skipped ? "unskip" : "skip"}" data-ui="companies.detail.skip">${skipped ? "Снова можно писать" : "Не писать"}</button>`,
  });
  openDrawerSource = null;
  bindBaseDetail(body);
  document.getElementById("platform-drawer-foot").querySelectorAll("[data-company-action]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const action = btn.dataset.companyAction;
      try {
        if (action === "write") {
          await api("/api/campaigns", { method: "POST", body: JSON.stringify({ keys: [card.key] }) });
          showToast("Письмо для компании готовится — появится в рассылке", "success");
          closePlatformDrawer();
          switchTab("outreach");
          return;
        }
        await api("/api/contacts/bulk", { method: "POST", body: JSON.stringify({ keys: [card.key], action }) });
        showSavedToast(action === "skip" ? `${card.company || "Компания"}: больше не пишем` : `${card.company || "Компания"}: снова можно писать`, async () => {
          await api("/api/contacts/bulk", { method: "POST", body: JSON.stringify({ keys: [card.key], action: action === "skip" ? "unskip" : "skip" }) });
          render.contacts();
        });
        closePlatformDrawer();
        render.contacts();
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error");
      }
    })
  );
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
                  ? `<button type="button" class="btn btn-small" data-contact-draft data-key="${escapeHtml(card.key)}" data-kind="${c.kind}" data-value="${escapeHtml(c.value)}">Написать</button>`
                  : ""}</span>
            </div>`
          )
          .join("")}
        ${card.emphasis ? `<p class="small"><b>На что сделать упор:</b> ${escapeHtml(card.emphasis)}</p>` : ""}
        <p class="small" data-ui="companies.detail.resume">${card.resume_hint ? `<b>Резюме для письма:</b> ${escapeHtml(card.resume_hint)}` : `<span class="warn-text"><b>Резюме для письма:</b> не найдено — проверьте «Мои резюме» → «Какое резюме куда уходит»</span>`}</p>
        ${card.vacancies.length ? `<h4 data-ui="companies.detail.vacancies">Вакансии компании</h4>${card.vacancies.slice(-3).map((v) => `<div class="small">${sourceIconHtml(v.source)}<a href="${escapeHtml(v.link)}" target="_blank" rel="noopener">${escapeHtml(v.title || v.link)}</a></div>`).join("")}` : ""}
        ${card.company ? `<div class="step-actions">${card.website ? "" : `<input type="text" class="dossier-site" placeholder="сайт компании" aria-label="Сайт компании" />`}
          <button type="button" class="btn btn-small" data-dossier data-key="${escapeHtml(card.key)}" title="Найти контакты на сайте компании и через Hunter" data-ui="companies.detail.dossier">Найти ещё контакты</button></div>` : ""}
      </div>
      <div>
        <h4 data-ui="companies.detail.history">История</h4>
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
        if (res.hunter_error) showToast(res.hunter_error, "error", 8000);
        render.contacts();
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error", 6000);
        btn.disabled = false;
        btn.textContent = "Найти ещё контакты";
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
        showToast("Черновик готов — проверьте и отправьте в «Общении».", "success", 6000);
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
  files.reverse().forEach((f) => anchor.after(new Option(`↳ ${f}`, `file:${f}`)));
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
    <span class="bulk-count">Выбрано <b class="mono">${keys.length.toLocaleString("ru-RU")}</b></span>
    <button type="button" class="btn btn-primary btn-small" data-bulk="write">Написать письма</button>
    <button type="button" class="btn btn-small" data-bulk="mark_written" title="Вы уже писали этим компаниям сами — рассылка их пропустит">Писал сам</button>
    <button type="button" class="btn btn-small" data-bulk="${skipped ? "unskip" : "skip"}">${skipped ? "Снова можно писать" : "Не писать"}</button>
    <button type="button" class="btn btn-ghost btn-small" data-bulk="clear">Снять выбор</button>
    <details class="bulk-more">
      <summary class="btn btn-ghost btn-small">Ещё</summary>
      <div class="bulk-menu">
        ${moreByFilter ? `<button type="button" data-bulk="all">Выбрать все ${baseFiltered.length.toLocaleString("ru-RU")} по фильтру</button>` : ""}
        <button type="button" data-bulk="unmark_written" title="Снять ручную отметку «писал сам»">Не писал</button>
        ${skipped ? "" : `<button type="button" data-bulk="unskip">Снова можно писать</button>`}
        <button type="button" data-bulk="delete" class="danger">Удалить из Базы</button>
      </div>
    </details>`;
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
        }
        await withButtonLoading(b, async () => {
          if (action === "write") {
            await api("/api/campaigns", { method: "POST", body: JSON.stringify({ keys }) });
            baseState.selected.clear();
            showToast("Рассылка создана — подготовьте письма", "success");
            switchTab("outreach");
            return;
          }
          if (action === "delete") {
            const { removed } = await api("/api/contacts/bulk", { method: "POST", body: JSON.stringify({ keys, action }) });
            baseState.selected.clear();
            showUndo(`Удалено компаний: ${removed.length}`, async () => {
              await api("/api/contacts/restore", { method: "POST", body: JSON.stringify({ cards: removed }) });
              render.contacts();
            });
            return;
          }
          await api("/api/contacts/bulk", { method: "POST", body: JSON.stringify({ keys, action }) });
        });
        if (action === "write") return;
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
  bar.style.setProperty("--undo-duration", "10000ms");
  bar.innerHTML = `<span>${escapeHtml(text)}</span><button type="button" class="btn btn-secondary btn-small">Отменить</button>`;
  document.body.appendChild(bar);
  const timer = setTimeout(() => bar.remove(), 10000);
  bar.querySelector("button").addEventListener("click", async () => {
    clearTimeout(timer);
    bar.remove();
    try {
      await undo();
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
  });
}

// «Что сделать сейчас» — первое, что видно на Главной. Заодно раздаёт
// счётчики в строку подразделов «Общения».
let lastTodoBadges = {};

// Аналитика: итоги за выбранный период (неделя, месяц, всё время) и
// таблица по источникам — что приносит ответы.
let statsPeriodDays = 7;
async function renderResults() {
  const el = document.getElementById("results-panel");
  let r;
  try {
    r = await api(`/api/results?days=${statsPeriodDays}`);
  } catch (e) {
    renderRetryState(el, `Не удалось загрузить результаты: ${e.message}`, renderResults);
    return;
  }
  const w = r.week;
  const p = r.prev;
  const all = statsPeriodDays >= 3650;
  const prevLabel = statsPeriodDays === 7 ? "прошлой неделей" : statsPeriodDays === 30 ? "прошлым месяцем" : "";
  const rate = (x) => (x.applied ? Math.round((100 * x.replies) / x.applied) : 0);
  const card = (label, help, value, prevValue, suffix = "", i = 0) => {
    const delta = value - prevValue;
    const tone = delta > 0 ? "good" : delta < 0 ? "bad" : "flat";
    const deltaText = all ? "за всё время" : delta === 0 ? `как за ${prevLabel.replace("прошлой неделей", "прошлую неделю").replace("прошлым месяцем", "прошлый месяц")}` : `на ${Math.abs(delta)}${suffix} ${delta > 0 ? "больше" : "меньше"}, чем ${prevLabel}`;
    return `<div class="card kpi-card stagger-item" style="animation-delay:${staggerDelay(i, 40)}">
      <div class="kpi-label tip" tabindex="0">${escapeHtml(label)}<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="8" cy="8" r="6"/><path d="M8 7v4M8 5h.01" stroke-linecap="round"/></svg><span class="tiptext" role="tooltip">${escapeHtml(help)}</span></div>
      <div class="kpi-main"><span class="kpi-value mono">${value}${suffix}</span></div>
      <div class="kpi-delta">${all ? "" : `<span class="trend-${tone}">${delta > 0 ? "↑" : delta < 0 ? "↓" : "·"}</span>`}${escapeHtml(deltaText)}</div>
    </div>`;
  };
  const label = (src) => (src === "email_campaign" ? `${plogoHtml("mail")}Рассылка по почте` : `${plogoHtml(src)}${escapeHtml(sourceLabel(src))}`);
  el.innerHTML = `
    <div class="kpi-grid">
      ${card("Отправлено откликов", "Реальные отклики на площадках и письма рассылки за период.", w.applied, p.applied, "", 0)}
      ${card("Ответов", "Ответы, приглашения и офферы — по времени ответа.", w.replies, p.replies, "", 1)}
      ${card("Доля ответов", "Ответы ÷ отклики за период.", rate(w), rate(p), "%", 2)}
      ${card("Интервью", "Приглашения на интервью и офферы за период.", w.interviews, p.interviews, "", 3)}
    </div>
    <section class="card pad-card" aria-labelledby="by-source-h">
      <div class="card-head flat between"><h3 id="by-source-h">Что приносит ответы</h3><span class="muted small">источники с низким откликом можно выключить — лимиты уйдут на те, что отвечают</span></div>
      ${r.by_source.length
        ? `<div class="table-wrap"><table class="results-table">
            <thead><tr><th>Откуда</th><th>Отправлено</th><th>Ответы</th><th>Интервью</th><th title="Доля ответов от отправленного">Доля ответов</th></tr></thead>
            <tbody>${r.by_source
              .map((row) => `<tr><td><span class="src-cell">${label(row.source)}</span></td><td class="mono">${row.applied}</td><td class="mono"><b>${row.replies}</b></td><td class="mono">${row.interviews}</td><td class="mono">${row.applied ? rate(row) + "%" : "—"}</td></tr>`)
              .join("")}</tbody></table></div>`
        : `<p class="muted small">За период пока ничего не отправлено — запустите бота или рассылку.</p>`}
    </section>`;
  updateAllTableScrollHints();
}

// «Отклики по неделям»: 13 недель, площадной график с перекрестием.
let weeklyChartSnapshot = null;
let weeklyChartValues = null;
let weeklyChartAnimationFrame = 0;

function animateWeeklyChart(svg) {
  if (REDUCE_MOTION || !svg) return;
  const line = svg.querySelector(".chart-line");
  const length = line?.getTotalLength?.() || 0;
  if (!line || !length) return;
  line.style.strokeDasharray = `${length} ${length}`;
  line.style.strokeDashoffset = String(length);
  void line.getBBox();
  svg.classList.add("is-entering");
  line.addEventListener("animationend", () => {
    line.style.strokeDasharray = "none";
    line.style.strokeDashoffset = "0";
    svg.classList.remove("is-entering");
  }, { once: true });
}

function renderWeeklyChart(entries) {
  const el = document.getElementById("weekly-chart");
  const readout = document.getElementById("weekly-readout");
  if (!el) return;
  const weeks = 13;
  const now = new Date();
  now.setHours(23, 59, 59, 999);
  const counts = new Array(weeks).fill(0);
  entries.forEach((e) => {
    if (e.status !== "applied" || !e.applied_at) return;
    const ago = Math.floor((now - new Date(e.applied_at)) / (7 * 86400000));
    if (ago >= 0 && ago < weeks) counts[weeks - 1 - ago] += 1;
  });
  const snapshot = JSON.stringify(counts);
  if (snapshot === weeklyChartSnapshot && el.querySelector("svg")) return;
  const animate = snapshot !== weeklyChartSnapshot;
  const previousCounts = weeklyChartValues;
  weeklyChartSnapshot = snapshot;
  weeklyChartValues = counts.slice();
  const W = 640;
  const H = 180;
  const pad = { l: 28, r: 8, t: 10, b: 22 };
  const max = Math.max(4, ...counts, ...(previousCounts || []));
  const x = (i) => pad.l + (i * (W - pad.l - pad.r)) / (weeks - 1);
  const y = (v) => H - pad.b - (v / max) * (H - pad.t - pad.b);
  const linePath = (values) => values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const areaPath = (values) => `${linePath(values)} L${x(weeks - 1).toFixed(1)} ${H - pad.b} L${x(0).toFixed(1)} ${H - pad.b} Z`;
  const line = linePath(counts);
  const area = areaPath(counts);
  const ticks = [0, Math.round(max / 2), max];
  const label = (i) => (i === weeks - 1 ? "эта неделя" : `${weeks - 1 - i} нед. назад`);
  // Линии и заливка тянутся по ширине карточки (preserveAspectRatio=none,
  // толщина штриха от этого не меняется); подписи и точка — обычным HTML
  // поверх, чтобы не растягивались вместе с SVG.
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" class="area-svg" aria-hidden="true">
      ${ticks.map((t) => `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(t)}" y2="${y(t)}" class="grid-line" vector-effect="non-scaling-stroke"/>`).join("")}
      <path d="${area}" class="chart-area"/>
      <path d="${line}" class="chart-line" vector-effect="non-scaling-stroke"/>
      <line class="crosshair" x1="0" x2="0" y1="${pad.t}" y2="${H - pad.b}" visibility="hidden" vector-effect="non-scaling-stroke"/>
    </svg>
    ${ticks.map((t) => `<span class="axis-label" style="top:${(y(t) / H) * 100}%">${t}</span>`).join("")}
    <span class="chart-dot" hidden></span>
    <div class="area-axis small muted"><span>13 нед. назад</span><span>8 нед.</span><span>4 нед.</span><span>эта неделя</span></div>`;
  const svg = el.querySelector("svg");
  if (animate && previousCounts && !REDUCE_MOTION) {
    cancelAnimationFrame(weeklyChartAnimationFrame);
    const chartLine = svg.querySelector(".chart-line");
    const chartArea = svg.querySelector(".chart-area");
    const startedAt = performance.now();
    const duration = 360;
    const tick = (now) => {
      const t = Math.min(1, (now - startedAt) / duration);
      const eased = 1 - (1 - t) ** 3;
      const values = counts.map((value, i) => previousCounts[i] + (value - previousCounts[i]) * eased);
      chartLine.setAttribute("d", linePath(values));
      chartArea.setAttribute("d", areaPath(values));
      if (t < 1) weeklyChartAnimationFrame = requestAnimationFrame(tick);
    };
    weeklyChartAnimationFrame = requestAnimationFrame(tick);
  } else if (animate) {
    animateWeeklyChart(svg);
  }
  const cross = svg.querySelector(".crosshair");
  const dot = el.querySelector(".chart-dot");
  const show = (clientX) => {
    const rect = svg.getBoundingClientRect();
    const rel = ((clientX - rect.left) / rect.width) * W;
    const i = Math.max(0, Math.min(weeks - 1, Math.round(((rel - pad.l) / (W - pad.l - pad.r)) * (weeks - 1))));
    cross.setAttribute("x1", x(i));
    cross.setAttribute("x2", x(i));
    cross.setAttribute("visibility", "visible");
    dot.hidden = false;
    dot.style.left = `${(x(i) / W) * 100}%`;
    dot.style.top = `${(y(counts[i]) / H) * rect.height}px`;
    readout.textContent = `${label(i)} · ${counts[i]} ${plural(counts[i], "отклик", "отклика", "откликов")}`;
  };
  svg.addEventListener("pointermove", (e) => show(e.clientX));
  svg.addEventListener("pointerleave", () => {
    cross.setAttribute("visibility", "hidden");
    dot.hidden = true;
    readout.textContent = `всего за 13 недель: ${counts.reduce((a, b) => a + b, 0)}`;
  });
  readout.textContent = `всего за 13 недель: ${counts.reduce((a, b) => a + b, 0)}`;
}

// 1 письмо, 2 письма, 5 писем.
function plural(n, one, few, many) {
  const m = Math.abs(n) % 100;
  if (m > 10 && m < 20) return many;
  return m % 10 === 1 ? one : m % 10 >= 2 && m % 10 <= 4 ? few : many;
}

// ---------- Главная: строки площадок и шторка ----------

let lastStatus = null;
let lastRunNow = null;
let lastOutreach = null;
let lastTelegramWatch = null;
const platformStatusSignatures = new Map();
let lastLiveFeedKeys = null;
let lastInboxStageByKey = new Map();
let lastDraftCodes = null;
let lastHhReminderCodes = null;
// Площадка, чья шторка открыта сейчас: опрос Главной обновляет её
// шапку (состояние, счётчик), пока человек ничего в ней не правит.
let openDrawerSource = null;
let drawerDirty = false;

const CHEVRON_SVG = `<svg class="chev" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 4 4 4-4 4"/></svg>`;

// Эмодзи в начале серверных фраз («⛔ …», «🔄 …») — в новом виде их
// заменяет цветная точка состояния.
function stripLeadingEmoji(text) {
  return String(text || "").replace(/^[\p{Extended_Pictographic}️‍\s]+/u, "");
}

function plogoHtml(name) {
  const icon = SOURCE_ICON[name] || { text: name.slice(0, 2).toUpperCase(), color: "#5b6068" };
  return `<span class="plogo" aria-hidden="true" style="background:${icon.color}">${icon.text}</span>`;
}

function skeletonRowsList(n) {
  return Array.from({ length: n })
    .map(() => `<div class="row skeleton-row-line"><span class="skeleton" style="width:24px;height:24px"></span><span class="skeleton" style="height:12px;flex:1"></span><span class="skeleton" style="width:72px;height:6px"></span></div>`)
    .join("");
}

// Строка площадки в списке Главной. m — модель из sourceRowModel() или
// своих каналов: key, name, logo, dot, statusText, counter, pct.
function platformRowHtml(m) {
  const pct = m.pct == null ? null : Math.max(0, Math.min(100, m.pct));
  const signature = `${m.dot}|${m.statusText}|${!!m.running}`;
  const statusChanged = platformStatusSignatures.has(m.key) && platformStatusSignatures.get(m.key) !== signature;
  platformStatusSignatures.set(m.key, signature);
  const bar = pct == null
    ? `<span class="bar is-empty" aria-hidden="true"></span>`
    : `<span class="bar" aria-hidden="true"><span class="${pct >= 100 ? "full" : pct >= 70 ? "warn" : ""}" style="width:${pct}%"></span></span>`;
  return `<div class="platform-row-wrap" data-source="${m.key}" draggable="true">
    <button type="button" class="row platform-row${m.running ? " is-running" : ""}" data-open-source="${m.key}" aria-label="${escapeHtml(m.name)}: ${escapeHtml(m.statusText)}. Открыть настройки">
      ${m.logo}
      <span class="row-main">
        <span class="row-title">${escapeHtml(m.name)}</span>
        <span class="row-sub"><span class="dot ${m.dot}${statusChanged ? " status-changed" : ""}"></span><span class="row-sub-text${statusChanged ? " status-changed" : ""}">${escapeHtml(m.statusText)}</span></span>
      </span>
      ${m.counter != null ? `<span class="row-count mono">${escapeHtml(m.counter)}</span>` : ""}
      ${bar}
      ${CHEVRON_SVG}
    </button>
  </div>`;
}

function sourceRowModel(s, runNow) {
  const running = !!(runNow?.running && runNow.current_source === s.name);
  const searchOnly = s.name === "telegram" ? !s.auto_message : !s.auto_apply;
  const mode = OWN_CHANNELS.has(s.name) ? "собирает вакансии и контакты HR" : searchOnly ? "только ищет" : "откликается сам";
  let dot = "ok";
  let text;
  if (running) {
    dot = "running";
    text = "идёт ход — ищу и оцениваю вакансии";
  } else if (!s.schedule_enabled) {
    dot = "idle";
    text = "выключена";
  } else if (s.status === "blocked" || s.paused) {
    // Четыре статуса из единого словаря: работает, пауза, нужен вход, ошибка.
    dot = "warn";
    text = `пауза · ${s.last_error?.summary || "после капчи нужна проверка на сайте"}`;
  } else if (s.status === "error" && s.last_error?.kind === "login") {
    dot = "warn";
    text = "нужен вход · откройте и нажмите «Войти»";
  } else if (s.status === "error") {
    dot = "error";
    text = `ошибка · ${s.last_error?.summary || "последний ход не удался"}`;
  } else if (s.status === "never_run") {
    dot = "never_run";
    text = `${mode} · ещё не запускалась`;
  } else {
    text = `${mode} · проверка ${fmtDay(s.last_run)}`;
  }
  const hasLimit = !OWN_CHANNELS.has(s.name) && s.daily_limit;
  return {
    key: s.name,
    name: sourceLabel(s.name),
    logo: plogoHtml(s.name),
    dot,
    statusText: text,
    counter: hasLimit ? `${s.applied_today}/${s.daily_limit}` : null,
    pct: hasLimit && s.schedule_enabled ? Math.round((100 * s.applied_today) / s.daily_limit) : null,
    running,
  };
}

function telegramRowModel(w) {
  const dot = w.running ? "ok" : w.enabled ? "never_run" : "idle";
  const text = w.running
    ? `слушает ${w.channels} ${plural(w.channels, "канал", "канала", "каналов")} · найдено ${w.matched}`
    : w.enabled
      ? w.daemon_running ? "подключается…" : "включён — заработает после «Запустить»"
      : "выключен";
  return { key: "telegram", name: "Telegram-парсер", logo: plogoHtml("telegram"), dot, statusText: text, counter: `${w.channels} кан.`, pct: null };
}

function mailRowModel(o) {
  const next = pipelineNext(o);
  if (next.kind === "empty") {
    return { key: "mail", name: "Рассылка по почте", logo: plogoHtml("mail"), dot: "idle", statusText: "База пуста — загрузите список компаний", counter: null, pct: null };
  }
  const dot = next.tone === "alert" ? "error" : next.tone === "active" ? "running" : next.tone === "waiting" ? "never_run" : "ok";
  return {
    key: "mail",
    name: "Рассылка по почте",
    logo: plogoHtml("mail"),
    dot,
    statusText: stripLeadingEmoji(next.status),
    counter: `${o.plan.sent_today}/${o.plan.limit}`,
    pct: o.plan.limit ? Math.round((100 * o.plan.sent_today) / o.plan.limit) : null,
  };
}

let lastOwnChannels = "";
async function renderOwnChannels() {
  let w, o;
  try {
    [w, o] = await Promise.all([api("/api/settings/telegram-watch"), api("/api/outreach/summary")]);
  } catch (e) {
    return;
  }
  lastOutreach = o;
  lastTelegramWatch = w;
  const own = (lastStatus?.sources || []).filter((s) => OWN_CHANNELS.has(s.name) && s.name !== "telegram");
  const snapshot = JSON.stringify([w, o, own, lastRunNow]);
  if (snapshot === lastOwnChannels) return;
  lastOwnChannels = snapshot;
  const rows = [telegramRowModel(w)];
  const byName = Object.fromEntries(own.map((s) => [s.name, s]));
  if (byName.direct) {
    rows.push({ ...sourceRowModel(byName.direct, lastRunNow), name: "Сайты компаний" });
  }
  rows.push(mailRowModel(o));
  ["talanto", "hirify"].forEach((n) => byName[n] && rows.push(sourceRowModel(byName[n], lastRunNow)));
  const el = document.getElementById("own-channels");
  setHtmlIfChanged(el, applySourceOrder(rows, "key", "cj-source-order-own").map(platformRowHtml).join(""));
  if (openDrawerSource === "mail" && isPlatformDrawerOpen() && !drawerDirty) openMailDrawer(true);
  if (openDrawerSource === "telegram" && isPlatformDrawerOpen() && !drawerDirty) openTelegramDrawer(true);
}

function refreshOwnChannels() {
  lastOwnChannels = "";
  renderOwnChannels();
}

// Сохранение из шторки сразу, без кнопки «Сохранить»: уведомление
// «… · сохранено» с «Отменить», которое возвращает прежнее значение.
async function saveSourceSettings(source, body, label, undoBody) {
  try {
    await api("/api/settings", { method: "POST", body: JSON.stringify({ source, ...body }) });
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
    return false;
  }
  showSavedToast(`${sourceLabel(source)}: ${label}`, undoBody
    ? async () => {
        await api("/api/settings", { method: "POST", body: JSON.stringify({ source, ...undoBody }) });
        showToast(`${sourceLabel(source)}: вернул как было`, "info");
        afterSourceSaved(source);
      }
    : null);
  afterSourceSaved(source);
  return true;
}

function afterSourceSaved(source) {
  lastOverviewSnapshot = "";
  lastOwnChannels = "";
  render.overview();
  if (openDrawerSource === source && isPlatformDrawerOpen()) {
    refreshSourceDrawerHead(source);
  }
}

function statusLineHtml(m) {
  return `<span class="dot ${m.dot}"></span><span>${escapeHtml(m.statusText)}</span>`;
}

function fieldRowHtml({ title, hint = "", control, ui = "" }) {
  return `<div class="field-row"${ui ? ` data-ui="${ui}"` : ""}>
    <div class="field-text"><div class="field-title">${title}</div>${hint ? `<div class="field-hint">${hint}</div>` : ""}</div>
    <div class="field-control">${control}</div>
  </div>`;
}

function switchHtml(cls, checked, label, extra = "") {
  return `<input type="checkbox" class="switch ${cls}" ${checked ? "checked" : ""} aria-label="${escapeHtml(label)}" ${extra} />`;
}

// Причина сбоя и одно действие, чтобы его исправить.
function fixBlockHtml(s) {
  const blocked = s.status === "blocked" || s.paused;
  if (!blocked && s.status !== "error") return "";
  const err = s.last_error || {};
  const login = !blocked && err.kind === "login";
  const summary = err.summary || (blocked ? "Пауза: площадка ждёт проверки на сайте после капчи." : "Ошибка: последний ход не удался.");
  const actions = blocked
    ? `<button type="button" class="btn btn-primary btn-small" data-drawer-action="unblock">Я прошёл проверку — снять паузу</button>
       <button type="button" class="btn btn-ghost btn-small" data-drawer-action="accounts">Подключения</button>`
    : `<button type="button" class="btn btn-primary btn-small" data-drawer-action="run">${login ? "Войти" : "Повторить сейчас"}</button>
       <button type="button" class="btn btn-ghost btn-small" data-drawer-action="logs">Журнал</button>`;
  const warn = blocked || login;
  return `<div class="fix ${warn ? "is-warn" : "is-error"}" data-ui="home.platform.error drawer.fix">
    <span class="dot ${warn ? "warn" : "error"}"></span>
    <div class="fix-body">
      <div>${escapeHtml(summary)}${blocked ? ` Откройте сайт в окне бота, пройдите проверку и нажмите кнопку ниже (то же, что <code>/resume ${s.name}</code> в боте).` : ""}</div>
      ${err.detail ? `<details class="fix-detail"><summary>Подробности</summary><pre>${escapeHtml(err.detail)}</pre></details>` : ""}
      <div class="fix-actions">${actions}</div>
    </div>
  </div>`;
}

// Итог последнего захода площадки: «новых 0» — не поломка, а «всё уже
// просмотрено»; без этой строки такой заход в интерфейсе невидим.
function lastSummaryKvHtml(sum) {
  const parts = [`новых ${sum.new}`];
  if (sum.new) {
    parts.push(`слабое совпадение ${sum.low_fit}`);
    parts.push(`откликов ${sum.applied}`);
  }
  const title = `Проверено ${fmtTime(sum.at)}. «Новых» — вакансий, которых ещё не было в журнале.`;
  return `<div class="kv" title="${escapeHtml(title)}"><span>Итог захода</span><span>${parts.join(" · ")}</span></div>`;
}

function sourceDrawerBody(s, limits, salary) {
  const defaultDaily = s.name === "linkedin" ? limits.linkedin_daily_application_limit : limits.daily_application_limit;
  const isOwn = OWN_CHANNELS.has(s.name);
  const lastRunRows = `
    <div class="kv"><span>Последняя проверка</span><span>${s.schedule_enabled ? fmtDay(s.last_run) : "—"}</span></div>
    <div class="kv"><span>Следующая проверка</span><span>${s.schedule_enabled ? fmtTime(s.next_run) : "—"}</span></div>
    ${s.schedule_enabled && s.duration_seconds != null ? `<div class="kv"><span>Последний ход</span><span>${Math.max(1, Math.round(s.duration_seconds / 60))} мин${s.idle_streak >= 2 ? ", пусто — следующая проверка реже" : ""}</span></div>` : ""}
    ${s.schedule_enabled && s.last_summary ? lastSummaryKvHtml(s.last_summary) : ""}`;
  const readiness = (s.readiness && s.readiness.missing) || [];
  return `
    ${fixBlockHtml(s)}
    ${readiness.length ? `<div class="fix is-warn"><span class="dot warn"></span><div class="fix-body">Не хватает: ${escapeHtml(readiness.join(", "))}</div></div>` : ""}
    <div class="field-stack">
      ${fieldRowHtml({ title: "Площадка включена", hint: isOwn ? "Бот собирает здесь вакансии и контакты HR по кругу" : "Бот ищет здесь вакансии по кругу", control: switchHtml("d-schedule", s.schedule_enabled, "Площадка включена"), ui: "drawer.enabled home.platform.toggle" })}
      ${isOwn ? "" : fieldRowHtml({ title: "Откликаться самому", hint: "Выключено — бот только находит, откликаетесь вы", control: switchHtml("d-auto", s.auto_apply, "Откликаться самому"), ui: "drawer.auto-apply home.platform.mode" })}
    </div>
    ${isOwn ? "" : fieldRowHtml({
      title: "Откликов в день, не больше",
      hint: `Сегодня отправлено ${s.applied_today}${s.daily_limit_override ? ` · своё значение, по умолчанию ${defaultDaily} <button type="button" class="link-btn" data-drawer-action="daily-reset">вернуть</button>` : " · как у всех площадок"}`,
      control: `<div class="stepper" data-ui="drawer.daily-limit home.platform.today">
        <button type="button" class="btn btn-small" data-step="-1" aria-label="Меньше">−</button>
        <input type="number" class="d-daily-limit mono" min="1" value="${s.daily_limit}" aria-label="Откликов в день" />
        <button type="button" class="btn btn-small" data-step="1" aria-label="Больше">+</button>
      </div>`,
    })}
    ${isOwn ? "" : `<div class="field-block" data-ui="drawer.positions">
      <div class="field-title">Должности для поиска</div>
      <div class="field-hint">Пусто — как в «Что ищу»: ${escapeHtml((s.effective_positions || []).join(", ") || "—")}</div>
      <textarea class="d-positions" rows="2" placeholder="оставить пустым — использовать общие">${escapeHtml((s.positions_override || []).join("\n"))}</textarea>
    </div>`}
    <div class="kv-list" data-ui="home.platform.last-run">${lastRunRows}</div>
    <details class="drawer-more" data-ui="drawer.more">
      <summary>Ещё настройки: ${isOwn ? "расписание" : "резюме, расписание, лимиты, фильтры"}</summary>
      <div class="drawer-more-body">
        ${fieldRowHtml({
          title: "Интервал хода, минут",
          hint: s.continuous_cycle_active ? "Включён «Постоянный цикл» (Настройки → Лимиты и оценка) — свой интервал не действует, все идут по кругу." : "Минимум 3 минуты — почти реалтайм, но не похоже на бота.",
          control: `<input type="number" class="d-interval num-input" min="3" step="1" value="${Math.round((s.interval_hours ?? 3) * 60)}" ${s.continuous_cycle_active ? "disabled" : ""} aria-label="Интервал хода, минут" />`,
          ui: "drawer.interval",
        })}
        ${isOwn ? "" : fieldRowHtml({
          title: "Резюме на площадке",
          hint: "id резюме на сайте площадки, если их несколько",
          control: `<input type="text" class="d-resume-id" value="${escapeHtml(s.resume_id || "")}" placeholder="id резюме" aria-label="id резюме на площадке" />`,
          ui: "drawer.resume-id",
        })}
        ${isOwn ? "" : fieldRowHtml({
          title: "Максимум за один заход",
          hint: `Не дневной лимит. По умолчанию ${limits.job_max_applications}`,
          control: `<span class="override-field"><input type="number" class="d-max-applications num-input" min="1" value="${s.job_max_applications_override ? s.job_max_applications : ""}" placeholder="${limits.job_max_applications}" ${s.job_max_applications_override ? "" : "disabled"} aria-label="Максимум за один заход" /><label class="override-toggle"><input type="checkbox" class="d-max-applications-override" ${s.job_max_applications_override ? "checked" : ""} /> своё</label></span>`,
          ui: "drawer.per-run",
        })}
        ${isOwn ? "" : `<div class="field-block" data-ui="drawer.locations">
          <div class="field-title">Свои локации</div>
          <div class="field-hint">Пусто — как в «Что ищу»${s.name === "linkedin" ? "; у LinkedIn свои локации (linkedin.locations)" : `: ${escapeHtml((s.effective_locations || []).join(", ") || "любые")}`}</div>
          <textarea class="d-locations" rows="2" placeholder="оставить пустым — использовать общие">${escapeHtml((s.locations_override || []).join("\n"))}</textarea>
        </div>`}
        ${sourceFiltersHtml(s, salary)}
      </div>
    </details>`;
}

function sourceFiltersHtml(s, salary) {
  const remote = s.remote_only_managed ? "" : fieldRowHtml({ title: "Только удалённые вакансии", control: switchHtml("d-remote-only", s.remote_only, "Только удалённые вакансии"), ui: "drawer.filters" });
  const select = (cls, label, options, value, multiple = false) => fieldRowHtml({
    title: label,
    control: `<select class="${cls}" ${multiple ? `multiple size="${options.length}"` : ""} aria-label="${escapeHtml(label)}">${options
      .map(([v, t]) => `<option value="${v}" ${(multiple ? (value || []).includes(v) : (value || "") === v) ? "selected" : ""}>${t}</option>`)
      .join("")}</select>`,
    ui: "drawer.filters",
  });
  if (s.name === "linkedin") {
    return fieldRowHtml({
      title: "Зарплата для скрининга LinkedIn",
      hint: "USD в год, диапазоном",
      control: `<input type="text" class="d-linkedin-salary" value="${escapeHtml(salary.linkedin_salary_range_usd || "")}" placeholder="60000-80000" aria-label="Зарплата для скрининга LinkedIn" /><span class="d-salary-hint field-hint" aria-live="polite"></span>`,
      ui: "drawer.linkedin-salary",
    });
  }
  if (s.name === "avito") {
    return remote
      + select("d-hc-qualification", "Опыт работы", [["", "Любой"], ["no_experience", "Без опыта"], ["under_1_year", "До 1 года"], ["over_1_year", "Более 1 года"], ["over_3_years", "Более 3 лет"], ["over_5_years", "Более 5 лет"], ["over_10_years", "Более 10 лет"]], s.qualification)
      + select("d-hc-employment-type", "Занятость", [["", "Любая"], ["full_time", "Полная"], ["part_time", "Частичная"], ["temporary", "Временная"]], s.employment_type);
  }
  if (s.name === "getmatch") {
    return remote + (s.levels_managed ? "" : select("d-gm-experience-level", "Уровень вакансии (пусто — любой)", [["junior", "Junior"], ["middle", "Middle"], ["senior", "Senior"], ["lead", "Lead / Manager"]], s.experience_level, true));
  }
  if (s.name === "habr_career") {
    return remote
      + (s.levels_managed ? "" : select("d-hc-qualification", "Квалификация", [["", "Любая"], ["intern", "Стажёр (Intern)"], ["junior", "Младший (Junior)"], ["middle", "Средний (Middle)"], ["senior", "Старший (Senior)"], ["lead", "Ведущий (Lead)"]], s.qualification))
      + select("d-hc-employment-type", "Тип занятости", [["", "Любой"], ["full_time", "Полный рабочий день"], ["part_time", "Неполный рабочий день"]], s.employment_type);
  }
  if (s.name === "djinni") {
    return fieldRowHtml({
      title: "Поднимать профиль раз в 7 дней",
      hint: "Кнопка «Bump My Profile» на Djinni — бот нажимает её сам, как только Djinni разрешит",
      control: switchHtml("d-auto-bump", s.auto_bump_resume, "Поднимать профиль"),
      ui: "drawer.bump",
    });
  }
  if (s.name === "headhunter") {
    return `${fieldRowHtml({ title: "Автоответ HR в чате", hint: "Простые вопросы бот закрывает сам, сложные — вам в «Общение»", control: switchHtml("d-auto-reply", s.auto_reply, "Автоответ HR в чате"), ui: "drawer.hh-chat" })}
      ${fieldRowHtml({ title: "Письмо в чат после отклика", hint: "Если отклик ушёл без письма — досылает его в чат вакансии", control: switchHtml("d-chat-cover-letter-followup", s.chat_cover_letter_followup, "Письмо в чат после отклика") })}
      ${fieldRowHtml({ title: "Поднимать резюме", control: switchHtml("d-auto-bump", s.auto_bump_resume, "Поднимать резюме на HH"), ui: "drawer.bump" })}
      ${fieldRowHtml({ title: "Напомнить о себе, если молчат, через", hint: "Дней; 0 — не напоминать. Готовые напоминания — в «Общении»", control: `<input type="number" class="d-reminder-days num-input" min="0" value="${s.reminder_follow_up_days ?? 7}" aria-label="Напомнить через дней" />`, ui: "drawer.reminder-days" })}
      ${fieldRowHtml({ title: "Отправлять напоминания сами", hint: "Выключено — ждут вашего «Отправить» в «Общении»", control: switchHtml("d-auto-reminder", s.auto_reminder, "Отправлять напоминания сами") })}
      ${fieldRowHtml({ title: "Зарплата для ответов HR", hint: "Подставляется в автоответ в чате", control: `<input type="text" class="d-hh-salary" value="${escapeHtml(salary.hh_salary_expectations || "")}" placeholder="250000-300000 RUR" aria-label="Зарплата для ответов HR" /><span class="d-salary-hint field-hint" aria-live="polite"></span>`, ui: "drawer.hh-salary" })}`;
  }
  return "";
}

function sourceDrawerFoot(s, running) {
  return `<button type="button" class="btn btn-primary" data-drawer-action="${running ? "stop" : "run"}" data-ui="home.platform.run-now">${running ? "Остановить ход" : "Запустить ход сейчас"}</button>
    ${OWN_CHANNELS.has(s.name) ? "" : `<button type="button" class="btn btn-ghost" data-drawer-action="history" data-ui="home.platform.history">Отклики</button>`}
    <button type="button" class="btn btn-ghost" data-drawer-action="logs" data-ui="home.platform.logs">Журнал</button>`;
}

async function openSourceDrawer(name) {
  let status, limits, salary;
  try {
    [status, limits, salary] = await Promise.all([api("/api/status"), api("/api/settings/limits"), api("/api/settings/salary")]);
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
    return;
  }
  lastStatus = status;
  const s = status.sources.find((x) => x.name === name);
  if (!s) return;
  const m = sourceRowModel(s, lastRunNow);
  openDrawerSource = name;
  drawerDirty = false;
  const body = openSideDrawer({
    title: `${plogoHtml(name)}<span>${name === "direct" ? "Сайты компаний" : sourceLabel(name)}</span>`,
    sub: statusLineHtml(m),
    body: sourceDrawerBody(s, limits, salary) + (name === "direct" ? `<p class="field-hint">Откуда собирать и какие компании отслеживать — <button type="button" class="link-btn" data-drawer-action="settings-direct">Настройки → Сайты компаний</button>. Компании с подходящими вакансиями попадают в <button type="button" class="link-btn" data-drawer-action="base-sites">Базу</button>.</p>` : ""),
    foot: sourceDrawerFoot(s, m.running),
  });
  bindSourceDrawer(body, s);
}

async function refreshSourceDrawerHead(name) {
  if (["telegram", "mail"].includes(name)) return;
  const s = lastStatus?.sources.find((x) => x.name === name);
  if (!s) return;
  const m = sourceRowModel(s, lastRunNow);
  const sub = document.getElementById("platform-drawer-sub");
  if (sub) sub.innerHTML = statusLineHtml(m);
  const foot = document.getElementById("platform-drawer-foot");
  if (foot && !foot.contains(document.activeElement)) foot.innerHTML = sourceDrawerFoot(s, m.running);
}

function bindSourceDrawer(body, s) {
  const name = s.name;
  const linesOfEl = (el) => el.value.split("\n").map((x) => x.trim()).filter(Boolean);
  body.querySelectorAll(".d-positions, .d-locations").forEach(initTagInput);
  body.addEventListener("input", () => (drawerDirty = true));

  const onSwitch = (cls, field, labels) => {
    const box = body.querySelector(cls);
    box?.addEventListener("change", () => {
      const v = box.checked;
      saveSourceSettings(name, { [field]: v }, v ? labels[0] : labels[1], { [field]: !v });
    });
  };
  onSwitch(".d-schedule", "schedule_enabled", ["включена · сохранено", "выключена · сохранено"]);
  onSwitch(".d-auto-bump", "auto_bump_resume", ["поднимать резюме · сохранено", "не поднимать резюме · сохранено"]);
  onSwitch(".d-remote-only", "remote_only", ["только удалённые · сохранено", "любой формат · сохранено"]);
  onSwitch(".d-auto-reply", "auto_reply", ["автоответ в чате включён", "автоответ в чате выключен"]);
  onSwitch(".d-chat-cover-letter-followup", "chat_cover_letter_followup", ["письмо в чат после отклика включено", "письмо в чат после отклика выключено"]);
  onSwitch(".d-auto-reminder", "auto_reminder", ["напоминания уходят сами", "напоминания ждут вашего «Отправить»"]);

  const auto = body.querySelector(".d-auto");
  auto?.addEventListener("change", async () => {
    const v = auto.checked;
    if (v && !(await showConfirm(`${sourceLabel(name)}: бот начнёт сам отправлять отклики — до дневного лимита. Включить?`))) {
      auto.checked = false;
      return;
    }
    saveSourceSettings(name, { auto_apply: v }, v ? "откликается сам · сохранено" : "только ищет · сохранено", { auto_apply: !v });
  });

  // Дневной лимит: − N + и ручной ввод. Своё число = «своё значение»
  // для этой площадки; «вернуть» снимает его.
  const daily = body.querySelector(".d-daily-limit");
  if (daily) {
    let saveTimer = null;
    const prev = { override: s.daily_limit_override, value: s.daily_limit };
    const commit = () => {
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        const v = Math.max(1, parseInt(daily.value, 10) || 1);
        daily.value = v;
        if (v === prev.value && prev.override) return;
        const undo = prev.override ? { daily_application_limit: prev.value } : { clear_daily_application_limit: true };
        saveSourceSettings(name, { daily_application_limit: v }, `не больше ${v} откликов в день · сохранено`, undo);
        prev.override = true;
        prev.value = v;
      }, 500);
    };
    body.querySelectorAll("[data-step]").forEach((b) =>
      b.addEventListener("click", () => {
        daily.value = Math.max(1, (parseInt(daily.value, 10) || 0) + Number(b.dataset.step));
        commit();
      })
    );
    daily.addEventListener("change", commit);
  }

  const saveOnChange = (cls, build, label) => {
    const el = body.querySelector(cls);
    if (!el) return;
    el.addEventListener("change", () => {
      const payload = build(el);
      if (payload) saveSourceSettings(name, payload, label);
    });
  };
  saveOnChange(".d-positions", (el) => ({ positions: linesOfEl(el) }), "должности · сохранено");
  saveOnChange(".d-locations", (el) => ({ locations: linesOfEl(el) }), "локации · сохранено");
  saveOnChange(".d-interval", (el) => ({ interval_hours: Math.max(3, parseInt(el.value, 10) || 3) / 60 }), "интервал · сохранено");
  saveOnChange(".d-resume-id", (el) => ({ resume_id: el.value.trim() }), "id резюме · сохранено");
  saveOnChange(".d-reminder-days", (el) => ({ reminder_follow_up_days: Math.max(0, parseInt(el.value, 10) || 0) }), "напоминание · сохранено");
  saveOnChange(".d-hc-qualification", (el) => ({ qualification: el.value }), "фильтр · сохранено");
  saveOnChange(".d-hc-employment-type", (el) => ({ employment_type: el.value }), "фильтр · сохранено");
  saveOnChange(".d-gm-experience-level", (el) => ({ experience_level: Array.from(el.selectedOptions).map((o) => o.value) }), "уровень · сохранено");
  saveOnChange(".d-max-applications", (el) => ({ job_max_applications: Math.max(1, parseInt(el.value, 10) || 1) }), "максимум за заход · сохранено");
  const perRunOverride = body.querySelector(".d-max-applications-override");
  perRunOverride?.addEventListener("change", () => {
    const input = body.querySelector(".d-max-applications");
    input.disabled = !perRunOverride.checked;
    if (perRunOverride.checked) {
      input.focus();
    } else {
      input.value = "";
      saveSourceSettings(name, { clear_job_max_applications: true }, "максимум за заход — как у всех · сохранено");
    }
  });

  body.querySelectorAll(".d-hh-salary, .d-linkedin-salary").forEach((input) => {
    const hint = input.parentElement.querySelector(".d-salary-hint");
    const validate = () => {
      const v = input.value.trim();
      const ok = !v || /^\d{4,}\s*[-–]\s*\d{4,}(\s*\S+)?$/.test(v);
      if (hint) {
        const message = ok ? "" : `Ожидается диапазон вида «${input.placeholder}»`;
        if (hint.textContent !== message) hint.textContent = message;
        hint.classList.toggle("warn-text", !ok);
        hint.classList.toggle("has-error", !ok);
      }
      input.setAttribute("aria-invalid", String(!ok));
      return ok;
    };
    input.addEventListener("input", validate);
    validate();
    input.addEventListener("change", async () => {
      if (!validate()) return;
      const key = input.classList.contains("d-hh-salary") ? "hh_salary_expectations" : "linkedin_salary_range_usd";
      try {
        await api("/api/settings/salary", { method: "POST", body: JSON.stringify({ [key]: input.value.trim() }) });
        showSavedToast(`${sourceLabel(name)}: зарплата · сохранено`);
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error");
      }
    });
  });
}

// Кнопки в шторках Главной: запуск хода, журнал, переходы.
async function handleDrawerAction(btn) {
  const action = btn.dataset.drawerAction;
  const name = openDrawerSource;
  if (action === "run") {
    if (!(await showConfirm(`Запустить ${sourceLabel(name)} прямо сейчас? Это реальный прогон, не тест — если включены отклики, они уйдут по-настоящему.`))) return;
    try {
      await withButtonLoading(btn, () => api("/api/run-now", { method: "POST", body: JSON.stringify({ sources: [name] }) }));
    } catch (e) {
      showToast(`Не удалось запустить ${sourceLabel(name)}: ${e.message}`, "error");
      return;
    }
    showToast(`${sourceLabel(name)}: ход запущен`, "success");
    lastOverviewSnapshot = "";
    render.overview();
    watchSourceRunCompletion(name);
  } else if (action === "stop") {
    try {
      await withButtonLoading(btn, () => api("/api/run-now/stop", { method: "POST" }));
      showToast(`${sourceLabel(name)}: остановка запрошена — текущий отклик досылается`, "success");
    } catch (e) {
      showToast(`Не удалось остановить: ${e.message}`, "error");
    }
  } else if (action === "unblock") {
    try {
      await withButtonLoading(btn, () => api(`/api/sources/${name}/resume`, { method: "POST" }));
      showToast(`${sourceLabel(name)}: пауза снята, попробую в ближайший ход`, "success");
      afterSourceSaved(name);
      openSourceDrawer(name);
    } catch (e) {
      showToast(e.message.replace(/^\d+: /, ""), "error");
    }
  } else if (action === "daily-reset") {
    await saveSourceSettings(name, { clear_daily_application_limit: true }, "дневной лимит — как у всех · сохранено");
    openSourceDrawer(name);
  } else if (action === "history") {
    closePlatformDrawer();
    document.getElementById("filter-source").value = name;
    switchTab("history");
  } else if (action === "logs") {
    closePlatformDrawer();
    document.getElementById("log-source").value = name === "mail" ? "" : name;
    switchTab("logs");
  } else if (action === "accounts") {
    closePlatformDrawer();
    gotoSettings("settings-accounts");
  } else if (action === "settings-direct") {
    closePlatformDrawer();
    gotoSettings("settings-direct");
  } else if (action === "settings-tg") {
    closePlatformDrawer();
    gotoSettings("settings-tg-quick");
  } else if (action === "base-sites") {
    closePlatformDrawer();
    document.getElementById("contacts-filter-source").value = "sites";
    baseState.page = 0;
    switchTab("contacts");
  } else if (action === "base-telegram") {
    closePlatformDrawer();
    document.getElementById("contacts-filter-source").value = "telegram";
    baseState.page = 0;
    switchTab("contacts");
  } else if (action === "talk") {
    closePlatformDrawer();
    switchTab("telegram");
  } else if (action === "outreach") {
    closePlatformDrawer();
    switchTab("outreach");
  }
}

async function watchSourceRunCompletion(name) {
  for (;;) {
    await new Promise((r) => setTimeout(r, 3000));
    let runStatus;
    try {
      runStatus = await api("/api/run-now/status");
    } catch (e) {
      return;
    }
    if (!runStatus.running || runStatus.current_source !== name) break;
  }
  showToast(`${sourceLabel(name)}: ход завершён — см. «Вакансии»`, "success");
  lastOverviewSnapshot = "";
  render.overview();
}

function gotoSettings(tab) {
  switchTab("settings");
  switchSettingsTab(tab);
  if (tab === "settings-tg-quick") loadTelegramWatch();
}

function openTelegramDrawer(refresh = false) {
  const w = lastTelegramWatch;
  if (!w) return;
  const m = telegramRowModel(w);
  openDrawerSource = "telegram";
  if (!refresh) drawerDirty = false;
  const body = openSideDrawer({
    title: `${plogoHtml("telegram")}<span>Telegram-парсер</span>`,
    sub: statusLineHtml(m),
    body: `<div class="field-stack">
        ${fieldRowHtml({ title: "Парсер включён", hint: "Новый пост с нужным словом — за секунды в боте и в «Общении»", control: switchHtml("d-tg-enabled", w.enabled, "Telegram-парсер включён"), ui: "home.tg" })}
      </div>
      <div class="kv-list">
        <div class="kv"><span>Каналов</span><span class="mono">${w.channels}</span></div>
        ${w.running && w.last_post_at ? `<div class="kv"><span>Последний пост</span><span>${relativeTimeRu(new Date(w.last_post_at * 1000).toISOString())}</span></div>` : ""}
        <div class="kv"><span>Вакансий найдено с запуска</span><span class="mono">${w.matched}</span></div>
        <div class="kv"><span>Контактов HR в Базе</span><span class="mono">${w.contacts_collected}</span></div>
        <div class="kv"><span>Ответы HR в диалогах</span><span>${w.running ? "ловит сразу" : "проверяет каждые 30 мин"}</span></div>
      </div>
      <p class="field-hint">Каналы, ключевые слова, текст «Здравствуйте» и автоотправка — в <button type="button" class="link-btn" data-drawer-action="settings-tg">Настройки → Telegram-парсер</button>. Контакты HR из постов — в <button type="button" class="link-btn" data-drawer-action="base-telegram">Базе</button>.</p>`,
    foot: `<button type="button" class="btn btn-primary" data-drawer-action="talk">Открыть диалоги</button>
      <button type="button" class="btn btn-ghost" data-drawer-action="settings-tg">Правила парсера</button>`,
  });
  body.querySelector(".d-tg-enabled").addEventListener("change", async (e) => {
    const on = e.target.checked;
    e.target.disabled = true;
    try {
      // Один переключатель на весь Telegram: парсер + поиск по расписанию.
      await Promise.all([
        api("/api/settings/telegram-watch", { method: "POST", body: JSON.stringify({ enabled: on }) }),
        api("/api/settings", { method: "POST", body: JSON.stringify({ source: "telegram", schedule_enabled: on }) }),
      ]);
      showSavedToast(on ? "Telegram-парсер включён" : "Telegram-парсер выключен");
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
    refreshOwnChannels();
  });
}

function openMailDrawer(refresh = false) {
  const o = lastOutreach;
  if (!o) return;
  openDrawerSource = "mail";
  if (!refresh) drawerDirty = false;
  const m = mailRowModel(o);
  const body = openSideDrawer({
    title: `${plogoHtml("mail")}<span>Рассылка по почте</span>`,
    sub: statusLineHtml(m),
    body: `<div id="own-mail-card" data-ui="home.pipeline">${pipelineCardHtml(o)}</div>`,
    foot: `<button type="button" class="btn btn-primary" data-drawer-action="outreach">Открыть рассылку</button>`,
  });
  animateCounts(body);
  bindPipelineCard(body, o);
  body.querySelectorAll("[data-own-go]").forEach((b) =>
    b.addEventListener("click", () => {
      closePlatformDrawer();
      switchTab(b.dataset.ownGo);
    })
  );
  body.querySelectorAll("[data-own-settings]").forEach((b) =>
    b.addEventListener("click", () => {
      closePlatformDrawer();
      gotoSettings(b.dataset.ownSettings);
    })
  );
}

function openPlatform(key) {
  if (key === "telegram") openTelegramDrawer();
  else if (key === "mail") openMailDrawer();
  else openSourceDrawer(key);
}

// «Компании и рассылка» — весь путь в одной карточке: собрали → в Базе →
// отправка. Крупно — одна кнопка следующего шага, остальное мелко и в
// «Подробнее». Действия — здесь же или в боковой панели, без перехода.
function pipelineNext(o) {
  const ms = o.mail_status;
  const cur = o.current;
  const p = o.plan;
  const todayText = (n) =>
    n < o.available
      ? `Сегодня отправлю ${n}, остальные — в следующие дни${p.warmup && p.limit < p.daily_limit ? ": первые дни пишу меньше, чтобы Gmail не заблокировал почту" : ""}.`
      : "";
  if (!o.base_total) return { kind: "empty" };
  if (ms?.state === "stopped") {
    return { tone: "alert", status: ms.text, action: ms.goto.startsWith("settings-")
      ? { label: "Что делать", attrs: `data-own-settings="${ms.goto}"`, primary: true }
      : { label: "Проверить адреса в Базе", attrs: `data-own-go="${ms.goto}"`, primary: true } };
  }
  // Автоматический режим: первую порцию вы уже смотрели — дальше бот сам
  // пишет и отправляет, поэтому кнопок «Написать»/«Отправить» нет.
  const autoOn = o.auto_send && cur?.reviewed;
  const autoOff = { label: "Выключить автоматический режим", attrs: `data-pipeline="auto-off"` };
  if (ms?.state === "active" || ms?.state === "waiting") {
    return { tone: ms.state, status: ms.text,
      small: { label: "Остановить рассылку", attrs: `data-pipeline="stop" data-id="${ms.campaign}"` },
      extra: autoOn ? autoOff : null };
  }
  if (autoOn && cur?.progress?.kind === "prepare") {
    const pr = cur.progress;
    return { tone: "active", status: `Пишу сегодняшнюю порцию: ${pr.done} из ${pr.total} — отправлю сам в рабочее время`,
      progress: pr.done / Math.max(1, pr.total), small: autoOff };
  }
  if (autoOn && cur?.pending && !cur.draft) {
    const today = new Date().toLocaleDateString("sv-SE"); // ГГГГ-ММ-ДД по вашему поясу, как batch_day
    const when = cur.batch_day === today ? "завтра" : "в ближайшие минуты";
    return { tone: "waiting",
      status: `Автоматический режим: каждый день бот сам пишет и отправляет порцию. Следующая — ${when}; в очереди ${cur.pending.toLocaleString("ru-RU")}.`,
      small: autoOff };
  }
  if (cur?.progress?.kind === "prepare") {
    const pr = cur.progress;
    return { tone: "active", status: `Пишу письма: ${pr.done} из ${pr.total}`, progress: pr.done / Math.max(1, pr.total),
      small: { label: "Остановить", attrs: `data-pipeline="stop" data-id="${cur.id}"` } };
  }
  if (cur?.draft) {
    if (!o.email_connected) {
      return { status: `Готово ${cur.draft} ${plural(cur.draft, "письмо", "письма", "писем")} — осталось подключить Gmail, чтобы отправить.`,
        action: { label: "Подключить Gmail", attrs: `data-own-settings="settings-outreach"`, primary: true } };
    }
    return { status: `Готово ${cur.draft} ${plural(cur.draft, "письмо", "письма", "писем")}. Просмотрите — можно поправить или убрать — и отправьте.${o.auto_send && !cur.reviewed ? " Это первая порция: дальше в автоматическом режиме бот будет писать и отправлять сам." : ""}`,
      action: { label: `Просмотреть и отправить (${cur.draft})`, attrs: `data-pipeline="review"`, primary: true } };
  }
  if (cur?.pending) {
    const n = Math.min(cur.pending, p.limit);
    return { status: `В очереди рассылки ${cur.pending} ${plural(cur.pending, "компания", "компании", "компаний")}. ${todayText(n)}${o.auto_send ? " Автоматический режим включён: первую порцию проверьте сами, дальше бот будет писать и отправлять сам." : ""}`,
      action: { label: `Написать ${n} ${plural(n, "письмо", "письма", "писем")}`, attrs: `data-pipeline="prepare" data-id="${cur.id}"`, primary: true } };
  }
  if (o.available) {
    const n = Math.min(o.available, p.limit);
    return { status: `Можно написать ${o.available.toLocaleString("ru-RU")} ${plural(o.available, "компании", "компаниям", "компаниям")}. ${todayText(n)}${o.auto_send ? " Автоматический режим включён: первую порцию проверьте сами, дальше бот будет писать и отправлять сам." : ""}`,
      action: { label: `Написать ${n} ${plural(n, "письмо", "письма", "писем")}`, attrs: `data-pipeline="create"`, primary: true } };
  }
  return { status: "Всем компаниям из Базы уже написали. Загрузите новый список — бот напишет и им.",
    action: { label: "Загрузить список", attrs: `data-pipeline="upload"`, primary: true } };
}

function pipelineCardHtml(o) {
  const next = pipelineNext(o);
  const a = o.added_week;
  const settingsBtn = `<button type="button" class="icon-btn" data-own-settings="settings-outreach" title="Настройки почты и защиты" aria-label="Настройки почты"><svg aria-hidden="true" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="2.2"/><path d="M8 1.8v1.6M8 12.6v1.6M1.8 8h1.6M12.6 8h1.6M3.6 3.6l1.1 1.1M11.3 11.3l1.1 1.1M3.6 12.4l1.1-1.1M11.3 4.7l1.1-1.1"/></svg></button>`;
  if (next.kind === "empty") {
    return `<div class="source-card own-card pipeline-card">
      <h3>Компании и рассылка ${settingsBtn}</h3>
      <ol class="pipeline-intro small">
        <li>Соберите компании — загрузите список или включите сбор с сайтов компаний.</li>
        <li>Бот напишет каждой компании личное письмо по вашему резюме.</li>
        <li>Письма уйдут с вашей почты Gmail — по одному, в рабочее время.</li>
      </ol>
      <div class="pipeline-actions">
        <button type="button" class="btn btn-primary" data-pipeline="upload">Загрузить список компаний</button>
        <button type="button" class="btn btn-ghost btn-small" data-pipeline="prompt">Где взять список?</button>
      </div>
      <label class="checkbox-row small"><input type="checkbox" class="switch" id="pipeline-sites" ${o.sites_enabled ? "checked" : ""} /> Собирать компании с сайтов компаний сам</label>
    </div>`;
  }
  const btn = (x) => x ? `<button type="button" class="btn ${x.primary ? "btn-primary" : "btn-ghost btn-small"}" ${x.attrs}>${escapeHtml(x.label)}</button>` : "";
  const ms = o.mail_status;
  return `<div class="source-card own-card pipeline-card${next.tone === "alert" ? " is-alert" : ""}">
    <h3><span class="dot ${next.tone === "alert" ? "error" : next.tone === "active" ? "ok running" : next.tone === "waiting" ? "never_run" : "ok"}"></span> Компании и рассылка
      ${o.auto_send ? `<span class="auto-badge" title="Бот сам пишет и отправляет новые порции писем">авто</span>` : ""}${settingsBtn}</h3>
    <p class="pipeline-status${next.tone === "alert" ? " err-text" : ""}">${escapeHtml(next.status)}</p>
    ${next.progress !== undefined ? `<div class="progress"><div style="width:${Math.round(next.progress * 100)}%"></div></div>` : ""}
    <div class="pipeline-actions">${btn(next.action)}${btn(next.small)}${btn(next.extra)}</div>
    <div class="pipeline-steps">
      <div><span class="muted small">Новых за неделю</span><b data-count="pl-new">${o.added_week_total}</b></div>
      <div><span class="muted small">Можно написать</span><b data-count="pl-available">${o.available}</b></div>
      <div><span class="muted small">Отправлено сегодня</span><b><span data-count="pl-today">${o.plan.sent_today}</span> <span class="muted small">из ${o.plan.limit}</span></b></div>
    </div>
    <label class="checkbox-row small"><input type="checkbox" class="switch" id="pipeline-sites" ${o.sites_enabled ? "checked" : ""} /> Собирать компании с сайтов компаний сам</label>
    <details class="pipeline-more small">
      <summary>Подробнее</summary>
      <div class="row"><span>Откуда за неделю</span><span>сайты +${a.sites} · Telegram +${a.telegram} · файлы +${a.file}</span></div>
      <div class="row"><span>Всего в Базе</span><span>${o.base_total.toLocaleString("ru-RU")}</span></div>
      ${ms?.last ? `<div class="row"><span>Последнее письмо</span><span>${fmtDay(ms.last.at)} → ${escapeHtml(ms.last.company)}</span></div>` : ""}
      <div class="row"><span>Всего отправлено</span><span>${o.sent} · ответили ${o.replied} · возвраты ${o.bounced}${o.followups ? ` · напоминаний готово ${o.followups}` : ""}</span></div>
      ${o.days_needed > 1 ? `<div class="row"><span>На всю Базу</span><span>≈ ${o.days_needed} ${plural(o.days_needed, "день", "дня", "дней")} отправки</span></div>` : ""}
      <div class="pipeline-links">
        <button type="button" class="btn btn-ghost btn-small" data-pipeline="upload">Загрузить список</button>
        <button type="button" class="btn btn-ghost btn-small" data-own-go="contacts">Открыть Базу</button>
        <button type="button" class="btn btn-ghost btn-small" data-own-go="outreach">История рассылок</button>
        <button type="button" class="btn btn-ghost btn-small" data-own-settings="settings-direct">Сайты компаний: настроить</button>
      </div>
    </details>
  </div>`;
}

function bindPipelineCard(el, o) {
  el.querySelector("#pipeline-sites")?.addEventListener("change", async (e) => {
    e.target.disabled = true;
    try {
      await api("/api/settings", { method: "POST", body: JSON.stringify({ source: "direct", schedule_enabled: e.target.checked }) });
      showToast(e.target.checked ? "Сбор с сайтов компаний включён" : "Сбор с сайтов компаний выключен", "success");
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
    refreshOwnChannels();
  });
  el.querySelectorAll("[data-pipeline]").forEach((b) =>
    b.addEventListener("click", async () => {
      const action = b.dataset.pipeline;
      if (action === "upload") {
        importToDrawer = true;
        document.getElementById("import-file").click();
        return;
      }
      if (action === "prompt") return openPromptDrawer();
      if (action === "review") return openReviewDrawer();
      if (action === "auto-off") {
        b.disabled = true;
        try {
          await api("/api/settings/outreach", { method: "POST", body: JSON.stringify({ auto_send: false }) });
          showToast("Автоматический режим выключен — каждую новую порцию бот пришлёт вам на просмотр", "success");
        } catch (err) {
          showToast(err.message.replace(/^\d+: /, ""), "error");
        }
        return refreshOwnChannels();
      }
      if (action === "stop" && !(await showConfirm("Остановить рассылку? Неотправленные письма останутся — продолжить можно в любой момент."))) return;
      b.disabled = true;
      try {
        if (action === "create") {
          const c = await api("/api/campaigns", { method: "POST", body: JSON.stringify({ source: "" }) });
          await api(`/api/campaigns/${c.id}/prepare`, { method: "POST", body: JSON.stringify({ resume: "" }) });
          showToast("Пишу письма — это пара минут, можно заниматься другим", "success");
        } else {
          await api(`/api/campaigns/${b.dataset.id}/${action}`, { method: "POST", body: JSON.stringify({ resume: "" }) });
        }
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error");
      }
      refreshOwnChannels();
    })
  );
}

// Боковая панель поверх Главной — та же, что у окна площадки.
// Шторка справа — одна на всё приложение: площадка, письма рассылки,
// промт для ИИ. Старый вызов openSideDrawer(title, html) тоже работает.
function openSideDrawer(titleOrOpts, bodyHtml) {
  const o = typeof titleOrOpts === "object" && titleOrOpts
    ? titleOrOpts
    : { title: escapeHtml(titleOrOpts), body: bodyHtml };
  if (typeof titleOrOpts !== "object") {
    openDrawerSource = null;
    drawerDirty = false;
  }
  document.getElementById("platform-drawer-title").innerHTML = o.title;
  const sub = document.getElementById("platform-drawer-sub");
  sub.innerHTML = o.sub || "";
  sub.hidden = !o.sub;
  const body = document.getElementById("platform-drawer-body");
  body.innerHTML = o.body;
  const foot = document.getElementById("platform-drawer-foot");
  foot.innerHTML = o.foot || "";
  foot.hidden = !o.foot;
  const overlay = document.getElementById("platform-drawer-overlay");
  const wasClosing = overlay.classList.contains("is-closing");
  clearTimeout(drawerCloseTimer);
  overlay.classList.remove("is-closing");
  const wasOpen = overlay.style.display !== "none" && !wasClosing;
  overlay.style.display = "flex";
  if (!wasOpen) trapFocus(document.getElementById("platform-drawer"));
  return body;
}

function openPromptDrawer() {
  const body = openSideDrawer("Где взять список компаний", `
    <p class="small">Откройте ChatGPT в режиме <b>Deep Research</b> или Claude с <b>Research</b> — нужен поиск в интернете: обычный чат придумывает адреса. Вставьте промт, поменяйте то, что в [скобках], попросите сохранить таблицу в Excel или CSV и загрузите файл.</p>
    <textarea id="drawer-prompt" rows="16" readonly aria-label="Промт для ИИ">${escapeHtml(document.getElementById("ai-prompt").value)}</textarea>
    <div class="step-actions">
      <button type="button" class="btn btn-secondary btn-small" id="drawer-prompt-copy">Скопировать промт</button>
      <button type="button" class="btn btn-primary btn-small" id="drawer-upload">Загрузить файл</button>
    </div>`);
  body.querySelector("#drawer-prompt-copy").addEventListener("click", (e) => {
    copyToClipboard(body.querySelector("#drawer-prompt").value, e.currentTarget, body.querySelector("#drawer-prompt"));
  });
  body.querySelector("#drawer-upload").addEventListener("click", () => {
    importToDrawer = true;
    document.getElementById("import-file").click();
  });
}

// Просмотр писем перед отправкой: список компаний с первой строкой,
// полный текст — по клику; «Начать отправку» видна сразу, листать не надо.
function openReviewDrawer() {
  const cur = lastOutreach?.current;
  if (!cur) return;
  const resumes = lastTelegramWatch?.resumes || [];
  const body = openSideDrawer(`Письма: ${cur.draft}`, `
    <div class="review-head">
      <label class="muted small">Резюме во вложении
        <select id="review-resume" aria-label="Резюме во вложении">
          <option value="">основное резюме</option>
          ${resumes.map((r) => `<option value="${escapeHtml(r.name)}">${escapeHtml(r.name)}</option>`).join("")}
        </select>
      </label>
      <button type="button" class="btn btn-primary" id="review-send">Начать отправку (${cur.draft})</button>
      <label class="checkbox-row small"><input type="checkbox" class="switch" id="review-auto" ${lastOutreach.auto_send ? "checked" : ""} />
        Дальше бот отправляет новые порции сам, без моего просмотра</label>
      <p class="muted small">${escapeHtml(mailPlanText(lastOutreach.plan))}. По одному, со случайными паузами — как человек; что не уйдёт сегодня, отправлю в следующие дни сам.</p>
    </div>
    <p class="small review-about">Письма написаны по вашему резюме: обращение по имени, почему именно эта компания, 2–3 ваших достижения, 150–180 слов. Резюме — во вложении. Любое письмо можно поправить или убрать.</p>
    <div class="letters">${cur.drafts
      .map(
        (i) => `<details class="letter">
          <summary><strong>${escapeHtml(i.company)}</strong> <span class="muted small">${escapeHtml(i.email)}</span>
            <div class="muted small letter-first">${escapeHtml(truncate((i.text || "").split("\n").find((l) => l.trim()) || "", 110))}</div></summary>
          <div class="muted small">Тема: ${escapeHtml(i.subject)}</div>
          <textarea rows="9" data-letter="${escapeHtml(i.code)}" aria-label="Текст письма">${escapeHtml(i.text)}</textarea>
          <div class="step-actions"><button type="button" class="btn btn-ghost btn-small" data-letter-skip="${escapeHtml(i.code)}">Убрать из рассылки</button></div>
        </details>`
      )
      .join("")}</div>`);
  body.querySelectorAll("[data-letter]").forEach((ta) =>
    ta.addEventListener("change", async () => {
      try {
        await api(`/api/hr-drafts/${ta.dataset.letter}`, { method: "PUT", body: JSON.stringify({ text: ta.value }) });
        showToast("Письмо сохранено");
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error");
      }
    })
  );
  body.querySelectorAll("[data-letter-skip]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      await api(`/api/hr-drafts/${btn.dataset.letterSkip}/skip`, { method: "POST" });
      btn.closest(".letter").remove();
      refreshOwnChannels();
    })
  );
  body.querySelector("#review-auto").addEventListener("change", async (e) => {
    try {
      await api("/api/settings/outreach", { method: "POST", body: JSON.stringify({ auto_send: e.target.checked }) });
      showToast(e.target.checked
        ? "Новые порции бот будет писать и отправлять сам — в рабочее время, с защитой почты"
        : "Каждую новую порцию бот пришлёт вам на просмотр", "success");
    } catch (err) {
      e.target.checked = !e.target.checked;
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
  });
  body.querySelector("#review-send").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try {
      await api(`/api/campaigns/${cur.id}/send`, {
        method: "POST",
        body: JSON.stringify({ resume: body.querySelector("#review-resume").value }),
      });
      closePlatformDrawer();
      showToast("Рассылка включена — письма пойдут по одному в рабочее время", "success");
    } catch (err) {
      e.target.disabled = false;
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
    refreshOwnChannels();
  });
}

// Кнопка действия у пункта «Нужно ваше решение» — по id пункта с сервера.
const TODO_ACTIONS = {
  campaign_drafts: "Просмотреть",
  drafts: "Ответить",
  replies: "Открыть",
  interviews: "Подготовиться",
  paused: "Исправить",
  errors: "Открыть",
  tg_login: "Войти",
  watch_conn: "Журнал",
  gateway_silent: "Проверить",
  low_disk: "Подробнее",
  linkedin_forms: "Посмотреть",
  hh_reminders: "Напомнить",
  tg_pending: "Открыть",
  mail_stopped: "Исправить",
};

// Пункты, о которых сервер в /api/todo не знает, но они видны из
// /api/status и сводки рассылки: очередь сообщений в Telegram,
// молчащие работодатели на HH, сбои площадок, остановленная рассылка.
function todoExtras(status) {
  const extra = [];
  if (!status) return extra;
  if (status.pending_telegram_sends) {
    const n = status.pending_telegram_sends;
    extra.push({ id: "tg_pending", count: n, view: "telegram", text: `${plural(n, "сообщение ждёт", "сообщения ждут", "сообщений ждут")} отправки в Telegram — уйдут в рабочие часы` });
  }
  if (status.hh_reminders_due) {
    const n = status.hh_reminders_due;
    extra.push({ id: "hh_reminders", count: n, view: "replies", text: `${plural(n, "отклик", "отклика", "откликов")} на HH давно без ответа — можно напомнить о себе` });
  }
  const broken = status.sources.filter((s) => s.schedule_enabled && s.status === "error");
  if (broken.length) {
    extra.push({ id: "errors", count: broken.length, view: "overview", source: broken[0].name, text: `${plural(broken.length, "площадка", "площадки", "площадок")} с ошибкой: ${broken.map((s) => sourceLabel(s.name)).join(", ")}` });
  }
  const ms = lastOutreach?.mail_status;
  if (ms?.state === "stopped") {
    extra.push({ id: "mail_stopped", count: "!", view: ms.goto || "outreach", text: `Рассылка остановлена: ${stripLeadingEmoji(ms.text)}` });
  }
  return extra;
}

async function renderTodo(todo, status = lastStatus) {
  const el = document.getElementById("todo-panel");
  if (!todo) {
    try {
      todo = await api("/api/todo");
    } catch (e) {
      return false; // сеть моргнула — не прячем дашборд из-за этого
    }
  }
  lastTodoBadges = todo.badges || {};
  applySubnavBadges();
  const setup = todo.setup || [];
  const missing = setup.filter((c) => !c.ok);
  const missingRequired = missing.filter((c) => c.required);
  const done = setup.length - missing.length;
  const stepsHtml = (next) => `<ol class="setup-steps">${setup
    .map(
      (c, i) => `<li class="${c.ok ? "is-done" : c === next ? "is-next" : ""}">
        <button type="button" class="setup-step" data-setup-goto="${escapeHtml(c.goto)}" ${c.goto && !c.ok ? "" : "disabled"}>
          <span class="setup-step-mark">${c.ok ? "✓" : i + 1}</span>${escapeHtml(c.label)}${c.required ? "" : ` <span class="muted small">по желанию</span>`}
        </button></li>`
    )
    .join("")}</ol>`;
  // Три состояния: 1) не настроено главное (резюме, ключ ИИ, площадка) —
  // чек-лист для новичка вместо подсказки-тура; 2) главное есть,
  // дополнительное нет — одна тихая строка, её можно раскрыть или скрыть ✕;
  // 3) всё есть — ничего. Сломалось потом — отдельным пунктом ниже.
  let setupHtml = "";
  const optionalKey = missing.map((c) => c.id).join(",");
  let dismissed = "";
  try {
    dismissed = localStorage.getItem("cj-setup-dismissed") || "";
  } catch (e) {}
  if (missingRequired.length) {
    const next = missingRequired[0];
    setupHtml = `<div class="setup" data-ui="home.setup">
        <div class="setup-head">
          <h3>Готовность: ${done} из ${setup.length}</h3>
          <div class="progress setup-progress"><div style="width:${Math.round((100 * done) / setup.length)}%"></div></div>
        </div>
        <div class="setup-next">
          <div><span class="muted small">Следующий шаг</span><div><b>${escapeHtml(next.label)}</b> — ${escapeHtml(next.hint)}</div></div>
          ${next.goto ? `<button type="button" class="btn btn-primary" data-setup-goto="${escapeHtml(next.goto)}">Сделать</button>` : ""}
        </div>
        ${stepsHtml(next)}
      </div>`;
  } else if (missing.length && dismissed !== optionalKey) {
    setupHtml = `<details class="setup-slim">
        <summary>Всё главное настроено · можно ещё подключить: ${missing.map((c) => escapeHtml(c.label)).join(", ")}
          <button type="button" class="icon-btn setup-dismiss" title="Скрыть — всё есть в Настройки → Подключения" aria-label="Скрыть">✕</button></summary>
        ${stepsHtml(null)}
      </details>`;
  }
  const items = [...todo.items, ...todoExtras(status)];
  const badge = document.getElementById("overview-error-badge");
  if (items.length) {
    badge.textContent = String(items.length);
    badge.style.display = "";
  } else {
    badge.style.display = "none";
  }
  const head = `<div class="card-head"><h3>Нужно ваше решение</h3><span class="muted small">всё остальное бот делает сам</span></div>`;
  if (!setHtmlIfChanged(el, `${setupHtml}${head}${items.length
    ? `<div class="todo-list">${items
        .map(
          (i, n) => `<div class="todo-row stagger-item" style="animation-delay:${staggerDelay(n, 40)}">
            <span class="todo-count mono">${escapeHtml(String(i.count))}</span>
            <span class="todo-text">${escapeHtml(stripLeadingEmoji(i.text))}</span>
            <button type="button" class="btn btn-small" data-todo-view="${escapeHtml(i.view)}" data-todo-id="${escapeHtml(i.id || "")}" data-todo-source="${escapeHtml(i.source || "")}">${TODO_ACTIONS[i.id] || "Открыть"}</button>
          </div>`
        )
        .join("")}</div>`
    : `<div class="todo-calm"><span class="dot ok"></span>Сейчас ничего не ждёт вашего решения — бот справляется сам.</div>`}`)) return !!missingRequired.length;
  el.querySelector(".setup-dismiss")?.addEventListener("click", (e) => {
    e.preventDefault(); // не раскрывать <details>
    try {
      // Запоминаем именно этот набор: появится новое — строка вернётся.
      localStorage.setItem("cj-setup-dismissed", optionalKey);
    } catch (err) {}
    el.querySelector(".setup-slim")?.remove();
  });
  el.querySelectorAll("[data-setup-goto]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const goto = btn.dataset.setupGoto;
      if (goto.startsWith("settings-")) gotoSettings(goto);
      else if (goto) switchTab(goto);
    })
  );
  el.querySelectorAll("[data-todo-view]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.dataset.todoView;
      if (btn.dataset.todoSource) openPlatform(btn.dataset.todoSource);
      else if (btn.dataset.todoId === "paused") {
        const paused = (lastStatus?.sources || []).find((s) => s.paused || s.status === "blocked");
        if (paused) openPlatform(paused.name);
      } else if (view.startsWith("settings-")) gotoSettings(view);
      else switchTab(view);
    });
  });
  return !!missingRequired.length;
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
function normalizeTelegramChannel(raw) {
  let value = String(raw || "").trim();
  const lower = value.toLowerCase();
  for (const prefix of ["https://t.me/", "http://t.me/", "t.me/", "@"]) {
    if (lower.startsWith(prefix)) {
      value = value.slice(prefix.length);
      break;
    }
  }
  return value.split("/")[0].trim();
}

function telegramChannelsFromText(raw) {
  const seen = new Set();
  return String(raw || "")
    .split(/\r?\n/)
    .map(normalizeTelegramChannel)
    .filter((channel) => /^[A-Za-z0-9_]{5,32}$/.test(channel))
    .filter((channel) => {
      const key = channel.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function setTelegramChannels(channels) {
  const input = document.getElementById("tg-channels");
  input.value = telegramChannelsFromText((channels || []).join("\n")).join("\n");
  renderTelegramChannelList();
}

function renderTelegramChannelList() {
  const list = document.getElementById("tg-channel-list");
  if (!list) return;
  const channels = telegramChannelsFromText(
    document.getElementById("tg-channels").value
  );
  list.replaceChildren();
  if (!channels.length) {
    const empty = document.createElement("p");
    empty.className = "muted small tg-channel-empty";
    empty.textContent = "Пока нет каналов. Вставьте ссылку из Telegram.";
    list.append(empty);
    return;
  }
  channels.forEach((channel) => {
    const item = document.createElement("div");
    item.className = "tg-channel-card";
    item.setAttribute("role", "listitem");
    const link = document.createElement("a");
    link.href = `https://t.me/${encodeURIComponent(channel)}`;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = `@${channel}`;
    link.className = "tg-channel-link";
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "tg-channel-remove";
    remove.setAttribute("aria-label", `Удалить @${channel}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      setTelegramChannels(channels.filter((item) => item !== channel));
      markTelegramChannelsEdited();
      document.getElementById("tg-channel-editor-status").textContent = `Удалён @${channel}.`;
      requestTelegramSettingsSave();
    });
    item.append(link, remove);
    list.append(item);
  });
}

let telegramChannelsSavePending = false;
let telegramChannelsSavePromise = null;
let telegramChannelsChangedBeforeLoad = false;
let telegramChannelsRevision = 0;
let telegramSettingsSaveQueue = Promise.resolve();

function serializeTelegramSettingsSave(save) {
  const request = telegramSettingsSaveQueue.then(save, save);
  telegramSettingsSaveQueue = request.catch(() => {});
  return request;
}

function markTelegramChannelsEdited() {
  telegramChannelsRevision += 1;
}

function requestTelegramSettingsSave() {
  const pane = document.getElementById("tg-rules-panel");
  if (pane.dataset.loaded !== "1") {
    telegramChannelsChangedBeforeLoad = true;
    document.getElementById("tg-channel-editor-status").textContent =
      "Сохраню каналы после загрузки настроек…";
    return Promise.resolve();
  }
  telegramChannelsSavePending = true;
  if (!telegramChannelsSavePromise) {
    telegramChannelsSavePromise = (async () => {
      const status = document.getElementById("tg-channel-editor-status");
      while (telegramChannelsSavePending) {
        telegramChannelsSavePending = false;
        const channels = telegramChannelsFromText(
          document.getElementById("tg-channels").value
        );
        status.textContent = "Сохранение каналов…";
        try {
          const saved = await serializeTelegramSettingsSave(() =>
            api("/api/settings/telegram", {
              method: "POST",
              body: JSON.stringify({ channels }),
            })
          );
          if (telegramChannelsSavePending) continue;
          const savedChannels = saved.channels || [];
          setTelegramChannels(savedChannels);
          status.textContent = `Сохранено: ${savedChannels.length} каналов.`;
        } catch (error) {
          status.textContent = `Не удалось сохранить каналы: ${error.message}`;
        }
      }
      telegramChannelsSavePromise = null;
      if (telegramChannelsSavePending) requestTelegramSettingsSave();
    })();
  }
  return telegramChannelsSavePromise;
}

function addTelegramChannels(raw) {
  const status = document.getElementById("tg-channel-editor-status");
  const candidates = String(raw || "")
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
  const invalid = candidates.filter(
    (value) => !/^[A-Za-z0-9_]{5,32}$/.test(normalizeTelegramChannel(value))
  );
  if (invalid.length) {
    status.textContent = "Не удалось распознать ссылку. Добавьте публичный username или ссылку t.me/username.";
    return false;
  }
  const previous = telegramChannelsFromText(
    document.getElementById("tg-channels").value
  );
  const next = telegramChannelsFromText([...previous, ...candidates].join("\n"));
  const added = next.length - previous.length;
  setTelegramChannels(next);
  status.textContent = added
    ? `Добавлено: ${added}.`
    : "Этот канал уже есть в списке.";
  if (added) {
    markTelegramChannelsEdited();
    requestTelegramSettingsSave();
  }
  return true;
}

function initTelegramChannelEditor() {
  const input = document.getElementById("tg-channel-input");
  if (!input || input.dataset.bound) return;
  input.dataset.bound = "1";
  const add = () => {
    if (addTelegramChannels(input.value)) input.value = "";
    input.focus();
  };
  document.getElementById("tg-channel-add").addEventListener("click", add);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      add();
    }
  });
  document.getElementById("tg-channel-paste").addEventListener("click", async () => {
    const status = document.getElementById("tg-channel-editor-status");
    try {
      const copied = await navigator.clipboard.readText();
      if (addTelegramChannels(copied)) input.value = "";
      input.focus();
    } catch (_) {
      status.textContent = "Браузер не дал доступ к буферу. Вставьте ссылку в поле через Cmd/Ctrl+V.";
      input.focus();
    }
  });
  document
    .getElementById("tg-channels")
    .addEventListener("input", () => {
      markTelegramChannelsEdited();
      if (document.getElementById("tg-rules-panel").dataset.loaded !== "1") {
        telegramChannelsChangedBeforeLoad = true;
      }
      renderTelegramChannelList();
    });
  document
    .getElementById("tg-channels")
    .addEventListener("change", requestTelegramSettingsSave);
  renderTelegramChannelList();
}

function fillTelegramRules(settings, requestedChannelsRevision = telegramChannelsRevision) {
  const localChannels = telegramChannelsChangedBeforeLoad
    ? telegramChannelsFromText(
        document.getElementById("tg-channels").value
      )
    : [];
  const preserveLocalChannels = requestedChannelsRevision < telegramChannelsRevision;
  const channels = telegramChannelsChangedBeforeLoad
    ? telegramChannelsFromText([...(settings.channels || []), ...localChannels].join("\n"))
    : preserveLocalChannels
      ? telegramChannelsFromText(
          document.getElementById("tg-channels").value
        )
      : settings.channels || [];
  setTelegramChannels(channels);
  document.getElementById("tg-max-age").value = settings.max_post_age_days ?? "";
  document.getElementById("tg-daily-limit").value = settings.daily_message_limit ?? "";
  document.getElementById("tg-auto-message").checked = !!settings.auto_message;
  document.getElementById("tg-hours-start").value = settings.active_hours_start ?? "";
  document.getElementById("tg-hours-end").value = settings.active_hours_end ?? "";
  document.getElementById("tg-rules-panel").dataset.loaded = "1";
  document.getElementById("tg-source-auto").dataset.loaded = "1";
  if (telegramChannelsChangedBeforeLoad) {
    telegramChannelsChangedBeforeLoad = false;
    requestTelegramSettingsSave();
  }
}

async function loadTelegramWatch() {
  const channelsRevision = telegramChannelsRevision;
  api("/api/settings/telegram")
    .then((settings) => fillTelegramRules(settings, channelsRevision))
    .catch((error) => {
      if (telegramChannelsChangedBeforeLoad) {
        document.getElementById("tg-channel-editor-status").textContent =
          `Не удалось загрузить настройки каналов: ${error.message}`;
      }
    });
  const w = await api("/api/settings/telegram-watch");
  // Строка статуса во вкладке «Общение → Telegram».
  const line = document.getElementById("tg-quick-line-status");
  if (line) {
    const state = w.running ? "on" : w.enabled ? "wait" : "off";
    line.className = `parser-state is-${state}`;
    line.innerHTML = `<span class="dot ${state === "on" ? "ok" : state === "wait" ? "never_run" : "idle"}"></span>${escapeHtml({
      on: `Telegram-парсер слушает ${w.channels} ${plural(w.channels, "канал", "канала", "каналов")}`,
      wait: w.daemon_running ? "Telegram-парсер подключается…" : "Telegram-парсер заработает после «Запустить»",
      off: "Telegram-парсер выключен — включается в «Правилах парсера»",
    }[state])}`;
    document.getElementById("parser-numbers").innerHTML = [
      [w.channels, w.running ? "каналов слушаю" : "каналов в списке"],
      [w.matched, "вакансий найдено с запуска"],
      [w.contacts_collected, "контактов HR в базе"],
    ]
      .map(([n, t]) => `<span><b class="mono">${n}</b> ${t}</span>`)
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
        : "Включено — заработает, когда нажмёте «Запустить бота»"
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
  document.getElementById("tgq-builtin-stop").textContent = (w.builtin_stop_words || [])
    .map((s) => `«${s}»`)
    .join(", ");
  const greeting = document.getElementById("tgq-greeting");
  greeting.value = w.greeting;
  updateGreetingPreview();
  document.getElementById("tgq-auto-message").checked = w.auto_message;
  document.getElementById("tgq-preview").checked = !!w.preview_before_send;
  document.getElementById("tgq-night").checked = !!w.night_to_morning;
  document.getElementById("tgq-smart-greeting").checked = w.smart_greeting;
  document.getElementById("tgq-llm-vacancy-filter").checked =
    w.llm_vacancy_filter;
  document.getElementById("tgq-delay-min").value = Math.round((w.message_delay_min_seconds || 0) / 60);
  document.getElementById("tgq-delay-max").value = Math.round((w.message_delay_max_seconds || 0) / 60);
  document.getElementById("tgq-hours-start").value = w.active_hours_start ?? "";
  document.getElementById("tgq-hours-end").value = w.active_hours_end ?? "";
  document.getElementById("tgq-daily-limit").value = w.daily_message_limit;
  document.getElementById("tgq-backfill-days").value = w.channel_backfill_days;
  document.getElementById("tgq-pending-status").textContent = w.pending_sends
    ? `В очереди на отправку: ${w.pending_sends}`
    : "Очередь пуста — нет отложенных сообщений";
  renderTelegramResumes(w.resumes);
  document.getElementById("tgq-resume-route").innerHTML = `<b>Автовыбор при отклике:</b> русская вакансия → ${w.resume_route_ru ? escapeHtml(w.resume_route_ru) : "не найдено"}, зарубежная → ${w.resume_route_en ? escapeHtml(w.resume_route_en) : "не найдено"}`;
  document.getElementById("tgq-bot-state").innerHTML = w.bot_connected
    ? "Приходят в ваш бот в Telegram — с кнопками быстрого ответа."
    : `Бот уведомлений не подключён — <a href="#" data-goto-settings="settings-notifications">подключить</a> (1 минута), иначе кнопок не будет.`;
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

let resumeUploadBusy = false;
let resumeUploadExtraNames = null;

function setResumeUploadStatus(message = "", tone = "") {
  const status = document.getElementById("tgq-resume-status");
  if (!status) return;
  status.textContent = message;
  status.dataset.tone = tone;
}

function setResumeUploadBusy(busy) {
  resumeUploadBusy = busy;
  const table = document.getElementById("resume-table");
  if (table) {
    table.setAttribute("aria-busy", String(busy));
  table.querySelectorAll("button").forEach((button) => { button.disabled = busy; });
  }
  ["tgq-resume-add", "resume-dropzone-pick"].forEach((id) => {
    const button = document.getElementById(id);
    if (button) button.disabled = busy;
  });
  const dropzone = document.getElementById("resume-dropzone");
  if (dropzone) {
    dropzone.classList.toggle("is-uploading", busy);
    dropzone.setAttribute("aria-busy", String(busy));
  }
}

function validateResumePdf(file) {
  if (!file || !/\.pdf$/i.test(file.name)) {
    throw new Error("Поддерживаются только файлы PDF.");
  }
  if (!file.size) throw new Error("Файл пустой. Выберите другое резюме.");
}

function storedTelegramResumeName(filename) {
  const stem = filename.replace(/\.pdf$/i, "").replace(/[^\p{L}\p{N}_-]+/gu, "_").replace(/^_+|_+$/g, "") || "resume";
  return `${stem.slice(0, 60)}.pdf`;
}

async function animateResumeRowExit(row) {
  if (REDUCE_MOTION || !row || typeof row.animate !== "function") return;
  const height = row.getBoundingClientRect().height;
  const style = getComputedStyle(row);
  const animation = row.animate([
    {
      height: `${height}px`,
      opacity: 1,
      transform: "translateX(0)",
      paddingTop: style.paddingTop,
      paddingBottom: style.paddingBottom,
      borderTopWidth: style.borderTopWidth,
    },
    {
      height: "0px",
      opacity: 0,
      transform: "translateX(-6px)",
      paddingTop: "0px",
      paddingBottom: "0px",
      borderTopWidth: "0px",
    },
  ], { duration: 170, easing: "cubic-bezier(0.23, 1, 0.32, 1)", fill: "forwards" });
  row.style.overflow = "hidden";
  await animation.finished.catch(() => {});
}

async function renderResumes({ animateKey = "" } = {}) {
  const el = document.getElementById("resume-table");
  const routingEl = document.getElementById("resume-routing");
  if (!el) return;
  let r;
  try {
    r = await api("/api/resumes");
  } catch (e) {
    renderRetryState(el, `Не удалось загрузить резюме: ${e.message}`, renderResumes);
    return;
  }
  resumeUploadExtraNames = new Set(r.extra.map((file) => file.name));
  const fileCell = (f, missing) =>
    f.exists
      ? `<span class="resume-file" title="${escapeHtml(f.name)}"><span class="pdf-badge" aria-hidden="true">PDF</span><span class="resume-name">${escapeHtml(f.name)}</span></span>
         <span class="muted small">${Math.max(1, Math.round(f.size / 1024))} КБ · ${fmtDay(f.updated_at)}</span>`
      : `<span class="${missing === "err" ? "err-text" : "muted"} small">${missing === "err" ? "не загружено" : "не загружено — берётся основное"}</span>`;
  const row = (title, where, file, action, kind = "") => `
    <div class="resume-row${animateKey === kind ? " resume-row-enter" : ""}" role="row" ${kind ? `data-resume-kind="${escapeHtml(kind)}"` : ""}>
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
      `<button type="button" class="btn btn-${r.primary.exists ? "ghost" : "primary"} btn-small" data-upload="primary" ${resumeUploadBusy ? "disabled" : ""}>${r.primary.exists ? "Заменить" : "Загрузить"}</button>`, "primary")}
    ${row("Для международных", "LinkedIn, Wellfound, Himalayas; письма на английском",
      fileCell(r.linkedin, "soft"),
      `<button type="button" class="btn btn-ghost btn-small" data-upload="linkedin" ${resumeUploadBusy ? "disabled" : ""}>${r.linkedin.exists ? "Заменить" : "Загрузить"}</button>`, "linkedin")}
    ${r.extra
      .map((f) =>
        row("Дополнительное", "своя кнопка «+ резюме» под вакансией в Telegram; можно выбрать в рассылке",
          fileCell(f),
          `<button type="button" class="btn btn-ghost btn-small" data-delete-extra="${escapeHtml(f.name)}" aria-label="Удалить ${escapeHtml(f.name)}">Удалить</button>`, `extra:${f.name}`)
      )
      .join("")}
    ${r.extra.length ? "" : `<div class="resume-row resume-empty"><div class="muted small">Дополнительных пока нет — например, резюме под другую роль. Кнопка «Добавить резюме» выше.</div></div>`}`;
  if (resumeUploadBusy) el.querySelectorAll("button").forEach((button) => { button.disabled = true; });
  el.querySelectorAll("[data-upload]").forEach((b) =>
    b.addEventListener("click", () => document.getElementById(`resume-upload-${b.dataset.upload}`).click())
  );
  el.querySelectorAll('[data-resume-kind="primary"], [data-resume-kind="linkedin"]').forEach((rowEl) => {
    rowEl.addEventListener("dragenter", (event) => {
      if (resumeUploadBusy || ![...event.dataTransfer.types].includes("Files")) return;
      event.preventDefault();
      rowEl.classList.add("is-drop-target");
    });
    rowEl.addEventListener("dragover", (event) => {
      if (resumeUploadBusy || ![...event.dataTransfer.types].includes("Files")) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
    });
    rowEl.addEventListener("dragleave", (event) => {
      if (!rowEl.contains(event.relatedTarget)) rowEl.classList.remove("is-drop-target");
    });
    rowEl.addEventListener("drop", (event) => {
      if (resumeUploadBusy) return;
      const file = event.dataTransfer.files?.[0];
      if (!file) return;
      event.preventDefault();
      rowEl.classList.remove("is-drop-target");
      uploadResumeFile(rowEl.dataset.resumeKind, file);
    });
  });
  el.querySelectorAll("[data-delete-extra]").forEach((b) =>
    b.addEventListener("click", async () => {
      await withButtonLoading(b, async () => {
        try {
          await api(`/api/telegram/resumes/${encodeURIComponent(b.dataset.deleteExtra)}`, { method: "DELETE" });
          await animateResumeRowExit(b.closest(".resume-row"));
          showToast("Дополнительное резюме удалено", "success");
          await renderResumes();
        } catch (err) {
          showToast(err.message.replace(/^\d+: /, ""), "error");
        }
      });
    })
  );

  if (!routingEl) return;
  const routeFields = [
    ["telegram_ru", "Telegram · русская вакансия"],
    ["telegram_en", "Telegram · зарубежная вакансия"],
    ["email_ru", "Рассылка · компания из России/СНГ"],
    ["email_en", "Рассылка · зарубежная компания"],
  ];
  const options = (selected) => (r.available || [])
    .map((item) => `<option value="${escapeHtml(item.value)}" ${item.value === selected ? "selected" : ""}>${escapeHtml(item.value)}</option>`)
    .join("");
  routingEl.innerHTML = `
    <div class="resume-routing-head">
      <div>
        <h4>Какое резюме прикладывать автоматически</h4>
        <p class="muted small">Бот определяет язык вакансии и страну компании, затем прикладывает выбранный здесь PDF.</p>
      </div>
      <span id="resume-routing-status" class="muted small" role="status"></span>
    </div>
    ${r.available?.length ? `<div class="resume-routing-grid">
      ${routeFields.map(([key, label]) => `<label class="limit-field">
        <span>${label}</span>
        <select data-resume-route="${key}" aria-label="${label}">${options(r.routing?.[key] || "")}</select>
      </label>`).join("")}
    </div>` : `<p class="muted small">Сначала загрузите хотя бы одно резюме в PDF.</p>`}`;

  routingEl.querySelectorAll("[data-resume-route]").forEach((select) => {
    select.addEventListener("change", async () => {
      const status = routingEl.querySelector("#resume-routing-status");
      const fields = [...routingEl.querySelectorAll("[data-resume-route]")];
      fields.forEach((field) => (field.disabled = true));
      status.textContent = "Сохраняю…";
      try {
        const payload = Object.fromEntries(fields.map((field) => [field.dataset.resumeRoute, field.value]));
        await api("/api/resumes/routing", { method: "PUT", body: JSON.stringify(payload) });
        status.textContent = "Сохранено";
      } catch (err) {
        status.textContent = err.message.replace(/^\d+: /, "");
        showToast(status.textContent, "error");
      } finally {
        fields.forEach((field) => (field.disabled = false));
      }
    });
  });
}

async function uploadResumeFile(kind, file) {
  if (resumeUploadBusy) {
    setResumeUploadStatus("Дождитесь завершения текущей загрузки.", "error");
    return false;
  }
  try {
    validateResumePdf(file);
    if (kind === "extra" && file.size > 20 * 1024 * 1024) {
      throw new Error("Дополнительное резюме должно быть не больше 20 МБ.");
    }
  } catch (error) {
    setResumeUploadStatus(error.message, "error");
    return false;
  }

  setResumeUploadBusy(true);
  const targetName = kind === "primary" ? "Основное резюме" : kind === "linkedin" ? "Международное резюме" : file.name;
  setResumeUploadStatus(`Загружается «${file.name}» в раздел «${targetName}»…`, "loading");
  try {
    const formData = new FormData();
    formData.append("file", file);
    if (kind === "extra") {
      if (!resumeUploadExtraNames) {
        const current = await api("/api/resumes");
        resumeUploadExtraNames = new Set(current.extra.map((item) => item.name));
      }
      const storedName = storedTelegramResumeName(file.name);
      if (resumeUploadExtraNames.has(storedName)) {
        throw new Error(`Резюме «${storedName}» уже есть. Переименуйте файл, чтобы не заменить его случайно.`);
      }
      const response = await fetch("/api/telegram/resumes", { method: "POST", body: formData });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Не удалось загрузить файл.");
      resumeUploadExtraNames = new Set((payload.resumes || []).map((item) => item.name));
      await renderResumes({ animateKey: `extra:${storedName}` });
      setResumeUploadStatus(`«${file.name}» добавлено.`, "success");
      return true;
    }

    await api(`/api/resume/upload?kind=${kind}`, { method: "POST", headers: {}, body: formData });
    await renderResumes({ animateKey: kind });
    if (kind === "primary") {
      setResumeUploadStatus("Файл загружен. Обновляю текст резюме для писем…", "loading");
      try {
        await api("/api/resume/refresh-plain-text", { method: "POST" });
        setResumeUploadStatus("Резюме обновлено — письма будут использовать новый файл.", "success");
      } catch (error) {
        setResumeUploadStatus(`Файл загружен, но ИИ не смог перечитать его: ${error.message.replace(/^\d+: /, "")}`, "error");
      }
    } else {
      setResumeUploadStatus("Международное резюме обновлено.", "success");
    }
    return true;
  } catch (error) {
    setResumeUploadStatus(`Не удалось загрузить «${file.name}»: ${error.message.replace(/^\d+: /, "")}`, "error");
    return false;
  } finally {
    setResumeUploadBusy(false);
  }
}

async function uploadTelegramResumes(files) {
  const validFiles = [];
  const rejected = [];
  for (const file of files) {
    try { validateResumePdf(file); validFiles.push(file); }
    catch (error) { rejected.push(`${file.name}: ${error.message}`); }
  }
  if (!validFiles.length) {
    if (rejected.length) setResumeUploadStatus(rejected.join(" "), "error");
    return;
  }
  let uploaded = 0;
  const failed = [...rejected];
  for (const file of validFiles) {
    if (await uploadResumeFile("extra", file)) uploaded += 1;
    else failed.push(document.getElementById("tgq-resume-status")?.textContent || file.name);
  }
  if (failed.length) setResumeUploadStatus(`${uploaded ? `Добавлено: ${uploaded}. ` : ""}${failed.join(" ")}`, "error");
  else if (uploaded > 1) setResumeUploadStatus(`Добавлено резюме: ${uploaded}.`, "success");
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
        auto_message: document.getElementById("tgq-auto-message").checked,
        preview_before_send: document.getElementById("tgq-preview").checked,
        night_to_morning: document.getElementById("tgq-night").checked,
        smart_greeting: document.getElementById("tgq-smart-greeting").checked,
        llm_vacancy_filter: document.getElementById("tgq-llm-vacancy-filter")
          .checked,
        message_delay_min_seconds: Math.max(0, parseInt(document.getElementById("tgq-delay-min").value, 10) || 0) * 60,
        message_delay_max_seconds: Math.max(0, parseInt(document.getElementById("tgq-delay-max").value, 10) || 0) * 60,
        active_hours_start: parseInt(document.getElementById("tgq-hours-start").value, 10) || 0,
        active_hours_end: parseInt(document.getElementById("tgq-hours-end").value, 10) || 24,
        daily_message_limit: Math.max(1, parseInt(document.getElementById("tgq-daily-limit").value, 10) || 15),
        channel_backfill_days: Math.max(0, parseInt(document.getElementById("tgq-backfill-days").value, 10) || 0),
      }),
    });
    await loadTelegramWatch();
    status.textContent = "Сохранено — применяется сразу.";
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

let importToDrawer = false; // файл выбран с Главной — предпросмотр в боковой панели

async function importPreview(file, el = document.getElementById("import-preview")) {
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
  document.getElementById("import-cancel").addEventListener("click", () =>
    el.closest("#platform-drawer") ? closePlatformDrawer() : (el.innerHTML = "")
  );
  document.getElementById("import-commit").addEventListener("click", async () => {
    try {
      const res = await api("/api/import/commit", {
        method: "POST",
        body: JSON.stringify({ token: data.token, include_unverified: document.getElementById("import-unverified").checked }),
      });
      showToast(`База обновлена: +${res.companies} ${plural(res.companies, "компания", "компании", "компаний")}`, "success");
      if (el.closest("#platform-drawer")) {
        // С Главной — там и остаёмся: карточка покажет следующий шаг.
        closePlatformDrawer();
        refreshOwnChannels();
        return;
      }
      el.innerHTML = `<p class="ok-text">Добавлено: компаний ${res.companies}, контактов ${res.contacts} из ${escapeHtml(res.filename)}. </p>
        <button type="button" class="btn btn-primary btn-small" data-goto-outreach>Перейти к рассылке →</button>`;
      el.querySelector("[data-goto-outreach]").addEventListener("click", () => switchTab("outreach"));
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

// «Что бот делает сейчас»: последние значимые строки журнала без служебных.
// «Что бот делает сейчас»: последние понятные строки журнала, или
// «бот остановлен» с кнопкой запуска.
async function renderLiveFeed() {
  const body = document.getElementById("live-feed-body");
  const dot = document.getElementById("live-feed-dot");
  if (!body) return;
  const running = !!lastStatus?.daemon_running;
  const busy = !!lastRunNow?.running;
  dot.className = `dot ${running || busy ? "running" : "idle"}`;
  if (!running && !busy) {
    if (!setHtmlIfChanged(body, `<p class="feed-stopped">Бот остановлен. Площадки не ищут по расписанию; рассылка работает, пока открыто приложение.</p>
      <button type="button" class="btn btn-small" id="feed-run">Запустить</button>`)) return;
    body.querySelector("#feed-run").addEventListener("click", () => document.getElementById("daemon-toggle").click());
    return;
  }
  try {
    const { lines } = await api("/api/logs?lines=120");
    const parsedRows = (lines || [])
      .filter((l) => / (INFO|WARNING|ERROR) +\|/.test(l) && !l.includes("api.telegram.org"))
      .slice(-8)
      .reverse()
      .map((l) => {
        const [, time = "", level = "", , msg = l] = l.match(/^\S+ (\S+) \| (\w+) *\| ([^-]*) - (.*)$/) || [];
        return { key: `${time}|${msg}`, time, level, message: msg.slice(0, 160) };
      });
    const rows = parsedRows.map((row) => {
      const entering = lastLiveFeedKeys && !lastLiveFeedKeys.has(row.key) && !REDUCE_MOTION;
      return `<div class="feed-row${row.level === "INFO" ? "" : " is-warn"}${entering ? " feed-row-enter" : ""}"><span class="mono feed-time">${escapeHtml(row.time.slice(0, 5))}</span><span>${escapeHtml(row.message)}</span></div>`;
    });
    lastLiveFeedKeys = new Set(parsedRows.map((row) => row.key));
    setHtmlIfChanged(body, rows.join("") || `<p class="feed-stopped">Пока тихо — бот ждёт следующего хода.</p>`);
  } catch (e) {
    /* лента необязательна */
  }
}


// Пометки «не поддерживается»: по выбранным в «Что ищу» фильтрам — на каких
// площадках каждый действует, а на каких нет (данные: /api/filters/support).
let filterSupport = null;
function currentSearchFilters() {
  const checked = (sel) => [...document.querySelectorAll(sel)].filter((e) => e.checked).map((e) => e.value);
  const formats = ["remote", "hybrid", "onsite"].filter((f) => document.getElementById(`search-${f}`)?.checked);
  return {
    formats,
    salary: !!document.getElementById("search-only-with-salary")?.checked,
    levels: checked(".search-level"),
    employment: checked(".search-employment"),
    period: Number(document.getElementById("search-posted-within")?.value || 0),
  };
}
// ok — применяется, partial — применяется при условии, none — не применяется
function filterVerdict(name, want, v) {
  if (name === "formats") {
    if (v === true) return "ok";
    if (!v) return "none";
    const only = want.length === 1;
    if (v === "remote") return want.length === 1 && want[0] === "remote" ? "ok" : want.includes("remote") ? "partial" : "none";
    return only ? "ok" : "partial"; // single
  }
  if (name === "employment") {
    if (v === true) return "ok";
    if (!v) return "none";
    const fp = want.filter((e) => e === "full" || e === "part");
    return fp.length === 1 ? "ok" : "partial"; // single: полная или частичная
  }
  return v ? "ok" : "none";
}
async function renderFilterCoverage() {
  const box = document.getElementById("search-filter-coverage");
  if (!box) return;
  try {
    if (!filterSupport) filterSupport = (await api("/api/filters/support")).support;
  } catch (e) {
    return;
  }
  const f = currentSearchFilters();
  const rows = [
    ["formats", "Формат работы", f.formats.length ? f.formats : null],
    ["levels", "Уровень", f.levels.length ? f.levels : null],
    ["salary", "Только с зарплатой", f.salary ? [1] : null],
    ["employment", "Тип занятости", f.employment.length ? f.employment : null],
    ["period", "Опубликовано", f.period ? [f.period] : null],
  ].filter((r) => r[2]);
  if (!rows.length) {
    box.innerHTML = "Фильтры не выбраны — поиск идёт без ограничений на всех площадках.";
    return;
  }
  box.innerHTML = rows
    .map(([key, title, want]) => {
      const none = [];
      const partial = [];
      Object.entries(filterSupport).forEach(([src, sup]) => {
        const verdict = filterVerdict(key, want, sup[key]);
        if (verdict === "none") none.push(sourceLabel(src));
        if (verdict === "partial") partial.push(sourceLabel(src));
      });
      const parts = [];
      if (none.length) parts.push(`не применяется: ${none.join(", ")}`);
      if (partial.length) parts.push(`частично (нужен один вариант): ${partial.join(", ")}`);
      return `<div><b>${title}</b> — ${parts.length ? parts.join("; ") : "применяется на всех площадках"}</div>`;
    })
    .join("");
}
document
  .querySelectorAll("#search-remote,#search-hybrid,#search-onsite,#search-only-with-salary,.search-level,.search-employment,#search-posted-within")
  .forEach((el) => el.addEventListener("change", renderFilterCoverage));

const SENT_LABELS = { sent: "отправлено", replied: "ответили", bounced: "возврат", failed: "не ушло" };
let sentRows = [];
function renderSentLog() {
  const q = document.getElementById("sent-search").value.trim().toLowerCase();
  const st = document.getElementById("sent-status").value;
  const rows = sentRows.filter(
    (r) => (!st || r.status === st) && (!q || `${r.company} ${r.email} ${r.subject}`.toLowerCase().includes(q))
  );
  const el = document.getElementById("sent-list");
  if (!rows.length) {
    el.textContent = sentRows.length ? "Ничего не найдено." : "Пока ни одно письмо не отправлено.";
    return;
  }
  const counts = {};
  sentRows.forEach((r) => (counts[r.status] = (counts[r.status] || 0) + 1));
  el.innerHTML = `<p>${Object.entries(counts).map(([k, n]) => `${SENT_LABELS[k] || k}: <b>${n}</b>`).join(" · ")}</p>
    <table class="table"><thead><tr><th>Дата</th><th>Кому</th><th>Тема</th><th>Статус</th></tr></thead><tbody>${rows
      .slice(0, 200)
      .map(
        (r) => `<tr><td>${r.sent_at ? escapeHtml(fmtDay(r.sent_at)) : "—"}</td>
        <td title="${escapeHtml(r.email)}">${escapeHtml(r.company || r.email)}</td>
        <td><details><summary>${escapeHtml(r.subject || "(без темы)")}</summary><pre class="small" style="white-space:pre-wrap">${escapeHtml(r.text)}</pre></details></td>
        <td title="${escapeHtml(r.reason)}">${SENT_LABELS[r.status] || r.status}</td></tr>`
      )
      .join("")}</tbody></table>`;
}
async function loadSentLog() {
  try {
    sentRows = (await api("/api/outreach/sent")).items;
  } catch (e) {
    return;
  }
  renderSentLog();
}
document.getElementById("sent-search")?.addEventListener("input", renderSentLog);
document.getElementById("sent-status")?.addEventListener("change", renderSentLog);

async function loadCampaigns() {
  loadSentLog();
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
    ${stepHead(1, "Кому писать", data.available || cur ? "done" : "active")}
    ${
      data.available
        ? `<p>Можно написать <b>${data.available}</b> ${plural(data.available, "компании", "компаниям", "компаниям")} с email, которым вы ещё не писали:</p>
           <div class="campaign-stats">${sources.map(([s, n]) => `<span class="stat-pill">${escapeHtml(s)} <b>${n}</b></span>`).join("")}</div>`
        : `<p class="muted">${cur ? "Все новые адреса уже в текущей рассылке." : "Пока некому писать — загрузите свой список или подождите, пока бот соберёт контакты из Telegram и вакансий."}</p>`
    }
    <div class="step-actions">
      <button type="button" class="btn btn-small" data-base-open>Выбрать в Базе</button>
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
         <button type="button" class="btn btn-primary" data-campaign="${cur.id}" data-action="prepare">Написать ${batch} ${plural(batch, "письмо", "письма", "писем")}</button>`
      : `<p class="muted">Ещё в очереди: <b>${cur.stats.pending}</b> — следующая порция будет готова завтра, когда эти письма уйдут${days > 1 ? ` (≈ ${days} ${plural(days, "день", "дня", "дней")} на всю рассылку)` : ""}.</p>`;
  } else if (!cur && data.available) {
    const days = data.days_needed;
    body = `<p class="muted small">Для каждой компании — своё письмо: обращение по имени, почему именно она, 2–3 ваших достижения под её профиль, 150–180 слов, тема «[Должность] Application — Имя Фамилия».</p>
      ${days > 1 ? `<p class="muted small">Сейчас можно ${data.daily_limit} писем в день${data.mail_plan.warmup && data.daily_limit < data.mail_plan.daily_limit ? ` (разогрев ящика — дальше больше, до ${data.mail_plan.daily_limit})` : ""}: вся база — ≈ ${days} ${plural(days, "день", "дня", "дней")} отправки. Письма пишутся порциями, каждый день новая порция приходит в бот. Быстрее — выберите нужные компании в Базе фильтрами и «Написать письма».</p>` : ""}
      <div class="step-actions">
        ${sources.length > 1 ? `<select id="campaign-source" aria-label="Кому писать">
          <option value="">всем (${data.available})</option>
          ${sources.map(([s, n]) => `<option value="${escapeHtml(s)}">${escapeHtml(s)} (${n})</option>`).join("")}
        </select>` : ""}
        <button type="button" class="btn btn-primary" id="campaign-create">Подготовить письма</button>
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
    sendBody = `<p>Отправка идёт по расписанию — ждут ещё <b>${drafts.length}</b>. ${escapeHtml(data.mail_plan.reason || "Следующее письмо — в течение 15 минут.")}</p>
      <div class="step-actions"><button type="button" class="btn btn-ghost btn-small" data-campaign="${cur.id}" data-action="stop">Остановить рассылку</button></div>
      <p class="field-hint">${escapeHtml(mailPlanText(data.mail_plan))}</p>`;
  } else if (drafts.length) {
    sendBody = `<div class="step-actions">
        <label class="muted small">Резюме во вложении
          <select data-campaign-resume="${cur.id}" aria-label="Резюме во вложении">
            <option value="">автоматически: RU/EN по компании</option>
            ${resumes.map((r) => `<option value="${escapeHtml(r.name)}">${escapeHtml(r.name)}</option>`).join("")}
          </select>
        </label>
        <button type="button" class="btn btn-primary" data-campaign="${cur.id}" data-action="send">Начать отправку (${drafts.length})</button>
      </div>
      <p class="muted small">Бот отправляет по одному, со случайными паузами в течение рабочего дня — как человек. Что не уйдёт сегодня, продолжит сам в следующее время отправки. Можно закрыть окно.</p>
      <p class="field-hint">${escapeHtml(mailPlanText(data.mail_plan))}</p>`;
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
          <p><b>Молчат больше недели: ${due.length}</b> — короткое напоминание уйдёт в ту же ветку письма, без вложения.</p>
          <div class="letters">${due
            .map(
              (i) => `<details class="letter">
                <summary><strong>${escapeHtml(i.company || i.email)}</strong> <span class="muted small">${escapeHtml(i.email)}</span></summary>
                <textarea rows="4" data-letter="${escapeHtml(i.follow_up_code)}" aria-label="Текст напоминания">${escapeHtml(i.follow_up_text)}</textarea>
                <div class="step-actions"><button type="button" class="btn btn-ghost btn-small" data-letter-skip="${escapeHtml(i.follow_up_code)}">Не напоминать</button></div>
              </details>`
            )
            .join("")}</div>
          ${c.progress ? "" : `<div class="step-actions"><button type="button" class="btn btn-primary btn-small" data-campaign="${c.id}" data-action="followups">Отправить напоминания (${due.length})</button></div>`}
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
  renderMailGuard(data.mail_plan);

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
      if (action === "send" && !(await showConfirm("Отправить письма через Gmail с резюме во вложении?"))) return;
      if (action === "followups" && !(await showConfirm("Отправить напоминания через Gmail в те же ветки писем?"))) return;
      if (action === "delete" && !(await showConfirm("Удалить рассылку? Неотправленные письма тоже удалятся."))) return;
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

// «Защита почты»: сколько ушло сегодня из лимита, возвраты, разогрев,
// часы отправки и почему сейчас пауза.
function renderMailGuard(p) {
  const el = document.getElementById("mail-guard");
  if (!el || !p) return;
  const pct = p.limit ? Math.round((100 * p.sent_today) / p.limit) : 0;
  el.innerHTML = `<div class="card-head flat between"><h3 id="mail-guard-h">Защита почты</h3><button type="button" class="link-btn small" data-goto-settings="settings-outreach">настроить</button></div>
    <div class="guard-row"><span>Сегодня</span><span class="mono">${p.sent_today} / ${p.limit}</span></div>
    <div class="progress"><div style="width:${Math.min(100, pct)}%"></div></div>
    <div class="kv-list flat">
      <div class="kv"><span>Возвратов за сутки</span><span class="mono ${p.bounce_stopped ? "err-text" : ""}">${p.recent_bounces} · стоп после ${p.bounce_stop}</span></div>
      ${p.warmup ? `<div class="kv"><span>Разогрев ящика</span><span>день ${p.warmup_day}${p.limit < p.daily_limit ? `, до ${p.daily_limit} — постепенно` : ""}</span></div>` : ""}
      <div class="kv"><span>Когда отправляю</span><span>${p.send_hours_enabled !== false ? `${p.weekdays_only ? "по будням" : "каждый день"}, ${p.send_from}:00–${p.send_to}:00` : p.weekdays_only ? "по будням, в любое время" : "круглосуточно"}</span></div>
      <div class="kv"><span>Сейчас</span><span>${p.can_send ? "можно отправлять" : escapeHtml(p.reason || "пауза")}</span></div>
    </div>`;
  bindGotoSettings(el);
}

function progressHtml(label, progress, id) {
  const pct = Math.round((100 * progress.done) / Math.max(progress.total, 1));
  return `<p>${label}: <b>${progress.done}</b> из ${progress.total}</p>
    <div class="progress"><div style="width:${pct}%"></div></div>
    <div class="step-actions"><button type="button" class="btn btn-ghost btn-small" data-campaign="${id}" data-action="stop">Остановить</button></div>`;
}

// Карточка на Главной — "постоянный цикл" был спрятан внутри
// Настроек → Лимиты откликов, а это прямой ответ на "успею ли я в
// первые 30 кандидатов", так что вынесен на самое видное место.
// ---------- Главная: шапка, карточки, полоса источников ----------

function renderDaemonState(status) {
  const badge = document.getElementById("daemon-badge");
  const runningLabel = status.daemon_started_at
    ? `бот работает · ${formatElapsed(status.daemon_started_at)}`
    : "бот работает";
  const gw = status.telegram_gateway;
  badge.title = gw?.alive ? (gw.connected ? "Telegram-шлюз на связи" : "Telegram-шлюз переподключается") : "";
  const pausedAll = !!status.pause_all?.paused;
  setHtmlIfChanged(badge, `<span class="badge-dot"></span><span class="btn-label">${
    pausedAll ? "пауза на всё" : status.daemon_running ? (status.daemon_paused ? "бот на паузе" : runningLabel) : "бот остановлен"
  }${gw?.alive ? (gw.connected ? " · Telegram ✓" : " · Telegram …") : ""}</span>`);
  badge.classList.toggle("on", status.daemon_running && !status.daemon_paused);
  badge.classList.toggle("off", !status.daemon_running || !!status.daemon_paused);
  document.getElementById("brand-dot")?.classList.toggle("is-live", !!status.daemon_running && !status.daemon_paused);
  // Одна кнопка: «Запустить» ↔ «Остановить» (на паузе — «Возобновить»).
  const toggleBtn = document.getElementById("daemon-toggle");
  const isPauseAction = status.daemon_running && !status.daemon_paused;
  toggleBtn.classList.toggle("is-pause-action", isPauseAction);
  toggleBtn.classList.toggle("is-paused", !!status.daemon_paused);
  const label = !status.daemon_running ? "Запустить" : status.daemon_paused ? "Возобновить" : "Остановить";
  toggleBtn.querySelector(".btn-label").textContent = label;
  toggleBtn.title = !status.daemon_running
    ? "Запустить бота: площадки по расписанию, Telegram-парсер, проверка ответов"
    : status.daemon_paused
      ? "Возобновить работу бота"
      : "Остановить бота";
  const homeRun = document.getElementById("home-run");
  if (homeRun) {
    homeRun.textContent = !status.daemon_running ? "Запустить бота" : status.daemon_paused ? "Возобновить" : "Остановить бота";
    homeRun.classList.toggle("btn-primary", !status.pause_all?.paused && (!status.daemon_running || !!status.daemon_paused));
    homeRun.title = toggleBtn.title;
  }
}

// Общий режим «Откликаться / Только искать» — тот же флаг auto_apply,
// что «Откликаться автоматически» в Настройках, только на виду.
function modeSources(status) {
  return status.sources.filter((s) => s.schedule_enabled && !OWN_CHANNELS.has(s.name));
}

function renderHomeMode(status) {
  const box = document.getElementById("home-mode");
  if (!box) return;
  const on = modeSources(status);
  const auto = on.filter((s) => s.auto_apply);
  const state = !on.length ? "none" : auto.length === on.length ? "apply" : auto.length === 0 ? "search" : "mixed";
  box.dataset.state = state;
  box.title = state === "mixed"
    ? `Сейчас сами откликаются ${auto.length} из ${on.length} площадок — выберите один режим для всех`
    : state === "none" ? "Ни одна площадка не включена" : "";
  box.querySelectorAll("[data-mode]").forEach((b) => {
    const sel = b.dataset.mode === state;
    b.classList.toggle("on", sel);
    b.setAttribute("aria-checked", sel ? "true" : "false");
    b.disabled = state === "none";
  });
  positionSegmented(box);
}

function positionSegmented(box) {
  const ind = box.querySelector(".segmented-ind");
  const sel = box.querySelector("button.on");
  if (!ind) return;
  if (!sel) {
    ind.style.opacity = "0";
    return;
  }
  ind.style.opacity = "1";
  ind.style.width = `${sel.offsetWidth}px`;
  ind.style.transform = `translateX(${sel.offsetLeft - 3}px)`;
}

async function setHomeMode(mode) {
  const status = await api("/api/status");
  const on = modeSources(status);
  if (!on.length) return;
  const enable = mode === "apply";
  const targets = on.filter((s) => !!s.auto_apply !== enable);
  if (!targets.length) return;
  if (enable && !(await showConfirm(`Бот начнёт сам отправлять отклики на ${targets.length} ${plural(targets.length, "площадке", "площадках", "площадках")} — до дневного лимита каждой. Включить?`))) return;
  try {
    for (const s of targets) {
      await api("/api/settings", { method: "POST", body: JSON.stringify({ source: s.name, auto_apply: enable }) });
    }
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
  }
  showSavedToast(enable ? "Бот снова откликается сам" : "Только искать: вакансии копятся в «Вакансиях», откликаетесь вы", async () => {
    for (const s of targets) {
      await api("/api/settings", { method: "POST", body: JSON.stringify({ source: s.name, auto_apply: !enable }) });
    }
    lastOverviewSnapshot = "";
    render.overview();
  });
  lastOverviewSnapshot = "";
  render.overview();
}

function syncRadioGroupTabStops(group) {
  if (!group) return null;
  const radios = [...group.querySelectorAll('[role="radio"]:not(:disabled)')];
  const selected = radios.find((radio) => radio.getAttribute("aria-checked") === "true") || radios[0] || null;
  radios.forEach((radio) => {
    radio.tabIndex = radio === selected ? 0 : -1;
  });
  return selected;
}

function initRadioGroupKeyboard() {
  document.querySelectorAll('[role="radiogroup"]').forEach(syncRadioGroupTabStops);
  const radioGroupsObserver = new MutationObserver((records) => {
    records.forEach((record) => record.addedNodes.forEach((node) => {
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      if (node.matches('[role="radiogroup"]')) syncRadioGroupTabStops(node);
      node.querySelectorAll?.('[role="radiogroup"]').forEach(syncRadioGroupTabStops);
    }));
  });
  radioGroupsObserver.observe(document.body, { childList: true, subtree: true });
  let tabNavigationPending = false;
  document.addEventListener("keydown", (event) => {
    if (event.key === "Tab") {
      tabNavigationPending = true;
      setTimeout(() => { tabNavigationPending = false; }, 0);
      return;
    }
    const current = event.target.closest?.('[role="radio"]');
    if (!current || !["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(event.key)) return;
    const group = current.closest('[role="radiogroup"]');
    const radios = [...(group?.querySelectorAll('[role="radio"]:not(:disabled)') || [])];
    if (radios.length < 2) return;
    event.preventDefault();
    const direction = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : -1;
    const currentIndex = radios.indexOf(current);
    const next = radios[(currentIndex + direction + radios.length) % radios.length];
    next.click();
    if (next.isConnected) next.focus();
    syncRadioGroupTabStops(group);
  });
  document.addEventListener("focusin", (event) => {
    if (!tabNavigationPending) return;
    const radio = event.target.closest?.('[role="radio"]');
    const group = radio?.closest('[role="radiogroup"]');
    if (!group) return;
    tabNavigationPending = false;
    const selected = syncRadioGroupTabStops(group);
    if (selected && selected !== radio) selected.focus();
  });
  document.addEventListener("click", (event) => {
    const radio = event.target.closest?.('[role="radio"]');
    const group = radio?.closest('[role="radiogroup"]');
    if (!radio || !group || radio.disabled) return;
    group.querySelectorAll('[role="radio"]').forEach((option) => {
      option.setAttribute("aria-checked", String(option === radio));
    });
    syncRadioGroupTabStops(group);
  });
}

function renderHomeLimit(status, stats) {
  const el = document.getElementById("home-limit");
  if (!el) return;
  const on = modeSources(status);
  const sum = on.reduce((acc, s) => acc + (s.daily_limit || 0), 0);
  const total = status.total_daily_application_limit || 0;
  const limit = total ? Math.min(total, sum || total) : sum;
  el.textContent = limit ? `сегодня ${stats.day} из ${limit} откликов` : "";
  el.title = limit ? (total ? "Общий дневной лимит по всем площадкам (Настройки → Лимиты и оценка)" : "Сумма дневных лимитов включённых площадок") : "";
}

function sparkPaths(values, w = 96, h = 32) {
  if (!values.length) return { line: "", area: "" };
  const max = Math.max(1, ...values);
  const step = values.length > 1 ? w / (values.length - 1) : w;
  const pts = values.map((v, i) => [i * step, h - 2 - (v / max) * (h - 4)]);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  return { line, area: `${line} L${w} ${h} L0 ${h} Z` };
}

function kpiCardHtml({ label, help, value, prev, prevLabel, series, i }) {
  const delta = value - prev;
  const arrow = delta > 0 ? "↑" : delta < 0 ? "↓" : "·";
  const tone = delta > 0 ? "good" : delta < 0 ? "bad" : "flat";
  const text = delta === 0 ? `как ${prevLabel}` : `на ${Math.abs(delta)} ${delta > 0 ? "больше" : "меньше"}, чем ${prevLabel}`;
  const sp = series ? sparkPaths(series) : null;
  return `<div class="card kpi-card stagger-item" style="animation-delay:${staggerDelay(i, 40)}">
    <div class="kpi-label tip" tabindex="0">${escapeHtml(label)}
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="8" cy="8" r="6"/><path d="M8 7v4M8 5h.01" stroke-linecap="round"/></svg>
      <span class="tiptext" role="tooltip">${escapeHtml(help)}</span>
    </div>
    <div class="kpi-main">
      <span class="kpi-value mono" data-count="kpi-${i}">${value}</span>
      ${sp ? `<svg class="spark" viewBox="0 0 96 32" aria-hidden="true"><path d="${sp.area}" class="spark-area"/><path d="${sp.line}" class="spark-line"/></svg>` : ""}
    </div>
    <div class="kpi-delta"><span class="trend-${tone}">${arrow}</span>${escapeHtml(text)}</div>
  </div>`;
}

async function renderKpis(stats) {
  const el = document.getElementById("stats-row");
  let results = null;
  try {
    results = await api("/api/results");
  } catch (e) {}
  const daily = stats.daily || [];
  const cards = [
    { label: "Откликов сегодня", help: "Реально отправленные отклики с полуночи. Пропуски и тестовые прогоны не считаются.", value: stats.day, prev: stats.prev_day, prevLabel: "вчера", series: daily.slice(-7) },
    { label: "За неделю", help: "Отклики за последние 7 дней, сравнение — с 7 днями до них.", value: stats.week, prev: stats.prev_week, prevLabel: "на прошлой неделе", series: daily.slice(-14) },
    { label: "За месяц", help: "Отклики за последние 30 дней, сравнение — с 30 днями до них.", value: stats.month, prev: stats.prev_month, prevLabel: "в прошлом месяце", series: Array.from({ length: Math.ceil(daily.length / 3) }, (_, i) => daily.slice(i * 3, i * 3 + 3).reduce((a, b) => a + b, 0)) },
  ];
  if (results) {
    cards.push({ label: "Ответов работодателей", help: "Ответы, приглашения и офферы за 7 дней — с площадок, из Telegram и на письма рассылки.", value: results.week.replies, prev: results.prev.replies, prevLabel: "неделей раньше", series: null });
  }
  if (!setHtmlIfChanged(el, cards.map((c, i) => kpiCardHtml({ ...c, i })).join(""))) return;
  animateCounts(el);
}

async function renderHomeSplit() {
  const el = document.getElementById("home-split");
  if (!el) return;
  let r;
  try {
    r = await api("/api/results?days=30");
  } catch (e) {
    return;
  }
  const label = (src) => (src === "email_campaign" ? "Рассылка по почте" : sourceLabel(src));
  const rows = r.by_source.filter((x) => x.applied > 0).sort((a, b) => b.applied - a.applied);
  const total = rows.reduce((acc, x) => acc + x.applied, 0);
  const top = rows.slice(0, 5);
  const rest = rows.slice(5).reduce((acc, x) => acc + x.applied, 0);
  const segs = top.map((x, i) => ({ name: label(x.source), value: x.applied, color: `var(--chart-${i + 1})`, replies: x.replies }));
  if (rest) segs.push({ name: `Прочие: ${rows.slice(5).map((x) => label(x.source)).join(", ")}`, value: rest, color: "var(--chart-6)", replies: rows.slice(5).reduce((a, x) => a + x.replies, 0) });
  if (!setHtmlIfChanged(el, `<div class="card-head flat between"><h3 id="home-split-h">Куда ушли отклики за месяц</h3><span class="mono small muted">${total}</span></div>
    ${total
      ? `<div class="segs" role="img" aria-label="${escapeHtml(segs.map((x) => `${x.name}: ${x.value}`).join(", "))}">${segs
          .map((x, i) => `<div class="seg" data-i="${i}" style="flex:${x.value} 1 0;background:${x.color}"></div>`)
          .join("")}</div>
        <div class="seg-caption small muted" id="home-split-caption">Наведите на полосу, чтобы увидеть долю площадки</div>
        <div class="seg-legend">${segs
          .map((x) => `<div class="seg-key"><span class="seg-swatch" style="background:${x.color}"></span><span class="seg-name">${escapeHtml(x.name)}</span><span class="mono">${x.value}</span></div>`)
          .join("")}</div>`
      : `<p class="small muted">За 30 дней откликов пока нет — включите площадки ниже и запустите бота.</p>`}`)) return;
  const cap = el.querySelector("#home-split-caption");
  el.querySelectorAll(".seg").forEach((seg) => {
    seg.addEventListener("mouseenter", () => {
      const x = segs[Number(seg.dataset.i)];
      cap.textContent = `${x.name}: ${x.value} ${plural(x.value, "отклик", "отклика", "откликов")} (${Math.round((100 * x.value) / total)}%), ответов ${x.replies}`;
    });
    seg.addEventListener("mouseleave", () => (cap.textContent = "Наведите на полосу, чтобы увидеть долю площадки"));
  });
}

// Вход в аккаунт Telegram (Настройки → Подключения) и значок
// состояния в «Общении» — по /api/telegram/status.
function applyTelegramAccountStatus(status) {
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
      "Сначала вставьте api_id и api_hash ниже.";
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
  const offRow = document.getElementById("tg-account-off-row");
  if (offRow) offRow.hidden = !status.connected;
  if (status.connected) {
    document.getElementById("telegram-login-code-row").style.display =
      "none";
    document.getElementById("telegram-login-password-row").style.display =
      "none";
    document.getElementById("telegram-login-status").textContent = "";
  }
}

async function refreshTelegramAccount() {
  try {
    applyTelegramAccountStatus(await api("/api/telegram/status"));
  } catch (e) {
    /* не критично */
  }
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
    const todoPromise = api("/api/todo").catch(() => null);
    if (!overviewLoaded) {
      document.getElementById("stats-row").innerHTML = skeletonStats();
      document.getElementById("source-grid-ru").innerHTML = skeletonRowsList(4);
      document.getElementById("source-grid-intl").innerHTML = skeletonRowsList(3);
    }

    const [status, stats, runNow, todo] = await Promise.all([
      api("/api/status"),
      api("/api/stats"),
      api("/api/run-now/status"),
      todoPromise,
    ]);
    lastStatus = status;
    lastRunNow = runNow;
    const isOnboarding = todo ? await renderTodo(todo, status) : document.getElementById("dashboard-sections").style.display === "none";
    // Обязательные шаги (резюме/ключ ИИ/площадка) не пройдены — ниже
    // нечего показывать: пустая статистика и площадки без резюме
    // только отвлекают от чек-листа выше него. См. #dashboard-sections
    // в index.html.
    document.getElementById("dashboard-sections").style.display = isOnboarding ? "none" : "";

    // ponytail: без этой проверки весь блок ниже пересобирался на каждый
    // опрос раз в 7с, даже когда ничего не изменилось — это и было
    // «мерцание», о котором сообщил пользователь.
    const snapshot = JSON.stringify({ status, stats, runNow });
    const unchanged = overviewLoaded && snapshot === lastOverviewSnapshot;
    lastOverviewSnapshot = snapshot;

    renderDaemonState(status);
    renderPauseAll(status);
    renderHomeMode(status);
    renderHomeLimit(status, stats);

    if (!unchanged) {
      // Telegram, «Сайты компаний», Talanto и Hirify — в «Свои каналы».
      const ruSources = status.sources.filter((s) => !INTL_SOURCES.has(s.name) && !OWN_CHANNELS.has(s.name));
      const intlSources = status.sources.filter((s) => INTL_SOURCES.has(s.name));
      const rowOf = (s, i) => platformRowHtml(sourceRowModel(s, runNow), i);
      setHtmlIfChanged(document.getElementById("source-grid-ru"), applySourceOrder(ruSources, "name", "cj-source-order-ru")
        .map(rowOf)
        .join(""));
      setHtmlIfChanged(document.getElementById("source-grid-intl"), applySourceOrder(intlSources, "name", "cj-source-order-intl")
        .map(rowOf)
        .join(""));
      if (openDrawerSource && isPlatformDrawerOpen() && !drawerDirty) {
        refreshSourceDrawerHead(openDrawerSource);
      }
    }

    await Promise.all([
      renderOwnChannels(),
      renderLiveFeed(),
      renderKpis(stats),
      renderHomeSplit(),
    ]);
    overviewLoaded = true;
  },

  async history({ animateRows: requestedRowMotion = false } = {}) {
    const firstHistoryLoad = !historyLoaded;
    const source = document.getElementById("filter-source").value;
    const q = document.getElementById("filter-query").value;
    const params = new URLSearchParams();
    if (source) params.set("source", source);
    if (q) params.set("q", q);

    const tbody = document.getElementById("history-rows");
    if (!historyLoaded) tbody.innerHTML = skeletonRows(6, 5);

    const all = await api(`/api/applications?${params}`);
    historyLoaded = true;
    if (!jobThresholds) {
      api("/api/settings/limits")
        .then((l) => (jobThresholds = { min: l.job_min_score, fit: l.job_suitability_score }))
        .catch(() => {});
    }

    const historyViewKey = JSON.stringify([params.toString(), historyChip]);
    const previousStatusByKey = lastHistoryViewKey === historyViewKey
      ? new Map(historyRows.map((entry) => [historyEntryKey(entry), historyStatusSignature(entry)]))
      : new Map();
    const historySnapshot = JSON.stringify({ params: params.toString(), chip: historyChip, all });
    if (historySnapshot === lastHistorySnapshot) return;
    lastHistorySnapshot = historySnapshot;
    lastHistoryViewKey = historyViewKey;

    renderHistoryChips(all);
    renderActiveFilters("history");
    const entries = all.filter(HISTORY_CHIPS[historyChip].test);
    const animateRows = firstHistoryLoad || (requestedRowMotion && !REDUCE_MOTION);
    lastHistoryEntries = entries;
    const today = all.filter((e) => e.status === "applied" && (e.applied_at || "").slice(0, 10) === new Date().toISOString().slice(0, 10)).length;
    document.getElementById("history-today").textContent = `сегодня ${today} ${plural(today, "отклик", "отклика", "откликов")}`;
    document.getElementById("history-count").textContent = `показано ${entries.length}`;
    if (!entries.length) {
      historyRows = [];
      tbody.innerHTML = `<tr><td colspan="5">${emptyStateHtml("Ничего не нашлось. Сбросьте фильтр или поищите по другому слову.", requestedRowMotion || firstHistoryLoad)}</td></tr>`;
      updateHistoryScrollHint();
      return;
    }
    historyRows = entries.slice().sort((a, b) => (b.applied_at || "").localeCompare(a.applied_at || ""));
    tbody.innerHTML = historyRows
      .map((e, i) => {
        const stage = e.effective_stage ? STAGE_LABELS[e.effective_stage] : "";
        const tone = e.status === "applied" ? (e.effective_stage === "rejected" ? "bad" : e.effective_stage ? "good" : "") : e.status === "dry_run" ? "" : "muted";
        const statusChanged = previousStatusByKey.has(historyEntryKey(e))
          && previousStatusByKey.get(historyEntryKey(e)) !== historyStatusSignature(e);
        return `<tr class="job-row${animateRows ? " reveal" : ""}" data-row-index="${i}"${animateRows ? ` style="transition-delay:${staggerDelay(i, 25)}"` : ""}>
          <td class="mono small muted nowrap">${fmtDay(e.applied_at)}</td>
          <td><button type="button" class="job-row-open job-cell" aria-label="Открыть вакансию ${escapeHtml(e.title)} в компании ${escapeHtml(e.company || "без названия")}">${plogoHtml(e.source)}<span class="row-main"><span class="row-title">${highlightText(e.company || "—", q)}</span><span class="row-sub">${highlightText(e.title, q)}${e.remote_region ? ` · ${REGION_LABELS[e.remote_region] || ""}` : ""}</span></span></button></td>
          <td class="small nowrap">${escapeHtml(e.salary || "—")}</td>
          <td><span class="status-text ${tone}${statusChanged ? " status-changed" : ""}">${escapeHtml(statusLabel(e.status))}</span>${stage ? `<span class="stage-tag${statusChanged ? " status-changed" : ""}">${escapeHtml(stage)}</span>` : ""}${e.apply_anyway && isSkipped(e) ? `<span class="stage-tag">отклик запланирован</span>` : ""}${e.feedback ? `<span class="stage-tag" title="${escapeHtml(e.feedback.reason || "")}">ваша пометка</span>` : ""}</td>
          <td class="num mono">${e.score ?? "—"}${e.score != null ? `<span class="muted"> / 10</span>` : ""}</td>
        </tr>`;
      })
      .join("");
    updateHistoryScrollHint();
    if (animateRows) observeReveal(tbody);
  },

  async replies() {
    const firstRepliesLoad = !repliesLoaded;
    const tbody = document.getElementById("replies-rows");
    const loadError = document.getElementById("replies-load-error");
    if (loadError) loadError.hidden = true;
    if (!repliesLoaded) {
      tbody.setAttribute("aria-busy", "true");
      tbody.innerHTML = Array.from({ length: 4 }, () => `<div class="talk-row-skeleton" aria-hidden="true"><span class="skeleton talk-skeleton-avatar"></span><span class="talk-skeleton-copy"><span class="skeleton talk-skeleton-title"></span><span class="skeleton talk-skeleton-meta"></span><span class="skeleton talk-skeleton-preview"></span></span></div>`).join("");
    }

    const [inboxResult, draftsResult, remindersResult, telegramResult, postsResult] = await Promise.allSettled([
      api("/api/inbox"),
      renderDraftsQueue(),
      renderHhRemindersQueue(),
      render.telegram(),
      renderTelegramPosts(),
    ]);
    const failures = [
      inboxResult.status === "rejected" && `входящие: ${inboxResult.reason.message}`,
      draftsResult.status === "rejected" && `черновики: ${draftsResult.reason.message}`,
      remindersResult.status === "rejected" && `напоминания HH: ${remindersResult.reason.message}`,
      telegramResult.status === "rejected" && `Telegram: ${telegramResult.reason.message}`,
      postsResult.status === "rejected" && `вакансии из Telegram: ${postsResult.reason.message}`,
    ].filter(Boolean);
    if (failures.length && loadError && typeof renderRetryState === "function") {
      renderRetryState(loadError, `Не удалось обновить ${failures.join("; ")}.`, () => render.replies());
      loadError.hidden = false;
    }
    if (inboxResult.status === "rejected") {
      tbody.removeAttribute("aria-busy");
      if (!repliesLoaded) tbody.replaceChildren();
      if (!loadError) throw inboxResult.reason;
      return;
    }
    const entries = inboxResult.value;
    tbody.removeAttribute("aria-busy");
    // Конфетти — только на реально новый ответ, появившийся после
    // первой загрузки за сессию, не на каждое открытие вкладки с уже
    // существующими данными.
    if (repliesLoaded && entries.length > lastRepliesCount) {
      fireConfetti();
      showToast("Новый ответ от работодателя!", "success");
    }
    lastRepliesCount = entries.length;
    repliesLoaded = true;

    const freshness = document.getElementById("talk-refresh-status");
    if (freshness) freshness.textContent = `Обновлено · ${new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;

    const repliesSnapshot = JSON.stringify(entries);
    if (repliesSnapshot === lastRepliesSnapshot) return;
    lastRepliesSnapshot = repliesSnapshot;
    lastRepliesEntries = entries;
    renderRepliesRows({ animateContent: firstRepliesLoad });
  },

  async analytics() {
    renderResults();
    requestAnimationFrame(() => positionSegmented(document.getElementById("stats-period")));
    renderActivityHeatmap();
    const gapsEl = document.getElementById("gaps-list");
    const candidatesEl = document.getElementById("blacklist-candidates");
    gapsEl.innerHTML = Array.from({ length: 3 }, () => `<li><div class="skeleton" style="height:14px"></div></li>`).join("");
    candidatesEl.innerHTML = Array.from({ length: 2 }, () => `<div class="skeleton" style="height:20px;margin-bottom:6px"></div>`).join("");

    const [gapsResult, candidatesResult, funnelResult, marketResult] = await Promise.allSettled([
      api("/api/analytics/gaps"),
      api("/api/analytics/blacklist-candidates"),
      api("/api/analytics/funnel"),
      api("/api/analytics/market"),
    ]);
    if (funnelResult.status === "fulfilled") {
      renderFunnel(funnelResult.value);
    } else {
      renderRetryState(document.getElementById("funnel"), `Не удалось загрузить воронку: ${funnelResult.reason.message}`, () => render.analytics());
    }
    if (marketResult.status === "fulfilled") {
      renderMarket(marketResult.value);
    } else {
      const retryMarket = () => render.analytics();
      ["skill-demand", "vacancy-sources", "salary-stats"].forEach((id) => {
        renderRetryState(document.getElementById(id), `Не удалось загрузить данные рынка: ${marketResult.reason.message}`, retryMarket);
      });
    }
    renderOffers();

    const gaps = gapsResult.status === "fulfilled" ? gapsResult.value : null;
    if (gaps === null) {
      renderRetryState(gapsEl, `Не удалось загрузить дефицит навыков: ${gapsResult.reason.message}`, () => render.analytics(), "li");
    }
    const gapMax = gaps?.length ? Math.max(...gaps.map(([, c]) => c)) : 1;
    if (gaps !== null) gapsEl.innerHTML = gaps.length
      ? gaps
          .map(
            ([gap, count], i) =>
              `<li class="funnel-row stagger-item" style="animation-delay:${staggerDelay(i, 40)}"><span class="funnel-label">${escapeHtml(gap)}</span><span class="funnel-track"><span class="funnel-bar" style="width:${Math.round((count / gapMax) * 100)}%"></span></span><span class="funnel-value">${count}</span></li>`
          )
          .join("")
      : `<li>${emptyStateHtml("Пока нет данных.")}</li>`;
    growFunnelBars(gapsEl);

    if (candidatesResult.status === "rejected") {
      renderRetryState(candidatesEl, `Не удалось загрузить кандидатов: ${candidatesResult.reason.message}`, () => render.analytics());
    } else if (!candidatesResult.value.length) {
      candidatesEl.innerHTML = emptyStateHtml("Нет кандидатов на чёрный список.");
    } else {
      const candidates = candidatesResult.value;
      candidatesEl.innerHTML = candidates
      .map(
        (c, i) => `
      <div class="candidate-row stagger-item" style="animation-delay:${staggerDelay(i)}">
        <input type="checkbox" value="${escapeHtml(c)}" class="blacklist-check" aria-label="Кандидат: ${escapeHtml(c)}" />
        <span>${escapeHtml(c)}</span>
        <button type="button" class="btn btn-secondary btn-small block-hh-employer" data-company="${escapeHtml(c)}" title="Заблокировать работодателя на hh.ru (серверный бан, только для HeadHunter)">Скрыть на hh.ru</button>
      </div>`
      )
      .join("");
    }
  },

  async settings() {
    const loadError = document.getElementById("settings-load-error");
    loadError.hidden = true;
    loadOutreachSettings().catch(showSettingsLoadError); // заполняет сводку и фильтры удалёнки на других вкладках
    loadAccounts().catch(showSettingsLoadError);
    refreshTelegramAccount();
    let status;
    let salary;
    let limits;
    try {
      [status, salary, limits] = await Promise.all([
        api("/api/status"),
        api("/api/settings/salary"),
        api("/api/settings/limits"),
      ]);
    } catch (err) {
      showSettingsLoadError(err);
      return;
    }
    renderAutoAll(status);
    renderAutoChat(status);

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
      document.getElementById("search-remote").checked = !!search.remote;
      document.getElementById("search-hybrid").checked = !!search.hybrid;
      document.getElementById("search-onsite").checked = !!search.onsite;
      document.getElementById("search-only-with-salary").checked =
        !!search.only_with_salary;
      document.querySelectorAll(".search-level").forEach((el) => {
        el.checked = (search.levels || []).includes(el.value);
      });
      document.querySelectorAll(".search-employment").forEach((el) => {
        el.checked = (search.employment_types || []).includes(el.value);
      });
      document.getElementById("search-posted-within").value = String(search.posted_within_days || 0);
      renderFilterCoverage();
    }).catch(showSettingsLoadError);

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
      renderFallbackOrder(llm);
    }).catch(showSettingsLoadError);

    api("/api/settings/llm/status").then(applyLLMProviderStatus).catch(showSettingsLoadError);
    refreshTelegramConnectStatus();

    api("/api/settings/autostart").then((autostart) => {
      const toggle = document.getElementById("autostart-toggle");
      const note = document.getElementById("autostart-status");
      toggle.checked = autostart.enabled;
      toggle.disabled = !autostart.supported;
      note.textContent = autostart.supported
        ? ""
        : "Не поддерживается на этой ОС.";
    }).catch(showSettingsLoadError);

    api("/api/settings/daemon_service").then((svc) => {
      const toggle = document.getElementById("daemon-service-toggle");
      const note = document.getElementById("daemon-service-status");
      toggle.checked = svc.enabled;
      toggle.disabled = !svc.supported;
      note.textContent = svc.supported
        ? ""
        : "Не поддерживается на этой ОС (или в собранном приложении).";
    }).catch(showSettingsLoadError);

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
    updateFitThresholdPreview();
    document.getElementById("limit-history-retention").value = String(
      limits.application_retention_days || 0
    );
    document.getElementById("limit-cover-letter-style").value = limits.cover_letter_style || "memorable";
    document.getElementById("limit-continuous-cycle").checked = limits.continuous_cycle_enabled;
    document.getElementById("limit-continuous-gap").value = limits.continuous_cycle_gap_minutes || 3;
    renderTotalBudget(status, limits.total_daily_application_limit);
    if (limits.llm_daily_cost_alert_usd != null) {
      document.getElementById("llm-alert-usd").value =
        limits.llm_daily_cost_alert_usd;
    }
    if (limits.llm_daily_token_limit != null) {
      document.getElementById("llm-token-limit").value =
        limits.llm_daily_token_limit;
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
    }).catch(showSettingsLoadError);

    // Площадки — тем же списком, что на Главной; строка открывает ту же
    // шторку. Готовность (чего не хватает) — в тексте строки.
    lastStatus = status;
    const platformCards = document.getElementById("platform-cards");
    const rowFor = (src) => {
      const m = sourceRowModel(src, lastRunNow);
      const missing = (src.readiness && src.readiness.missing) || [];
      if (missing.length) {
        m.dot = "warn";
        m.statusText = `не хватает: ${missing.join(", ")}`;
      }
      if (src.name === "direct") m.name = "Сайты компаний";
      return m;
    };
    const groups = [
      ["Свои каналы", status.sources.filter((x) => OWN_CHANNELS.has(x.name) && x.name !== "telegram")],
      ["Русские площадки", status.sources.filter((x) => !INTL_SOURCES.has(x.name) && !OWN_CHANNELS.has(x.name))],
      ["Зарубежные площадки", status.sources.filter((x) => INTL_SOURCES.has(x.name))],
    ];
    platformCards.innerHTML = groups
      .map(([title, list]) => `<div class="grp">${title}</div>${list.map((x, i) => platformRowHtml(rowFor(x), i)).join("")}`)
      .join("");
    platformCards.querySelectorAll(".platform-row-wrap").forEach((w) => w.setAttribute("draggable", "false"));
    platformCards.querySelectorAll("[data-open-source]").forEach((btn) =>
      btn.addEventListener("click", () => openPlatform(btn.dataset.openSource))
    );

  },

  async telegram() {
    const channelsRevision = telegramChannelsRevision;
    loadTelegramWatch();
    const [status, settings, conversations] = await Promise.all([
      api("/api/telegram/status"),
      api("/api/settings/telegram"),
      api("/api/telegram/conversations"),
    ]);
    applyTelegramAccountStatus(status);
    fillTelegramRules(settings, channelsRevision);

    const unreadCount = conversations.filter((c) => c.unread).length;
    const navBadge = document.getElementById("telegram-unread-badge");
    if (unreadCount > 0) {
      animateCountValue(navBadge, "telegram-unread", unreadCount);
      navBadge.style.display = "";
    } else {
      shownCounts["telegram-unread"] = 0;
      navBadge.textContent = "0";
      navBadge.style.display = "none";
    }

    telegramConversationsCache = conversations;
    if (currentView === "replies") {
      renderRepliesRows();
      updateTalkListCount();
    }
    if (activeTelegramContact && !conversations.some(
      (c) => c.contact.toLowerCase() === activeTelegramContact.toLowerCase()
    )) {
      activeTelegramContact = null;
      updateTelegramComposerState();
      telegramLoadedHistory = { contact: null, messages: [], hasMore: false };
      document.getElementById("tg-chat-panel").style.display = "none";
      document.getElementById("tg-chat-delete").hidden = true;
      document.getElementById("tg-chat-empty").style.display = "";
    }
    // "Выберите диалог слева" в правой панели уместно, только пока
    // список слева не пуст — иначе получаются два взаимоисключающих
    // сообщения одновременно ("диалогов нет" + "выберите один из них").
    const chatEmpty = document.getElementById("tg-chat-empty");
    if (!activeTelegramContact) {
      const previousText = chatEmpty.textContent;
      const wasVisible = chatEmpty.style.display !== "none";
      chatEmpty.textContent = conversations.length
        ? "Выберите диалог слева."
        : "Диалогов пока нет — появятся здесь, как только кто-то напишет.";
      if (!wasVisible || previousText !== chatEmpty.textContent) animateTalkEmptyState();
    }
    renderTelegramConversationRows(conversations);

    if (activeTelegramContact) {
      await openTelegramConversation(activeTelegramContact, false, true, true, false, true);
    }
  },

  async logs() {
    const source = document.getElementById("log-source").value;
    const params = new URLSearchParams({ lines: "300" });
    if (source) params.set("source", source);
    const pre = document.getElementById("log-output");
    const errorPanel = document.getElementById("log-error");
    const loading = document.getElementById("log-loading");
    if (!logsLoaded) {
      loading.hidden = false;
      pre.hidden = true;
    }

    let data;
    try {
      data = await api(`/api/logs?${params}`);
    } catch (err) {
      renderRetryState(errorPanel, `Не удалось загрузить журнал: ${err.message}`, () => render.logs());
      errorPanel.hidden = false;
      pre.hidden = !logsLoaded;
      loading.hidden = true;
      return;
    }
    errorPanel.hidden = true;
    loading.hidden = true;
    pre.hidden = false;
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

function renderTelegramConversationRows(conversations) {
  const list = document.getElementById("tg-conv-list");
  const query = document.getElementById("replies-filter-query")?.value.trim().toLowerCase() || "";
  const shown = query ? conversations.filter((c) =>
    [c.contact, c.company, c.title, c.channel, c.last_message?.text]
      .filter(Boolean).join(" ").toLowerCase().includes(query)
  ) : conversations;
  if (!shown.length) {
    list.innerHTML = `<p class="muted small">${query ? "Диалоги не найдены." : "Пока нет диалогов."}</p>`;
    return;
  }
  list.innerHTML = shown.map((c) => `
    <div class="conv-item${c.contact === activeTelegramContact ? " active" : ""}" data-contact="${escapeHtml(c.contact)}" role="button" tabindex="0">
      ${plogoHtml("telegram")}
      <span class="conv-copy"><span class="conv-contact">${c.unread ? '<span class="conv-unread-dot"></span>' : ""}@${highlightText(c.contact, query)}</span>
      <span class="conv-preview">${highlightText(c.last_message?.text || "", query)}</span></span>
      <small class="conv-time">${c.last_activity_at ? escapeHtml(fmtDay(c.last_activity_at)) : ""}</small>
    </div>`).join("");
  list.querySelectorAll(".conv-item").forEach((el) => {
    el.addEventListener("click", (event) => openTelegramConversation(el.dataset.contact, false, false, false, event.detail > 0));
    el.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openTelegramConversation(el.dataset.contact);
      }
    });
  });
}

// Фильтр по тексту — чисто на клиенте: сервер и так уже отдаёт не
// больше 300 строк за раз, дозапрашивать их под каждую букву поиска
// незачем. Позиция прокрутки сохраняется при автообновлении раз в
// 7с, кроме случая "уже был внизу" — тогда новые строки уезжают вниз
// вместе с прокруткой, как ожидается от live-хвоста лога.
// Формат строки задан в src/logging.py (loguru): "ГГГГ-ММ-ДД ЧЧ:ММ:СС.мс
// | УРОВЕНЬ | модуль:функция:строка - сообщение". По умолчанию строка
// "модуль:функция:строка" — код для разработчика, а не для соискателя,
// который просто хочет знать, что бот сейчас делает. Человеческий вид
// её прячет и убирает DEBUG, "Технические детали" возвращают как есть.
const LOG_LINE_RE = /^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})\.\d+ \| (\w+)\s*\| [^-]*- (.*)$/;
const LOG_LEVEL_ICON = { WARNING: "внимание · ", ERROR: "ошибка · ", CRITICAL: "ошибка · " };

function humanizeLogLine(line) {
  const m = line.match(LOG_LINE_RE);
  // Строки без метки времени — это продолжение (питон-трейсбек: "File
  // ..., line N, in ...", объекты "<... at 0x...>") многострочного
  // ERROR-сообщения от backtrace=True/diagnose=True в src/logging.py.
  // В человеческом виде это чистый шум программиста — прячем, сама
  // ERROR-строка с сутью ошибки уже прошла отдельной строкой выше.
  if (!m) return null;
  const [, , time, level, message] = m;
  if (level === "DEBUG") return null;
  return `${time}  ${LOG_LEVEL_ICON[level] || ""}${message}`;
}

function renderLogLines() {
  const pre = document.getElementById("log-output");
  const query = document.getElementById("log-search").value.trim().toLowerCase();
  const raw = document.getElementById("log-raw-toggle").checked;
  let lines = query
    ? lastLogsLines.filter((l) => l.toLowerCase().includes(query))
    : lastLogsLines;
  if (!raw) {
    lines = lines.map(humanizeLogLine).filter((l) => l !== null);
  }
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
  interview: { title: "Приглашение на интервью", group: "interview" },
  test_task: { title: "Тестовое задание", group: "interview" },
  offer: { title: "Оффер", group: "interview" },
  replied: { title: "Ответили", group: "replied" },
  rejected: { title: "Отказ", group: "rejected" },
};
let repliesKind = "";

let selectedInboxIndex = -1;
let selectedInboxKey = null;
let talkEntries = [];

function inboxEntryKey(entry) {
  const identity = entry.external_id
    ? `id:${entry.external_id}`
    : entry.contact
    ? `contact:${entry.contact}`
    : `link:${entry.link || entry.company || entry.title || ""}`;
  return `${entry.source || entry.channel || ""}|${identity}`;
}

function telegramConversationCount(conversations, inboxEntries) {
  const contacts = new Set();
  for (const conversation of conversations) {
    if (conversation.contact) contacts.add(conversation.contact.toLowerCase());
  }
  for (const entry of inboxEntries) {
    if (entry.channel === "telegram_dm" && entry.contact) contacts.add(entry.contact.toLowerCase());
  }
  return contacts.size;
}

function updateTalkListCount() {
  const badge = document.getElementById("talk-list-count");
  if (!badge) return;
  const conversations = telegramConversationCount(telegramConversationsCache, lastRepliesEntries);
  const otherReplies = lastRepliesEntries.filter((entry) => entry.channel !== "telegram_dm").length;
  const activePosts = tgPostsData.posts.filter((post) => !["hidden", "blocked"].includes(post.status)).length;
  const count = talkListTab === "posts" ? (tgPostsData.total ?? tgPostsData.posts.length) : activePosts + conversations + otherReplies;
  animateCountValue(badge, `talk-list-${talkListTab}`, count);
}

function renderRepliesRows({ animateContent = false } = {}) {
  const list = document.getElementById("replies-rows");
  const query = document.getElementById("replies-filter-query").value.trim().toLowerCase();
  const activeFilters = document.getElementById("replies-active-filters");
  if (activeFilters) {
    activeFilters.innerHTML = query
      ? `<button type="button" class="active-filter-chip" data-clear-replies-query aria-label="Убрать фильтр Поиск: ${escapeHtml(query)}"><span>Поиск: ${escapeHtml(query)}</span><span aria-hidden="true">×</span></button>`
      : "";
    activeFilters.querySelector("[data-clear-replies-query]")?.addEventListener("click", (event) => {
      document.getElementById("replies-filter-query").value = "";
      renderRepliesRows({ animateContent: event.detail > 0 });
      renderTelegramConversationRows(telegramConversationsCache);
    });
  }
  const groupOf = (e) => (INBOX_KIND[e.stage] || INBOX_KIND.replied).group;
  const counts = { interview: 0, replied: 0, rejected: 0, telegram: 0 };
  lastRepliesEntries.forEach((e) => {
    counts[groupOf(e)]++;
  });
  counts.telegram = telegramConversationCount(telegramConversationsCache, lastRepliesEntries);
  const chips = [
    ["", "Главное", counts.interview + counts.replied],
    ["interview", "Интервью и офферы", counts.interview],
    ["replied", "Ответили", counts.replied],
    ["telegram", "Telegram", counts.telegram],
    ["rejected", "Отказы", counts.rejected],
  ];
  const chipBox = document.getElementById("replies-kind");
  chipBox.innerHTML = chips
    .map(([k, label, n]) => `<button type="button" class="chip${k === repliesKind ? " active" : ""}" data-kind="${k}" aria-pressed="${k === repliesKind}">${label} <b data-count="replies-${k}">${n}</b></button>`)
    .join("");
  animateCounts(chipBox);
  chipBox.querySelectorAll("[data-kind]").forEach((b) =>
    b.addEventListener("click", (event) => {
      repliesKind = b.dataset.kind;
      renderRepliesRows({ animateContent: event.detail > 0 });
      lastTgPostsSnapshot = "";
      refreshTelegramPostsPanel();
    })
  );

  const entries = lastRepliesEntries.filter((e) => {
    if (repliesKind === "telegram") {
      if (e.channel !== "telegram_dm") return false;
    } else if (repliesKind ? groupOf(e) !== repliesKind : groupOf(e) === "rejected") return false;
    if (!query) return true;
    return [e.company, e.title, e.text, e.contact, e.source, e.label, e.link]
      .filter(Boolean).some((value) => String(value).toLowerCase().includes(query));
  });
  const nextStageByKey = new Map(lastRepliesEntries.map((entry) => [inboxEntryKey(entry), entry.stage || ""]));
  const changedStages = new Set([...nextStageByKey].filter(([key, stage]) => lastInboxStageByKey.has(key) && lastInboxStageByKey.get(key) !== stage).map(([key]) => key));
  lastInboxStageByKey = nextStageByKey;
  talkEntries = entries;
  if (!entries.length) {
    list.innerHTML = "";
    list.hidden = true;
    chipBox.hidden = (!lastRepliesEntries.length && !telegramConversationsCache.length) || talkListTab === "posts";
    return;
  }
  list.hidden = false;
  chipBox.hidden = talkListTab === "posts";
  const where = (e) =>
    e.channel === "telegram_dm" ? `Telegram @${escapeHtml(e.contact)}`
    : e.channel === "email" ? `Письмо · ${escapeHtml(e.contact)}`
    : escapeHtml(sourceLabel(e.source));
  const logo = (e) => (e.channel === "telegram_dm" ? plogoHtml("telegram") : e.channel === "email" ? plogoHtml("mail") : plogoHtml(e.source));
  list.innerHTML = entries
    .map((e, i) => {
      const kind = INBOX_KIND[e.stage] || INBOX_KIND.replied;
      const preview = e.channel === "telegram_dm" || e.channel === "email" ? e.text : e.title;
      return `<button type="button" class="row talk-row inbox-${kind.group}${e.unread ? " is-unread" : ""}${inboxEntryKey(e) === selectedInboxKey ? " is-selected" : ""}" data-inbox-index="${i}">
        ${logo(e)}
        <span class="row-main">
          <span class="talk-row-top"><span class="row-title">${highlightText(e.company || (e.contact ? "@" + e.contact : "—"), query)}</span><span class="muted small nowrap">${fmtDay(e.at)}</span></span>
          <span class="row-sub"><span class="talk-kind kind-${kind.group}${changedStages.has(inboxEntryKey(e)) ? " status-changed" : ""}">${escapeHtml(kind.title)}</span>${e.unread ? `<span class="tab-badge">новое</span>` : ""}${e.draft ? `<span class="stage-tag">черновик готов</span>` : ""}</span>
          <span class="talk-preview small muted">${highlightText(truncate(preview || where(e), 110), query)}</span>
        </span>
      </button>`;
    })
    .join("");
  if (animateContent && !REDUCE_MOTION) {
    list.classList.remove("talk-list-content-arrive");
    void list.offsetWidth;
    list.classList.add("talk-list-content-arrive");
    list.addEventListener("animationend", (event) => {
      if (event.target === list) list.classList.remove("talk-list-content-arrive");
    }, { once: true });
  }
  list.querySelectorAll("[data-inbox-index]").forEach((btn) =>
    btn.addEventListener("click", (event) => selectInboxItem(Number(btn.dataset.inboxIndex), event.detail > 0))
  );
}

function talkTimelineHtml(entry) {
  const events = [];
  if (entry.applied_at) events.push({ label: "Отклик отправлен", at: entry.applied_at });
  if (entry.sent_at) events.push({ label: entry.channel === "email" ? "Письмо отправлено" : "Сообщение отправлено", at: entry.sent_at });
  if (entry.replied_at) events.push({ label: "Ответ работодателя", at: entry.replied_at });
  else if (entry.stage && (entry.state_at || (entry.channel !== "email" && entry.at))) events.push({ label: (INBOX_KIND[entry.stage] || INBOX_KIND.replied).title, at: entry.state_at || entry.at });
  else if (entry.at) events.push({ label: "Последнее сообщение", at: entry.at });
  events.sort((a, b) => (Date.parse(a.at) || 0) - (Date.parse(b.at) || 0));
  if (!events.length) return "";
  return `<section class="talk-timeline-wrap" aria-label="История событий"><strong class="field-title">История</strong><ol class="talk-timeline">${events.map((event, index) => `<li style="--timeline-index:${index}"><span class="talk-timeline-dot" aria-hidden="true"></span><span><b>${escapeHtml(event.label)}</b><time datetime="${escapeHtml(event.at)}">${escapeHtml(fmtTime(event.at))}</time></span></li>`).join("")}</ol></section>`;
}

function talkContextHtml(e) {
  const where = e.channel === "telegram_dm" ? `Telegram · @${escapeHtml(e.contact)}` : e.channel === "email" ? `Письмо · ${escapeHtml(e.contact)}` : escapeHtml(sourceLabel(e.source));
  const stage = e.external_id ? `<div class="field-block"><div class="field-title">Этап</div><label class="inbox-stage">${stageSelectHtml({ ...e, effective_stage: e.stage })}</label><div class="field-hint">Ставится сам по ответу площадки; поправьте, если бот ошибся.</div></div>` : "";
  const interview = (INBOX_KIND[e.stage] || {}).group === "interview" && e.external_id;
  return `<div class="field-block"><div class="field-title">${escapeHtml(e.company || "—")}</div>
      <div class="field-hint">${escapeHtml(e.title || "")}</div>
      <div class="field-hint">${where}${e.label ? " · " + escapeHtml(e.label) : ""}</div></div>
    ${talkTimelineHtml(e)}
    ${stage}
    <div class="talk-actions">
      ${e.channel === "email" && e.link ? `<a class="btn btn-small" href="${escapeHtml(e.link)}" target="_blank" rel="noopener">Открыть в Gmail ↗</a>` : ""}
      ${e.channel === "telegram_dm" ? `<a class="btn btn-small" href="https://t.me/${encodeURIComponent(e.contact)}" target="_blank" rel="noopener">Открыть в Telegram ↗</a>` : ""}
      ${e.link && e.channel !== "email" ? `<a class="btn btn-small btn-ghost" href="${escapeHtml(e.link)}" target="_blank" rel="noopener">Открыть вакансию ↗</a>` : ""}
      ${interview ? `<button type="button" class="btn btn-small" data-talk-action="prep">Подготовка к интервью</button>` : ""}
      ${interview ? `<button type="button" class="btn btn-small btn-ghost" data-talk-action="calendar">Интервью в календарь</button>` : ""}
      ${e.contact ? blockContactButtonHtml(e.contact) : ""}
    </div>`;
}

function animateTalkTimeline(body) {
  if (REDUCE_MOTION || !body?.querySelector(".talk-timeline li")) return;
  const items = Array.from(body.querySelectorAll(".talk-timeline li"));
  items.forEach((item) => item.classList.remove("is-entering"));
  void body.offsetWidth;
  const generation = String((Number(body.dataset.motionGeneration) || 0) + 1);
  body.dataset.motionGeneration = generation;
  items.forEach((item) => item.classList.add("is-entering"));
  items[items.length - 1]?.addEventListener("animationend", () => {
    if (body.dataset.motionGeneration === generation) items.forEach((item) => item.classList.remove("is-entering"));
  }, { once: true });
}

function showTalkContext(e, animate = false) {
  const body = document.getElementById("talk-context-body");
  body.classList.remove("muted", "small");
  body.innerHTML = e ? talkContextHtml(e) : "";
  if (animate) animateTalkTimeline(body);
  bindStageSelects(body);
  body.querySelectorAll("[data-talk-action]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      if (btn.dataset.talkAction === "block") return; // см. initTalkExtras
      if (btn.dataset.talkAction === "calendar") {
        openCalendarOverlay({ ...e, title: e.title || "" });
        return;
      }
      btn.disabled = true;
      btn.textContent = "Готовлю справку…";
      try {
        const { prep } = await api("/api/applications/prep", { method: "POST", body: JSON.stringify({ source: e.source, external_id: e.external_id }) });
        const panel = document.getElementById("talk-item-panel");
        document.getElementById("tg-chat-panel").style.display = "none";
        document.getElementById("tg-chat-empty").style.display = "none";
        panel.hidden = false;
        panel.innerHTML = `<div class="thread-head"><h3 class="m0">Подготовка: ${escapeHtml(e.company)}</h3><span class="muted small">справка к интервью</span></div><div class="letter-text">${escapeHtml(prep.replace(/\*\*/g, ""))}</div>`;
      } catch (err) {
        showToast(err.message.replace(/^\d+: /, ""), "error");
      } finally {
        btn.disabled = false;
        btn.textContent = "Подготовка к интервью";
      }
    })
  );
  document.getElementById("tg-chat-delete").hidden = !(e && e.channel === "telegram_dm") && !activeTelegramContact;
}

function selectInboxItem(i, animatePane = false) {
  const e = talkEntries[i];
  if (!e) return;
  selectedInboxIndex = i;
  selectedInboxKey = inboxEntryKey(e);
  setTalkMobilePane("thread", animatePane);
  document.querySelectorAll("#replies-rows .talk-row").forEach((r, n) => r.classList.toggle("is-selected", n === i));
  showTalkContext(e, true);
  if (e.channel === "telegram_dm") {
    openTelegramConversation(e.contact, true, false, false, animatePane);
    return;
  }
  activeTelegramContact = null;
  updateTelegramComposerState();
  closeTelegramPost();
  document.querySelectorAll("#tg-conv-list .conv-item").forEach((el) => el.classList.remove("active"));
  document.getElementById("tg-chat-panel").style.display = "none";
  document.getElementById("tg-chat-empty").style.display = "none";
  document.getElementById("tg-chat-delete").hidden = true;
  const kind = INBOX_KIND[e.stage] || INBOX_KIND.replied;
  const panel = document.getElementById("talk-item-panel");
  setTalkMotionVisibility(panel, true, animatePane);
  panel.innerHTML = `<div class="thread-head"><h3 class="m0">${escapeHtml(kind.title)}</h3><span class="muted small">${fmtTime(e.at)}</span></div>
    <div class="field-hint">${escapeHtml([e.company, e.title].filter(Boolean).join(" — "))}</div>
    ${e.text ? `<div class="chat-bubble in">${escapeHtml(e.text)}</div>` : `<div class="letter-text muted">Текст ответа — на сайте площадки. Этап выставлен по статусу отклика.</div>`}
    ${e.draft ? `<div class="fix is-warn"><span class="dot warn"></span><div class="fix-body">Черновик ответа готов — вверху, в «Ждут вашего решения».</div></div>` : ""}`;
}

async function openTelegramConversation(contact, fromInbox = false, keepTab = false, preserveScroll = false, animatePane = false, preservePane = false) {
  if (!keepTab) setTalkListTab("chats", false);
  if (!preservePane) setTalkMobilePane("thread", animatePane);
  const contactChanged = activeTelegramContact !== contact;
  if (contactChanged) {
    document.getElementById("tg-chat-suggestions").innerHTML = "";
    document.getElementById("tg-chat-input").value = "";
    const retry = document.getElementById("tg-chat-retry");
    if (retry) retry.hidden = true;
    const chatStatus = document.getElementById("tg-chat-status");
    chatStatus.textContent = "";
    chatStatus.classList.remove("is-error", "is-success", "is-sending");
    updateTelegramNewMessagesIndicator(0);
    telegramLoadedHistory = { contact, messages: [], hasMore: false };
  }
  activeTelegramContact = contact;
  updateTelegramComposerState();
  closeTelegramPost();
  document.getElementById("talk-item-panel").hidden = true;
  if (!fromInbox) {
    selectedInboxIndex = -1;
    selectedInboxKey = null;
    document.querySelectorAll("#replies-rows .talk-row").forEach((r) => r.classList.remove("is-selected"));
    const match = lastRepliesEntries.find((x) => x.channel === "telegram_dm" && x.contact === contact);
    if (match) showTalkContext(match, contactChanged);
    else {
      const body = document.getElementById("talk-context-body");
      body.innerHTML = `<div class="field-block"><div class="field-title">@${escapeHtml(contact)}</div><div class="field-hint">Telegram · ответов пока нет</div></div><div class="talk-actions"><a class="btn btn-small" href="https://t.me/${encodeURIComponent(contact)}" target="_blank" rel="noopener">Открыть в Telegram ↗</a>${blockContactButtonHtml(contact)}</div>`;
    }
  }
  document.getElementById("tg-chat-delete").hidden = false;
  document
    .querySelectorAll("#tg-conv-list .conv-item")
    .forEach((el) =>
      el.classList.toggle("active", el.dataset.contact === contact)
    );

  const messages = document.getElementById("tg-chat-messages");
  const previouslyLoadedMessages = telegramLoadedHistory.contact === contact
    ? telegramLoadedHistory.messages
    : [];
  const previousScrollTop = messages.scrollTop;
  const stickToBottom = !preserveScroll || shouldStickToBottom(messages);
  const conv = await api(`/api/telegram/conversations/${contact}`);
  document.getElementById("tg-chat-empty").style.display = "none";
  document.getElementById("tg-chat-panel").style.display = "";
  if (contactChanged && animatePane) animateConversationChange(document.getElementById("tg-chat-panel"));
  document.getElementById("tg-chat-contact").textContent = `@${contact}`;

  const older = document.getElementById("tg-chat-older");
  older.hidden = true;
  const visibleMessages = previouslyLoadedMessages.length
    ? mergeTelegramMessages(previouslyLoadedMessages, conv.messages)
    : conv.messages;
  const newlyReceivedKeys = preserveScroll
    ? newerTelegramMessageKeys(previouslyLoadedMessages, conv.messages)
    : new Set();
  syncTelegramMessageBubbles(messages, visibleMessages, newlyReceivedKeys);
  telegramLoadedHistory = {
    contact,
    messages: visibleMessages,
    hasMore: telegramLoadedHistory.contact === contact && telegramLoadedHistory.hasMore,
  };
  if (stickToBottom) messages.scrollTop = messages.scrollHeight;
  else messages.scrollTop = previousScrollTop;
  const newerCount = countNewerTelegramMessages(previouslyLoadedMessages, conv.messages);
  updateTelegramNewMessagesIndicator(stickToBottom ? 0 : newerCount, preserveScroll && !stickToBottom && newerCount > 0);
  // Полная переписка из самого Telegram — и то, что писали через бота, и
  // руками в Telegram (журнал приложения знает только своё). Есть, пока
  // работает шлюз; иначе остаётся журнал приложения.
  api(`/api/telegram/history/${encodeURIComponent(contact)}`)
    .then((h) => {
      if (activeTelegramContact !== contact || h.source !== "telegram") return;
      const previouslyKnownMessages = telegramLoadedHistory.contact === contact
        ? telegramLoadedHistory.messages
        : [];
      const newMessageKeys = newerTelegramMessageKeys(previouslyKnownMessages, h.messages);
      const newMessageCount = newMessageKeys.size;
      const freshIds = new Set(h.messages.map((m) => m.id));
      const old = telegramLoadedHistory.contact === contact
        ? telegramLoadedHistory.messages.filter((m) => !freshIds.has(m.id) && m.id < h.messages[0]?.id)
        : [];
      telegramLoadedHistory = {
        contact,
        messages: [...old, ...h.messages],
        hasMore: old.length ? telegramLoadedHistory.hasMore : h.has_more,
      };
      older.hidden = !telegramLoadedHistory.hasMore;
      const historyStickToBottom = !preserveScroll || shouldStickToBottom(messages);
      const historyScrollTop = messages.scrollTop;
      syncTelegramMessageBubbles(messages, telegramLoadedHistory.messages, newMessageKeys);
      if (historyStickToBottom) messages.scrollTop = messages.scrollHeight;
      else messages.scrollTop = historyScrollTop;
      updateTelegramNewMessagesIndicator(historyStickToBottom ? 0 : newMessageCount, preserveScroll && !historyStickToBottom && newMessageCount > 0);
    })
    .catch(() => {});

  // Открытие треда гасит бейдж "непрочитано" на бэкенде (см.
  // get_telegram_conversation) — обновляем счётчик в шапке вкладки,
  // не дожидаясь следующего полного render.telegram().
  const navBadge = document.getElementById("telegram-unread-badge");
  const remaining = document.querySelectorAll(
    "#tg-conv-list .conv-unread-dot"
  ).length;
  const selected = [...document.querySelectorAll("#tg-conv-list .conv-item")]
    .find((el) => el.dataset.contact === contact);
  const dot = selected?.querySelector(".conv-unread-dot");
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

async function startResumeAudit(general = false) {
  const statusEl = document.getElementById("gen-status");
  const downloadEl = document.getElementById("gen-download");
  const progressEl = document.getElementById("gen-progress");
  const jobUrl = general ? null : document.getElementById("gen-job-url").value.trim() || null;
  if (!jobUrl && !general) {
    showToast("Вставьте ссылку на вакансию — или «Проверить резюме» ниже, без вакансии.", "error");
    return;
  }
  if (general) document.getElementById("gen-status").scrollIntoView({ block: "center", behavior: REDUCE_MOTION ? "auto" : "smooth" });
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

  // Разбор — на самой странице «Мои резюме», под кнопками, а не окном.
  const panel = document.getElementById("resume-audit-overlay");
  panel.hidden = false;
  panel.scrollIntoView({ block: "start", behavior: REDUCE_MOTION ? "auto" : "smooth" });
}

function closeResumeAuditModal() {
  document.getElementById("resume-audit-overlay").hidden = true;
}

function isResumeAuditModalOpen() {
  return false;
}

// Настройки → «Сайты компаний»: переключатели и список компаний.
// Раньше резервные копии (daily_backup, src/utils/backup.py) были
// видны только одной строкой в подсказке "Где хранятся мои данные?" —
// восстановить можно было только вручную в файлах на диске.
async function loadBackups() {
  const el = document.getElementById("backups-list");
  el.innerHTML = `<div class="skeleton" style="height:60px"></div>`;
  const { backups } = await api("/api/backups");
  if (!backups.length) {
    el.innerHTML = emptyStateHtml("Пока нет ни одной копии — появится после первого дня работы бота.");
    return;
  }
  el.innerHTML = backups
    .map(
      (b) => `
    <div class="account-row">
      <span class="account-text"><b>${escapeHtml(backupLabel(b))}</b><span class="muted small">${b.manual ? "вручную · " : ""}${b.files} ${plural(b.files, "файл", "файла", "файлов")} · ${Math.max(1, Math.round(b.size_bytes / 1024))} КБ</span></span>
      <button type="button" class="btn btn-secondary btn-small" data-restore-backup="${escapeHtml(b.date)}">Восстановить</button>
    </div>`
    )
    .join("");
  el.querySelectorAll("[data-restore-backup]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const date = btn.dataset.restoreBackup;
      const ok = await showConfirm(
        `Восстановить данные на состояние ${backupLabel({ date })}? База компаний, рассылки, отклики, переписка и черновики будут заменены копией за эту дату — текущее состояние тоже сохранится отдельным снимком, но проверьте дату перед подтверждением.`
      );
      if (!ok) return;
      btn.disabled = true;
      try {
        await api("/api/backups/restore", {
          method: "POST",
          body: JSON.stringify({ date }),
        });
        showToast("Восстановлено — перезагружаю страницу", "success");
        setTimeout(() => location.reload(), 1200);
      } catch (e) {
        showToast(`Ошибка: ${e.message}`, "error");
        btn.disabled = false;
      }
    });
  });
}

async function loadDirectSettings() {
  const d = await api("/api/direct/summary");
  document.getElementById("direct-wwr").checked = d.wwr;
  document.getElementById("direct-hn").checked = d.hn;
  document.getElementById("direct-talanto").checked = d.talanto;
  document.getElementById("direct-hirify").checked = d.hirify;
  loadDirectCompanies();
}

async function saveDirectSetting(e) {
  const field = {
    "direct-wwr": "wwr",
    "direct-hn": "hn",
    "direct-talanto": "talanto",
    "direct-hirify": "hirify",
  }[e.target.id];
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
  if (!document.getElementById(paneId)) paneId = "settings-search";
  if (paneId === "settings-direct") loadDirectSettings().catch(() => {});
  if (paneId === "settings-backups") loadBackups().catch(() => {});
  if (paneId === "settings-auto") loadAutoPane().catch(() => {});
  if (paneId === "settings-resume-short") renderSettingsResumeSummary().catch(() => {});
  if (paneId === "settings-look") fillLookPane();
  if (paneId === "settings-tg-quick") loadTelegramWatch();
  hideSettingsSearch();
  document.querySelectorAll("#settings-jump button").forEach((b) => {
    const isTarget = b.dataset.settingsTab === paneId;
    b.classList.toggle("active", isTarget);
    b.setAttribute("aria-selected", String(isTarget));
  });
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
// Изначально писалось только для "Вакансий" — тот же градиент нужен
// любой широкой таблице (напр. "по источникам" в Аналитике), поэтому
// это теперь общая функция плюс делегированный слушатель ниже, а не
// разводка под каждую таблицу отдельно.
function updateTableScrollHint(wrap) {
  if (!wrap) return;
  const overflowing =
    wrap.scrollWidth > wrap.clientWidth + 1 &&
    wrap.scrollLeft < wrap.scrollWidth - wrap.clientWidth - 1;
  wrap.classList.toggle("has-overflow-right", overflowing);
}

function updateHistoryScrollHint() {
  updateTableScrollHint(document.getElementById("history-table-wrap"));
}

function updateAllTableScrollHints() {
  document.querySelectorAll(".table-wrap").forEach(updateTableScrollHint);
}

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
function emptyStateHtml(message, animate = false) {
  return `<div class="empty-state${animate && !REDUCE_MOTION ? " empty-state-enter" : ""}">
    <svg viewBox="0 0 40 40" fill="none" width="36" height="36">
      <circle cx="20" cy="20" r="17" stroke="currentColor" stroke-width="1.6" stroke-dasharray="3 4" opacity="0.3"/>
      <circle cx="20" cy="20" r="10" stroke="currentColor" stroke-width="1.6" opacity="0.35"/>
    </svg>
    <p>${escapeHtml(message)}</p>
  </div>`;
}

function renderRetryState(container, message, retry, elementName = "div") {
  if (!container) return;
  const state = document.createElement(elementName);
  state.className = "inline-retry";
  state.setAttribute("role", "alert");
  const text = document.createElement("span");
  text.textContent = message || "Не удалось загрузить данные.";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn btn-small";
  button.textContent = "Повторить";
  button.addEventListener("click", async () => {
    try {
      await withButtonLoading(button, retry);
    } catch (err) {
      if (text.isConnected) text.textContent = `Повторить не удалось: ${err.message}`;
    }
  });
  state.append(text, button);
  container.replaceChildren(state);
}

function showSettingsLoadError(error) {
  const container = document.getElementById("settings-load-error");
  if (!container) return;
  container.hidden = false;
  renderRetryState(container, `Не удалось загрузить часть настроек: ${error.message}`, () => render.settings());
}

// Всплывающие сообщения этого окна — в «Уведомлениях» (вкладка «В окне»):
// пропустили уведомление — его можно перечитать.
const toastLog = [];
function logToast(message, type) {
  toastLog.unshift({ at: new Date().toISOString(), text: String(message), kind: type === "error" ? "failure" : "activity", status: "window" });
  toastLog.length = Math.min(toastLog.length, 50);
}

function revealToast(el) {
  if (REDUCE_MOTION) {
    el.classList.add("is-visible");
    return;
  }
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (el.isConnected) el.classList.add("is-visible");
  }));
}

function dismissToast(el) {
  if (!el?.isConnected) return;
  const finish = () => el.remove();
  el.classList.add("is-closing");
  setTimeout(finish, REDUCE_MOTION ? 30 : 220);
}

function showToast(message, type = "info", duration = 3500) {
  logToast(message, type);
  const container = document.getElementById("toast-container");
  if (!container) return;
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.style.setProperty("--toast-duration", `${Math.max(1, duration)}ms`);
  el.innerHTML = `<span class="toast-dot"></span><span>${escapeHtml(message)}</span>`;
  container.appendChild(el);
  revealToast(el);
  setTimeout(() => dismissToast(el), duration);
}

// «Сохранено» с кнопкой «Отменить»: изменение уже записано, отмена
// возвращает прежнее значение.
function showSavedToast(message, undo = null, duration = 6000) {
  logToast(message, "success");
  const container = document.getElementById("toast-container");
  if (!container) return;
  const el = document.createElement("div");
  el.className = "toast success";
  el.style.setProperty("--toast-duration", `${Math.max(1, duration)}ms`);
  el.innerHTML = `<svg class="toast-check" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="m3.5 8.5 3 3 6-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><span>${escapeHtml(message)}</span>${undo ? `<button type="button" class="toast-action">Отменить</button>` : ""}`;
  container.appendChild(el);
  revealToast(el);
  const timer = setTimeout(() => dismissToast(el), duration);
  el.querySelector(".toast-action")?.addEventListener("click", async () => {
    clearTimeout(timer);
    dismissToast(el);
    try {
      await undo();
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
  });
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
  const scaleX = parentRect.width ? btnRect.width / parentRect.width : 1;
  const scaleY = parentRect.height ? btnRect.height / parentRect.height : 1;
  indicator.style.transform = `translate(${x}px, ${y}px) scale(${scaleX}, ${scaleY})`;
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
// Разделы, которые сохраняются сами: [контейнер, скрытая кнопка
// «Сохранить», которую нажимает автосохранение]. Кнопки читают значения
// полей по id, поэтому «Отменить» просто возвращает полям прежние
// значения и сохраняет ещё раз.
const AUTOSAVE = [
  ["settings-search", "search-save"],
  ["settings-exclude", "search-save"],
  ["settings-limits", "limits-save"],
  ["settings-llm-costs", "limits-save"],
  ["settings-tg-quick", "tgq-save"],
  ["settings-outreach", "outreach-save"],
  ["tg-rules-panel", "tg-settings-save"],
  ["tg-source-auto", "tg-settings-save"],
  ["settings-llm-provider-block", "llm-provider-save"],
];

function snapshotFields(container) {
  const snap = {};
  container.querySelectorAll("input[id], select[id], textarea[id]").forEach((el) => {
    if (el.type === "file" || el.type === "password") return;
    if (el.type === "checkbox" || el.type === "radio") snap[el.id] = el.checked;
    else if (el.multiple) snap[el.id] = Array.from(el.selectedOptions).map((o) => o.value);
    else snap[el.id] = el.value;
  });
  const active = container.querySelector("#provider-grid .provider-card.active");
  if (active) snap.__provider = active.dataset.provider;
  return snap;
}

function restoreFields(container, snap) {
  if (snap.__provider) applyLLMSelection(snap.__provider, snap["llm-model"]);
  Object.entries(snap).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (!el || id.startsWith("__")) return;
    if (el.type === "checkbox" || el.type === "radio") el.checked = value;
    else if (el.multiple) Array.from(el.options).forEach((o) => (o.selected = value.includes(o.value)));
    else el.value = value;
    if (el.tagName === "TEXTAREA" && el.dataset.tagInputInit) renderTagChips(el);
  });
}

function initAutosave() {
  AUTOSAVE.forEach(([paneId, btnId]) => {
    const pane = document.getElementById(paneId);
    const btn = document.getElementById(btnId);
    if (!pane || !btn) return;
    let before = null;
    let timer = null;
    const loaded = () => !pane.dataset.needsLoad || pane.dataset.loaded === "1";
    // Снимок «как было» — до первой правки: фокус или нажатие в разделе.
    const remember = () => {
      if (!before && loaded()) before = snapshotFields(pane);
    };
    pane.addEventListener("focusin", remember);
    pane.addEventListener("pointerdown", remember);
    pane.addEventListener("change", (e) => {
      if (e.target.type === "file" || e.target.type === "password") return;
      if (e.target.id === "tg-channels") return; // сохраняется канал-специфичной очередью
      if (!loaded()) return; // ещё не загрузили — не затираем пустым
      if (e.target.closest(".no-autosave")) return;
      clearTimeout(timer);
      const field = e.target;
      const prev = before;
      timer = setTimeout(async () => {
        btn.click();
        await new Promise((r) => setTimeout(r, 700));
        const statusEl = btn.parentElement.querySelector('[id$="-status"]');
        if (statusEl && /ошибка/i.test(statusEl.textContent || "")) {
          showToast(statusEl.textContent, "error", 6000);
          return;
        }
        before = snapshotFields(pane);
        showSavedToast("Сохранено", prev
          ? async () => {
              restoreFields(pane, prev);
              btn.click();
              before = prev;
              showToast("Вернул как было", "info");
            }
          : null);
        if (field.classList) {
          field.classList.remove("save-flash");
          void field.offsetWidth;
          field.classList.add("save-flash");
        }
      }, 700);
    });
  });
}

// ---------- Настройки: «Отклики и переписка», «Мои резюме», «Вид» ----------

async function loadAutoPane() {
  const [status, salary, search] = await Promise.all([
    api("/api/status"),
    api("/api/settings/salary"),
    api("/api/settings/search"),
  ]);
  lastStatus = status;
  renderAutoAll(status);
  renderAutoChat(status);
  const hh = status.sources.find((x) => x.name === "headhunter") || {};
  const set = (id, prop, value) => {
    const el = document.getElementById(id);
    if (el) el[prop] = value;
  };
  set("hh-auto-reply", "checked", !!hh.auto_reply);
  set("hh-cover-to-chat", "checked", !!hh.chat_cover_letter_followup);
  set("hh-auto-bump", "checked", !!hh.auto_bump_resume);
  set("hh-auto-reminder", "checked", !!hh.auto_reminder);
  set("hh-reminder-days", "value", hh.reminder_follow_up_days ?? 7);
  set("hh-salary-expectations", "value", salary.hh_salary_expectations || "");
  set("search-once-per-company", "checked", !!search.apply_once_at_company);
}

function initAutoPane() {
  const hhSwitch = (id, field, on, off) => {
    const box = document.getElementById(id);
    box?.addEventListener("change", async () => {
      const v = box.checked;
      await saveSourceSettings("headhunter", { [field]: v }, v ? on : off, { [field]: !v });
      loadAutoPane();
    });
  };
  hhSwitch("hh-auto-reply", "auto_reply", "автоответ в чате включён", "автоответ в чате выключен");
  hhSwitch("hh-cover-to-chat", "chat_cover_letter_followup", "письмо в чат после отклика включено", "письмо в чат после отклика выключено");
  hhSwitch("hh-auto-bump", "auto_bump_resume", "поднимать резюме", "не поднимать резюме");
  hhSwitch("hh-auto-reminder", "auto_reminder", "напоминания уходят сами", "напоминания ждут вашего «Отправить»");
  document.getElementById("hh-reminder-days")?.addEventListener("change", (e) => {
    saveSourceSettings("headhunter", { reminder_follow_up_days: Math.max(0, parseInt(e.target.value, 10) || 0) }, "напоминание · сохранено");
  });
  const salary = document.getElementById("hh-salary-expectations");
  salary?.addEventListener("change", async () => {
    try {
      await api("/api/settings/salary", { method: "POST", body: JSON.stringify({ hh_salary_expectations: salary.value.trim() }) });
      showSavedToast("Зарплата для ответов HR · сохранено");
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
  });
  const once = document.getElementById("search-once-per-company");
  once?.addEventListener("change", async () => {
    const v = once.checked;
    const post = (value) => api("/api/settings/search", { method: "POST", body: JSON.stringify({ apply_once_at_company: value }) });
    try {
      await post(v);
      showSavedToast(v ? "Один отклик в одну компанию" : "Можно несколько откликов в одну компанию", async () => {
        await post(!v);
        once.checked = !v;
      });
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
      once.checked = !v;
    }
  });
}

async function renderSettingsResumeSummary() {
  const el = document.getElementById("settings-resume-summary");
  if (!el) return;
  const r = await api("/api/resumes");
  const file = (f, fallback) => (f.exists ? `<span class="mono small">${escapeHtml(f.name)}</span>` : `<span class="${fallback ? "muted" : "err-text"} small">${fallback || "не загружено"}</span>`);
  el.innerHTML = `
    <div class="kv"><span>Резюме на русском — HH, GetMatch, Habr, Telegram</span>${file(r.primary)}</div>
    <div class="kv"><span>Резюме на английском — LinkedIn и зарубежные</span>${file(r.linkedin, "берётся основное")}</div>
    <div class="kv"><span>Дополнительные — выбор в чате и рассылке</span><span class="mono small">${r.extra.length || "нет"}</span></div>`;
}

function fillLookPane() {
  let theme = "system";
  let density = "comfortable";
  let motion = "system";
  try {
    theme = localStorage.getItem("cj-theme") || "system";
    density = localStorage.getItem("cj-density") || "comfortable";
    motion = localStorage.getItem("cj-motion") || "system";
  } catch (e) {}
  document.getElementById("look-theme").value = theme;
  document.getElementById("look-density").value = density;
  document.getElementById("look-motion").value = motion;
}

function initLookPane() {
  document.getElementById("look-theme").addEventListener("change", (e) => {
    setTheme(e.target.value, e.target);
    showSavedToast("Тема сохранена");
  });
  document.getElementById("look-density").addEventListener("change", (e) => {
    const compact = e.target.value === "compact";
    if (compact) document.documentElement.dataset.density = "compact";
    else delete document.documentElement.dataset.density;
    try {
      localStorage.setItem("cj-density", e.target.value);
    } catch (err) {}
    showSavedToast(compact ? "Компактная плотность" : "Обычная плотность");
  });
  document.getElementById("look-motion").addEventListener("change", (e) => {
    const reduce = e.target.value === "reduce";
    if (reduce) document.documentElement.dataset.motion = "reduce";
    else delete document.documentElement.dataset.motion;
    try {
      localStorage.setItem("cj-motion", e.target.value);
    } catch (err) {}
    syncReducedMotionPreference(e.target.value);
    showSavedToast(reduce ? "Анимации выключены" : "Анимации как в системе");
  });
}

// ---------- Поиск по настройкам ----------

function settingsSearchIndex() {
  const items = [];
  let group = "";
  const groupOf = {};
  document.querySelectorAll("#settings-jump > *").forEach((el) => {
    if (el.classList.contains("settings-jump-label")) group = el.textContent.trim();
    else if (el.dataset.settingsTab) groupOf[el.dataset.settingsTab] = { group, name: el.textContent.trim() };
  });
  document.querySelectorAll(".settings-pane").forEach((pane) => {
    const where = groupOf[pane.id] || { group: "", name: pane.querySelector("h3")?.textContent || "" };
    pane.querySelectorAll(".field-row, .field-block").forEach((field, i) => {
      const title = field.querySelector(".field-title")?.textContent.trim();
      if (!title) return;
      const hint = field.querySelector(".field-hint")?.textContent.trim() || "";
      items.push({ pane: pane.id, field, title, hint, path: `${where.group} → ${where.name}`, key: `${pane.id}:${i}` });
    });
  });
  return items;
}

let settingsSearchActiveIndex = 0;

function hideSettingsSearch() {
  const box = document.getElementById("settings-search-results");
  if (!box || box.hidden) return;
  box.hidden = true;
  document.querySelector(".settings-content")?.classList.remove("is-searching");
  const input = document.getElementById("settings-find-input");
  input?.setAttribute("aria-expanded", "false");
  input?.removeAttribute("aria-activedescendant");
}

function updateSettingsSearchActive() {
  const list = document.getElementById("settings-search-list");
  const input = document.getElementById("settings-find-input");
  if (!list || !input) return;
  const options = [...list.querySelectorAll('[role="option"]')];
  options.forEach((option, index) => {
    const active = index === settingsSearchActiveIndex;
    option.setAttribute("aria-selected", String(active));
    if (active) input.setAttribute("aria-activedescendant", option.id);
  });
  if (!options.length) input.removeAttribute("aria-activedescendant");
  options[settingsSearchActiveIndex]?.scrollIntoView({ block: "nearest" });
}

function openSettingsSearchHit(hitIndex) {
  const items = document.getElementById("settings-search-list")?.__items || [];
  const item = items[hitIndex];
  if (!item) return;
  const input = document.getElementById("settings-find-input");
  input.value = "";
  hideSettingsSearch();
  switchSettingsTab(item.pane);
  let parent = item.field.parentElement;
  while (parent) {
    if (parent.tagName === "DETAILS") parent.open = true;
    parent = parent.parentElement;
  }
  item.field.scrollIntoView({ block: "center", behavior: REDUCE_MOTION ? "auto" : "smooth" });
  item.field.classList.remove("field-found");
  void item.field.offsetWidth;
  item.field.classList.add("field-found");
  item.field.querySelector("input, select, textarea, button")?.focus({ preventScroll: true });
}

function renderSettingsSearch(query) {
  const box = document.getElementById("settings-search-results");
  const input = document.getElementById("settings-find-input");
  const q = query.trim().toLowerCase();
  if (!q) {
    hideSettingsSearch();
    return;
  }
  const words = q.split(/\s+/);
  const found = settingsSearchIndex().filter((it) => {
    const text = `${it.title} ${it.hint} ${it.path}`.toLowerCase();
    return words.every((w) => text.includes(w));
  });
  box.hidden = false;
  input.setAttribute("aria-expanded", "true");
  settingsSearchActiveIndex = 0;
  document.querySelector(".settings-content").classList.add("is-searching");
  box.innerHTML = `<div class="card-head"><h3>${found.length ? `Найдено настроек: ${found.length}` : "Ничего не нашлось"}</h3><span class="muted small">${found.length ? "нажмите — откроется раздел, и поле подсветится" : "попробуйте «лимит», «резюме» или «Telegram»"}</span></div>
    <div class="settings-hits" id="settings-search-list" role="listbox" aria-label="Найденные настройки">${found
      .slice(0, 40)
      .map((it, i) => {
        const meta = `${it.path}${it.hint ? " · " + truncate(it.hint, 90) : ""}`;
        return `<div id="settings-option-${i}" class="row settings-hit" role="option" aria-selected="${i === 0}" data-hit="${i}" tabindex="-1"><span class="row-main"><span class="row-title">${highlightText(it.title, q)}</span><span class="row-sub">${highlightText(meta, q)}</span></span>${CHEVRON_SVG}</div>`;
      })
      .join("")}</div>`;
  const list = document.getElementById("settings-search-list");
  list.__items = found.slice(0, 40);
  list.querySelectorAll("[data-hit]").forEach((option) => {
    option.addEventListener("click", () => openSettingsSearchHit(Number(option.dataset.hit)));
    option.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openSettingsSearchHit(Number(option.dataset.hit));
      }
    });
  });
  updateSettingsSearchActive();
}

function initSettingsSearch() {
  const input = document.getElementById("settings-find-input");
  if (!input) return;
  input.addEventListener("input", () => renderSettingsSearch(input.value));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      input.value = "";
      hideSettingsSearch();
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      const items = document.getElementById("settings-search-list")?.__items || [];
      if (!items.length) return;
      e.preventDefault();
      const direction = e.key === "ArrowDown" ? 1 : -1;
      settingsSearchActiveIndex = (settingsSearchActiveIndex + direction + items.length) % items.length;
      updateSettingsSearchActive();
    } else if (e.key === "Enter") {
      e.preventDefault();
      openSettingsSearchHit(settingsSearchActiveIndex);
    }
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

let sidebarTransitionTimer = null;

function sidebarCanCollapse() {
  return !window.matchMedia("(max-width: 760px)").matches;
}

function restoreSidebarCollapse() {
  const sidebar = document.querySelector(".sidebar");
  const collapsed = localStorage.getItem("cj-sidebar-collapsed") === "1" && sidebarCanCollapse();
  sidebar.classList.toggle("collapsed", collapsed);
}

function finishSidebarTransition(sidebar) {
  clearTimeout(sidebarTransitionTimer);
  sidebar.classList.remove("is-transitioning");
  repositionTabIndicators();
}

function toggleSidebarCollapse() {
  if (!sidebarCanCollapse()) return;
  const sidebar = document.querySelector(".sidebar");
  const collapsed = !sidebar.classList.contains("collapsed");
  sidebar.classList.add("is-transitioning");
  sidebar.classList.toggle("collapsed", collapsed);
  localStorage.setItem("cj-sidebar-collapsed", collapsed ? "1" : "0");

  const onTransitionEnd = (event) => {
    if (event.target === sidebar && event.propertyName === "width") {
      sidebar.removeEventListener("transitionend", onTransitionEnd);
      finishSidebarTransition(sidebar);
    }
  };
  sidebar.addEventListener("transitionend", onTransitionEnd);
  clearTimeout(sidebarTransitionTimer);
  sidebarTransitionTimer = setTimeout(() => {
    sidebar.removeEventListener("transitionend", onTransitionEnd);
    finishSidebarTransition(sidebar);
  }, 350);
}

function initSidebarCollapse() {
  document
    .getElementById("sidebar-collapse-toggle")
    .addEventListener("click", toggleSidebarCollapse);
  window.matchMedia("(max-width: 760px)").addEventListener("change", () => {
    const sidebar = document.querySelector(".sidebar");
    sidebar.classList.remove("is-transitioning");
    restoreSidebarCollapse();
    requestAnimationFrame(repositionTabIndicators);
  });
}

// ---------- Командная палитра ----------

let commandActiveIndex = 0;

function collectCommandItems(query) {
  const items = [];
  const status = lastStatus;
  if (status) {
    status.sources
      .filter((s) => s.name !== "telegram")
      .forEach((s) => items.push({ label: `${s.name === "direct" ? "Сайты компаний" : sourceLabel(s.name)}: настройки`, hint: "Площадка", action: () => { switchTab("overview"); openPlatform(s.name); } }));
  }
  items.push(
    { label: "Telegram-парсер: состояние", hint: "Площадка", action: () => { switchTab("overview"); openTelegramDrawer(); } },
    { label: "Рассылка по почте: что сейчас", hint: "Площадка", action: () => { switchTab("overview"); openMailDrawer(); } },
    { label: "Только искать, без откликов", hint: "Режим", action: () => setHomeMode("search") },
    { label: "Снова откликаться", hint: "Режим", action: () => setHomeMode("apply") },
    { label: status?.daemon_running ? "Остановить бота" : "Запустить бота", hint: "Действие", action: () => document.getElementById("daemon-toggle").click() },
    { label: status?.pause_all?.paused ? "Снять паузу" : "Пауза на всё", hint: "Действие", action: () => setPauseAll(!status?.pause_all?.paused) },
    { label: "Уведомления", hint: "История", action: () => openNotifications() },
    { label: "Сделать резервную копию сейчас", hint: "Настройки", action: () => { gotoSettings("settings-backups"); document.getElementById("backup-now")?.click(); } },
    { label: "Тема: светлая", hint: "Вид", ui: "shell.theme", action: () => setTheme("light") },
    { label: "Тема: тёмная", hint: "Вид", ui: "shell.theme", action: () => setTheme("dark") },
    { label: "Тема: как в системе", hint: "Вид", ui: "shell.theme", action: () => setTheme("system") },
    { label: "Как пользоваться", hint: "Помощь", action: () => document.getElementById("help-dialog").showModal() },
    { label: "Горячие клавиши", hint: "Помощь", action: () => openShortcutsOverlay() }
  );
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
    // База компаний (1500+ строк) — раньше палитра искала только по
    // разделам/вакансиям, будто половины данных не существует; та же
    // мультиполевая логика, что уже в renderContactsList (компания/HR/
    // сайт/контакты/вакансии), просто здесь только для подсказки.
    lastContacts
      .filter((c) =>
        [c.company, c.hr, c.website, ...(c.contacts || []).map((x) => x.value), ...(c.vacancies || []).map((v) => v.title)]
          .filter(Boolean)
          .some((v) => v.toLowerCase().includes(q))
      )
      .slice(0, 8)
      .forEach((c) => {
        items.push({
          label: c.company || c.hr || c.website || "Компания без названия",
          hint: "База компаний",
          action: () => {
            document.getElementById("contacts-filter-query").value = c.company || "";
            switchTab("contacts");
          },
        });
      });
  }
  return items;
}

function updateCommandActive(results) {
  results.querySelectorAll(".command-item").forEach((el, i) => {
    const active = i === commandActiveIndex;
    el.classList.toggle("active", active);
    el.setAttribute("aria-selected", String(active));
  });
  const activeItem = results.querySelector(`#command-option-${commandActiveIndex}`);
  const input = document.getElementById("command-input");
  if (activeItem) input.setAttribute("aria-activedescendant", activeItem.id);
  else input.removeAttribute("aria-activedescendant");
}

function renderCommandResults(query) {
  const results = document.getElementById("command-results");
  const items = collectCommandItems(query).filter((it) =>
    it.label.toLowerCase().includes(query.toLowerCase())
  );
  commandActiveIndex = 0;
  results.__items = items;
  if (!items.length) {
    results.innerHTML = `<div class="command-empty" role="status">Ничего не найдено</div>`;
    document.getElementById("command-input").removeAttribute("aria-activedescendant");
    return;
  }
  results.innerHTML = items
    .map(
      (it, i) =>
        `<div id="command-option-${i}" class="command-item${i === 0 ? " active" : ""}" role="option" aria-selected="${i === 0}" data-index="${i}"><span>${highlightText(it.label, query)}</span><span class="muted">${escapeHtml(it.hint)}</span></div>`
    )
    .join("");
  document.getElementById("command-input").setAttribute("aria-activedescendant", "command-option-0");
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
  overlay.classList.add("is-instant");
  overlay.style.display = "flex";
  input.setAttribute("aria-expanded", "true");
  input.value = "";
  renderCommandResults("");
  trapFocus(overlay);
  input.focus();
}

function closeCommandPalette() {
  document.getElementById("command-input").setAttribute("aria-expanded", "false");
  document.getElementById("command-input").removeAttribute("aria-activedescendant");
  hideOverlay(document.getElementById("command-overlay"));
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
      hideOverlay(overlay);
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

let drawerCloseTimer = null;

function closePlatformDrawer() {
  const overlay = document.getElementById("platform-drawer-overlay");
  if (overlay.style.display === "none") return;
  openDrawerSource = null;
  drawerDirty = false;
  releaseFocusTrap(document.getElementById("platform-drawer"));
  if (REDUCE_MOTION) {
    overlay.style.display = "none";
    overlay.classList.remove("is-closing");
    return;
  }
  overlay.classList.add("is-closing");
  clearTimeout(drawerCloseTimer);
  drawerCloseTimer = setTimeout(() => {
    overlay.style.display = "none";
    overlay.classList.remove("is-closing");
  }, 240);
}

function isPlatformDrawerOpen() {
  return document.getElementById("platform-drawer-overlay").style.display !== "none";
}

// ---------- Вакансии: чипы, шторка «Почему бот так решил», клавиши ----------

let historyChip = "all";
let historyRows = [];
let historySelected = -1;
let jobThresholds = null;
let lastHistoryViewKey = "";
function historyEntryKey(entry) {
  return `${entry.source || ""}|${entry.id ?? entry.external_id ?? entry.link ?? entry.url ?? `${entry.company || ""}|${entry.title || ""}`}`;
}
function historyStatusSignature(entry) {
  return `${entry.status || ""}|${entry.effective_stage || ""}|${entry.applied_at || ""}`;
}
const isSkipped = (e) => (e.status || "").startsWith("skipped");
const HISTORY_CHIPS = {
  all: { label: "Все", test: (e) => e.effective_stage !== "rejected" },
  applied: { label: "Отправлено", test: (e) => e.status === "applied" && !e.effective_stage },
  replied: { label: "Ответили", test: (e) => e.effective_stage === "replied" },
  interview: { label: "Интервью", test: (e) => ["interview", "test_task", "offer"].includes(e.effective_stage) },
  skipped: { label: "Пропущено", test: isSkipped },
  dry_run: { label: "Тестовый прогон", test: (e) => e.status === "dry_run" },
  rejected: { label: "Отказ", test: (e) => e.effective_stage === "rejected" },
};

function renderHistoryChips(all) {
  const box = document.getElementById("history-chips");
  box.innerHTML = Object.entries(HISTORY_CHIPS)
    .map(([k, c]) => {
      const n = all.filter(c.test).length;
      if (!n && k !== "all" && k !== historyChip) return "";
      return `<button type="button" class="chip${k === historyChip ? " active" : ""}" data-chip="${k}" aria-pressed="${k === historyChip}">${c.label} <b>${n}</b></button>`;
    })
    .join("");
  box.querySelectorAll("[data-chip]").forEach((b) =>
    b.addEventListener("click", (event) => {
      historyChip = b.dataset.chip;
      // Старые фильтры — для совместимости со ссылками на «Вакансии».
      document.getElementById("filter-show-rejected").checked = historyChip === "rejected";
      lastHistorySnapshot = "";
      render.history({ animateRows: event.detail > 0 });
    })
  );
}

function jobVerdict(e) {
  if (e.score == null) return { tone: "flat", text: "Оценки нет — площадка не отдала описание или ИИ был недоступен" };
  const t = jobThresholds || { min: 4, fit: 7 };
  if (e.score >= t.fit) return { tone: "good", text: "Уверенное совпадение — отклик с письмом" };
  if (e.score >= t.min) return { tone: "warn", text: "Среднее совпадение — отклик помечен как слабый" };
  return { tone: "bad", text: "Слабое совпадение — бот не откликался" };
}

function jobStageButtons(e) {
  if (!e.external_id || e.status !== "applied") return "";
  const current = e.effective_stage ?? "";
  const opts = [["", "Без ответа"], ...Object.entries(STAGE_LABELS)];
  return `<div class="field-block" data-ui="jobs.stage"><div class="field-title">Этап</div>
    <div class="stage-buttons" role="radiogroup" aria-label="Этап">${opts
      .map(([v, l]) => `<button type="button" class="chip${v === current ? " active" : ""}" role="radio" aria-checked="${v === current}" data-set-stage="${v}">${l[0].toUpperCase() + l.slice(1)}</button>`)
      .join("")}</div>
    <div class="field-hint">Ставится сам по ответу площадки. Поправьте, если бот ошибся; «Без ответа» снимает ручную отметку.</div></div>`;
}

function jobDrawerBody(e, tab) {
  const v = jobVerdict(e);
  const t = jobThresholds || { min: 4, fit: 7 };
  if (tab === "letter") {
    return `<div class="field-block" data-ui="jobs.letter">
      <div class="field-hint">${e.status === "applied" ? `Это письмо ушло вместе с откликом ${fmtTime(e.applied_at)}.` : "Письмо не отправлялось — так бы оно выглядело."}</div>
      <div class="letter-text">${e.cover_letter ? escapeHtml(e.cover_letter) : `<span class="muted">Письма нет: отклик без письма или запись старше срока хранения.</span>`}</div>
      ${e.cover_letter ? `<div class="fix-actions"><button type="button" class="btn btn-small" data-job-action="copy-letter">Скопировать</button></div>` : ""}
    </div>`;
  }
  if (tab === "prep") {
    const prefill = e.source === "direct" && e.status === "dry_run" && /greenhouse\.io|lever\.co/.test(e.link);
    return `<div class="field-stack">
      ${e.external_id ? `<button type="button" class="btn" data-job-action="prep" data-ui="jobs.prep">Справка к интервью: что спросят и что подтянуть</button>` : ""}
      <div id="job-prep-body" class="letter-text" hidden></div>
      ${e.external_id ? `<div class="fix-actions">
        <button type="button" class="btn btn-small" data-job-action="trainer" data-ui="jobs.trainer">Тренажёр вопросов</button>
        <button type="button" class="btn btn-small" data-job-action="calendar" data-ui="jobs.calendar">Интервью в календарь</button>
      </div>` : ""}
      ${prefill ? `<button type="button" class="btn btn-small" data-job-action="prefill" data-ui="jobs.prefill">Заполнить форму отклика</button>` : ""}
      ${e.gaps && e.gaps.length ? `<div class="field-block"><div class="field-title">Что подтянуть</div><div class="field-hint">То, чего нет в резюме, но есть в вакансии:</div><ul class="plain-list">${e.gaps.map((g) => `<li>${escapeHtml(g)}</li>`).join("")}</ul></div>` : ""}
    </div>`;
  }
  return `<div class="verdict" data-ui="jobs.score">
      <div class="verdict-score"><span class="mono">${e.score ?? "—"}</span><span class="muted"> / 10</span></div>
      <div class="verdict-text"><span class="dot ${v.tone === "good" ? "ok" : v.tone === "warn" ? "warn" : v.tone === "bad" ? "error" : "idle"}"></span>${escapeHtml(v.text)}</div>
      <div class="field-hint">ниже ${t.min} — пропуск · от ${t.fit} — уверенное совпадение (Настройки → Лимиты и оценка)</div>
    </div>
    ${e.skills && e.skills.length ? `<div class="field-block"><div class="field-title">Навыки из вакансии</div><div class="tag-row">${e.skills.map((x) => `<span class="tag">${escapeHtml(x)}</span>`).join("")}</div></div>` : ""}
    <div class="field-block"><div class="field-title">Не хватает</div>${e.gaps && e.gaps.length ? `<ul class="plain-list">${e.gaps.map((g) => `<li>${escapeHtml(g)}</li>`).join("")}</ul>` : `<div class="field-hint">всё основное в резюме есть</div>`}</div>
    ${jobStageButtons(e)}
    ${jobMistakeHtml(e)}
    ${e.contacts && e.contacts.length ? `<div class="field-block" data-ui="jobs.contacts"><div class="field-title">Контакты из вакансии</div>${e.contacts.map((c) => `<a href="mailto:${escapeHtml(c)}">${escapeHtml(c)}</a>`).join("<br>")}</div>` : ""}`;
}

function openJobDrawer(e, tab = "decision") {
  const site = (() => {
    try {
      return new URL(e.link).hostname.replace(/^www\./, "");
    } catch (err) {
      return "сайте";
    }
  })();
  const tabs = [["decision", "Решение"], ["letter", "Письмо"], ["prep", "Подготовка"]];
  const body = openSideDrawer({
    title: `${plogoHtml(e.source)}<span>${escapeHtml(e.company || "—")}</span>`,
    sub: `<span>${escapeHtml(e.title)}${e.salary ? " · " + escapeHtml(e.salary) : ""} · ${escapeHtml(statusLabel(e.status))}</span>`,
    body: `<div class="segmented drawer-tabs" role="tablist" data-ui="jobs.drawer"><span class="segmented-ind" aria-hidden="true"></span>${tabs
      .map(([k, l]) => `<button type="button" role="tab" class="${k === tab ? "on" : ""}" aria-selected="${k === tab}" data-job-tab="${k}">${l}</button>`)
      .join("")}</div><div id="job-tab-body" class="field-stack">${jobDrawerBody(e, tab)}</div>`,
    foot: jobDrawerFoot(e, site),
  });
  jobMistakeOpen = false;
  openDrawerSource = null;
  const seg = body.querySelector(".drawer-tabs");
  requestAnimationFrame(() => positionSegmented(seg));
  seg.querySelectorAll("[data-job-tab]").forEach((b) =>
    b.addEventListener("click", () => {
      seg.querySelectorAll("[data-job-tab]").forEach((x) => {
        x.classList.toggle("on", x === b);
        x.setAttribute("aria-selected", x === b ? "true" : "false");
      });
      positionSegmented(seg);
      body.querySelector("#job-tab-body").innerHTML = jobDrawerBody(e, b.dataset.jobTab);
      bindJobDrawer(body, e);
    })
  );
  bindJobDrawer(body, e);
  const drawer = document.getElementById("platform-drawer");
  drawer.onclick = null;
  drawer.querySelectorAll("[data-job-action]").forEach(() => {});
  currentJobEntry = e;
}

let currentJobEntry = null;
let jobMistakeOpen = false;

// «Это была ошибка»: причины — как в демо; пометка уходит в оценку
// следующих вакансий (job_fit.score_job_fit).
const MISTAKE_REASONS = {
  should_apply: ["Стоило откликнуться", "Требование не обязательное", "Неверно понял формат работы"],
  should_skip: ["Не стоило откликаться", "Не мой стек", "Зарплата ниже ожиданий", "Не та география"],
};
const canApplyAnyway = (e) => isSkipped(e) && !!e.external_id;

function jobMistakeHtml(e) {
  const fb = e.feedback;
  if (fb && !jobMistakeOpen) {
    return `<div class="field-block mistake-note" data-ui="jobs.mistake"><div class="field-title">Ваша пометка</div>
      <div>«${escapeHtml(fb.reason || (fb.verdict === "should_apply" ? "Стоило откликнуться" : "Не стоило откликаться"))}» — бот учитывает её, когда оценивает похожие вакансии.</div>
      <div class="fix-actions"><button type="button" class="btn btn-small btn-ghost" data-job-action="mistake-clear">Снять пометку</button></div></div>`;
  }
  if (!jobMistakeOpen) return "";
  const verdict = isSkipped(e) ? "should_apply" : "should_skip";
  return `<div class="mistake-panel" data-ui="jobs.mistake"><div class="field-title">Что не так с этим решением?</div>
    <div class="chip-row">${MISTAKE_REASONS[verdict]
      .map((r) => `<button type="button" class="chip" data-mistake-reason="${escapeHtml(r)}" data-verdict="${verdict}">${escapeHtml(r)}</button>`)
      .join("")}</div>
    <form class="field-row-inline" data-mistake-form data-verdict="${verdict}"><input type="text" maxlength="300" placeholder="Или своими словами" aria-label="Своя причина" /><button type="submit" class="btn btn-small">Запомнить</button></form></div>`;
}

function jobDrawerFoot(e, site) {
  const anyway = canApplyAnyway(e);
  const planned = anyway && e.apply_anyway;
  return `${anyway ? `<button type="button" class="btn${planned ? "" : " btn-primary"}" data-job-action="apply-anyway" data-ui="jobs.apply-anyway" aria-pressed="${planned ? "true" : "false"}">${planned ? "Отклик запланирован · отменить" : "Откликнуться всё равно"}</button>` : ""}
    ${e.link ? `<a class="btn${anyway ? "" : " btn-primary"}" href="${escapeHtml(e.link)}" target="_blank" rel="noopener" data-ui="jobs.open">Открыть на ${escapeHtml(site)} ↗</a>` : ""}
    ${e.company ? `<button type="button" class="btn btn-ghost" data-job-action="find-hr" data-ui="jobs.find-hr">Найти HR компании</button>` : ""}
    ${e.external_id ? `<button type="button" class="btn btn-ghost foot-end" data-job-action="mistake" aria-expanded="${jobMistakeOpen}">Это была ошибка</button>` : ""}`;
}

function refreshJobDrawer(e) {
  const tabBody = document.getElementById("job-tab-body");
  if (!tabBody || currentJobEntry !== e) return;
  const active = document.querySelector("#platform-drawer [data-job-tab].on")?.dataset.jobTab || "decision";
  tabBody.innerHTML = jobDrawerBody(e, active);
  bindJobDrawer(tabBody, e);
  const site = (() => {
    try {
      return new URL(e.link).hostname.replace(/^www\./, "");
    } catch (err) {
      return "сайте";
    }
  })();
  document.getElementById("platform-drawer-foot").innerHTML = jobDrawerFoot(e, site);
  lastHistorySnapshot = "";
  render.history();
}

async function saveJobFeedback(e, verdict, reason) {
  const prev = e.feedback || null;
  const post = (v, r) =>
    api("/api/applications/feedback", { method: "POST", body: JSON.stringify({ source: e.source, external_id: e.external_id, verdict: v || "", reason: r || "" }) });
  try {
    const saved = await post(verdict, reason);
    e.feedback = saved.feedback || null;
    jobMistakeOpen = false;
    refreshJobDrawer(e);
    showSavedToast(
      verdict ? `Запомнил: «${reason}». Похожие вакансии буду оценивать иначе` : "Пометка снята",
      async () => {
        const back = await post(prev?.verdict, prev?.reason);
        e.feedback = back.feedback || null;
        refreshJobDrawer(e);
      }
    );
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
  }
}

async function toggleApplyAnyway(e) {
  const on = !e.apply_anyway;
  const post = (v) =>
    api("/api/applications/apply-anyway", { method: "POST", body: JSON.stringify({ source: e.source, external_id: e.external_id, on: v }) });
  try {
    await post(on);
    e.apply_anyway = on;
    refreshJobDrawer(e);
    showSavedToast(
      on
        ? `Откликнусь, когда ${sourceLabel(e.source)} снова покажет вакансию — без оценки ИИ, с письмом и в пределах лимита`
        : "Отклик отменён",
      async () => {
        await post(!on);
        e.apply_anyway = !on;
        refreshJobDrawer(e);
      },
      9000
    );
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
  }
}

function bindJobDrawer(root, e) {
  root.querySelectorAll("[data-mistake-reason]").forEach((b) =>
    b.addEventListener("click", () => saveJobFeedback(e, b.dataset.verdict, b.dataset.mistakeReason))
  );
  root.querySelectorAll("[data-mistake-form]").forEach((f) =>
    f.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const text = f.querySelector("input").value.trim();
      if (text) saveJobFeedback(e, f.dataset.verdict, text);
    })
  );
  root.querySelectorAll("[data-set-stage]").forEach((b) =>
    b.addEventListener("click", async () => {
      try {
        await api("/api/applications/stage", {
          method: "POST",
          body: JSON.stringify({ source: e.source, external_id: e.external_id, stage: b.dataset.setStage }),
        });
        const prev = e.effective_stage;
        e.effective_stage = b.dataset.setStage || null;
        root.querySelectorAll("[data-set-stage]").forEach((x) => {
          x.classList.toggle("active", x === b);
          x.setAttribute("aria-checked", x === b ? "true" : "false");
        });
        showSavedToast(`Этап: ${b.textContent}`, async () => {
          await api("/api/applications/stage", { method: "POST", body: JSON.stringify({ source: e.source, external_id: e.external_id, stage: prev || "" }) });
          e.effective_stage = prev;
          lastHistorySnapshot = "";
          render.history();
        });
        lastHistorySnapshot = "";
        render.history();
      } catch (err) {
        showToast(`Не удалось сохранить этап: ${err.message}`, "error");
      }
    })
  );
}

async function handleJobAction(btn) {
  const e = currentJobEntry;
  if (!e) return;
  const action = btn.dataset.jobAction;
  if (action === "mistake") {
    jobMistakeOpen = !jobMistakeOpen;
    const decision = document.querySelector('#platform-drawer [data-job-tab="decision"]');
    if (decision && !decision.classList.contains("on")) decision.click();
    refreshJobDrawer(e);
    document.querySelector("#platform-drawer .mistake-panel .chip")?.focus();
    return;
  }
  if (action === "mistake-clear") {
    saveJobFeedback(e, null, "");
    return;
  }
  if (action === "apply-anyway") {
    toggleApplyAnyway(e);
    return;
  }
  if (action === "copy-letter") {
    copyToClipboard(e.cover_letter || "", btn);
    showToast("Письмо скопировано", "success");
  } else if (action === "prep") {
    btn.disabled = true;
    btn.textContent = "Готовлю справку…";
    try {
      const { prep } = await api("/api/applications/prep", { method: "POST", body: JSON.stringify({ source: e.source, external_id: e.external_id }) });
      const box = document.getElementById("job-prep-body");
      box.hidden = false;
      box.textContent = prep.replace(/\*\*/g, "");
      btn.remove();
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
      btn.disabled = false;
      btn.textContent = "Справка к интервью: что спросят и что подтянуть";
    }
  } else if (action === "trainer") {
    openTrainer(e);
  } else if (action === "calendar") {
    openCalendarOverlay(e);
  } else if (action === "prefill") {
    btn.disabled = true;
    try {
      const { filled } = await api("/api/direct/prefill", { method: "POST", body: JSON.stringify({ source: e.source, external_id: e.external_id }) });
      showToast(filled.length ? `Форма открыта в Chrome, заполнено: ${filled.join(", ")}. Ответьте на вопросы компании и нажмите Submit.` : "Форма открыта в Chrome — эту разметку заполнить не удалось, заполните вручную.", "success", 8000);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
    }
  } else if (action === "find-hr") {
    btn.disabled = true;
    btn.textContent = "Ищу контакты…";
    try {
      const res = await api("/api/contacts/from-application", { method: "POST", body: JSON.stringify({ source: e.source, external_id: e.external_id }) });
      showToast(res.message || (res.added ? `Найдено контактов: ${res.added}` : "Компания добавлена в Базу — публичных контактов на сайте нет"), res.added ? "success" : "info", 7000);
      focusContactKey = res.key;
      closePlatformDrawer();
      switchTab("contacts");
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
      btn.disabled = false;
      btn.textContent = "Найти HR компании";
    }
  }
}

let historyTargetHighlightTimer = null;

function highlightHistoryTarget(row) {
  const previous = document.querySelector("#history-rows .job-row.is-target-highlight");
  if (historyTargetHighlightTimer) clearTimeout(historyTargetHighlightTimer);
  previous?.classList.remove("is-target-highlight");
  if (REDUCE_MOTION || !row) return;
  row.classList.remove("is-target-highlight");
  void row.offsetWidth;
  row.classList.add("is-target-highlight");
  historyTargetHighlightTimer = setTimeout(() => {
    row.classList.remove("is-target-highlight");
    historyTargetHighlightTimer = null;
  }, 900);
}

function selectHistoryRow(i, open = false, animate = false) {
  const rows = document.querySelectorAll("#history-rows .job-row");
  if (!rows.length) return;
  historySelected = Math.max(0, Math.min(rows.length - 1, i));
  rows.forEach((r, n) => r.classList.toggle("is-selected", n === historySelected));
  rows[historySelected].querySelector(".job-row-open")?.focus({ preventScroll: false });
  if (open) {
    if (animate) highlightHistoryTarget(rows[historySelected]);
    openJobDrawer(historyRows[historySelected]);
  }
}

function initJobsView() {
  const tbody = document.getElementById("history-rows");
  tbody.addEventListener("click", (ev) => {
    const row = ev.target.closest(".job-row");
    if (!row || ev.target.closest("a")) return;
    selectHistoryRow(Number(row.dataset.rowIndex), true, ev.detail > 0);
  });
  document.getElementById("platform-drawer").addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-job-action]");
    if (btn) handleJobAction(btn);
  });
  // j/k — по строкам, пока открыт раздел «Вакансии» и курсор не в поле.
  document.addEventListener("keydown", (ev) => {
    if (currentView !== "history" || isCommandPaletteOpen()) return;
    const tag = (ev.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    if (ev.key === "j" || ev.key === "k") {
      ev.preventDefault();
      selectHistoryRow(historySelected + (ev.key === "j" ? 1 : -1), isPlatformDrawerOpen());
    }
  });
  ["filter-source"].forEach((id) =>
    document.getElementById(id).addEventListener("change", () => {
      lastHistorySnapshot = "";
      render.history({ animateRows: shouldAnimateNavigation() });
    })
  );
  let qTimer = null;
  document.getElementById("filter-query").addEventListener("input", () => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => {
      lastHistorySnapshot = "";
      render.history();
    }, 250);
  });
}

// Дополнительные действия строки "Истории" — в одном выпадающем меню,
// а не 4-5 кнопок в ячейке.
function rowActionsHtml(e, i) {
  const actions = [];
  if (e.effective_stage === "interview") {
    actions.push(
      `<button type="button" data-prep-btn data-row-index="${i}">Подготовка к интервью</button>`,
      `<button type="button" data-trainer-btn data-row-index="${i}">Тренажёр вопросов</button>`,
      `<button type="button" data-calendar-btn data-row-index="${i}">Интервью в календарь</button>`
    );
  }
  if (e.source === "direct" && e.status === "dry_run" && /greenhouse\.io|lever\.co/.test(e.link)) {
    actions.push(`<button type="button" data-prefill-btn data-row-index="${i}">Заполнить форму отклика</button>`);
  }
  if (e.company) {
    actions.push(`<button type="button" data-find-hr data-row-index="${i}">Найти HR компании</button>`);
  }
  if (e.contacts && e.contacts.length) {
    actions.push(
      ...e.contacts.map((c) => `<a href="mailto:${escapeHtml(c)}">${escapeHtml(c)}</a>`)
    );
  }
  if (!actions.length) return "";
  return `<details class="row-actions"><summary>Действия ▾</summary><div class="row-actions-menu">${actions.join("")}</div></details>`;
}

// Карточка "черновик, ждущий решения" — общая для очереди HR-черновиков
// и очереди HH-напоминаний (раньше обе держали textarea всегда открытым:
// при 5-10 письмах страница превращалась в стену текста). <details> вместо
// самодельного JS-состояния открыт/закрыт — нативный сворачиваемый блок,
// доступный с клавиатуры бесплатно. Кнопки лежат в <summary>, поэтому их
// клик глушит propagation — иначе он же переключал бы разворот карточки.
function decisionCardHtml(item) {
  return `
    <details class="hr-draft${item.animate ? " hr-draft-enter" : ""}" data-draft-code="${escapeHtml(item.code)}">
      <summary>
        <div class="hr-draft-summary-text">
          <div class="muted small">${item.headlineHtml}</div>
          <div class="hr-draft-preview small">${escapeHtml(truncate(item.text, 90))}</div>
        </div>
        <div class="hr-draft-actions">
          <button type="button" class="btn btn-primary btn-small" data-draft-send>${escapeHtml(item.sendLabel)}</button>
          ${item.skip ? `<button type="button" class="btn btn-ghost btn-small" data-draft-skip>Пропустить</button>` : ""}
        </div>
      </summary>
      <div class="hr-draft-body">
        ${item.detailHtml || ""}
        <textarea rows="${item.rows}" aria-label="Текст черновика">${escapeHtml(item.text)}</textarea>
      </div>
    </details>`;
}

function wireDecisionCard(box, item, onDone) {
  const stop = (ev) => ev.stopPropagation();
  const sendBtn = box.querySelector("[data-draft-send]");
  sendBtn.addEventListener("click", async (ev) => {
    stop(ev);
    sendBtn.disabled = true;
    try {
      await item.send(box.querySelector("textarea").value);
      onDone();
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
      sendBtn.disabled = false;
    }
  });
  box.querySelector("[data-draft-skip]")?.addEventListener("click", async (ev) => {
    stop(ev);
    await item.skip();
    onDone();
  });
}

// "Отправить всё как есть" — одобряет пачкой без открытия каждой карточки,
// текст берёт исходный (неотредактированный); ошибки по отдельным письмам
// не прерывают остальные, статус — краткая сводка одним тостом.
async function sendAllAsIs(items, statusEl, refresh) {
  statusEl.textContent = `Отправляю 0 из ${items.length}…`;
  let sent = 0;
  let failed = 0;
  for (const item of items) {
    try {
      await item.send(item.text);
      sent++;
    } catch (e) {
      failed++;
    }
    statusEl.textContent = `Отправляю ${sent + failed} из ${items.length}…`;
  }
  showToast(
    failed ? `Отправлено ${sent}, не удалось ${failed}` : `Отправлено ${sent}`,
    failed ? "error" : "success"
  );
  refresh();
}

// Очередь "Ждут вашего решения" — все черновики (ответы и напоминания в
// Telegram, письма HR): правка текста, отправить или пропустить.
async function renderDraftsQueue() {
  const el = document.getElementById("drafts-queue");
  const drafts = await api("/api/hr-drafts");
  if (!drafts.length) {
    lastDraftCodes = new Set();
    el.style.display = "none";
    return;
  }
  const KIND = { reply: "Ответ HR", follow_up: "Напоминание", email: "Письмо HR" };
  el.style.display = "";
  const currentCodes = new Set(drafts.map((draft) => String(draft.code)));
  const items = drafts.map((d) => ({
    code: d.code,
    animate: lastDraftCodes !== null && !lastDraftCodes.has(String(d.code)),
    text: d.text,
    rows: 4,
    sendLabel: "Отправить",
    headlineHtml: `${KIND[d.kind] || "Сообщение"} ${d.channel === "email" ? "по почте" : "в Telegram"} →
      ${d.channel === "email" ? escapeHtml(d.contact) : "@" + escapeHtml(d.contact)}
      ${d.company ? ` · ${escapeHtml(d.company)}${d.title ? " — " + escapeHtml(d.title) : ""}` : ""}
      ${d.job_link ? ` · <a href="${escapeHtml(d.job_link)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">вакансия</a>` : ""}`,
    detailHtml: d.resume_file
      ? `<div class="muted small">Приложится резюме: <b>${escapeHtml(d.resume_file)}</b>${
          d.resume_russian === true ? " (для русской вакансии)" : d.resume_russian === false ? " (для зарубежной вакансии)" : ""
        }</div>`
      : d.channel === "email" && d.kind !== "follow_up"
      ? `<div class="err-text small">Резюме для вложения не найдено — загрузите в «Мои резюме», иначе письмо не уйдёт</div>`
      : "",
    send: async (text) => {
      const res = await api(`/api/hr-drafts/${d.code}/send`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      showToast(res.message, "success");
    },
    skip: async () => {
      await api(`/api/hr-drafts/${d.code}/skip`, { method: "POST" });
    },
  }));
  lastDraftCodes = currentCodes;
  el.innerHTML = `
    <div class="hr-draft-queue-head">
      <h3 class="m0"><span class="dot warn"></span> Ждут вашего «Отправить» · ${drafts.length}</h3>
      <button type="button" class="btn btn-secondary btn-small" id="drafts-send-all">Отправить все как есть</button>
    </div>
    <p class="muted small" id="drafts-send-all-status" role="status"></p>
    ${items.map(decisionCardHtml).join("")}`;
  el.querySelectorAll("[data-draft-code]").forEach((box, i) =>
    wireDecisionCard(box, items[i], renderDraftsQueue)
  );
  el.querySelector("#drafts-send-all").addEventListener("click", (ev) => {
    ev.target.disabled = true;
    sendAllAsIs(items, document.getElementById("drafts-send-all-status"), renderDraftsQueue);
  });
}

// Очередь "Молчат долго" (HH) — отдельно от drafts-queue: не черновик
// ответа, а напоминание о себе по уже отправленному отклику.
async function renderHhRemindersQueue() {
  const el = document.getElementById("hh-reminders-queue");
  let reminders;
  try {
    reminders = await api("/api/headhunter/reminders");
  } catch (e) {
    el.style.display = "none";
    return;
  }
  if (!reminders.length) {
    lastHhReminderCodes = new Set();
    el.style.display = hhReminderBatchSummary ? "" : "none";
    document.getElementById("hh-reminders-list").innerHTML = hhReminderBatchSummary
      ? `<p class="muted small" role="status">${escapeHtml(hhReminderBatchSummary)}</p>`
      : "";
    return;
  }
  el.style.display = "";
  document.getElementById("hh-reminders-count").textContent = `· ${reminders.length} ${plural(reminders.length, "отклик", "отклика", "откликов")}`;
  const currentCodes = new Set(reminders.map((reminder) => String(reminder.external_id)));
  const items = reminders.map((r) => ({
    code: r.external_id,
    animate: lastHhReminderCodes !== null && !lastHhReminderCodes.has(String(r.external_id)),
    text: r.text,
    rows: 3,
    sendLabel: "Напомнить",
    headlineHtml: `${escapeHtml(r.company)}${r.title ? " — " + escapeHtml(r.title) : ""} · откликнулись ${fmtDay(r.applied_at)}
      · <a href="${escapeHtml(r.link)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">вакансия</a>`,
    detailHtml: "",
    send: async (text) => {
      await api("/api/headhunter/reminders/send", {
        method: "POST",
        body: JSON.stringify({ external_id: r.external_id, text }),
      });
      showToast("Напоминание отправлено", "success");
    },
    skip: null,
  }));
  lastHhReminderCodes = currentCodes;
  document.getElementById("hh-reminders-list").innerHTML = `
    <div class="hr-draft-queue-head">
      <span></span>
      <button type="button" class="btn btn-secondary btn-small" id="hh-reminders-send-all">Отправить все как есть</button>
    </div>
    <p class="muted small" id="hh-reminders-send-all-status" role="status">${escapeHtml(hhReminderBatchSummary)}</p>
    ${items.map(decisionCardHtml).join("")}`;
  el.querySelectorAll("[data-draft-code]").forEach((box, i) =>
    wireDecisionCard(box, items[i], renderHhRemindersQueue)
  );
  el.querySelector("#hh-reminders-send-all").addEventListener("click", (ev) => {
    ev.target.disabled = true;
    sendAllHhRemindersAsIs(
      items,
      document.getElementById("hh-reminders-send-all-status"),
      renderHhRemindersQueue
    ).finally(() => {
      if (ev.target.isConnected) ev.target.disabled = false;
    });
  });
}

async function sendAllHhRemindersAsIs(items, statusEl, refresh) {
  statusEl.textContent = `Открываю HH и отправляю ${items.length}…`;
  try {
    const response = await api("/api/headhunter/reminders/send-all", {
      method: "POST",
      body: JSON.stringify({
        reminders: items.map((item) => ({
          external_id: item.code,
          text: item.text,
        })),
      }),
    });
    const sent = response.results.filter((result) => result.sent).length;
    const failed = response.results.length - sent;
    hhReminderBatchSummary = failed
      ? `Отправлено ${sent} из ${response.results.length}; не удалось ${failed}. Неотправленные остались в очереди.`
      : `Отправлено ${sent} из ${response.results.length}.`;
    showToast(hhReminderBatchSummary, failed ? "error" : "success", 7000);
  } catch (error) {
    const message = error.message.replace(/^\d+: /, "");
    hhReminderBatchSummary = `Напоминания не отправлены: ${message}`;
    statusEl.textContent = hhReminderBatchSummary;
    showToast(hhReminderBatchSummary, "error", 7000);
    return;
  }
  try {
    await refresh();
  } catch (error) {
    showToast("Напоминания отправлены, но список не обновился. Обновите вкладку позже.", "info", 7000);
  }
}

// «Сегодня: 12 из 25 · разогрев, день 3 · отправка будни 9–19».
function mailPlanText(p) {
  if (!p) return "";
  const warm = p.warmup && p.limit < p.daily_limit ? ` (разогрев, день ${p.warmup_day} — до ${p.daily_limit} дойдёт постепенно)` : "";
  const when = p.send_hours_enabled !== false
    ? `${p.weekdays_only ? "будни" : "каждый день"} ${p.send_from}:00–${p.send_to}:00`
    : p.weekdays_only ? "будни, в любое время" : "круглосуточно";
  return `Сегодня отправлено ${p.sent_today} из ${p.limit}${warm} · отправка: ${when}${p.can_send ? "" : ` · пауза: ${p.reason}`}`;
}

async function loadOutreachSettings() {
  const s = await api("/api/settings/outreach");
  document.getElementById("outreach-email").value = s.email_address;
  document.getElementById("outreach-app-password").value = "";
  document.getElementById("outreach-app-password").placeholder = s.email_connected
    ? "Пароль сохранён — введите новый, чтобы заменить"
    : "Пароль приложения (16 символов)";
  document.getElementById("outreach-email-status").textContent = s.email_connected
    ? `Почта подключена: ${s.email_address}`
    : "Почта не подключена — письма HR будут только черновиками для ручной отправки.";
  document.getElementById("outreach-hunter-status").textContent = s.hunter_preview
    ? `сохранён: ${s.hunter_preview}`
    : "не задан";
  document.getElementById("outreach-email-limit").value = s.email_daily_limit;
  document.getElementById("outreach-send-from").value = s.send_from;
  document.getElementById("outreach-send-to").value = s.send_to;
  document.getElementById("outreach-send-hours-enabled").checked = s.send_hours_enabled !== false;
  document.getElementById("outreach-send-from").disabled = s.send_hours_enabled === false;
  document.getElementById("outreach-send-to").disabled = s.send_hours_enabled === false;
  document.getElementById("outreach-weekdays").checked = s.weekdays_only;
  document.getElementById("outreach-warmup").checked = s.warmup;
  document.getElementById("outreach-auto-send").checked = s.auto_send;
  document.getElementById("outreach-bounce-stop").value = s.bounce_stop;
  document.getElementById("outreach-guard-status").textContent = mailPlanText(s.mail_plan);
  document.getElementById("outreach-follow-up").value = s.follow_up_days;
  document.getElementById("outreach-digest").checked = s.digest_enabled;
  document.getElementById("outreach-digest-hour").value = s.digest_hour;
  document.getElementById("digest-quiet").checked = s.digest_quiet;
  document.getElementById("notify-activity").checked = s.notify_activity !== false;
  document.getElementById("notify-failures").checked = s.notify_failures !== false;
  document.getElementById("outreach-letter-instructions").value = s.letter_instructions || "";
  renderLetterInstructions(s.letter_instructions || "");
  document.getElementById("outreach-skip-us").checked = s.skip_us_only;
  document.getElementById("outreach-skip-eu").checked = s.skip_europe_only;
  document.getElementById("outreach-candidate-telegram").value = s.candidate_telegram;
  document.getElementById("outreach-candidate-whatsapp").value = s.candidate_whatsapp;
  document.getElementById("outreach-candidate-linkedin").value = s.candidate_linkedin;
  document.getElementById("outreach-resume-route").innerHTML =
    `<b>Автовыбор при отправке письма:</b> компания РФ/СНГ → ${
      s.resume_route_ru ? escapeHtml(s.resume_route_ru) : "не найдено"
    }, зарубежная → ${s.resume_route_en ? escapeHtml(s.resume_route_en) : "не найдено"}`;
}

async function saveOutreachSettings() {
  const status = document.getElementById("outreach-save-status");
  const button = document.getElementById("outreach-save");
  const num = (id) => parseInt(document.getElementById(id).value, 10);
  const body = {
    email_address: document.getElementById("outreach-email").value.trim(),
    email_daily_limit: num("outreach-email-limit"),
    send_from: num("outreach-send-from"),
    send_to: num("outreach-send-to"),
    send_hours_enabled: document.getElementById("outreach-send-hours-enabled").checked,
    weekdays_only: document.getElementById("outreach-weekdays").checked,
    warmup: document.getElementById("outreach-warmup").checked,
    auto_send: document.getElementById("outreach-auto-send").checked,
    bounce_stop: num("outreach-bounce-stop"),
    follow_up_days: num("outreach-follow-up"),
    digest_enabled: document.getElementById("outreach-digest").checked,
    digest_hour: num("outreach-digest-hour"),
    skip_us_only: document.getElementById("outreach-skip-us").checked,
    skip_europe_only: document.getElementById("outreach-skip-eu").checked,
    candidate_telegram: document.getElementById("outreach-candidate-telegram").value.trim(),
    candidate_whatsapp: document.getElementById("outreach-candidate-whatsapp").value.trim(),
    candidate_linkedin: document.getElementById("outreach-candidate-linkedin").value.trim(),
    letter_instructions: document.getElementById("outreach-letter-instructions").value.trim(),
  };
  const password = document.getElementById("outreach-app-password").value.trim();
  if (password) body.email_app_password = password;
  const hunter = document.getElementById("outreach-hunter").value.trim();
  if (hunter) body.hunter_api_key = hunter;
  status.textContent = "Сохранение…";
  let saved = false;
  await withButtonLoading(button, async () => {
    try {
      await api("/api/settings/outreach", { method: "POST", body: JSON.stringify(body) });
      document.getElementById("outreach-hunter").value = "";
      status.textContent = "Сохранено";
      showToast("Настройки почты сохранены", "success");
      await loadOutreachSettings();
      saved = true;
    } catch (err) {
      status.textContent = `Не удалось сохранить: ${err.message.replace(/^\d+: /, "")}`;
      showToast(status.textContent, "error");
    }
  });
  return saved;
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
  // state: нет/active — крутится; waiting — жёлтая точка; stopped — красная, нужны вы.
  const icon = (a) =>
    a.state === "waiting" ? `<span class="dot warn activity-icon" aria-hidden="true"></span>`
      : a.state === "stopped" ? `<span class="dot error activity-icon" aria-hidden="true"></span>`
      : `<span class="activity-spin" aria-hidden="true"></span>`;
  if (!setHtmlIfChanged(el, items
    .map(
      (a) => `<button type="button" class="activity-item${a.state ? ` is-${a.state}` : ""}" data-activity-view="${a.goto || a.view}">
        ${icon(a)}
        <span>${escapeHtml(a.text)}${a.source ? " " + escapeHtml(sourceLabel(a.source)) : ""}${a.total ? ` · ${a.done}/${a.total}` : ""}${a.state === "stopped" ? " — что делать →" : ""}</span>
      </button>`
    )
    .join(""))) return;
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
  const on = modeSources(status);
  const auto = on.filter((s) => s.auto_apply);
  const box = document.getElementById("search-auto-all");
  box.checked = on.length > 0 && auto.length === on.length;
  box.indeterminate = auto.length > 0 && auto.length < on.length;
  document.getElementById("search-auto-note").textContent = on.length
    ? `сейчас сами откликаются: ${auto.length} из ${on.length}`
    : "ни одна площадка не включена";
  box.onchange = async () => {
    const enable = box.checked;
    if (enable && !(await showConfirm(`Бот начнёт сам отправлять отклики на ${on.length} ${plural(on.length, "площадке", "площадках", "площадках")} — до дневного лимита каждой. Включить?`))) {
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

// «Вести переписку» — один тумблер на три настройки HH: автоответ в чате,
// досылка письма в чат и напоминание молчащим работодателям.
function renderAutoChat(status) {
  const hh = status.sources.find((s) => s.name === "headhunter");
  const box = document.getElementById("search-auto-chat");
  const note = document.getElementById("search-auto-chat-note");
  if (!box || !hh) return;
  const flags = [hh.auto_reply, hh.chat_cover_letter_followup, hh.auto_reminder];
  const active = flags.filter(Boolean).length;
  box.checked = active === flags.length;
  box.indeterminate = active > 0 && active < flags.length;
  note.textContent = hh.schedule_enabled
    ? "отвечает на рутинные вопросы, досылает письмо, напоминает о себе (HH)"
    : "HeadHunter сейчас выключен";
  box.onchange = async () => {
    const enable = box.checked;
    if (enable && !(await showConfirm("Бот начнёт сам отвечать работодателям в чатах HH, досылать письма и напоминать о себе. Приглашения и вопросы про время и деньги по-прежнему приходят вам. Включить?"))) {
      renderAutoChat(status);
      return;
    }
    box.disabled = true;
    try {
      await api("/api/settings", {
        method: "POST",
        body: JSON.stringify({ source: "headhunter", auto_reply: enable, chat_cover_letter_followup: enable, auto_reminder: enable }),
      });
      showToast(enable ? "Переписка включена" : "Переписку веду я сам", "success");
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    } finally {
      box.disabled = false;
      renderAutoChat(await api("/api/status"));
      lastOverviewSnapshot = "";
    }
  };
}

// «Подключения»: сервисы (то же, что «Готовность» на Главной) и
// площадки — вход, пауза после капчи, последняя ошибка.
// Пока не пройдены обязательные шаги (резюме/ключ ИИ/площадка, см.
// _REQUIRED_SETUP в api.py) — сворачиваем вкладки настроек, которые
// имеют смысл только для уже работающего бота (стиль писем, каналы
// отправки, автозапуск), чтобы новичок не видел все 8 вкладок сразу.
// Ничего не блокируется навсегда — "Показать всё" снимает это в любой
// момент и запоминает выбор.
function updateSettingsOnboarding(todo) {
  const jump = document.getElementById("settings-jump");
  const hint = document.getElementById("settings-onboarding-hint");
  if (!jump || !hint) return;
  const missingRequired = (todo.setup || []).some((c) => c.required && !c.ok);
  let revealed = false;
  try {
    revealed = localStorage.getItem("cj-settings-full-shown") === "1";
  } catch (e) {}
  const onboarding = missingRequired && !revealed;
  jump.classList.toggle("onboarding", onboarding);
  hint.style.display = onboarding ? "" : "none";
}

async function loadAccounts() {
  const [todo, status] = await Promise.all([api("/api/todo"), api("/api/status")]);
  updateSettingsOnboarding(todo);
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
        // «Вход в Telegram» — блок входа здесь же, в Подключениях.
        const anchor = b.dataset.anchor || (goto === "settings-accounts" ? "tg-connect-panel" : "");
        const target = anchor && document.getElementById(anchor);
        if (target) {
          if (target.tagName === "DETAILS") target.open = true;
          target.scrollIntoView({ block: "center", behavior: REDUCE_MOTION ? "auto" : "smooth" });
        }
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
        notify_activity: document.getElementById("notify-activity").checked,
        notify_failures: document.getElementById("notify-failures").checked,
      }),
    });
    showToast("Уведомления сохранены", "success");
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
  }
}

async function testOutreachEmail() {
  const status = document.getElementById("outreach-email-status");
  if (!(await saveOutreachSettings())) return;
  status.textContent = "Отправляю письмо себе…";
  try {
    await api("/api/settings/outreach/test-email", { method: "POST" });
    status.textContent = "Письмо отправлено — проверьте почту. Всё работает.";
  } catch (err) {
    status.textContent = `Ошибка: ${err.message.replace(/^\d+: /, "")}`;
  }
}

function showOverlay(id) {
  const overlay = document.getElementById(id);
  overlay.style.display = "flex";
  trapFocus(overlay);
}

// Общий выход для всех .command-overlay (диалоги/командная палитра) —
// раньше каждое место само дублировало "display:none +
// releaseFocusTrap", без анимации закрытия. Фокус освобождаем сразу
// (не ждём decorативный фейд), сам overlay прячем по animationend —
// с safety-таймаутом на случай, если событие почему-то не придёт.
function hideOverlay(overlay) {
  if (!overlay || overlay.style.display === "none") return;
  releaseFocusTrap(overlay);
  if (REDUCE_MOTION || overlay.id === "command-overlay") {
    overlay.style.display = "none";
    overlay.classList.remove("is-closing", "is-instant");
    return;
  }
  overlay.classList.add("is-closing");
  const finish = () => {
    overlay.style.display = "none";
    overlay.classList.remove("is-closing");
  };
  overlay.addEventListener("animationend", finish, { once: true });
  setTimeout(finish, 220);
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
  hideOverlay(document.getElementById("cover-letter-overlay"));
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
  hideOverlay(document.getElementById("shortcuts-overlay"));
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
    if (e.key === "/") {
      const searchByView = {
        history: "filter-query",
        replies: "replies-filter-query",
        contacts: "contacts-filter-query",
        settings: "settings-find-input",
        logs: "log-search",
      };
      const search = document.getElementById(searchByView[currentView]);
      if (search && !search.disabled && search.getClientRects().length) {
        e.preventDefault();
        search.focus();
      }
      return;
    }
    if (e.key === "?") {
      e.preventDefault();
      const overlay = document.getElementById("shortcuts-overlay");
      if (overlay.style.display === "none") openShortcutsOverlay();
      else closeShortcutsOverlay();
      return;
    }
    if (/^[1-6]$/.test(e.key)) {
      const buttons = document.querySelectorAll("nav.tabs button[data-tab]");
      const idx = parseInt(e.key, 10) - 1;
      if (buttons[idx]) switchTab(buttons[idx].dataset.tab);
    }
  });
}

// ---------- Cursor-spotlight + magnetic primary buttons ----------
// Один делегированный слушатель на весь документ вместо одного на
// карточку — дешевле при десятках карточек на Обзоре.
function clearPointerEffects() {
  document.querySelectorAll(".btn-primary.is-magnetic").forEach((button) => {
    button.style.transform = "";
    button.classList.remove("is-magnetic");
  });
  document.querySelectorAll(".source-card, .provider-card").forEach((card) => {
    card.style.removeProperty("--spot-x");
    card.style.removeProperty("--spot-y");
  });
}

function initPointerEffects() {
  let pointerFrame = 0;
  let latestPointer = null;
  document.addEventListener("mousemove", (e) => {
    if (REDUCE_MOTION) return;
    latestPointer = { target: e.target, clientX: e.clientX, clientY: e.clientY };
    if (pointerFrame) return;
    pointerFrame = requestAnimationFrame(() => {
      pointerFrame = 0;
      if (REDUCE_MOTION || !latestPointer) return;
      const { target, clientX, clientY } = latestPointer;
      const card = target.closest(".source-card, .provider-card");
      if (card) {
        const rect = card.getBoundingClientRect();
        card.style.setProperty("--spot-x", `${clientX - rect.left}px`);
        card.style.setProperty("--spot-y", `${clientY - rect.top}px`);
      }
      const btn = target.closest(".btn-primary:not(:disabled)");
      document.querySelectorAll(".btn-primary.is-magnetic").forEach((el) => {
        if (el !== btn) {
          el.style.transform = "";
          el.classList.remove("is-magnetic");
        }
      });
      if (btn) {
        btn.classList.add("is-magnetic");
        const rect = btn.getBoundingClientRect();
        const dx = (clientX - (rect.left + rect.width / 2)) * 0.15;
        const dy = (clientY - (rect.top + rect.height / 2)) * 0.25;
        btn.style.transform = `translate(${dx}px, ${dy}px)`;
      }
    });
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
  const wasDisabled = btn.disabled;
  const previousBusy = btn.getAttribute("aria-busy");
  btn.disabled = true;
  btn.setAttribute("aria-busy", "true");
  btn.classList.add("is-loading");
  try {
    return await fn();
  } finally {
    btn.disabled = wasDisabled;
    if (previousBusy === null) btn.removeAttribute("aria-busy");
    else btn.setAttribute("aria-busy", previousBusy);
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
  try {
    if (localStorage.getItem("cj-seen-tour") === "1") return;
  } catch (e) {}
  let step = 0;
  const previouslyFocused = document.activeElement;
  const overlay = document.createElement("div");
  overlay.className = "tour-overlay";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Обзор приложения");
  const highlight = document.createElement("div");
  highlight.className = "tour-highlight";
  const tooltip = document.createElement("div");
  tooltip.className = "tour-tooltip";
  let activeTarget = null;
  overlay.append(highlight, tooltip);

  function positionStep() {
    if (!activeTarget) return;
    const rect = activeTarget.getBoundingClientRect();
    Object.assign(highlight.style, {
      top: `${rect.top - 4}px`,
      left: `${rect.left - 4}px`,
      width: `${rect.width + 8}px`,
      height: `${rect.height + 8}px`,
    });
    const viewportPadding = 12;
    const tooltipWidth = Math.max(1, Math.min(260, window.innerWidth - viewportPadding * 2));
    tooltip.style.width = `${tooltipWidth}px`;
    const tooltipHeight = tooltip.getBoundingClientRect().height || 150;
    tooltip.style.top = `${Math.max(viewportPadding, Math.min(rect.top, window.innerHeight - tooltipHeight - viewportPadding))}px`;
    tooltip.style.left = `${Math.max(viewportPadding, Math.min(rect.right + 16, window.innerWidth - tooltipWidth - viewportPadding))}px`;
  }

  function renderStep() {
    const { tab, text } = TOUR_STEPS[step];
    activeTarget = document.querySelector(`nav.tabs button[data-tab="${tab}"]`);
    if (!activeTarget) return finish();
    const isLast = step === TOUR_STEPS.length - 1;
    overlay.setAttribute("aria-label", `Обзор приложения, шаг ${step + 1} из ${TOUR_STEPS.length}`);
    tooltip.innerHTML = `
      <button type="button" class="tour-skip" id="tour-skip" title="Пропустить" aria-label="Пропустить">✕</button>
      <p id="tour-description" aria-live="polite">${escapeHtml(text)}</p>
      <div class="tour-actions">
        <span class="tour-step">${step + 1} / ${TOUR_STEPS.length}</span>
        <button type="button" class="btn btn-primary btn-small" id="tour-next">${isLast ? "Готово" : "Дальше"}</button>
      </div>`;
    positionStep();
    const nextButton = document.getElementById("tour-next");
    nextButton.addEventListener("click", () => {
      step += 1;
      if (step >= TOUR_STEPS.length) finish();
      else renderStep();
    });
    document.getElementById("tour-skip").addEventListener("click", finish);
    nextButton.focus();
  }

  const onKeydown = (event) => {
    if (event.key === "Escape") {
      finish();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = [
      ...tooltip.querySelectorAll(
        'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
      ),
    ];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && (document.activeElement === first || !tooltip.contains(document.activeElement))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (document.activeElement === last || !tooltip.contains(document.activeElement))) {
      event.preventDefault();
      first.focus();
    }
  };

  function finish() {
    document.removeEventListener("keydown", onKeydown);
    window.removeEventListener("resize", positionStep);
    try {
      localStorage.setItem("cj-seen-tour", "1");
    } catch (e) {}
    overlay.remove();
    if (previouslyFocused && typeof previouslyFocused.focus === "function") {
      previouslyFocused.focus();
    }
  }

  document.body.appendChild(overlay);
  document.addEventListener("keydown", onKeydown);
  window.addEventListener("resize", positionStep);
  renderStep();
}


// 13 недель x 7 дней, как в GitHub contributions — считаем прямо на
// клиенте по уже существующему /api/applications, отдельного
// backend-эндпоинта для этого заводить незачем.
// Воронка — один ряд величин по этапам: горизонтальные полосы одного
// цвета (--accent), число подписано у каждой полосы, ширина — доля от
// числа реальных откликов; подсказка при наведении — title.
// Полосы рисовались сразу на конечной ширине — на фоне анимированных
// колец на карточках площадок это смотрелось недоделанным. Ширина уже
// стоит в style инлайново (шаблон ниже) — сбрасываем в 0, ждём кадр,
// возвращаем обратно; сам переход — CSS transition на .funnel-bar.
function growFunnelBars(container) {
  if (REDUCE_MOTION || !container) return;
  const bars = [...container.querySelectorAll(".funnel-bar")];
  const targets = bars.map((b) => b.style.width);
  bars.forEach((b) => (b.style.width = "0%"));
  void container.offsetWidth;
  requestAnimationFrame(() => {
    bars.forEach((b, i) => (b.style.width = targets[i]));
  });
}

function renderFunnel(funnel) {
  const el = document.getElementById("funnel");
  if (!funnel.applied) {
    el.innerHTML = emptyStateHtml("Пока нет реальных откликов.");
    return;
  }
  // "Ответили" — это НЕ "дошли хотя бы до ответа" (тогда оно было бы ≥
  // интервью+отказов), а именно "застряли на обычном ответе, не дошли
  // ни до приглашения, ни до отказа" — funnel() в applied_log.py
  // считает effective_stage() как один, взаимоисключающий этап на
  // заявку, а не нарастающим итогом. Без явной оговорки цифры выглядят
  // как баг (интервью может быть больше "ответили").
  const stageLabel = (key, v) =>
    key === "replied" ? "Ответили (без приглашения и отказа)" : v[0].toUpperCase() + v.slice(1);
  const rows = [["applied", "Отклики"], ...Object.entries(STAGE_LABELS).map(([k, v]) => [k, stageLabel(k, v)])];
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
  growFunnelBars(el);
}

// Спрос на навыки — тот же вид, что воронка (одна величина, один цвет),
// плюс отметка "есть в резюме"; зарплаты — таблица по валютам.
function renderMarket(market) {
  const skillsEl = document.getElementById("skill-demand");
  skillsEl.innerHTML = market.skills.length
    ? market.skills
        .map(
          (s) => `
      <div class="funnel-row" title="${escapeHtml(s.skill)}: ${s.count} вакансий, ${s.share}%${s.in_resume === false ? " — нет в резюме" : s.in_resume == null ? " — резюме недоступно" : ""}">
        <span class="funnel-label">${escapeHtml(s.skill)}</span>
        <span class="funnel-track"><span class="funnel-bar" style="width:${s.share}%"></span></span>
        <span class="funnel-value">${s.share}%${s.in_resume === false ? ` <span class="tag-miss">нет в резюме</span>` : s.in_resume == null ? ` <span class="muted small">резюме недоступно</span>` : ""}</span>
      </div>`
        )
        .join("")
    : emptyStateHtml("Появится после новых откликов — навыки извлекаются из текста вакансий с этого обновления.");
  growFunnelBars(skillsEl);

  const srcEl = document.getElementById("vacancy-sources");
  const srcRows = Object.entries(market.by_source || {}).sort((a, b) => b[1] - a[1]);
  const srcMax = srcRows.length ? srcRows[0][1] : 1;
  srcEl.innerHTML = srcRows.length
    ? srcRows
        .map(
          ([name, n]) => `
      <div class="funnel-row">
        <span class="funnel-label">${escapeHtml(sourceLabel(name))}</span>
        <span class="funnel-track"><span class="funnel-bar" style="width:${Math.round((n / srcMax) * 100)}%"></span></span>
        <span class="funnel-value">${n}</span>
      </div>`
        )
        .join("")
    : emptyStateHtml("Пока нет собранных вакансий.");
  growFunnelBars(srcEl);

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
  let entries;
  try {
    entries = await api("/api/applications");
  } catch (err) {
    renderRetryState(el, `Не удалось загрузить активность: ${err.message}`, renderActivityHeatmap);
    return;
  }
  renderWeeklyChart(entries);
  const counts = new Map();
  entries.forEach((e) => {
    if (e.status !== "applied") return;
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
    const human = d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", weekday: "short" });
    cells.push({
      date: key,
      level,
      label: `${human}: ${count} ${plural(count, "отклик", "отклика", "откликов")}`,
      title: `${human}: ${count}`,
    });
  }
  syncHeatmapCells(el, cells, el.childElementCount === 0);
  const readout = document.getElementById("heatmap-readout");
  el.onmouseover = (e) => {
    const c = e.target.closest(".heatmap-cell");
    if (c && readout) readout.textContent = c.dataset.label;
  };
  el.onmouseleave = () => readout && (readout.textContent = "отклики за 13 недель");
}

function syncHeatmapCells(container, cells, animateEntrance = false) {
  if (!container) return;
  const existing = new Map(Array.from(container.children, (cell) => [cell.dataset.date, cell]));
  let cursor = container.firstElementChild;
  for (const item of cells) {
    let cell = existing.get(item.date);
    existing.delete(item.date);
    if (!cell) {
      cell = document.createElement("div");
      cell.className = "heatmap-cell";
      cell.dataset.date = item.date;
      container.insertBefore(cell, cursor);
    } else if (cell !== cursor) {
      container.insertBefore(cell, cursor);
    }
    cell.dataset.level = String(item.level);
    cell.dataset.label = item.label;
    cell.title = item.title;
    cursor = cell.nextElementSibling;
  }
  existing.forEach((cell) => cell.remove());
  if (animateEntrance && !REDUCE_MOTION && cells.length) {
    container.classList.remove("is-entering");
    void container.offsetWidth;
    container.classList.add("is-entering");
    container.addEventListener("animationend", (event) => {
      if (event.target === container) container.classList.remove("is-entering");
    }, { once: true });
  }
}

const copyFeedbackState = new WeakMap();

async function copyToClipboard(text, btn, fallbackField) {
  let state;
  if (btn) {
    state = copyFeedbackState.get(btn) || { original: btn.innerHTML, timer: null };
    clearTimeout(state.timer);
    btn.classList.remove("copied");
    btn.innerHTML = state.original;
    copyFeedbackState.set(btn, state);
  }
  try {
    await navigator.clipboard.writeText(text);
    if (btn) {
      btn.classList.add("copied");
      btn.innerHTML = state.original.includes("<svg")
        ? `<svg aria-hidden="true" viewBox="0 0 20 20" fill="none"><path d="m4 10.5 4 4 8-9" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`
        : "✓ Скопировано";
      clearTimeout(state.timer);
      state.timer = setTimeout(() => {
        btn.classList.remove("copied");
        btn.innerHTML = state.original;
        copyFeedbackState.delete(btn);
      }, 1400);
      copyFeedbackState.set(btn, state);
    }
    const announcer = document.getElementById("sr-announcer");
    if (announcer) announcer.textContent = "Скопировано";
    return true;
  } catch (err) {
    if (btn) {
      btn.classList.remove("copied");
      btn.innerHTML = state.original;
      copyFeedbackState.delete(btn);
    }
    fallbackField?.select();
    showToast("Не удалось скопировать. Проверьте разрешение браузера на буфер обмена.", "error");
    return false;
  }
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
    const row = e.target.closest(".platform-row-wrap");
    if (!row) return;
    dragged = row;
    row.classList.add("is-dragging");
    e.dataTransfer.effectAllowed = "move";
  });
  grid.addEventListener("dragover", (e) => {
    if (!dragged) return;
    e.preventDefault();
    const target = e.target.closest(".platform-row-wrap");
    if (!target || target === dragged || target.parentElement !== grid) return;
    const rect = target.getBoundingClientRect();
    const before = e.clientY < rect.top + rect.height / 2;
    grid.insertBefore(dragged, before ? target : target.nextSibling);
  });
  grid.addEventListener("dragend", () => {
    if (!dragged) return;
    dragged.classList.remove("is-dragging");
    dragged = null;
    const order = [...grid.querySelectorAll(".platform-row-wrap")].map((c) => c.dataset.source);
    saveSourceOrder(storageKey, order);
  });
}

// Тема: "light", "dark" или "system" (как в системе — ничего не
// сохраняем, берём из ОС).
function setTheme(mode, originEl = null) {
  const resolved = mode === "system"
    ? (window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark")
    : mode;
  const apply = () => {
    document.documentElement.dataset.theme = resolved;
    try {
      if (mode === "system") localStorage.removeItem("cj-theme");
      else localStorage.setItem("cj-theme", mode);
    } catch (e) {}
  };
  if (originEl) {
    const rect = originEl.getBoundingClientRect();
    document.documentElement.style.setProperty("--theme-toggle-x", `${rect.left + rect.width / 2}px`);
    document.documentElement.style.setProperty("--theme-toggle-y", `${rect.top + rect.height / 2}px`);
  }
  if (document.startViewTransition && !REDUCE_MOTION) document.startViewTransition(apply);
  else apply();
}

// ---------- Changelog popover ----------

const CHANGELOG_VERSION = "2026-10-08-new-ui";
const CHANGELOG_ITEMS = [
  "Новый вид: спокойная тёмная и светлая темы, цвет — только у состояний. Все функции на месте: редкие настройки — в шторке справа, на один клик ниже",
  "Главная: «Нужно ваше решение» первым блоком, итоги с трендом, площадки списком — нажмите на строку, и настройки откроются справа",
  "Режим «Откликаться / Только искать» для всех площадок разом — в шапке Главной",
  "Площадка на паузе после капчи — в её шторке кнопка «Я прошёл проверку — снять паузу» (то же, что /resume в боте)",
  "Изменения в шторке площадки сохраняются сразу — с кнопкой «Отменить» в уведомлении",
  "Палитра ⌘K ищет разделы, настройки, площадки и действия",
  "«Пауза на всё» в шапке Главной: отклики, рассылка и переписка от вашего имени стоят разом (в боте — /pause all)",
  "У каждой вакансии — «Почему бот так решил»; «Это была ошибка» запоминается и учитывается при оценке похожих, а пропущенную можно «Откликнуться всё равно»",
  "Вакансии из Telegram-каналов — прямо в «Общении», с черновиком от ИИ, выбором резюме и «Утром, в 10:00»",
  "«Уведомления» в меню: всё, что бот сообщал, даже без подключённого бота; в Настройках — что присылать",
];

function initChangelogPopover() {
  let seen = null;
  try {
    seen = localStorage.getItem("cj-seen-changelog");
    // Новичку «что нового» не нужно — запоминаем версию молча; окно
    // увидят только те, кто пользовался приложением до обновления.
    if (seen === null && localStorage.getItem("cj-seen-tour") !== "1") {
      localStorage.setItem("cj-seen-changelog", CHANGELOG_VERSION);
      return;
    }
  } catch (e) {
    return;
  }
  if (seen === CHANGELOG_VERSION) return;
  const el = document.createElement("div");
  el.className = "changelog-popover";
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-label", "Что нового");
  el.innerHTML = `
    <h4 data-ui="shell.changelog">Что нового</h4>
    <ul>${CHANGELOG_ITEMS.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>
    <button class="btn btn-primary" type="button">Понятно</button>
  `;
  document.body.appendChild(el);
  el.querySelector("button").addEventListener("click", () => {
    localStorage.setItem("cj-seen-changelog", CHANGELOG_VERSION);
    el.remove();
  });
}

// Бейдж непрочитанного виден только пока вкладка браузера открыта на
// экране — свёрнутое окно/фоновая вкладка про новые ответы HR или
// проблемную площадку никак не сигналит. MutationObserver, а не вызов
// из каждого места, где меняются оба бейджа (их минимум три) — один
// раз настроить и не думать про новые места в будущем.
const BASE_DOCUMENT_TITLE = document.title;
function updateDocumentTitleBadge() {
  const unread = parseInt(document.getElementById("telegram-unread-badge")?.textContent || "0", 10) || 0;
  const errorBadge = document.getElementById("overview-error-badge");
  const hasErrors = errorBadge && errorBadge.style.display !== "none";
  const count = unread + (hasErrors ? 1 : 0);
  document.title = count ? `(${count}) ${BASE_DOCUMENT_TITLE}` : BASE_DOCUMENT_TITLE;
}

function formatFitScoreThreshold(value) {
  const score = Number(value);
  return Number.isInteger(score) ? String(score) : score.toFixed(1).replace(".", ",");
}

function pulseSettingChanges(targets) {
  if (REDUCE_MOTION) return;
  targets.filter(Boolean).forEach((target) => {
    target.classList.remove("setting-change-pulse");
    void target.offsetWidth;
    target.classList.add("setting-change-pulse");
    target.addEventListener("animationend", () => target.classList.remove("setting-change-pulse"), { once: true });
  });
}

function updateFitThresholdPreview(changed = "", sourceField = "") {
  const minField = document.getElementById("limit-min-score");
  const fitField = document.getElementById("limit-suitability-score");
  const minSlider = document.getElementById("limit-min-score-slider");
  const fitSlider = document.getElementById("limit-suitability-score-slider");
  const board = document.getElementById("fit-threshold-board");
  if (!minField || !fitField || !minSlider || !fitSlider || !board) return;

  let min = changed === "min"
    ? Number(minSlider.value)
    : minField.value === "" ? Number(minSlider.value) : Number(minField.value);
  let fit = changed === "fit"
    ? Number(fitSlider.value)
    : fitField.value === "" ? Number(fitSlider.value) : Number(fitField.value);
  if (!Number.isFinite(min)) min = Number(minSlider.value) || 4;
  if (!Number.isFinite(fit)) fit = Number(fitSlider.value) || 7;
  min = Math.round(Math.max(0, Math.min(10, min)) * 2) / 2;
  fit = Math.round(Math.max(0, Math.min(10, fit)) * 2) / 2;

  if (min > fit) {
    if (changed === "min") fit = min;
    else min = fit;
  }

  const minText = formatFitScoreThreshold(min);
  const fitText = formatFitScoreThreshold(fit);
  board.classList.toggle("is-thresholds-equal", min === fit);
  const minPercent = `${min * 10}%`;
  const fitPercent = `${fit * 10}%`;
  board.style.setProperty("--fit-min-position", minPercent);
  board.style.setProperty("--fit-strong-position", fitPercent);
  minSlider.value = minText.replace(",", ".");
  fitSlider.value = fitText.replace(",", ".");
  if (sourceField !== minField.id) minField.value = minText.replace(",", ".");
  if (sourceField !== fitField.id) fitField.value = fitText.replace(",", ".");

  document.getElementById("fit-threshold-marker-min-value").textContent = minText;
  document.getElementById("fit-threshold-marker-fit-value").textContent = fitText;
  document.getElementById("fit-threshold-min-output").value = minText;
  document.getElementById("fit-threshold-fit-output").value = fitText;
  const summary = `Пропускать ниже ${minText} · сильное совпадение от ${fitText}`;
  document.getElementById("fit-threshold-live").textContent = summary;
  minSlider.setAttribute("aria-valuetext", `Пропускать оценки ниже ${minText}`);
  fitSlider.setAttribute("aria-valuetext", `Сильное совпадение от ${fitText}`);
  const weakBand = min === fit ? "слабого диапазона нет" : `от ${minText} до ${fitText} слабое совпадение`;
  document.getElementById("fit-threshold-scale").setAttribute(
    "aria-label",
    `Шкала оценки: ниже ${minText} пропускать, ${weakBand}, от ${fitText} сильное совпадение`
  );

  const explanation = min === fit
    ? `Ниже ${minText} бот пропустит вакансию. От ${fitText} — уверенное совпадение; диапазона слабых совпадений нет.`
    : `От ${minText} до значений ниже ${fitText} бот отправит отклик как на слабое совпадение. Ниже ${minText} — пропустит, от ${fitText} — уверенное совпадение.`;
  document.getElementById("fit-threshold-explainer").textContent = explanation;
  if (changed && !REDUCE_MOTION) {
    board.classList.remove("is-updating");
    void board.offsetWidth;
    board.classList.add("is-updating");
    board.addEventListener("animationend", () => board.classList.remove("is-updating"), { once: true });
  }
}

function initDashboard() {
  const titleBadgeObserver = new MutationObserver(updateDocumentTitleBadge);
  ["telegram-unread-badge", "overview-error-badge"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) titleBadgeObserver.observe(el, { attributes: true, attributeFilter: ["style"], childList: true, characterData: true, subtree: true });
  });

  document.querySelectorAll("nav.tabs button").forEach((b) => {
    b.addEventListener("click", () => switchTab(b.dataset.tab));
  });

  document.getElementById("theme-toggle")?.addEventListener("click", (ev) => {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    setTheme(next, ev.currentTarget);
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
  initAutoPane();
  initLookPane();
  initSettingsSearch();
  initJobsView();
  initRadioGroupKeyboard();
  document.querySelectorAll("#stats-period [data-days]").forEach((b) =>
    b.addEventListener("click", () => {
      statsPeriodDays = Number(b.dataset.days);
      document.querySelectorAll("#stats-period [data-days]").forEach((x) => {
        x.classList.toggle("on", x === b);
        x.setAttribute("aria-checked", x === b ? "true" : "false");
      });
      positionSegmented(document.getElementById("stats-period"));
      renderResults();
    })
  );
  initCommandPalette();
  initKeyboardShortcuts();

  document.getElementById("llm-key-toggle").addEventListener("click", () => {
    const input = document.getElementById("llm-key-input");
    input.type = input.type === "password" ? "text" : "password";
  });
  // Токен бота — такой же полноценный секрет, как ключ ИИ (даёт
  // управление ботом от вашего имени), но раньше был единственным
  // незамаскированным полем в "Подключениях" — остальные три (ключ ИИ,
  // пароль Gmail, ключ Hunter) уже type="password".
  document.getElementById("telegram-bot-token-toggle").addEventListener("click", () => {
    const input = document.getElementById("telegram-bot-token");
    input.type = input.type === "password" ? "text" : "password";
  });
  initDragReorder("own-channels", "cj-source-order-own");
  initDragReorder("source-grid-ru", "cj-source-order-ru");
  initDragReorder("source-grid-intl", "cj-source-order-intl");
  initChangelogPopover();
  initPointerEffects();

  // Строка площадки на Главной открывает её шторку; кнопки внутри
  // шторки — запуск хода, журнал, переходы (см. handleDrawerAction).
  document.getElementById("dashboard-sections").addEventListener("click", (e) => {
    const row = e.target.closest("[data-open-source]");
    if (row) openPlatform(row.dataset.openSource);
  });
  document.getElementById("platform-drawer").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-drawer-action]");
    if (btn) handleDrawerAction(btn);
  });
  document.querySelectorAll("#home-mode [data-mode]").forEach((b) =>
    b.addEventListener("click", () => setHomeMode(b.dataset.mode))
  );
  document.getElementById("home-run").addEventListener("click", () => document.getElementById("daemon-toggle").click());
  document.getElementById("home-pause-all").addEventListener("click", () => setPauseAll(!pauseAllState.paused));
  document.getElementById("home-palette").addEventListener("click", openCommandPalette);
  document.getElementById("palette-open").addEventListener("click", openCommandPalette);
  window.addEventListener("resize", () => positionSegmented(document.getElementById("home-mode")));
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

  const telegramGroupBtn = document.getElementById(
    "telegram-connect-group-btn"
  );
  if (telegramGroupBtn) {
    refreshTelegramGroupConnectStatus();
    telegramGroupBtn.addEventListener("click", async () => {
      const statusEl = document.getElementById(
        "telegram-connect-group-status"
      );
      statusEl.textContent = "Открываю выбор группы в Telegram…";
      try {
        const { username } = await api(
          "/api/settings/telegram/connect-group",
          { method: "POST" }
        );
        if (username) {
          window.open(
            `https://t.me/${username}?startgroup=connect`,
            "_blank"
          );
        }
        statusEl.textContent =
          "Выберите группу в открывшемся Telegram — дальше подхватится само…";
        const timer = setInterval(async () => {
          const done = await refreshTelegramGroupConnectStatus();
          if (done) clearInterval(timer);
        }, 3000);
      } catch (e) {
        statusEl.textContent = `Ошибка: ${e.message}`;
      }
    });
  }

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
          ? "Будет запускаться при входе в систему."
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
          ? "Бот работает в фоне, даже когда окно закрыто."
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
    // Реальный запуск (отклики + письма) не подтверждался вообще, хотя
    // ручной прогон одной площадки — подтверждается ("Запустить X
    // прямо сейчас?" ниже). Спрашиваем один раз в день, а не на каждый
    // клик — иначе быстро станет просто ещё одним экраном, который
    // закрывают не читая.
    if (endpoint === "start") {
      const today = new Date().toISOString().slice(0, 10);
      if (localStorage.getItem("cj-start-confirmed-on") !== today) {
        const ok = await showConfirm(
          "Запустить бота? Начнутся реальные отклики и/или письма по включённым площадкам и режимам — не тестовый прогон. Проверить, что найдётся, без отправки — кнопка «Проверить площадки, ничего не отправляя» рядом."
        );
        if (!ok) return;
        localStorage.setItem("cj-start-confirmed-on", today);
      }
    }
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

  // Любая широкая таблица ("Вакансии", "по источникам" в Аналитике,
  // будущие) — без подсказки не видно, что справа есть ещё колонки.
  // Слушатель один, делегированный (scroll не всплывает, поэтому
  // capture:true), а не разводка под каждую таблицу отдельно.
  document.addEventListener(
    "scroll",
    (e) => {
      if (e.target.classList?.contains("table-wrap")) updateTableScrollHint(e.target);
    },
    true
  );
  window.addEventListener("resize", updateAllTableScrollHints);

  // Фильтры «Вакансий» применяются сразу (initJobsView); скрытая кнопка
  // «Применить» осталась для старых ссылок.
  document
    .getElementById("history-apply-filters")
    .addEventListener("click", () => render.history());
  document
    .getElementById("log-source")
    .addEventListener("change", () => render.logs());
  document
    .getElementById("log-search")
    .addEventListener("input", () => renderLogLines());
  const logRawToggle = document.getElementById("log-raw-toggle");
  logRawToggle.checked = localStorage.getItem("cj-logs-raw") === "1";
  logRawToggle.addEventListener("change", () => {
    localStorage.setItem("cj-logs-raw", logRawToggle.checked ? "1" : "0");
    renderLogLines();
  });
  document
    .getElementById("settings-onboarding-hint-reveal")
    .addEventListener("click", () => {
      try {
        localStorage.setItem("cj-settings-full-shown", "1");
      } catch (e) {}
      document.getElementById("settings-jump").classList.remove("onboarding");
      document.getElementById("settings-onboarding-hint").style.display = "none";
    });
  document
    .getElementById("replies-filter-query")
    .addEventListener("input", () => {
      renderRepliesRows();
      renderTelegramConversationRows(telegramConversationsCache);
      lastTgPostsSnapshot = "";
      refreshTelegramPostsPanel();
    });

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
      const button = document.getElementById("blacklist-add");
      await withButtonLoading(button, async () => {
        try {
          await api("/api/blacklist", {
            method: "POST",
            body: JSON.stringify({ companies }),
          });
          showToast(`Добавлено в чёрный список: ${companies.length}`, "success");
          await render.analytics();
        } catch (err) {
          showToast(err.message.replace(/^\d+: /, ""), "error");
        }
      });
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
      const label = btn.textContent;
      let blocked = false;
      await withButtonLoading(btn, async () => {
        btn.textContent = "…";
        try {
          await api("/api/headhunter/block-employer", {
            method: "POST",
            body: JSON.stringify({ company }),
          });
          blocked = true;
          showToast(`Запрошена блокировка работодателя «${company}» на hh.ru`, "success");
        } catch (err) {
          btn.textContent = label;
          showToast(err.message.replace(/^\d+: /, ""), "error");
        }
      });
      if (blocked) {
        btn.disabled = true;
        btn.textContent = "Запрошено";
      }
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
        const warn = risks.length ? "· есть замечания ATS" : "";
        const title = risks.length ? ` title="${escapeHtml(risks.join(" "))}"` : "";
        return `<option value="${s}"${title}>${escapeHtml(s)}${warn ? " " + warn : ""}</option>`;
      })
      .join("");
    const updateNote = () => {
      const risks = atsReport[select.value] || [];
      note.innerHTML = risks.length
        ? `Возможные проблемы с ATS у стиля «${escapeHtml(select.value)}»: ${risks.map(escapeHtml).join(" ")}`
        : `У стиля «${escapeHtml(select.value)}» известных проблем с ATS не найдено (проверка эвристическая, не гарантия).`;
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
    .addEventListener("click", () => startResumeAudit(false));
  document
    .getElementById("gen-resume-audit-general")
    .addEventListener("click", () => startResumeAudit(true));

  ["primary", "linkedin"].forEach((kind) => {
    const input = document.getElementById(`resume-upload-${kind}`);
    input.addEventListener("change", async () => {
      const file = input.files[0];
      if (!file) return;
      await uploadResumeFile(kind, file);
      input.value = "";
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
    const llmTokenLimitRaw = document.getElementById("llm-token-limit").value;
    const llmTokenLimit = llmTokenLimitRaw ? parseInt(llmTokenLimitRaw, 10) : null;
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
          cover_letter_style: document.getElementById("limit-cover-letter-style").value,
          continuous_cycle_enabled: document.getElementById("limit-continuous-cycle").checked,
          continuous_cycle_gap_minutes: Math.max(1, parseInt(document.getElementById("limit-continuous-gap").value, 10) || 3),
          ...(llmAlert !== null ? { llm_daily_cost_alert_usd: llmAlert } : {}),
          ...(llmTokenLimit !== null ? { llm_daily_token_limit: llmTokenLimit } : {}),
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
      pulseSettingChanges([
        document.getElementById("limit-daily"),
        document.getElementById("limit-linkedin"),
        document.getElementById("limit-per-run"),
      ]);
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

  // Строгость подбора подставляет значения в те же поля порогов и
  // обновляет шкалу. Изменения сохраняются общей кнопкой «Сохранить».
  // Не переиспользует applyRiskPreset:
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
      updateFitThresholdPreview();
      pulseSettingChanges([
        document.getElementById("limit-min-score-slider")?.closest(".fit-threshold-editor"),
        document.getElementById("limit-suitability-score-slider")?.closest(".fit-threshold-editor"),
      ]);
    });

  document.getElementById("limit-min-score-slider").addEventListener("input", () => {
    updateFitThresholdPreview("min");
    document.getElementById("limit-fit-preset").value = "";
  });
  document.getElementById("limit-suitability-score-slider").addEventListener("input", () => {
    updateFitThresholdPreview("fit");
    document.getElementById("limit-fit-preset").value = "";
  });
  document.querySelectorAll("#provider-grid .provider-card").forEach((card) => {
    card.addEventListener("click", () => {
      // Модель и ключ привязаны к провайдеру — переключение карточки
      // сразу подставляет список моделей и превью ключа именно этого
      // провайдера, а не оставляет значения от предыдущего (иначе,
      // например, gpt-4o-mini тихо отправился бы в запрос к Groq).
      applyLLMSelection(card.dataset.provider, null);
      card.dispatchEvent(new Event("change", { bubbles: true }));
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
            remote: document.getElementById("search-remote").checked,
            hybrid: document.getElementById("search-hybrid").checked,
            onsite: document.getElementById("search-onsite").checked,
            only_with_salary: document.getElementById(
              "search-only-with-salary"
            ).checked,
            levels: [...document.querySelectorAll(".search-level")]
              .filter((el) => el.checked)
              .map((el) => el.value),
            employment_types: [...document.querySelectorAll(".search-employment")]
              .filter((el) => el.checked)
              .map((el) => el.value),
            posted_within_days: Number(document.getElementById("search-posted-within").value),
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

  const sendTelegramCodeButton = document.getElementById("telegram-login-send-code");
  sendTelegramCodeButton.addEventListener("click", async () => {
    const status = document.getElementById("telegram-login-status");
    const phone = document.getElementById("telegram-login-phone").value.trim();
    if (!phone) {
      status.textContent = "Введите номер телефона.";
      return;
    }
    await withButtonLoading(sendTelegramCodeButton, async () => {
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
  });

  const submitTelegramCodeButton = document.getElementById("telegram-login-submit-code");
  submitTelegramCodeButton.addEventListener("click", async () => {
    const status = document.getElementById("telegram-login-status");
    const code = document.getElementById("telegram-login-code").value.trim();
    if (!code) {
      status.textContent = "Введите код.";
      return;
    }
    await withButtonLoading(submitTelegramCodeButton, async () => {
      status.textContent = "Проверяю код…";
      try {
        const result = await api("/api/telegram/login/code", {
          method: "POST",
          body: JSON.stringify({ code }),
        });
        if (result.needs_password) {
          status.textContent = "Включена двухфакторка — введите пароль.";
          document.getElementById("telegram-login-password-row").style.display = "";
        } else {
          status.textContent = "Вход выполнен.";
          document.getElementById("telegram-login-code-row").style.display = "none";
          await render.telegram();
        }
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });
  });

  const submitTelegramPasswordButton = document.getElementById("telegram-login-submit-password");
  submitTelegramPasswordButton.addEventListener("click", async () => {
    const status = document.getElementById("telegram-login-status");
    const password = document.getElementById("telegram-login-password").value;
    if (!password) {
      status.textContent = "Введите пароль.";
      return;
    }
    await withButtonLoading(submitTelegramPasswordButton, async () => {
      status.textContent = "Проверяю пароль…";
      try {
        await api("/api/telegram/login/password", {
          method: "POST",
          body: JSON.stringify({ password }),
        });
        status.textContent = "Вход выполнен.";
        document.getElementById("telegram-login-password-row").style.display = "none";
        await render.telegram();
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });
  });

  const saveTelegramSettingsButton = document.getElementById("tg-settings-save");
  saveTelegramSettingsButton.addEventListener("click", async () => {
    const status = document.getElementById("tg-settings-status");
    const numOrNull = (id) => {
      const v = document.getElementById(id).value.trim();
      return v === "" ? null : Number(v);
    };
    await withButtonLoading(saveTelegramSettingsButton, async () => {
      status.textContent = "Сохранение…";
      try {
        const channelsRevisionAtSave = telegramChannelsRevision;
        const saved = await serializeTelegramSettingsSave(() =>
          api("/api/settings/telegram", {
            method: "POST",
            body: JSON.stringify({
              channels: linesOf("tg-channels"),
              max_post_age_days: numOrNull("tg-max-age"),
              daily_message_limit: numOrNull("tg-daily-limit"),
              auto_message: document.getElementById("tg-auto-message").checked,
              active_hours_start: numOrNull("tg-hours-start"),
              active_hours_end: numOrNull("tg-hours-end"),
            }),
          })
        );
        const channels = saved.channels || [];
        if (channelsRevisionAtSave === telegramChannelsRevision) {
          setTelegramChannels(channels);
        }
        status.textContent = `Сохранено: ${channels.length} каналов.`;
        setTimeout(() => (status.textContent = ""), 2000);
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });
  });

  function setTelegramChatStatus(message, kind = "") {
    const status = document.getElementById("tg-chat-status");
    status.textContent = message;
    status.classList.remove("is-error", "is-success", "is-sending");
    if (kind) status.classList.add(`is-${kind}`);
  }

  async function sendTelegramMessage() {
    if (!activeTelegramContact || sendingTelegramMessage) return;
    const input = document.getElementById("tg-chat-input");
    const text = input.value.trim();
    if (!text) return;
    const contact = activeTelegramContact;
    const button = document.getElementById("tg-chat-send");
    const retry = document.getElementById("tg-chat-retry");
    sendingTelegramMessage = true;
    retry.hidden = true;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = "Отправка…";
    setTelegramChatStatus("Отправка…", "sending");
    try {
      await api(
        `/api/telegram/conversations/${contact}/send`,
        { method: "POST", body: JSON.stringify({ text }) }
      );
      input.value = "";
      updateTelegramComposerState();
      setTelegramChatStatus(`Отправлено · @${contact}`, "success");
      try {
        await openTelegramConversation(contact, true);
      } catch (refreshError) {
        setTelegramChatStatus(`Отправлено @${contact}, но историю не удалось обновить: ${refreshError.message}`, "success");
      }
    } catch (e) {
      setTelegramChatStatus(`Ошибка: ${e.message}`, "error");
      retry.hidden = false;
    } finally {
      sendingTelegramMessage = false;
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.textContent = "Отправить";
      updateTelegramComposerState();
    }
  }

  document
    .getElementById("tg-chat-send")
    .addEventListener("click", sendTelegramMessage);
  document.getElementById("tg-chat-retry")?.addEventListener("click", sendTelegramMessage);
  const chatInput = document.getElementById("tg-chat-input");
  chatInput.addEventListener("input", updateTelegramComposerState);
  chatInput.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter" && !ev.shiftKey && !ev.isComposing) {
      ev.preventDefault();
      sendTelegramMessage();
    }
  });
  updateTelegramComposerState();
  document.getElementById("tg-chat-later").addEventListener("click", sendTelegramMessageLater);
  document.getElementById("tg-chat-suggest").addEventListener("click", suggestTelegramReplies);

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
        await openTelegramConversation(activeTelegramContact, true);
      } catch (e) {
        status.textContent = `Ошибка: ${e.message}`;
      }
    });

  document
    .getElementById("tg-chat-delete")
    .addEventListener("click", async () => {
      if (!activeTelegramContact) return;
      const ok = await showConfirm(
        `Удалить переписку с @${activeTelegramContact} в Telegram и приложении? У вас она исчезнет без возможности восстановить. Контакт останется в списке тех, кому уже писали, чтобы автоматическая отправка не повторилась.`
      );
      if (!ok) return;
      try {
        await api(`/api/telegram/conversations/${activeTelegramContact}`, {
          method: "DELETE",
        });
        activeTelegramContact = null;
        updateTelegramComposerState();
        document.getElementById("tg-chat-panel").style.display = "none";
        document.getElementById("tg-chat-empty").style.display = "";
        document.getElementById("tg-chat-delete").hidden = true;
        document.getElementById("talk-context-body").innerHTML = "";
        showToast("Диалог удалён", "info");
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
  switchTab(knownTabs.has(initialTab) || initialTab === "telegram" ? initialTab : "overview");
  // Ссылка вида #outreach из другого места (закладка, назад/вперёд).
  window.addEventListener("hashchange", () => {
    const tab = location.hash.replace("#", "");
    if ((knownTabs.has(tab) || tab === "telegram") && tab !== currentView) {
      closePlatformDrawer();
      switchTab(tab);
    }
  });
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
  const pendingLiveRefresh = new Map();
  function refreshActiveTab() {
    const active = currentView;
    if (active && LIVE_TABS.has(active)) {
      if (pendingLiveRefresh.has(active)) return pendingLiveRefresh.get(active);
      const request = Promise.resolve()
        .then(() => render[active]())
        .catch((error) => console.error(`Не удалось обновить вкладку ${active}`, error))
        .finally(() => pendingLiveRefresh.delete(active));
      pendingLiveRefresh.set(active, request);
      return request;
    } else if (active === "settings") {
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
  restoreSidebarCollapse();
  document.getElementById("app-shell").style.display = "";
  initDashboard();
  document
    .getElementById("direct-company-add")
    .addEventListener("click", addDirectCompany);
  document.getElementById("settings-direct").addEventListener("change", saveDirectSetting);
  document.getElementById("offer-add").addEventListener("click", addOffer);
  document.getElementById("ai-prompt-open").addEventListener("click", openPromptDrawer);
  document.getElementById("ai-prompt-copy").addEventListener("click", (e) => {
    const prompt = document.getElementById("ai-prompt");
    copyToClipboard(prompt.value, e.currentTarget, prompt);
  });
  document.getElementById("outreach-save").addEventListener("click", saveOutreachSettings);
  document.getElementById("outreach-send-hours-enabled").addEventListener("change", (event) => {
    document.getElementById("outreach-send-from").disabled = !event.target.checked;
    document.getElementById("outreach-send-to").disabled = !event.target.checked;
  });
  initTelegramChannelEditor();
  document.getElementById("tgq-save").addEventListener("click", saveTelegramWatch);
  document.getElementById("import-btn").addEventListener("click", () => document.getElementById("import-file").click());
  document.getElementById("import-file").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file && importToDrawer) {
      importPreview(file, openSideDrawer(`Загрузка: ${file.name}`, ""));
    } else if (file) {
      importPreview(file);
    }
    importToDrawer = false;
    e.target.value = "";
  });
  document.getElementById("tgq-greeting").addEventListener("input", updateGreetingPreview);
  const openExtraResumePicker = () => {
    if (!resumeUploadBusy) document.getElementById("tgq-resume-file").click();
  };
  document.getElementById("tgq-resume-add").addEventListener("click", openExtraResumePicker);
  document.getElementById("resume-dropzone-pick").addEventListener("click", openExtraResumePicker);
  const resumeDropzone = document.getElementById("resume-dropzone");
  resumeDropzone.addEventListener("dragenter", (event) => {
    if (resumeUploadBusy || ![...event.dataTransfer.types].includes("Files")) return;
    event.preventDefault();
    resumeDropzone.classList.add("is-dragover");
  });
  resumeDropzone.addEventListener("dragover", (event) => {
    if (resumeUploadBusy || ![...event.dataTransfer.types].includes("Files")) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });
  resumeDropzone.addEventListener("dragleave", (event) => {
    if (!resumeDropzone.contains(event.relatedTarget)) resumeDropzone.classList.remove("is-dragover");
  });
  resumeDropzone.addEventListener("drop", (event) => {
    if (resumeUploadBusy || !event.dataTransfer.files?.length) return;
    event.preventDefault();
    resumeDropzone.classList.remove("is-dragover");
    uploadTelegramResumes([...event.dataTransfer.files]);
  });
  document.getElementById("tgq-resume-file").addEventListener("change", (e) => {
    uploadTelegramResumes([...e.target.files]);
    e.target.value = "";
  });
  document
    .querySelector('[data-settings-tab="settings-tg-quick"]')
    .addEventListener("click", loadTelegramWatch);
  bindGotoSettings(document.getElementById("view-replies"));
  document.querySelectorAll("[data-goto-view]").forEach((a) =>
    a.addEventListener("click", (e) => {
      e.preventDefault();
      switchTab(a.dataset.gotoView);
    })
  );
  const saveTelegramKeysButton = document.getElementById("tg-keys-save");
  saveTelegramKeysButton.addEventListener("click", async () => {
    await withButtonLoading(saveTelegramKeysButton, async () => {
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
  });
  document.getElementById("parser-open-base").addEventListener("click", () => {
    document.getElementById("contacts-filter-source").value = "telegram";
    switchTab("contacts");
  });
  document.querySelectorAll("#base-table th[data-sort] button").forEach((button) =>
    button.addEventListener("click", (event) => {
      pendingBaseSortPositions = captureBaseRowPositions(event.detail > 0);
      const th = button.closest("th[data-sort]");
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
  ["outreach-digest", "outreach-digest-hour", "digest-quiet", "notify-activity", "notify-failures"].forEach((id) => document.getElementById(id).addEventListener("change", saveDigest));
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
  initSettingsExtras();
  initNotifications();
  initTalkExtras();
});


// --- Доработки из раздела 11 карты интерфейса (docs/UI_MAP.md) -------------

// «2026-10-08» → «8 октября», ручная копия «2026-10-08-153012» → «8 октября, 15:30».
function backupLabel(b) {
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:-(\d{2})(\d{2})\d{2})?$/.exec(b.date || "");
  if (!m) return b.date;
  const day = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  const text = day.toLocaleDateString("ru-RU", { day: "numeric", month: "long" });
  return m[4] ? `${text}, ${m[4]}:${m[5]}` : text;
}

async function backupNow(btn) {
  btn.disabled = true;
  try {
    const res = await api("/api/backups/now", { method: "POST" });
    showToast(`Копия сохранена: ${backupLabel({ date: res.date })}`, "success");
    loadBackups();
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
  } finally {
    btn.disabled = false;
  }
}

function renderLetterInstructions(text) {
  const el = document.getElementById("outreach-letter-current");
  if (!el) return;
  el.textContent = text ? `Ваши правила: ${text.replace(/\s*\n\s*/g, "; ")}` : "Своих правил нет — бот пишет по основе.";
}

// «Запасные — пробуются по порядку»: провайдеры с сохранёнными ключами,
// кроме основного; порядок меняется стрелками и сохраняется сразу.
let fallbackOrderState = [];
function providerTitle(p) {
  const card = document.querySelector(`#provider-grid .provider-card[data-provider="${p}"] span`);
  return card ? card.textContent : p;
}
function renderFallbackOrder(llm) {
  const list = document.getElementById("llm-fallback-order");
  if (!list) return;
  const withKeys = Object.keys(llm.api_key_previews || {}).filter((p) => p !== llm.provider);
  const order = (llm.fallback_order || []).filter((p) => withKeys.includes(p));
  fallbackOrderState = [...order, ...withKeys.filter((p) => !order.includes(p))];
  if (!fallbackOrderState.length) {
    list.innerHTML = `<li class="order-empty muted small">Ключей других провайдеров нет — запасных не будет. Добавьте ключ ниже, выбрав провайдера.</li>`;
    return;
  }
  list.innerHTML = fallbackOrderState
    .map(
      (p, i) => `<li class="order-item"><span class="order-num">${i + 1}</span><span class="order-name">${escapeHtml(providerTitle(p))}</span>
        <button type="button" class="btn btn-ghost btn-icon btn-small" data-order-move="-1" data-order-index="${i}" aria-label="Поднять ${escapeHtml(providerTitle(p))}" ${i === 0 ? "disabled" : ""}>↑</button>
        <button type="button" class="btn btn-ghost btn-icon btn-small" data-order-move="1" data-order-index="${i}" aria-label="Опустить ${escapeHtml(providerTitle(p))}" ${i === fallbackOrderState.length - 1 ? "disabled" : ""}>↓</button></li>`
    )
    .join("");
}

async function moveFallback(index, delta) {
  const before = [...fallbackOrderState];
  const to = index + delta;
  if (to < 0 || to >= fallbackOrderState.length) return;
  const order = [...fallbackOrderState];
  [order[index], order[to]] = [order[to], order[index]];
  try {
    const llm = await api("/api/settings/llm", { method: "POST", body: JSON.stringify({ fallback_order: order }) });
    renderFallbackOrder(llm);
    const btn = document.querySelector(`#llm-fallback-order [data-order-index="${to}"][data-order-move="${delta}"]`)
      || document.querySelector(`#llm-fallback-order [data-order-index="${to}"]`);
    btn?.focus();
    showSavedToast("Порядок запасных сохранён", async () => {
      renderFallbackOrder(await api("/api/settings/llm", { method: "POST", body: JSON.stringify({ fallback_order: before }) }));
    });
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
  }
}

async function disconnectTelegramAccount() {
  const ok = await showConfirm(
    "Отключить Telegram-аккаунт? Парсер и сообщения HR с вашего имени остановятся, сеанс закроется и в самом Telegram. Переписка, База и ключи останутся — подключить снова можно по номеру и коду."
  );
  if (!ok) return;
  try {
    const res = await api("/api/telegram/logout", { method: "POST" });
    showToast(res.logged_out ? "Telegram-аккаунт отключён" : "Отключено здесь. Если сеанс остался — завершите его в Telegram: Настройки → Устройства", "success", 7000);
    document.getElementById("tg-connect-panel").open = true;
    refreshTelegramAccount();
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
  }
}

function initSettingsExtras() {
  document.getElementById("tg-account-off")?.addEventListener("click", disconnectTelegramAccount);
  document.getElementById("backup-now")?.addEventListener("click", (e) => backupNow(e.currentTarget));
  document.getElementById("llm-fallback-order")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-order-move]");
    if (btn) moveFallback(Number(btn.dataset.orderIndex), Number(btn.dataset.orderMove));
  });
  const edit = document.getElementById("outreach-letter-edit");
  const box = document.getElementById("outreach-letter-box");
  edit?.addEventListener("click", () => {
    box.hidden = !box.hidden;
    edit.setAttribute("aria-expanded", String(!box.hidden));
    edit.textContent = box.hidden ? "Изменить" : "Свернуть";
    if (!box.hidden) document.getElementById("outreach-letter-instructions").focus();
  });
  document.getElementById("outreach-letter-instructions")?.addEventListener("change", (e) =>
    renderLetterInstructions(e.target.value.trim())
  );
}

// --- Уведомления: история того, что бот сообщал (колокольчик) --------------

const NOTIF_SEEN_KEY = "cj-notif-seen";
const NOTIF_STATUS = {
  sent: "в Telegram",
  queued: "ждёт связи с Telegram",
  app: "только здесь — бот не подключён",
  muted: "не отправлено — этот вид выключен",
  digest: "в утренней сводке",
  window: "сообщение в этом окне",
};
let notifItems = [];

function notifSeenAt() {
  try {
    return localStorage.getItem(NOTIF_SEEN_KEY) || "";
  } catch (e) {
    return "";
  }
}

function renderNotifCount() {
  const badge = document.getElementById("notif-count");
  if (!badge) return;
  const seen = notifSeenAt();
  const unread = notifItems.filter((n) => n.at > seen).length;
  badge.hidden = !unread;
  badge.textContent = unread > 99 ? "99+" : String(unread);
  document.getElementById("notif-open")?.setAttribute("aria-label", unread ? `Уведомления: новых ${unread}` : "Уведомления");
}

async function refreshNotifications() {
  if (document.visibilityState !== "visible") return;
  try {
    notifItems = (await api("/api/notifications?limit=100")).items || [];
  } catch (e) {
    return;
  }
  renderNotifCount();
}

function notifRowHtml(n) {
  const failure = n.kind === "failure";
  const time = n.at ? fmtDay(n.at) : "";
  const topic = SOURCE_LABELS[n.category] ? sourceLabel(n.category) : n.category;
  return `<li class="notif-row${failure ? " is-failure" : ""}">
    <span class="dot ${failure ? "error" : "ok"}" aria-hidden="true"></span>
    <div class="notif-body"><div class="notif-text">${escapeHtml(n.text)}</div>
      <div class="muted small">${escapeHtml(time)}${topic ? ` · ${escapeHtml(topic)}` : ""} · ${escapeHtml(NOTIF_STATUS[n.status] || n.status)}</div></div></li>`;
}

async function openNotifications() {
  await refreshNotifications();
  const filters = [["all", "Все"], ["failure", "Сбои"], ["activity", "Отклики и ответы"], ["window", "В окне"]];
  const body = openSideDrawer({
    title: "Уведомления",
    sub: "Что бот сообщал. Что присылать в Telegram — в Настройках → Уведомления",
    body: `<div class="subnav notif-filter" role="group" aria-label="Какие уведомления показать">${filters
      .map(([v, t], i) => `<button type="button" class="${i ? "" : "active"}" data-notif-filter="${v}" aria-pressed="${i ? "false" : "true"}">${t}</button>`)
      .join("")}</div><ul class="notif-list" id="notif-list"></ul>`,
    foot: `<button type="button" class="btn btn-small" id="notif-settings">Что присылать</button>`,
  });
  openDrawerSource = null;
  const list = body.querySelector("#notif-list");
  const show = (kind, animate = false) => {
    const items = kind === "window" ? toastLog : notifItems.filter((n) => kind === "all" || n.kind === kind);
    list.innerHTML = items.length
      ? items.map((item, index) => {
          const row = notifRowHtml(item);
          if (!animate || index > 6) return row;
          return row.replace('<li class="notif-row', `<li style="animation-delay:${index * 22}ms" class="notif-row notif-row-arrive`);
        }).join("")
      : `<li>${emptyStateHtml(kind === "failure" ? "Сбоев не было." : kind === "window" ? "В этом окне сообщений ещё не было." : "Пока бот ничего не сообщал.")}</li>`;
  };
  show("all");
  body.querySelectorAll("[data-notif-filter]").forEach((btn) =>
    btn.addEventListener("click", () => {
      body.querySelectorAll("[data-notif-filter]").forEach((b) => {
        b.classList.toggle("active", b === btn);
        b.setAttribute("aria-pressed", String(b === btn));
      });
      show(btn.dataset.notifFilter, shouldAnimateNavigation());
    })
  );
  document.getElementById("notif-settings").addEventListener("click", () => {
    closePlatformDrawer();
    gotoSettings("settings-notifications");
  });
  if (notifItems.length) {
    try {
      localStorage.setItem(NOTIF_SEEN_KEY, notifItems[0].at);
    } catch (e) {}
  }
  renderNotifCount();
}

function initNotifications() {
  document.getElementById("notif-open")?.addEventListener("click", openNotifications);
  refreshNotifications();
  setInterval(refreshNotifications, 30000);
}


// --- «Пауза на всё»: отклики, рассылка и переписка от вашего имени разом ---

let pauseAllState = { paused: false, since: "" };

function renderPauseAll(status) {
  pauseAllState = status.pause_all || { paused: false, since: "" };
  const paused = pauseAllState.paused;
  const btn = document.getElementById("home-pause-all");
  if (btn) {
    btn.textContent = paused ? "Снять паузу" : "Пауза на всё";
    btn.classList.toggle("btn-primary", paused);
    btn.setAttribute("aria-pressed", String(paused));
  }
  const banner = document.getElementById("pause-banner");
  if (!banner) return;
  banner.hidden = !paused;
  if (!paused) return;
  const since = pauseAllState.since ? fmtDay(pauseAllState.since) : "";
  banner.innerHTML = `<span class="dot warn" aria-hidden="true"></span>
    <span class="pause-text"><b>Всё на паузе${since ? ` с ${escapeHtml(since.replace(/^сегодня /, ""))}` : ""}.</b> Отклики, рассылка и переписка от вашего имени стоят. Ответы HR и команды боту приходят как обычно.</span>
    <button type="button" class="btn btn-small" data-pause-resume>Снять паузу</button>`;
  banner.querySelector("[data-pause-resume]").addEventListener("click", () => setPauseAll(false));
}

async function setPauseAll(paused) {
  try {
    const state = await api("/api/pause-all", { method: "POST", body: JSON.stringify({ paused }) });
    pauseAllState = state;
    lastOverviewSnapshot = "";
    if (currentView === "overview") render.overview();
    showSavedToast(
      paused ? "Всё на паузе: ничего не уходит от вашего имени" : "Пауза снята — бот продолжает",
      async () => {
        await api("/api/pause-all", { method: "POST", body: JSON.stringify({ paused: !paused }) });
        lastOverviewSnapshot = "";
        if (currentView === "overview") render.overview();
      }
    );
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
  }
}


// --- Общение: вакансии из Telegram с черновиком от ИИ (talk.tg.posts) ------

let tgPostsData = { posts: [], resume_options: [], sent_today: 0, daily_limit: 15 };
let talkListTab = "all";
let activeTgPostId = null;
let tgPostHistoryState = { postId: null, contact: null, messages: [] };
let lastTgPostsSnapshot = "";
let lastTgPostHistorySnapshot = "";
let tgPostsVisibleLimit = 200;
const tgPostResume = {}; // выбор «Резюме:» по посту, пока не отправили
let tgPostContactChoice = {}; // выбранный контакт сохраняется при обновлении
const hirifyLoginRequired = new Set(); // показываем повторный вход лишь при истёкшей сессии

// Время в будущем: «сегодня в 10:00», «завтра в 10:00», «9 окт. в 10:00».
function fmtWhen(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const days = Math.round((new Date(d).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 864e5);
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (days === 0) return `сегодня в ${time}`;
  if (days === 1) return `завтра в ${time}`;
  return `${d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })} в ${time}`;
}

function tgPostBadge(post) {
  if (post.status === "sent") return { dot: "ok", text: "отправлено" };
  if (post.status === "queued") return { dot: "idle", text: "в очереди на отправку" };
  if (post.status === "send_unknown") return { dot: "warn", text: "проверьте отправку" };
  if (post.status === "skipped_contacted") return { dot: "idle", text: "уже писали" };
  if (post.status === "hidden") return { dot: "idle", text: "скрыто" };
  if (post.status === "blocked") return { dot: "warn", text: "не писать" };
  if (post.scheduled) return { dot: "idle", text: `уйдёт ${fmtWhen(post.scheduled.send_after)}` };
  if (!tgPostRecipients(post).length) return { dot: "idle", text: "адресат не найден" };
  if (post.contacts.some((c) => (c.note || "").startsWith("писали"))) return { dot: "warn", text: "уже писали" };
  if (tgPostDraft(post)) return { dot: "ok", text: "черновик готов" };
  return { dot: "", text: "новая" };
}

async function renderTelegramPosts() {
  const block = document.getElementById("tg-posts-block");
  if (!block) return;
  let data;
  try {
    data = await api("/api/telegram/posts?scope=all&limit=200&offset=0");
    const posts = [...data.posts];
    while (posts.length < Math.min(tgPostsVisibleLimit, data.total) && posts.length) {
      const next = await api(`/api/telegram/posts?scope=all&limit=200&offset=${posts.length}`);
      if (!next.posts.length) break;
      posts.push(...next.posts);
    }
    data = { ...data, posts };
  } catch (e) {
    const postsList = document.getElementById("tg-posts-list");
    if (postsList && typeof renderRetryState === "function") {
      renderRetryState(
        postsList,
        `Не удалось загрузить вакансии из Telegram: ${e.message}`,
        () => renderTelegramPosts()
      );
    }
    throw e;
  }
  const previousPostIds = new Set(tgPostsData.posts.map((post) => post.id));
  const hadPostSnapshot = Boolean(lastTgPostsSnapshot);
  const arrivedPostIds = new Set(
    hadPostSnapshot && !REDUCE_MOTION && document.visibilityState === "visible"
      ? data.posts.filter((post) => !previousPostIds.has(post.id)).map((post) => post.id)
      : []
  );
  const previousActivePost = tgPostsData.posts.find((p) => p.id === activeTgPostId);
  tgPostsData = data;
  updateTalkListCount();
  const laterBtn = document.getElementById("tg-chat-later");
  if (laterBtn) laterBtn.textContent = `Утром, в ${data.morning_hour ?? 10}:00`;
  const showAll = talkListTab === "posts" || (talkListTab === "all" && (!repliesKind || repliesKind === "telegram"));
  block.hidden = !showAll;
  const more = document.getElementById("tg-posts-more");
  if (more) more.hidden = data.posts.length >= (data.total ?? data.posts.length);
  const query = document.getElementById("replies-filter-query")?.value.trim().toLowerCase() || "";
  const snapshot = JSON.stringify([data.posts.map((p) => [p.id, p.source, p.title, p.status, p.sent_at, p.resume_status, p.resume_name, p.draft?.code, p.scheduled?.id, p.contacts.map((c) => [c.kind, c.value, c.note]), p.recipient_options]), activeTgPostId, showAll, query]);
  if (snapshot === lastTgPostsSnapshot) {
    const active = data.posts.find((p) => p.id === activeTgPostId);
    if (active && !document.getElementById("tg-post-panel")?.hidden) loadTelegramPostHistory(active);
    return;
  }
  lastTgPostsSnapshot = snapshot;
  document.getElementById("tg-posts-count").textContent = `· ${data.total ?? data.posts.length}`;
  if (!data.posts.length) {
    document.getElementById("tg-posts-list").innerHTML = emptyStateHtml(
      "Вакансий пока нет. Здесь появятся посты из Telegram и Hirify."
    );
    document.getElementById("tg-chat-posts-list")?.replaceChildren();
    if (previousActivePost) {
      closeTelegramPost();
      document.getElementById("tg-chat-empty").style.display = "";
      document.getElementById("talk-context-body").innerHTML = "";
    }
    return;
  }
  const shown = query ? data.posts.filter((p) =>
    `${p.channel} ${p.source} ${p.title} ${p.text || ""} ${p.link || ""} ${(p.contacts || []).map((c) => c.value).join(" ")}`.toLowerCase().includes(query)
  ) : data.posts;
  const postRow = (p) => {
      const b = tgPostBadge(p);
      const source = p.source === "hirify" ? "Hirify" : `@${p.channel}`;
      const recipients = tgPostRecipients(p).map((c) => c.kind === "telegram" ? `@${c.value}` : c.value).join(", ") || "адресат не найден";
      const arrivalMotion = arrivedPostIds.has(p.id) && !query && showAll ? " talk-post-arrive" : "";
      return `<button type="button" class="row talk-row${p.id === activeTgPostId ? " is-selected" : ""}${arrivalMotion}" data-tg-post="${escapeHtml(p.id)}">
        ${plogoHtml(p.source === "hirify" ? "hirify" : "telegram")}
        <span class="row-main">
          <span class="talk-row-top"><span class="row-title" title="${escapeHtml(p.title)}">${escapeHtml(truncate(p.title, 90))}</span></span>
          <span class="talk-post-meta small muted"><span class="talk-post-source">${escapeHtml(source)}</span><span class="talk-post-status">${b.dot ? `<span class="dot ${b.dot}" aria-hidden="true"></span>` : ""}${escapeHtml(b.text)}</span><span class="talk-post-recipient" title="${escapeHtml(recipients)}">${escapeHtml(recipients)}</span><span class="talk-post-date">${p.found_at ? fmtDay(p.found_at) : ""}</span></span>
        </span>
      </button>`;
    };
  document.getElementById("tg-posts-list").innerHTML = shown.length ? shown.map(postRow).join("") : emptyStateHtml("Вакансии не найдены.");
  const conversationPosts = shown.filter((p) => !["hidden", "blocked"].includes(p.status));
  document.getElementById("tg-chat-posts-list").innerHTML = conversationPosts.map(postRow).join("");
  const active = data.posts.find((p) => p.id === activeTgPostId);
  if (active && (previousActivePost?.status !== active.status || previousActivePost?.resume_status !== active.resume_status) && !document.getElementById("tg-post-panel")?.hidden) openTelegramPost(active.id);
  if (previousActivePost && !active) {
    closeTelegramPost();
    document.getElementById("tg-chat-empty").style.display = "";
    document.getElementById("talk-context-body").innerHTML = "";
  }
}

function refreshTelegramPostsPanel() {
  return renderTelegramPosts().catch(() => {});
}

function closeTelegramPost() {
  activeTgPostId = null;
  lastTgPostHistorySnapshot = "";
  const panel = document.getElementById("tg-post-panel");
  if (panel) {
    panel.hidden = true;
    panel.innerHTML = "";
  }
  document.querySelectorAll("#tg-posts-list .talk-row, #tg-chat-posts-list .talk-row").forEach((r) => r.classList.remove("is-selected"));
}

function tgPostContact(post) {
  const recipients = tgPostRecipients(post);
  const chosen = tgPostContactChoice[post.id];
  const match = (value) => recipients.find((c) => c.value.toLowerCase() === String(value).toLowerCase());
  return chosen
    ? match(chosen)
    : post.draft
    ? match(post.draft.contact)
    : post.contact
    ? match(post.contact)
    : recipients.length === 1 ? recipients[0] : undefined;
}

function tgPostRecipients(post) {
  const options = post.recipient_options ?? post.contacts ?? [];
  return options.filter((c) => c.kind === "telegram" || c.kind === "email");
}

function tgPostDraft(post) {
  const chosen = tgPostContactChoice[post.id];
  if (chosen && post.draft?.contact !== chosen) return null;
  return post.draft;
}

function tgPostResumeChoice(post) {
  if (post.id in tgPostResume) return tgPostResume[post.id];
  const fit = tgPostsData.resume_options.find((r) => r.russian === post.russian || r.russian === null);
  return fit ? fit.name : "";
}

function animatePostRecipientSelection(panel, animate = false) {
  const check = panel?.querySelector(".post-recipient.active .post-recipient-check");
  if (!animate || REDUCE_MOTION || typeof check?.animate !== "function") return;
  check.animate(
    [{ opacity: 0.5, transform: "scale(.82)" }, { opacity: 1, transform: "scale(1)" }],
    { duration: 150, easing: "cubic-bezier(0.23, 1, 0.32, 1)" }
  );
}

function tgPostPanelHtml(post) {
  const recipients = tgPostRecipients(post);
  const contact = tgPostContact(post);
  const draft = tgPostDraft(post);
  const isEmail = contact?.kind === "email";
  const resume = tgPostResumeChoice(post);
  const full = !isEmail && tgPostsData.sent_today >= tgPostsData.daily_limit;
  const sourceName = post.source === "hirify" ? "Hirify" : `@${escapeHtml(post.channel)}`;
  const recipient = contact ? `${isEmail ? "" : "@"}${escapeHtml(contact.value)}` : "";
  const head = `<div class="post-head">${plogoHtml(post.source === "hirify" ? "hirify" : "telegram")}<div class="post-head-copy"><h3 class="m0" title="${escapeHtml(post.title)}">${escapeHtml(truncate(post.title, 100))}</h3>
    <span class="muted small">Источник: ${sourceName}${post.found_at ? " · " + escapeHtml(fmtDay(post.found_at)) : ""}</span></div></div>
    <details class="post-text"><summary><span><strong>Исходный пост</strong><small>${escapeHtml(truncate(post.text || post.title, 135))}</small></span><span aria-hidden="true">⌄</span></summary><div class="letter-text">${escapeHtml(post.text || "")}</div><a class="btn btn-small btn-ghost" href="${escapeHtml(post.link)}" target="_blank" rel="noopener">Открыть источник ↗</a></details>`;
  const contacts = `<div class="post-recipient-section"><div class="post-recipient-heading"><div class="post-section-label">Кому отправить <span class="muted" title="Выберите адресата перед отправкой">ⓘ</span></div></div>
    ${recipients.length ? `<div class="post-recipient-list" role="radiogroup" aria-label="Кому отправить">${recipients.map((c) => {
      const selected = c.value === contact?.value;
      const address = `${c.kind === "telegram" ? "@" : ""}${escapeHtml(c.value)}`;
      return `<button type="button" class="post-recipient${selected ? " active" : ""}" role="radio" aria-checked="${selected}" data-post-contact="${escapeHtml(c.value)}"><span class="post-recipient-icon">${c.kind === "telegram" ? "✈" : "@"}</span><span class="post-recipient-copy"><strong>${address}</strong><small>${c.kind === "telegram" ? "Telegram" : "Email"}${c.note ? ` · ${escapeHtml(c.note)}` : ""}</small></span><span class="post-recipient-check" aria-hidden="true">${selected ? "●" : "○"}</span></button>`;
    }).join("")}</div>` : `<p class="muted small">Адресат не найден. Проверьте исходную вакансию и добавьте контакт вручную.</p>`}
    ${post.source === "hirify" ? `<div class="post-hirify-actions">${hirifyLoginRequired.has(post.id) ? `<button type="button" class="btn btn-small btn-ghost" data-post-action="login-hirify">Повторить вход в Hirify</button>` : ""}<button type="button" class="btn btn-small" data-post-action="sync-hirify">Получить контакты из Hirify</button></div>` : ""}
    ${post.status === "new" ? `<details class="post-add-recipient"><summary>+ Добавить адресата</summary><div><select id="tg-post-contact-kind" aria-label="Тип адресата"><option value="telegram">Telegram</option><option value="email">Email</option></select><input id="tg-post-contact-value" type="text" autocomplete="off" placeholder="@username или email" aria-label="Адресат"><button type="button" class="btn btn-small" data-post-action="add-contact">Добавить адресата</button></div></details>` : ""}</div>`;
  const history = `<section class="post-history is-empty" aria-label="Переписка"><div id="tg-post-history" class="post-history-messages"><div class="post-history-empty"><span class="post-history-empty-icon" aria-hidden="true">▢</span><strong>${isEmail ? "Письмо ещё не отправлено" : "Переписки пока нет — она появится после отправки"}</strong><span>${contact ? `Напишите сообщение и отправьте его ${recipient}. Здесь будут все сообщения в этом диалоге.` : "Выберите адресата, чтобы увидеть историю и подготовить сообщение."}</span></div></div><button type="button" id="tg-post-new-messages" class="btn btn-small chat-new-messages" aria-live="polite" hidden>Показать новые сообщения</button></section>`;
  const locked = ["sent", "queued", "send_unknown", "skipped_contacted", "hidden", "blocked"].includes(post.status);
  const status = post.status === "sent"
    ? `Сообщение отправлено${post.sent_at ? ` ${escapeHtml(fmtDay(post.sent_at))}` : ""}${recipient ? ` → ${recipient}` : ""}.${post.resume_status === "sent" ? " Резюме тоже отправлено." : post.resume_status === "failed" ? " Резюме не отправилось — его можно отправить отдельно в переписке." : ""}`
    : post.status === "queued" ? "Сообщение ожидает автоматической отправки. Факт отправки появится здесь."
    : post.status === "send_unknown" ? "Отправку не удалось подтвердить. Проверьте переписку в Telegram."
    : post.status === "skipped_contacted" ? "Автоматическая отправка отменена: этому контакту уже писали."
    : post.status === "hidden" ? "Вакансия скрыта."
    : post.status === "blocked" ? "Для этого контакта установлено «Не писать»." : "";
  if (locked) return `${head}${contacts}${status ? `<div class="fix is-info"><span class="dot ${post.status === "sent" ? "ok" : "idle"}"></span><div class="fix-body">${status}</div></div>` : ""}${history}${contact?.kind === "telegram" && ["sent", "skipped_contacted"].includes(post.status) ? `<button type="button" class="btn btn-small" data-post-action="open-chat">Продолжить переписку с ${recipient}</button>` : ""}`;
  const scheduled = post.scheduled
    ? `<div class="fix is-info"><span class="dot idle"></span><div class="fix-body">Сообщение уйдёт ${escapeHtml(fmtWhen(post.scheduled.send_after))} — ночью HR не беспокоим.</div><button type="button" class="btn btn-small" data-post-action="unschedule">Отменить</button></div>`
    : "";
  if (!contact) return `${head}${contacts}${history}<div class="composer-empty">Выберите адресата: затем можно проверить черновик и отправить сообщение.</div>`;
  if (post.scheduled && !draft) return `${head}${contacts}${history}${scheduled}`;
  const draftBlock = draft
    ? `<div class="draft-note"><label for="tg-post-text">Сообщение</label><button type="button" class="btn btn-ghost btn-small" data-post-action="rewrite">✧ Переписать с ИИ</button></div>
       <textarea id="tg-post-text" rows="5" aria-label="Текст сообщения">${escapeHtml(draft.text)}</textarea>`
    : `<div class="composer-empty"><span>Черновика пока нет. ИИ напишет его под эту вакансию и ваше резюме — ничего не уйдёт без вашего «Отправить».</span>
       <button type="button" class="btn btn-primary btn-small" data-post-action="draft">Написать черновик</button></div>`;
  const resumes = [{ name: "", label: "без резюме" }, ...tgPostsData.resume_options];
  const chosenResume = resumes.find((r) => r.name === resume);
  const resumeRow = draft
    ? `<div class="post-attachment"><button type="button" class="post-attachment-open" data-post-action="resume-menu" aria-expanded="false" aria-controls="tg-post-resume-menu"><span aria-hidden="true">📎</span> ${resume ? "Прикрепить резюме" : "Выбрать резюме"}</button><span class="post-attachment-name">${resume ? escapeHtml(chosenResume?.label || resume.split(/[\\/]/).pop()) : "Без резюме"}</span>${resume ? `<button type="button" class="post-attachment-remove" data-post-resume="" aria-label="Убрать резюме">×</button>` : ""}<div id="tg-post-resume-menu" class="post-resume-menu" role="radiogroup" aria-label="Резюме" hidden>${resumes
        .map((r) => `<button type="button" class="${r.name === resume ? "active" : ""}" role="radio" aria-checked="${r.name === resume}" data-post-resume="${escapeHtml(r.name)}">${escapeHtml(r.label)}</button>`)
        .join("")}</div></div>
       <div class="post-delivery"><span class="post-route">${isEmail ? "С вашего Gmail" : "С вашего Telegram"} → <strong>${recipient}</strong><small> · ещё не отправлено</small></span>
       <span class="composer-actions">${!isEmail && !post.scheduled ? `<button type="button" class="btn btn-small" data-post-action="later">Утром, в ${tgPostsData.morning_hour ?? 10}:00</button>` : ""}
       <button type="button" class="btn btn-primary btn-small" data-post-action="send" ${full ? "disabled" : ""}>${full ? "Лимит на сегодня" : isEmail ? "Отправить письмо" : "Отправить в Telegram"}</button></span></div>
       <span class="muted small">${!isEmail ? `Сегодня ${tgPostsData.sent_today} из ${tgPostsData.daily_limit} · ` : ""}Ctrl/⌘ + Enter — отправить${resume ? " · с резюме" : ""}</span>`
    : "";
  return `${head}${contacts}${history}${scheduled}<div class="post-composer">${draftBlock}${resumeRow}</div>`;
}

function tgPostContextHtml(post) {
  const contact = tgPostContact(post);
  return `<div class="field-block"><div class="field-title">Вакансия из ${post.source === "hirify" ? "Hirify" : `@${escapeHtml(post.channel)}`}</div>
      <div class="field-hint">${escapeHtml(post.title)}</div>
      ${post.unverified ? `<div class="field-hint">ИИ не проверил, вакансия ли это — автоотправки не было</div>` : ""}</div>
    <div class="field-block"><div class="field-title">Контакт</div><div class="field-hint">${contact ? `${contact.kind === "telegram" ? "@" : ""}${escapeHtml(contact.value)}` : "не найден"}</div></div>
    <div class="talk-actions">
      <a class="btn btn-small" href="${escapeHtml(post.link)}" target="_blank" rel="noopener">Открыть пост ↗</a>
      <button type="button" class="btn btn-small btn-ghost" data-post-action="hide">Скрыть вакансию</button>
      ${contact ? `<button type="button" class="btn btn-small btn-ghost is-danger" data-post-action="block" data-ui="talk.block-company">Не писать компании</button>` : ""}
    </div>`;
}

function openTelegramPost(postId, animatePane = false) {
  const post = tgPostsData.posts.find((p) => p.id === postId);
  if (!post) return;
  setTalkMobilePane("thread", animatePane);
  activeTgPostId = postId;
  tgPostHistoryState = { postId, contact: null, messages: [] };
  activeTelegramContact = null;
  updateTelegramComposerState();
  selectedInboxIndex = -1;
  selectedInboxKey = null;
  document.querySelectorAll("#replies-rows .talk-row, #tg-conv-list .conv-item").forEach((r) => r.classList.remove("is-selected", "active"));
  document.querySelectorAll("#tg-posts-list .talk-row, #tg-chat-posts-list .talk-row").forEach((r) => r.classList.toggle("is-selected", r.dataset.tgPost === postId));
  document.getElementById("tg-chat-panel").style.display = "none";
  document.getElementById("tg-chat-empty").style.display = "none";
  document.getElementById("talk-item-panel").hidden = true;
  document.getElementById("tg-chat-delete").hidden = true;
  const panel = document.getElementById("tg-post-panel");
  setTalkMotionVisibility(panel, true, animatePane);
  panel.innerHTML = tgPostPanelHtml(post);
  const postHistory = panel.querySelector("#tg-post-history");
  const postNewMessages = panel.querySelector("#tg-post-new-messages");
  postHistory?.addEventListener("scroll", () => {
    if (shouldStickToBottom(postHistory) && postNewMessages) setTalkMotionVisibility(postNewMessages, false);
  }, { passive: true });
  postNewMessages?.addEventListener("click", () => {
    postHistory?.scrollTo({ top: postHistory.scrollHeight, behavior: REDUCE_MOTION ? "auto" : "smooth" });
    setTalkMotionVisibility(postNewMessages, false);
  });
  lastTgPostHistorySnapshot = "";
  loadTelegramPostHistory(post);
  const ctxBody = document.getElementById("talk-context-body");
  ctxBody.classList.remove("muted", "small");
  ctxBody.innerHTML = tgPostContextHtml(post);
}

async function loadTelegramPostHistory(post) {
  const contact = tgPostContact(post);
  if (contact?.kind !== "telegram") return;
  const history = document.getElementById("tg-post-history");
  if (!history) return;
  try {
    const page = await api(`/api/telegram/history/${encodeURIComponent(contact.value)}`);
    if (activeTgPostId !== post.id || tgPostContact(tgPostsData.posts.find((p) => p.id === post.id) || post)?.value !== contact.value) return;
    const current = document.getElementById("tg-post-history");
    if (!current) return;
    const snapshot = JSON.stringify([post.id, contact.value, page.messages.map((m) => [m.id, m.text, m.at])]);
    if (snapshot === lastTgPostHistorySnapshot) return;
    lastTgPostHistorySnapshot = snapshot;
    const previous = tgPostHistoryState.postId === post.id && tgPostHistoryState.contact === contact.value
      ? tgPostHistoryState.messages
      : [];
    const newMessageKeys = newerTelegramMessageKeys(previous, page.messages);
    const newMessageCount = newMessageKeys.size;
    tgPostHistoryState = { postId: post.id, contact: contact.value, messages: page.messages };
    const wasAtBottom = shouldStickToBottom(current);
    const previousTop = current.scrollTop;
    syncTelegramMessageBubbles(current, page.messages, newMessageKeys);
    current.closest(".post-history")?.classList.toggle("is-empty", page.messages.length === 0);
    if (wasAtBottom) current.scrollTop = current.scrollHeight;
    else current.scrollTop = previousTop;
    const more = document.getElementById("tg-post-new-messages");
    if (more) {
      const visible = !wasAtBottom && newMessageCount > 0;
      setTalkMotionVisibility(more, visible, visible);
      more.textContent = `Показать новые сообщения · ${newMessageCount}`;
    }
    if (!page.messages.length && !current.children.length) current.innerHTML = `<p class="post-history-empty">Переписки пока нет — она появится здесь после первого сообщения.</p>`;
  } catch (error) {
    const current = document.getElementById("tg-post-history");
    if (activeTgPostId === post.id && current && !current.children.length) current.innerHTML = `<p class="post-history-empty">История сейчас недоступна. Проверьте чат Telegram перед отправкой.</p>`;
    if (activeTgPostId === post.id && current) current.closest(".post-history")?.classList.toggle("is-empty", !current.querySelector(".chat-bubble"));
  }
}

async function refreshTelegramPost(postId = activeTgPostId) {
  lastTgPostsSnapshot = "";
  await renderTelegramPosts();
  if (postId && tgPostsData.posts.some((p) => p.id === postId)) openTelegramPost(postId);
  else closeTelegramPost();
}

async function tgPostAction(action, btn) {
  const post = tgPostsData.posts.find((p) => p.id === activeTgPostId);
  if (!post) return;
  if (action === "open-chat") {
    const contact = tgPostContact(post);
    if (contact?.kind === "telegram") openTelegramConversation(contact.value);
    return;
  }
  const textEl = document.getElementById("tg-post-text");
  const text = textEl ? textEl.value.trim() : "";
  const resume = tgPostResumeChoice(post);
  const wasDisabled = btn.disabled;
  const busy = (label) => {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
    btn.classList.add("is-loading");
    btn.textContent = label;
  };
  try {
    if (action === "login-hirify") {
      busy("Открываю Hirify…");
      const result = await api("/api/hirify/login", { method: "POST" });
      showToast(result.message || "Войдите в Hirify в открывшемся окне", "success");
      btn.textContent = "Повторить вход в Hirify";
    } else if (action === "sync-hirify") {
      busy("Читаю контакты…");
      const result = await api(`/api/telegram/posts/${post.id}/hirify-contacts`, { method: "POST" });
      hirifyLoginRequired.delete(post.id);
      await refreshTelegramPost(post.id);
      showToast(`Контакты Hirify сохранены: ${result.contacts?.length || 0}`, "success");
    } else if (action === "draft" || action === "rewrite") {
      busy(action === "draft" ? "Пишу черновик…" : "Переписываю…");
      const contact = tgPostContact(post);
      if (!contact) throw new Error("Сначала выберите адресата");
      await api(`/api/telegram/posts/${post.id}/draft`, { method: "POST", body: JSON.stringify({ contact: contact.value, rewrite: action === "rewrite" }) });
      await refreshTelegramPost(post.id);
      if (action === "rewrite") showToast("ИИ переписал черновик — проверьте текст перед отправкой", "success");
    } else if (action === "add-contact") {
      const kind = document.getElementById("tg-post-contact-kind")?.value;
      const value = document.getElementById("tg-post-contact-value")?.value.trim();
      if (!value) throw new Error("Введите Telegram-адрес или email адресата");
      busy("Добавляю…");
      const result = await api(`/api/telegram/posts/${post.id}/contacts`, { method: "POST", body: JSON.stringify({ kind, value }) });
      const added = result.contacts?.find((c) => c.kind === kind && c.value.toLowerCase() === value.replace(/^@/, "").toLowerCase());
      tgPostContactChoice = { ...tgPostContactChoice, [post.id]: added?.value || value.replace(/^@/, "") };
      await refreshTelegramPost(post.id);
      showToast("Адресат добавлен. Проверьте его перед отправкой", "success");
    } else if (action === "send") {
      if (!text) return;
      busy("Отправляю…");
      const contact = tgPostContact(post);
      if (contact.kind === "email") {
        const draft = tgPostDraft(post);
        const res = await api(`/api/hr-drafts/${draft.code}/send`, { method: "POST", body: JSON.stringify({ text, resume }) });
        showToast(res.message, "success");
      } else {
        // Отправлено — пост становится обычной перепиской в списке ниже.
        const res = await api(`/api/telegram/posts/${post.id}/send`, { method: "POST", body: JSON.stringify({ contact: contact.value, text, resume }) });
        showToast(res.warning || `Отправлено @${res.contact}${resume ? " + резюме" : ""}`, res.warning ? "error" : "success");
        delete tgPostResume[post.id];
        tgPostContactChoice = { ...tgPostContactChoice, [post.id]: undefined };
        await refreshTelegramPost(post.id);
        await render.telegram();
        openTelegramConversation(res.contact);
        return;
      }
      delete tgPostResume[post.id];
      tgPostContactChoice = { ...tgPostContactChoice, [post.id]: undefined };
      await refreshTelegramPost(post.id);
      render.telegram();
    } else if (action === "later") {
      if (!text) return;
      busy("Ставлю на утро…");
      const contact = tgPostContact(post);
      const res = await api(`/api/telegram/posts/${post.id}/later`, { method: "POST", body: JSON.stringify({ contact: contact.value, text, resume }) });
      await refreshTelegramPost(post.id);
      showSavedToast(`Уйдёт ${fmtWhen(res.send_after)} — ночью HR не беспокоим`, async () => {
        await api(`/api/telegram/posts/${post.id}/status`, { method: "POST", body: JSON.stringify({ status: "new" }) });
        await refreshTelegramPost(post.id);
      });
    } else if (action === "unschedule") {
      busy("Отменяю…");
      await api(`/api/telegram/posts/${post.id}/status`, { method: "POST", body: JSON.stringify({ status: "new" }) });
      showToast("Отправка отменена — черновик снова здесь", "success");
      await refreshTelegramPost(post.id);
    } else if (action === "hide" || action === "block") {
      busy(action === "hide" ? "Скрываю…" : "Обновляю компанию…");
      await api(`/api/telegram/posts/${post.id}/status`, { method: "POST", body: JSON.stringify({ status: action === "hide" ? "hidden" : "blocked" }) });
      closeTelegramPost();
      document.getElementById("tg-chat-empty").style.display = "";
      document.getElementById("talk-context-body").innerHTML = "";
      lastTgPostsSnapshot = "";
      await renderTelegramPosts();
      showSavedToast(action === "hide" ? "Вакансия скрыта" : "Больше не пишем этой компании — отмечено в Базе", async () => {
        await api(`/api/telegram/posts/${post.id}/status`, { method: "POST", body: JSON.stringify({ status: "new" }) });
        if (action === "block") {
          const contact = tgPostContact(post);
          if (contact) await api("/api/contacts/do-not-contact", { method: "POST", body: JSON.stringify({ value: contact.value, on: false }) }).catch(() => {});
        }
        await refreshTelegramPost(post.id);
      });
    }
  } catch (err) {
    if (action === "sync-hirify" && /^409:.*Войдите в Hirify/s.test(err.message)) hirifyLoginRequired.add(post.id);
    showToast(err.message.replace(/^\d+: /, ""), "error");
    if (document.body.contains(btn)) await refreshTelegramPost(post.id).catch(() => {});
  } finally {
    if (document.body.contains(btn)) {
      btn.disabled = wasDisabled;
      btn.removeAttribute("aria-busy");
      btn.classList.remove("is-loading");
    }
  }
}

// «Не писать компании» из разговора или вакансии: в Базе — «не писать».
function blockContactButtonHtml(value, postId = "") {
  return `<button type="button" class="btn btn-small btn-ghost is-danger" data-talk-action="block" data-block-contact="${escapeHtml(value)}" data-block-post="${escapeHtml(postId)}" data-ui="talk.block-company">Не писать компании</button>`;
}

async function blockContact(value, postId) {
  const post = (on) => api("/api/contacts/do-not-contact", { method: "POST", body: JSON.stringify({ value, on, post_id: postId || "" }) });
  try {
    await post(true);
    showSavedToast("Больше не пишем этой компании — отмечено в Базе", () => post(false));
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
  }
}

// «Ответ от ИИ» под перепиской Telegram: варианты подставляются в поле.
async function suggestTelegramReplies() {
  if (!activeTelegramContact) return;
  const btn = document.getElementById("tg-chat-suggest");
  const box = document.getElementById("tg-chat-suggestions");
  btn.disabled = true;
  btn.textContent = "Думаю…";
  try {
    const { suggestions } = await api(`/api/telegram/conversations/${activeTelegramContact}/suggest`, { method: "POST" });
    box.innerHTML = suggestions.length
      ? suggestions
          .map((x, i) => `<button type="button" class="chip" data-suggestion="${i}" title="${escapeHtml(x.text)}">${escapeHtml(x.label)}</button>`)
          .join("")
      : `<span class="muted small">ИИ не предложил вариантов — ответьте сами.</span>`;
    box.querySelectorAll("[data-suggestion]").forEach((chip) =>
      chip.addEventListener("click", () => {
        const x = suggestions[Number(chip.dataset.suggestion)];
        const input = document.getElementById("tg-chat-input");
        input.value = x.text;
        updateTelegramComposerState();
        input.focus();
        document.getElementById("tg-chat-attach-resume").classList.toggle("is-suggested", !!x.attach_resume);
        if (x.attach_resume) document.getElementById("tg-chat-status").textContent = "К этому ответу уместно приложить резюме — кнопка «Резюме».";
      })
    );
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Ещё варианты";
  }
}

async function sendTelegramMessageLater() {
  if (!activeTelegramContact) return;
  const input = document.getElementById("tg-chat-input");
  const text = input.value.trim();
  if (!text) {
    input.focus();
    return;
  }
  const contact = activeTelegramContact;
  try {
    const res = await api(`/api/telegram/conversations/${contact}/later`, { method: "POST", body: JSON.stringify({ text }) });
    input.value = "";
    updateTelegramComposerState();
    showSavedToast(`Уйдёт @${contact} ${fmtWhen(res.send_after)}`, async () => {
      await api(`/api/telegram/scheduled/${res.id}`, { method: "DELETE" });
      if (activeTelegramContact === contact) {
        input.value = text;
        updateTelegramComposerState();
      }
    });
  } catch (err) {
    showToast(err.message.replace(/^\d+: /, ""), "error");
  }
}

function telegramMenuItems(kind, hasContact) {
  if (kind === "post") return [
    { action: "open", label: "Открыть вакансию" },
    { action: "info", label: "Информация о вакансии" },
    { action: "remove-post", label: "Удалить вакансию из приложения", danger: true },
    ...(hasContact ? [{ action: "remove-contact", label: "Убрать контакт из приложения", danger: true }] : []),
  ];
  return [
    { action: "open", label: "Открыть переписку" },
    { action: "info", label: "Информация о контакте" },
    { action: "remove-contact", label: "Убрать контакт из приложения", danger: true },
    { action: "delete-dialog", label: "Удалить переписку в Telegram", danger: true },
  ];
}

let talkMenuTarget = null;

function setTalkMobilePane(pane, animate = false) {
  const layout = document.querySelector(".talk-layout");
  if (!layout) return;
  const mobile = window.matchMedia?.("(max-width: 760px)").matches;
  const wasThreadOpen = layout.classList.contains("is-mobile-thread-open");
  const willThreadOpen = pane === "thread";
  const list = layout.querySelector?.(".talk-list");
  const thread = layout.querySelector?.(".talk-thread");
  if (mobile && wasThreadOpen !== willThreadOpen) {
    layout.classList.toggle("is-motion-disabled", !animate || REDUCE_MOTION);
  }
  layout.classList.toggle("is-mobile-thread-open", willThreadOpen);
  for (const [element, hidden] of [[list, mobile && willThreadOpen], [thread, mobile && !willThreadOpen]]) {
    if (!element) continue;
    element.inert = hidden;
    element.setAttribute?.("aria-hidden", String(hidden));
  }
  if (mobile && wasThreadOpen !== willThreadOpen) {
    if (pane === "list") layout.querySelector(".talk-row.is-selected, .conv-item.active")?.focus({ preventScroll: true });
    else thread?.focus({ preventScroll: true });
  }
}

function syncTalkMobilePaneAccessibility() {
  const layout = document.querySelector(".talk-layout");
  if (!layout) return;
  setTalkMobilePane(layout.classList.contains("is-mobile-thread-open") ? "thread" : "list");
}

let talkResponsiveMotionTimer = null;
function animateTalkResponsiveChange() {
  const layout = document.querySelector(".shell.is-messenger .talk-layout");
  if (!layout || REDUCE_MOTION) return;
  clearTimeout(talkResponsiveMotionTimer);
  layout.classList.remove("is-breakpoint-changing");
  void layout.offsetWidth;
  layout.classList.add("is-breakpoint-changing");
  talkResponsiveMotionTimer = setTimeout(() => {
    layout.classList.remove("is-breakpoint-changing");
    talkResponsiveMotionTimer = null;
  }, 190);
}

function shouldStickToBottom(element, threshold = 48) {
  return element.scrollTop + element.clientHeight >= element.scrollHeight - threshold;
}

function updateTelegramNewMessagesIndicator(count, animate = false) {
  const button = document.getElementById("tg-chat-new-messages");
  if (!button) return;
  const total = Math.max(0, Number(count) || 0);
  const visible = total > 0;
  setTalkMotionVisibility(button, visible, animate && visible);
  button.textContent = total ? `Показать новые сообщения · ${total}` : "Показать новые сообщения";
}

function animateConversationChange(element) {
  if (REDUCE_MOTION || !element || typeof element.animate !== "function") return;
  element.animate(
    [{ opacity: 0.72, transform: "translateY(4px)" }, { opacity: 1, transform: "translateY(0)" }],
    { duration: 160, easing: "cubic-bezier(0.23, 1, 0.32, 1)" }
  );
}

function animateTalkEmptyState() {
  const element = document.getElementById("tg-chat-empty");
  if (REDUCE_MOTION || !element || typeof element.animate !== "function") return;
  element.animate(
    [{ opacity: 0, transform: "translateY(5px)" }, { opacity: 1, transform: "translateY(0)" }],
    { duration: 170, easing: "cubic-bezier(0.23, 1, 0.32, 1)" }
  );
}

function setTalkListTab(tab, reload = true) {
  const tabs = document.getElementById("talk-source-tabs");
  if (!tabs) return;
  talkListTab = tab;
  updateTalkListCount();
  tabs.querySelectorAll("[data-talk-list-tab]").forEach((button) => {
    const selected = button.dataset.talkListTab === tab;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
  });
  document.getElementById("talk-chats-block").hidden = tab !== "chats";
  document.getElementById("replies-kind").hidden = tab !== "chats" || (!lastRepliesEntries.length && !telegramConversationsCache.length);
  document.getElementById("tg-posts-block").hidden = tab !== "posts";
  if (reload && tab === "posts") refreshTelegramPostsPanel();
}

const talkMotionVisibilityAnimations = new WeakMap();

function setTalkMotionVisibility(element, open, animate = false, axis = "y") {
  if (!element) return;
  const previousAnimation = talkMotionVisibilityAnimations.get(element);
  previousAnimation?.cancel();
  talkMotionVisibilityAnimations.delete(element);

  if (open) {
    element.hidden = false;
    element.inert = false;
    element.setAttribute("aria-hidden", "false");
  } else {
    element.inert = true;
    element.setAttribute("aria-hidden", "true");
  }

  if (!animate || REDUCE_MOTION || typeof element.animate !== "function") {
    element.hidden = !open;
    return;
  }

  const offset = axis === "x" ? "translateX(7px)" : "translateY(5px) scale(.99)";
  const motionStyles = getComputedStyle(document.documentElement);
  const durationToken = motionStyles.getPropertyValue(open ? "--motion-enter" : "--motion-exit");
  const duration = Number.parseFloat(durationToken) || (open ? 170 : 120);
  const easing = motionStyles.getPropertyValue("--motion-ease-out").trim()
    || "cubic-bezier(0.23, 1, 0.32, 1)";
  const animation = element.animate(
    open
      ? [{ opacity: 0, transform: offset }, { opacity: 1, transform: "translate(0) scale(1)" }]
    : [{ opacity: 1, transform: "translate(0) scale(1)" }, { opacity: 0, transform: offset }],
    {
      duration,
      easing,
      fill: "both",
    }
  );
  talkMotionVisibilityAnimations.set(element, animation);
  animation.onfinish = () => {
    if (talkMotionVisibilityAnimations.get(element) !== animation) return;
    talkMotionVisibilityAnimations.delete(element);
    if (!open) element.hidden = true;
    animation.cancel();
  };
}

function setTalkContextOpen(open, animate = false) {
  const drawer = document.getElementById("talk-context");
  const toggle = document.getElementById("talk-context-toggle");
  setTalkMotionVisibility(drawer, open, animate, "x");
  toggle.setAttribute("aria-expanded", String(open));
  if (open) document.getElementById("talk-context-close").focus();
  else toggle.focus();
}

function setTalkToolsOpen(open, animate = false) {
  const panel = document.getElementById("talk-tools-panel");
  const toggle = document.getElementById("talk-tools-toggle");
  if (!panel || !toggle) return;
  setTalkMotionVisibility(panel, open, animate);
  toggle.setAttribute("aria-expanded", String(open));
  if (open) document.getElementById("talk-tools-close")?.focus();
  else toggle.focus();
}

function closeTalkMenu(animate = false) {
  const menu = document.getElementById("talk-context-menu");
  setTalkMotionVisibility(menu, false, animate);
  talkMenuTarget = null;
}

function showTalkMenu(event) {
  const row = event.target.closest("[data-tg-post], [data-contact], [data-inbox-index]");
  if (!row) return;
  let target = null;
  if (row.dataset.tgPost) {
    const post = tgPostsData.posts.find((p) => p.id === row.dataset.tgPost);
    if (post) {
      const contact = tgPostContact(post);
      target = { kind: "post", id: post.id, contact: contact?.kind === "telegram" ? contact.value : "" };
    }
  } else if (row.dataset.contact) {
    target = { kind: "conversation", contact: row.dataset.contact };
  } else if (row.dataset.inboxIndex != null) {
    const entry = talkEntries[Number(row.dataset.inboxIndex)];
    if (entry?.channel === "telegram_dm" && entry.contact) target = { kind: "conversation", contact: entry.contact };
  }
  if (!target) return;
  event.preventDefault();
  talkMenuTarget = target;
  const menu = document.getElementById("talk-context-menu");
  menu.innerHTML = telegramMenuItems(target.kind, !!target.contact)
    .map((item) => `<button type="button" role="menuitem" data-menu-action="${item.action}"${item.danger ? ' class="is-danger"' : ""}>${item.label}</button>`)
    .join("");
  setTalkMotionVisibility(menu, true, event.type === "contextmenu" || event.detail > 0);
  const rect = menu.getBoundingClientRect();
  const anchor = event.type === "contextmenu"
    ? { left: event.clientX, top: event.clientY }
    : row.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(anchor.left, window.innerWidth - rect.width - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(anchor.top, window.innerHeight - rect.height - 8))}px`;
  menu.querySelector("button")?.focus();
}

async function handleTalkMenuAction(action, animate = false) {
  const target = talkMenuTarget;
  closeTalkMenu(animate);
  if (!target) return;
  if (action === "open" || action === "info") {
    if (target.kind === "post") openTelegramPost(target.id);
    else await openTelegramConversation(target.contact);
    if (action === "info") setTalkContextOpen(true);
    return;
  }
  if (action === "delete-dialog") {
    await openTelegramConversation(target.contact);
    document.getElementById("tg-chat-delete").click();
    return;
  }
  const removingPost = action === "remove-post" && target.kind === "post";
  const removingContact = action === "remove-contact" && !!target.contact;
  if (!removingPost && !removingContact) return;
  const description = removingPost ? "вакансию" : `контакт @${target.contact}`;
  const confirmed = await showConfirm(`Удалить ${description} из приложения? В Telegram ничего не удалится. Повторный поиск не вернёт эту запись.`);
  if (!confirmed) return;
  try {
    const path = removingPost
      ? `/api/telegram/posts/${encodeURIComponent(target.id)}`
      : `/api/telegram/contacts/${encodeURIComponent(target.contact)}/local`;
    await api(path, { method: "DELETE" });
    const activeRemoved = removingPost
      ? activeTgPostId === target.id
      : activeTelegramContact === target.contact || (activeTgPostId && tgPostsData.posts.some((p) => p.id === activeTgPostId && tgPostContact(p)?.value === target.contact));
    if (activeRemoved) {
      activeTelegramContact = null;
      updateTelegramComposerState();
      closeTelegramPost();
      document.getElementById("tg-chat-panel").style.display = "none";
      document.getElementById("tg-chat-empty").style.display = "";
      document.getElementById("talk-context-body").innerHTML = "";
      setTalkContextOpen(false);
    }
    lastTgPostsSnapshot = "";
    await render.replies();
    showToast(`${removingPost ? "Вакансия" : "Контакт"} удалён из приложения`, "success");
  } catch (error) {
    showToast(error.message.replace(/^\d+: /, ""), "error");
  }
}

function initTalkExtras() {
  syncTalkMobilePaneAccessibility();
  if (typeof window !== "undefined") {
    window.matchMedia?.("(max-width: 760px)")?.addEventListener?.("change", () => {
      syncTalkMobilePaneAccessibility();
      animateTalkResponsiveChange();
    });
  }
  const tabs = document.getElementById("talk-source-tabs");
  if (tabs) {
    tabs.addEventListener("click", (event) => {
      const button = event.target.closest("[data-talk-list-tab]");
      if (button) setTalkListTab(button.dataset.talkListTab);
    });
    setTalkListTab("chats", false);
  }
  document.getElementById("talk-tools-toggle")?.addEventListener("click", (event) => {
    const toggle = document.getElementById("talk-tools-toggle");
    setTalkToolsOpen(toggle.getAttribute("aria-expanded") !== "true", event.detail > 0);
  });
  document.getElementById("talk-tools-close")?.addEventListener("click", (event) => setTalkToolsOpen(false, event.detail > 0));
  document.getElementById("talk-context-toggle")?.addEventListener("click", (event) => {
    const toggle = document.getElementById("talk-context-toggle");
    setTalkContextOpen(toggle.getAttribute("aria-expanded") !== "true", event.detail > 0);
  });
  document.getElementById("talk-context-close")?.addEventListener("click", (event) => setTalkContextOpen(false, event.detail > 0));
  document.getElementById("talk-thread-back")?.addEventListener("click", (event) => setTalkMobilePane("list", event.detail > 0));
  const chatMessages = document.getElementById("tg-chat-messages");
  chatMessages?.addEventListener("scroll", () => {
    if (shouldStickToBottom(chatMessages)) updateTelegramNewMessagesIndicator(0);
  }, { passive: true });
  document.getElementById("tg-chat-new-messages")?.addEventListener("click", () => {
    chatMessages?.scrollTo({ top: chatMessages.scrollHeight, behavior: REDUCE_MOTION ? "auto" : "smooth" });
    updateTelegramNewMessagesIndicator(0);
  });
  const talkList = document.querySelector?.(".talk-list");
  talkList?.addEventListener("contextmenu", showTalkMenu);
  talkList?.addEventListener("keydown", (event) => {
    if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) showTalkMenu(event);
  });
  document.getElementById("talk-context-menu")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-menu-action]");
    if (button) handleTalkMenuAction(button.dataset.menuAction, event.detail > 0);
  });
  document.addEventListener?.("click", (event) => {
    if (!event.target.closest?.("#talk-context-menu")) closeTalkMenu(event.detail > 0);
  });
  document.addEventListener?.("keydown", (event) => {
    if (event.key === "Escape") {
      closeTalkMenu();
      let closedOverlay = false;
      if (!document.getElementById("talk-tools-panel").hidden) {
        setTalkToolsOpen(false);
        closedOverlay = true;
      }
      if (!document.getElementById("talk-context").hidden) {
        setTalkContextOpen(false);
        closedOverlay = true;
      }
      if (!closedOverlay && window.matchMedia?.("(max-width: 760px)").matches && document.querySelector(".talk-layout.is-mobile-thread-open")) setTalkMobilePane("list");
    }
  });
  document.getElementById("tg-chat-older")?.addEventListener("click", async () => {
    const contact = activeTelegramContact;
    const oldest = telegramLoadedHistory.messages[0]?.id;
    if (!contact || !oldest) return;
    const button = document.getElementById("tg-chat-older");
    button.disabled = true;
    try {
      const page = await api(`/api/telegram/history/${encodeURIComponent(contact)}?before_id=${oldest}`);
      if (activeTelegramContact !== contact || page.source !== "telegram") return;
      const seen = new Set(telegramLoadedHistory.messages.map((m) => m.id));
      telegramLoadedHistory = {
        contact,
        messages: [...page.messages.filter((m) => !seen.has(m.id)), ...telegramLoadedHistory.messages],
        hasMore: page.has_more,
      };
      const messages = document.getElementById("tg-chat-messages");
      const previousHeight = messages.scrollHeight;
      const previousTop = messages.scrollTop;
      syncTelegramMessageBubbles(messages, telegramLoadedHistory.messages);
      messages.scrollTop = previousTop + messages.scrollHeight - previousHeight;
      button.hidden = !page.has_more;
    } catch (error) {
      showToast(`Не удалось загрузить старые сообщения: ${error.message}`, "error");
    } finally {
      button.disabled = false;
    }
  });
  document.getElementById("tg-posts-more")?.addEventListener("click", () => {
    tgPostsVisibleLimit += 200;
    lastTgPostsSnapshot = "";
    refreshTelegramPostsPanel();
  });
  for (const id of ["tg-posts-list", "tg-chat-posts-list"]) {
    document.getElementById(id)?.addEventListener("click", (e) => {
      const row = e.target.closest("[data-tg-post]");
      if (row) openTelegramPost(row.dataset.tgPost, e.detail > 0);
    });
  }
  const panel = document.getElementById("tg-post-panel");
  panel?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-post-action]");
    if (btn) {
      if (btn.dataset.postAction === "resume-menu") {
        const menu = document.getElementById("tg-post-resume-menu");
        if (menu) {
          const open = btn.getAttribute("aria-expanded") !== "true";
          setTalkMotionVisibility(menu, open, e.detail > 0);
          btn.setAttribute("aria-expanded", String(open));
        }
        return;
      }
      tgPostAction(btn.dataset.postAction, btn);
      return;
    }
    const chip = e.target.closest("[data-post-resume]");
    if (chip && activeTgPostId) {
      tgPostResume[activeTgPostId] = chip.dataset.postResume;
      const keep = document.getElementById("tg-post-text")?.value;
      openTelegramPost(activeTgPostId);
      if (keep != null) document.getElementById("tg-post-text").value = keep;
      if (e.detail > 0) animateConversationChange(panel.querySelector(".post-attachment"));
      return;
    }
    const who = e.target.closest("[data-post-contact]");
    if (who && activeTgPostId) {
      const post = tgPostsData.posts.find((p) => p.id === activeTgPostId);
      if (post && tgPostContact(post)?.value !== who.dataset.postContact) {
        tgPostContactChoice = { ...tgPostContactChoice, [post.id]: who.dataset.postContact };
        openTelegramPost(activeTgPostId);
        animatePostRecipientSelection(panel, e.detail > 0);
      }
    }
  });
  // Правка черновика сохраняется, когда уходите из поля.
  panel?.addEventListener("change", async (e) => {
    if (e.target.id !== "tg-post-text") return;
    const post = tgPostsData.posts.find((p) => p.id === activeTgPostId);
    const draft = post ? tgPostDraft(post) : null;
    if (!draft || !e.target.value.trim()) return;
    const text = e.target.value;
    try {
      await api(`/api/hr-drafts/${draft.code}`, { method: "PUT", body: JSON.stringify({ text }) });
      tgPostsData = { ...tgPostsData, posts: tgPostsData.posts.map((p) =>
        p.id === post.id && p.draft?.code === draft.code ? { ...p, draft: { ...p.draft, text } } : p
      ) };
    } catch (err) {
      showToast(err.message.replace(/^\d+: /, ""), "error");
    }
  });
  panel?.addEventListener("keydown", (e) => {
    if (e.target.id === "tg-post-text" && e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      panel.querySelector('[data-post-action="send"]')?.click();
    }
  });
  document.getElementById("talk-context-body")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-block-contact]");
    if (btn) {
      blockContact(btn.dataset.blockContact, btn.dataset.blockPost);
      return;
    }
    const postBtn = e.target.closest('[data-post-action="hide"], [data-post-action="block"]');
    if (postBtn) tgPostAction(postBtn.dataset.postAction, postBtn);
  });
}
