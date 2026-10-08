"""Постоянный шлюз Telegram: держит подключение и получает новые посты
каналов в момент публикации. Фильтр — ключевые слова, без LLM: скорость
важнее "умной" оценки, мы не откликаемся, а первыми узнаём о вакансии.
Подходящий пост пересылается вам (по умолчанию в «Избранное») целиком —
с форматированием и ссылкой на оригинал, следом строка с совпавшими
словами и найденными контактами. Заодно ловит ответы HR в личке.

Пока шлюз работает, он единственный владелец сессии Telegram: остальной
код (отправка черновиков из дашборда и т.п.) выполняет свои вызовы через
его подключение — см. active_watcher() и TelegramSourceClient."""

from __future__ import annotations

import asyncio
import hashlib
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional, Sequence

from src.job_sources.contact_book import ContactBook, contacts_from_text
from src.job_sources.hr_replies import _looks_russian, generate_first_message
from src.job_sources.resume_routing import resolve_resume
from src.job_sources.telegram.client import _SESSION_LOCK, normalize_channel
from src.job_sources.telegram_conversations import TelegramConversations
from src.job_sources.telegram_notify import (
    bot_credentials,
    bot_request,
    get_or_create_topic,
    notify_from_secrets,
)
from src.logging import logger
from src.utils.file_lock import state_file_lock
from src.utils.pause_all import is_paused

_ACTIVE: Optional["TelegramWatcher"] = None
RECONNECT_DELAY_SECONDS = 30
_SEEN_LIMIT = 3000
_BACKFILLED_CHANNELS_LOCK = threading.Lock()
# Слова, по которым сама по себе должность ничего не говорит.
_GENERIC_WORDS = {
    "developer",
    "разработчик",
    "engineer",
    "инженер",
    "программист",
    "senior",
    "middle",
    "junior",
    "lead",
    "specialist",
    "специалист",
}


def gateway_state() -> dict:
    """Состояние постоянного шлюза для дашборда: жив ли поток, есть ли
    соединение, когда пришёл последний пост канала (unix-время)."""
    w = _ACTIVE
    return {
        "alive": w is not None,
        "connected": bool(w is not None and w.connected),
        "last_post_at": getattr(w, "last_post_at", None) if w else None,
    }


def active_watcher() -> Optional["TelegramWatcher"]:
    return _ACTIVE if _ACTIVE is not None and _ACTIVE.connected else None


def default_keywords(positions: list[str]) -> list[str]:
    """Если слова не заданы — значимые слова из ваших должностей
    ("Python разработчик" → "python")."""
    words: list[str] = []
    for position in positions:
        for word in re.findall(r"[\w+#.]+", position.casefold()):
            if (
                word not in _GENERIC_WORDS
                and len(word) > 2
                and word not in words
            ):
                words.append(word)
    return words


# Маркеры "это пост кандидата, а не вакансии" — подтверждённый вживую
# инцидент: пост "Ищу работу Python-разработчиком, мой контакт:
# ..." совпал по ключевому слову "python" (оно и должно совпадать —
# кандидат честно написал свою специализацию), контакт из поста ушёл
# в Базу компаний как "работодатель", и рассылка на автомате отправила
# туда письмо — кандидату вместо HR. Проблема не в самом слове
# "python" (сузить keywords до целой фразы отсеет реальные вакансии с
# другой формулировкой), а в том, что пост вообще не вакансия — эти
# фразы такие посты выдают почти всегда, независимо от специализации.
# Хэштеги — разметка резюме в каналах (@python_jobs, @jobs_it): на 48
# реальных постах отсекли 16 резюме и ни одной вакансии. Голые «резюме»
# и «cv» — нет: вакансии пишут «присылайте резюме/CV» (5 из 48 отсеклись
# бы); «#cv» тоже нет — в ML-каналах это computer vision.
CANDIDATE_SELF_POST_MARKERS = (
    "ищу работу",
    "ищу вакансию",
    "в поиске работы",
    "рассматриваю предложения",
    "рассматриваю офферы",
    "рассмотрю предложения",
    "открыт к предложениям",
    "открыта к предложениям",
    "open to work",
    "opentowork",
    "looking for a job",
    "looking for new opportunities",
    "looking for opportunities",
    "резюме:",
    "моё резюме",
    "мое резюме",
    "мой резюме",
    "обо мне",
    "#резюме",
    "#resume",
    "#ищу",
    "хочу найти работу",
    "ищу проект",
)


def match_keywords(
    text: str, keywords: list[str], stop_words: list[str]
) -> list[str]:
    """Совпавшие ключевые слова (по вхождению, без учёта регистра) или
    пустой список, если совпадений нет или есть стоп-слово (свои из
    watch_stop_words + встроенные CANDIDATE_SELF_POST_MARKERS —
    последние нельзя выключить, см. их докстринг)."""
    lowered = text.casefold()
    all_stop_words = (*stop_words, *CANDIDATE_SELF_POST_MARKERS)
    if any(
        stop.casefold() in lowered for stop in all_stop_words if stop.strip()
    ):
        return []
    return [k for k in keywords if k.strip() and k.casefold() in lowered]


def _fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.casefold())[:400]
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


_VACANCY_CLASSIFIER_PROMPT = (
    "Пост из Telegram-канала о работе. Это объявление вакансии (компания "
    "ищет сотрудника), а не резюме/поиск работы кандидатом, реклама, "
    "курсы или вопрос? Ответь одним словом: ДА или НЕТ.\n\nПост:\n{text}"
)
# Строка с адресом про рекламу/размещение в самом канале — не адрес для
# отклика («Размещение вакансий: ads@канал» в подписи поста).
_NOT_APPLY_LINE_MARKERS = ("размещ", "реклам", "сотруднич", "advertis")


def _apply_email(text: str, emails: Sequence[str]) -> str:
    """Email для отклика — правилом, не ИИ: первый адрес из поста, строка
    которого не про рекламу канала. Раньше адрес выбирал gpt-4o-mini и на
    живых постах случайно отбрасывал настоящие «Контакты: hr@компания»
    (МТС, Альфа-Банк — от прогона к прогону по-разному); правило на тех
    же 17 вакансиях стабильно даёт верный адрес. Резюме с email кандидата
    сюда не доходят — их отсекают стоп-слова и ответ ИИ «не вакансия»."""
    for email in emails:
        line = next(
            (ln for ln in text.splitlines() if email.lower() in ln.lower()),
            "",
        )
        rest = line.lower().replace(email.lower(), "")
        if not any(m in rest for m in _NOT_APPLY_LINE_MARKERS):
            return email
    return ""


# Секунды ожидания перед каждым повтором при rate limit — не растёт
# бесконечно (лимиты обычно сбрасываются за минуты, не часы), суммарно
# держит один пост в очереди не больше ~100с, пока идёт reset окна
# лимита у провайдера. Другие посты (свои executor-потоки) это не
# блокирует — см. run_in_executor в _handle_post.
RATE_LIMIT_RETRY_DELAYS_SECONDS = (10, 30, 60)
RATE_LIMIT_MARKERS = ("429", "rate limit", "rate_limit", "too many requests")


def _llm_check_post(
    text: str, llm_api_key: str, emails: Sequence[str] = ()
) -> Optional[tuple[bool, str]]:
    """Короткий LLM-классификатор поверх стоп-слов (telegram.
    llm_vacancy_filter, выключен по умолчанию) — вызывается только для
    постов, уже прошедших match_keywords, не на весь поток каналов.

    Возвращает (вакансия?, email для отклика или ""). ИИ отвечает только
    «вакансия или нет»; адрес — из найденных в посте (emails) правилом
    _apply_email, ИИ его не выбирает и не выдумывает.

    None — ИИ недоступен (нет ключа, ошибка, исчерпан rate limit): решает
    _handle_post — пост в бот с пометкой, но без автоотправки и Базы.
    Rate limit — не сразу None: 50+ каналов легко дают всплеск запросов
    разом, а лимит провайдера обычно сбрасывается за минуты — ждём и
    пробуем снова (см. RATE_LIMIT_RETRY_DELAYS_SECONDS)."""
    if not llm_api_key:
        logger.warning(
            "Telegram-парсер: ИИ-проверка включена, но ключ не настроен"
        )
        return None
    from src.job_sources.llm_provider import get_chat_llm

    prompt = _VACANCY_CLASSIFIER_PROMPT.format(text=text[:600])
    attempts = len(RATE_LIMIT_RETRY_DELAYS_SECONDS) + 1
    for attempt in range(attempts):
        try:
            llm = get_chat_llm(llm_api_key, temperature=0)
            answer = llm.invoke(prompt)
            content = str(getattr(answer, "content", answer)).lower()
            if content.replace("*", "").strip().startswith("нет"):
                return False, ""
            return True, _apply_email(text, emails)
        except Exception as e:
            is_rate_limit = any(
                m in str(e).lower() for m in RATE_LIMIT_MARKERS
            )
            if not is_rate_limit or attempt == attempts - 1:
                logger.warning(
                    f"Telegram-парсер: LLM-классификатор недоступен "
                    f"(попытка {attempt + 1}/{attempts}): {e}"
                )
                return None
            delay = RATE_LIMIT_RETRY_DELAYS_SECONDS[attempt]
            logger.info(
                f"Telegram-парсер: LLM rate limit, повтор через {delay}с "
                f"(попытка {attempt + 1}/{attempts})"
            )
            time.sleep(delay)
    return None


_UNVERIFIED_MARK = " · ⚠️ не проверено ИИ"


class TelegramWatcher(threading.Thread):
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        session_path: Path,
        channels: list[str],
        keywords: list[str],
        stop_words: list[str],
        forward_to: str,
        parameters: dict,
        llm_api_key: str = "",
    ):
        super().__init__(name="telegram-watcher", daemon=True)
        self.llm_api_key = llm_api_key
        self.bot = bot_credentials(parameters)
        self.api_id, self.api_hash = api_id, api_hash
        self.session_path = session_path
        self.channels = [normalize_channel(c) for c in channels if c.strip()]
        self.keywords, self.stop_words = keywords, stop_words
        self.forward_to = forward_to or "me"
        self.parameters = parameters
        self.output_folder: Path = parameters["outputFileDirectory"]
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.client: Any = None
        self.connected = False
        self.last_post_at: Optional[float] = None
        self.matched_count = 0
        self._settings_task: Optional[asyncio.Task] = None
        self._stopping = threading.Event()
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._backfills_in_progress: set[str] = set()

    # --- запуск/остановка -------------------------------------------

    def run(self) -> None:
        global _ACTIVE
        from telethon import TelegramClient

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.client = TelegramClient(
            str(self.session_path), self.api_id, self.api_hash, loop=self.loop
        )
        _ACTIVE = self
        if self.bot is not None:
            threading.Thread(
                target=self._poll_bot_forever,
                name="telegram-bot-inbox",
                daemon=True,
            ).start()
        try:
            while not self._stopping.is_set():
                try:
                    self.loop.run_until_complete(self._serve())
                except Exception as e:
                    logger.warning(
                        f"Telegram-шлюз: обрыв ({e}), переподключаюсь…"
                    )
                self.connected = False
                if self._stopping.wait(RECONNECT_DELAY_SECONDS):
                    break
        finally:
            self.connected = False
            if _ACTIVE is self:
                _ACTIVE = None
            logger.info("Telegram-шлюз остановлен.")

    def stop(self) -> None:
        self._stopping.set()
        if self.loop is not None and self.client is not None:
            self.loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self.client.disconnect())
            )

    def update_llm_vacancy_filter(self, enabled: bool) -> None:
        """Применить LLM-фильтр к новым постам без перезапуска шлюза."""
        telegram = self.parameters.get("telegram") or {}
        self.parameters = {
            **self.parameters,
            "telegram": {
                **telegram,
                "llm_vacancy_filter": enabled,
            },
        }

    def _poll_bot_forever(self) -> None:
        """Постоянное чтение бота уведомлений (long polling): нажатия
        кнопок под вакансиями и команды обрабатываются за секунды, а не
        раз в 3 минуты. Разбор общий с демоном — main.handle_bot_updates."""
        from src.job_sources.telegram_control import poll_bot_updates

        assert self.bot is not None  # поток запускается только с ботом
        token = self.bot[0]
        while not self._stopping.is_set():
            try:
                updates = poll_bot_updates(
                    token, self.output_folder, timeout=25
                )
                if updates:
                    from main import handle_bot_updates

                    handle_bot_updates(
                        self.parameters, self.llm_api_key, updates
                    )
                self._flush_pending_sends()
                self._deliver_night_posts()
            except Exception as e:
                logger.warning(
                    f"Telegram-бот: не удалось прочитать обновления: {e}"
                )
                self._stopping.wait(5)

    def _flush_pending_sends(self) -> None:
        if is_paused(self.output_folder):
            return  # «Пауза на всё» — очередь ждёт, ничего не уходит
        tg_prefs = self.parameters.get("telegram") or {}
        start, end = tg_prefs.get("active_hours_start"), tg_prefs.get(
            "active_hours_end"
        )
        active_hours = (
            (start, end) if start is not None and end is not None else None
        )
        flush_pending_telegram_sends(
            lambda contact, text: self.call(
                lambda c: c.send_message(contact, text)
            ),
            self.output_folder,
            active_hours,
            send_file_fn=lambda contact, path: self.call(
                lambda c: c.send_file(contact, path)
            ),
            on_sent=lambda entry: remember_telegram_post_contact(
                self.output_folder,
                [{"kind": "telegram", "value": entry["contact"]}],
                entry.get("post") or {"link": entry.get("job_link", "")},
            ),
        )

    def call(
        self,
        factory: Callable[[Any], Coroutine[Any, Any, Any]],
        timeout: float = 60,
    ) -> Any:
        """Выполнить действие через подключение шлюза из другого потока.
        factory вызывается уже внутри loop шлюза: telethon.sync (его
        импортирует telegram/client.py) делает методы клиента синхронными
        вне запущенного loop — вызванный здесь же, в потоке вызывающего,
        c.get_entity() сразу шёл в чужой loop и падал «The asyncio event
        loop must not change after connection» (8.10, Talanto)."""
        assert self.loop is not None, "шлюз ещё не запущен"

        async def run() -> Any:
            return await factory(self.client)

        future = asyncio.run_coroutine_threadsafe(run(), self.loop)
        return future.result(timeout)

    # --- работа ---------------------------------------------------------

    async def _serve(self) -> None:
        from telethon import events

        # active_watcher() отдаёт вызовы через шлюз, только когда
        # self.connected уже True — а до этого момента (connect() +
        # подписка на десятки каналов, реально видено вживую до минуты)
        # сам шлюз пишет в тот же файл сессии SQLite, ничем не
        # защищённый. TelegramSourceClient.__enter__() в этом окне не
        # знает про шлюз и открывает вторую конкурентную сессию —
        # "database is locked". Держим тот же _SESSION_LOCK, что уже
        # сериализует остальные обращения к Telegram, на всё время
        # подключения — конкурирующий вызов подождёт вместо падения.
        _SESSION_LOCK.acquire()
        try:
            await self.client.connect()
            # _serve повторяется при переподключении — без снятия старых
            # обработчиков каждый пост приходил бы по несколько раз.
            self.client.remove_event_handler(self._on_channel_post)
            self.client.remove_event_handler(self._on_private_message)
            if not await self.client.is_user_authorized():
                logger.error(
                    "Telegram-шлюз: сессия не авторизована — войдите во "
                    "вкладке «Общение → Telegram»."
                )
                self._stopping.set()
                return
            await self._subscribe()
            self.client.add_event_handler(
                self._on_private_message,
                events.NewMessage(incoming=True, func=lambda e: e.is_private),
            )
            self.connected = True
        finally:
            _SESSION_LOCK.release()
        if self._settings_task is not None:
            self._settings_task.cancel()
        self._settings_task = asyncio.ensure_future(self._watch_settings())
        await self.client.run_until_disconnected()

    async def _subscribe(self) -> None:
        """Слушаем self.channels. Новые посты Telegram присылает только из
        каналов, где аккаунт состоит, — поэтому в новые каналы вступаем.
        Канал, который видим впервые, — досматриваем его историю за
        последние N дней (см. _backfill_channel): вакансия могла быть
        опубликована до того, как канал добавили, и всё ещё быть открыта."""
        from telethon import events
        from telethon.tl.functions.channels import JoinChannelRequest

        backfilled = _load_backfilled_channels(self.output_folder)
        chats = []
        for channel in self.channels:
            try:
                entity = await self.client.get_entity(channel)
                if getattr(entity, "left", False):
                    await self.client(JoinChannelRequest(entity))
                    logger.info(
                        f"Telegram-шлюз: вступил в @{channel}, чтобы "
                        "получать посты"
                    )
                chats.append(entity)
                if (
                    channel not in backfilled
                    and channel not in self._backfills_in_progress
                ):
                    self._backfills_in_progress.add(channel)
                    asyncio.ensure_future(
                        self._backfill_channel(entity, channel)
                    )
            except Exception as e:
                logger.warning(
                    f"Telegram-шлюз: канал @{channel} недоступен: {e}"
                )
        self.client.remove_event_handler(self._on_channel_post)
        self.client.add_event_handler(
            self._on_channel_post, events.NewMessage(chats=chats)
        )
        logger.info(
            f"Telegram-шлюз: слушаю {len(chats)} каналов, слова: "
            f"{', '.join(self.keywords) or '—'}"
        )

    async def _backfill_channel(self, entity, channel: str) -> None:
        days = (self.parameters.get("telegram") or {}).get(
            "channel_backfill_days", 14
        )
        try:
            if not days:
                return
            from datetime import datetime, timedelta, timezone

            since = datetime.now(timezone.utc) - timedelta(days=days)
            found = 0
            async for message in self.client.iter_messages(entity, limit=300):
                if message.date is not None and message.date < since:
                    break
                await self._handle_post(channel, message)
                found += 1
        except Exception as e:
            logger.warning(
                f"Telegram-шлюз: не удалось досмотреть историю @{channel} "
                f"за {days} дн.: {e}"
            )
            return
        finally:
            self._backfills_in_progress.discard(channel)
        _mark_channel_backfilled(self.output_folder, channel)
        logger.info(
            f"Telegram-шлюз: досмотрел @{channel} за {days} дн. "
            f"({found} постов проверено)"
        )

    async def _watch_settings(self) -> None:
        """Каналы, ключевые и стоп-слова меняются в дашборде на ходу —
        раз в минуту перечитываем work_preferences.yaml, без перезапуска."""
        import yaml

        while self.client.is_connected():
            await asyncio.sleep(60)
            try:
                prefs = (
                    yaml.safe_load(
                        (
                            Path(self.parameters["dataFolder"])
                            / "work_preferences.yaml"
                        ).read_text(encoding="utf-8")
                    )
                    or {}
                )
            except (OSError, KeyError, yaml.YAMLError):
                continue
            telegram = prefs.get("telegram") or {}
            if "llm_vacancy_filter" in telegram:
                self.update_llm_vacancy_filter(
                    bool(telegram["llm_vacancy_filter"])
                )
            self.parameters = {
                **self.parameters,
                "resume_routing": dict(prefs.get("resume_routing") or {}),
            }
            self.keywords = telegram.get("watch_keywords") or self.keywords
            self.stop_words = telegram.get("watch_stop_words") or []
            channels = [
                normalize_channel(c)
                for c in telegram.get("channels") or []
                if str(c).strip()
            ]
            if channels and channels != self.channels:
                self.channels = channels
                await self._subscribe()

    async def _on_channel_post(self, event) -> None:
        self.last_post_at = time.time()
        chat = await event.get_chat()
        channel = getattr(chat, "username", None) or str(event.chat_id)
        await self._handle_post(channel, event.message)

    async def _handle_post(self, channel: str, message) -> None:
        """Общая логика для живого поста (_on_channel_post) и досмотра
        истории нового канала (_backfill_channel) — фильтр, дедуп,
        автоотправка/доставка на модерацию одинаковы в обоих случаях."""
        text = (message.message or "").strip()
        if not text:
            return
        matched = match_keywords(text, self.keywords, self.stop_words)
        if not matched:
            return
        fingerprint = _fingerprint(text)
        if fingerprint in self._seen:
            return  # тот же пост, репостнутый в другой канал
        self._seen[fingerprint] = None
        if len(self._seen) > _SEEN_LIMIT:
            self._seen.popitem(last=False)

        link = f"https://t.me/{channel}/{message.id}"
        contacts = contacts_from_text(text, exclude=(channel,))
        title = text.splitlines()[0][:120]
        post = {
            "channel": channel,
            "link": link,
            "title": title,
            "text": text[:4000],
        }
        tg_prefs = self.parameters.get("telegram") or {}
        # ИИ-проверка (тумблер): «не вакансия» — пост отброшен. ИИ
        # недоступен — пост всё равно в бот с пометкой, но без автоотправки
        # и без Базы: бот вы читаете сами, потерянная вакансия дороже
        # лишнего поста, а автоматическое действие — только по проверенному.
        unverified = False
        if tg_prefs.get("llm_vacancy_filter"):
            verdict = await asyncio.get_event_loop().run_in_executor(
                None,
                _llm_check_post,
                text,
                self.llm_api_key,
                [c["value"] for c in contacts if c["kind"] == "email"],
            )
            if verdict is None:
                unverified = True
            else:
                is_vacancy, apply_email = verdict
                if not is_vacancy:
                    return
                if apply_email:
                    # Email для отклика из проверенной вакансии — сразу в
                    # Базу, как адреса с сайтов компаний. Остальные
                    # контакты поста — только после отправки из бота.
                    remember_telegram_post_contact(
                        self.output_folder,
                        [{"kind": "email", "value": apply_email}],
                        post,
                        sent=False,
                    )
        self.matched_count += 1

        telegram_contacts = [c for c in contacts if c["kind"] == "telegram"]
        if (
            tg_prefs.get("auto_message")
            and not unverified
            and len(telegram_contacts) == 1
            # На паузе вакансия приходит в бот с кнопками, как без
            # автоотправки, — не копится очередью, которая уйдёт разом.
            and not is_paused(self.output_folder)
        ):
            from src.job_sources.apply_pacing import (
                MAX_TELEGRAM_MESSAGE_DELAY_SECONDS,
                MIN_TELEGRAM_MESSAGE_DELAY_SECONDS,
            )

            contact_value = telegram_contacts[0]["value"]
            conversations = TelegramConversations(
                self.output_folder / "telegram_conversations.json"
            )
            daily_limit = tg_prefs.get("daily_message_limit", 15)
            if (
                not conversations.already_contacted(contact_value)
                and conversations.sent_today_count() < daily_limit
            ):
                (
                    intro_text,
                    resume_path,
                ) = await asyncio.get_event_loop().run_in_executor(
                    None, self._auto_message_text, title, text, link
                )
                if tg_prefs.get("preview_before_send"):
                    # «Показывать текст перед отправкой»: тот же текст —
                    # черновиком в «Общение» и в бот с «Отправить».
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        self._draft_for_preview,
                        {**post, "contacts": contacts, "unverified": False},
                        contact_value,
                        intro_text,
                        resume_path,
                    )
                    return
                queue_telegram_send(
                    self.output_folder,
                    contact_value,
                    intro_text,
                    link,
                    tg_prefs.get(
                        "message_delay_min_seconds",
                        MIN_TELEGRAM_MESSAGE_DELAY_SECONDS,
                    ),
                    tg_prefs.get(
                        "message_delay_max_seconds",
                        MAX_TELEGRAM_MESSAGE_DELAY_SECONDS,
                    ),
                    resume_path,
                    post=post,
                )
                logger.info(
                    f"Telegram auto_message: в очередь для @{contact_value}"
                )
                return

        if self.bot is not None and night_hold(tg_prefs):
            # «Ночные вакансии — утром»: пост сохранён (виден в «Общении»),
            # в бот придёт в начале рабочих часов — ночью не будим.
            post_id = save_watch_post(
                self.output_folder,
                {
                    **post,
                    "contacts": [
                        {"kind": c["kind"], "value": c["value"]}
                        for c in contacts
                    ],
                    "unverified": unverified,
                },
            )
            queue_night_post(self.output_folder, post_id, matched)
            return
        if self.bot is not None:
            # Через бота — чтобы под вакансией были кнопки быстрого ответа.
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._deliver_via_bot,
                {
                    **post,
                    "contacts": [
                        {"kind": c["kind"], "value": c["value"]}
                        for c in contacts
                    ],
                    "unverified": unverified,
                },
                matched,
            )
            return
        # Без бота пост тоже сохраняется — его видно в «Общении» с
        # черновиком от ИИ, а не только пересланным в «Избранное».
        save_watch_post(
            self.output_folder,
            {
                **post,
                "contacts": [
                    {"kind": c["kind"], "value": c["value"]} for c in contacts
                ],
                "unverified": unverified,
            },
        )
        try:
            forwarded = await self.client.forward_messages(
                self.forward_to, message
            )
            header = [
                f"🎯 {', '.join(matched)} · @{channel}"
                + (_UNVERIFIED_MARK if unverified else "")
            ]
            if contacts:
                header.append(
                    "Контакты: "
                    + ", ".join(
                        (
                            f"@{c['value']}"
                            if c["kind"] == "telegram"
                            else c["value"]
                        )
                        for c in contacts
                    )
                )
            await self.client.send_message(
                self.forward_to,
                "\n".join(header),
                reply_to=forwarded.id,
                link_preview=False,
            )
        except Exception as e:
            logger.warning(f"Telegram-шлюз: не удалось переслать {link}: {e}")

    def _deliver_via_bot(self, post: dict, matched: list[str]) -> None:
        assert self.bot is not None  # зовётся только при подключённом боте
        token, chat_id = self.bot
        post_id = save_watch_post(self.output_folder, post)
        contacts_line = (
            ", ".join(
                f"@{c['value']}" if c["kind"] == "telegram" else c["value"]
                for c in post["contacts"]
            )
            or "не найдены — откройте пост"
        )
        body = (
            post["text"]
            if len(post["text"]) <= 3000
            else post["text"][:3000] + "…"
        )
        russian = _looks_russian(post.get("text") or post.get("title", ""))
        routed_resume = resolve_resume(self.parameters, "telegram", russian)
        thread_id = get_or_create_topic(self.parameters, "Telegram-каналы")
        payload = {
            "chat_id": chat_id,
            "text": f"🎯 {', '.join(matched)} · @{post['channel']}"
            f"{_UNVERIFIED_MARK if post.get('unverified') else ''}\n"
            f"Контакты: {contacts_line}\n{post['link']}\n\n{body}",
            "disable_web_page_preview": True,
            "reply_markup": vacancy_keyboard(
                post_id,
                post["contacts"],
                [routed_resume] if routed_resume is not None else [],
                contact_notes(self.output_folder, post["contacts"]),
            ),
        }
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        try:
            bot_request(token, "sendMessage", payload)
        except Exception as e:
            logger.warning(
                f"Telegram-шлюз: бот не отправил вакансию {post['link']}: {e}"
            )

    def _draft_for_preview(
        self, post: dict, contact: str, text: str, resume_path: str
    ) -> None:
        """Черновик автоотправки на подтверждение: в «Общение» (очередь
        черновиков) и, если бот подключён, в бот с кнопками отправки."""
        from main import HR_DRAFTS_FILE
        from src.job_sources.hr_replies import DraftStore
        from src.job_sources.resume_routing import resume_relative_name

        post_id = save_watch_post(self.output_folder, post)
        code = DraftStore(self.output_folder / HR_DRAFTS_FILE).add(
            contact,
            text,
            "first",
            post["link"],
            russian=_looks_russian(post.get("text") or post.get("title", "")),
            resume=resume_relative_name(
                self.parameters, Path(resume_path) if resume_path else None
            ),
            post_id=post_id,
        )
        if self.bot is None:
            return
        token, chat_id = self.bot
        send_row = [{"text": "Отправить", "callback_data": f"d:{code}:-1"}]
        if resume_path:
            send_row.append(
                {
                    "text": f"Отправить + {Path(resume_path).stem}",
                    "callback_data": f"d:{code}:0",
                }
            )
        payload = {
            "chat_id": chat_id,
            "text": (
                f"Черновик для @{contact} · @{post['channel']}\n"
                f"{post['link']}\n\n{text}"
            )[:4000],
            "disable_web_page_preview": True,
            "reply_markup": {
                "inline_keyboard": [
                    send_row,
                    [
                        {"text": "Пропустить", "callback_data": f"x:{code}"},
                        {
                            "text": "Не писать компании",
                            "callback_data": f"nd:{code}",
                        },
                    ],
                ]
            },
        }
        thread_id = get_or_create_topic(self.parameters, "Telegram-каналы")
        if thread_id is not None:
            payload["message_thread_id"] = thread_id
        try:
            bot_request(token, "sendMessage", payload)
        except Exception as e:
            logger.warning(f"Telegram-шлюз: черновик не ушёл в бот: {e}")

    def _deliver_night_posts(self) -> None:
        """Утром — вакансии, пришедшие ночью, одной пачкой в бот."""
        tg_prefs = self.parameters.get("telegram") or {}
        if self.bot is None or night_hold(tg_prefs):
            return
        for item in take_night_posts(self.output_folder):
            post = get_watch_post(self.output_folder, item["post_id"])
            if post is None:
                continue
            self._deliver_via_bot(post, item.get("matched") or [])

    def _auto_message_text(
        self, title: str, post_text: str, link: str
    ) -> tuple[str, str]:
        """{текст, путь к резюме (пусто — не прикладывать)}. Текст —
        персонализированный под вакансию через ту же LLM-генерацию, что
        и ручное «написать первому», вместо одного и того же статичного
        текста всем подряд. Резюме — по маршруту telegram_ru/en,
        прикладывается отдельным файлом (см. flush_pending_telegram_sends),
        ссылку в тексте не даём. При любой ошибке (нет ключа LLM, сеть)
        — статичный шаблон без резюме, чтобы живой шлюз не падал."""
        from main import TELEGRAM_INTRO_TEMPLATE_DEFAULT, candidate_name

        tg_prefs = self.parameters.get("telegram") or {}
        template = (
            tg_prefs.get("intro_message_template")
            or TELEGRAM_INTRO_TEMPLATE_DEFAULT
        )
        fallback = template.format(role=title, link=link)
        if not self.llm_api_key:
            return fallback, ""
        try:
            russian = _looks_russian(post_text or title)
            resume_pdf = resolve_resume(self.parameters, "telegram", russian)
            if resume_pdf is None:
                return fallback, ""
            message = generate_first_message(
                resume_pdf,
                candidate_name(self.parameters, resume_pdf),
                "",
                title,
                post_text,
                "telegram",
                self.llm_api_key,
            )
            return message["text"] or fallback, str(resume_pdf)
        except Exception as e:
            logger.warning(
                f"Telegram auto_message: LLM недоступна, "
                f"шаблон как есть: {e}"
            )
            return fallback, ""

    async def _on_private_message(self, event) -> None:
        """Ответ HR в личке — мгновенно, вместо проверки раз в час."""
        sender = await event.get_sender()
        username = getattr(sender, "username", None)
        if not username:
            return
        conversations = TelegramConversations(
            self.output_folder / "telegram_conversations.json"
        )
        if not conversations.already_contacted(username):
            return
        text = (event.message.message or "").strip()
        if not text:
            return
        conversations.record_inbound(
            username, text, event.message.id, event.message.date
        )
        notify_from_secrets(
            self.parameters,
            f"✈️ Ответ HR @{username}: " f"{text}",
            category="Ответы HR",
        )


def start_telegram_watcher(
    parameters: dict, llm_api_key: str = ""
) -> Optional[TelegramWatcher]:
    """Запускает шлюз, если telegram.watch_enabled и есть ключи API.
    None — шлюз выключен или не настроен."""
    import yaml

    telegram = parameters.get("telegram") or {}
    if not telegram.get("watch_enabled"):
        return None
    try:
        secrets = (
            yaml.safe_load(
                Path(parameters["secretsFile"]).read_text(encoding="utf-8")
            )
            or {}
        )
    except OSError:
        return None
    tg = secrets.get("telegram") or {}
    if not tg.get("api_id") or not tg.get("api_hash"):
        logger.warning(
            "Telegram-шлюз: нет telegram.api_id/api_hash в secrets.yaml."
        )
        return None
    keywords = telegram.get("watch_keywords") or default_keywords(
        telegram.get("positions") or parameters.get("positions") or []
    )
    watcher = TelegramWatcher(
        int(tg["api_id"]),
        tg["api_hash"],
        parameters["outputFileDirectory"] / ".telegram_session",
        telegram.get("channels") or [],
        keywords,
        telegram.get("watch_stop_words") or [],
        telegram.get("watch_forward_to") or "me",
        parameters,
        llm_api_key,
    )
    watcher.start()
    return watcher


# --- Автоотправка (telegram.auto_message): очередь вместо time.sleep() --
# Пауза перед холодным сообщением — минуты (см. apply_pacing.py), а клик
# по кнопке "Отправить" и разбор команд бота идут в потоке
# _poll_bot_forever — блокирующий sleep там надолго заморозил бы приём
# следующих кнопок/команд. Вместо этого пишем "отправить не раньше X" и
# разгребаем очередь на каждом тике того же цикла (уже крутится каждые
# ~25 секунд длинным поллингом, ничего нового заводить не нужно).
PENDING_SENDS_FILE = ".pending_telegram_sends.json"
BACKFILLED_CHANNELS_FILE = ".telegram_backfilled_channels.json"


def _load_backfilled_channels(output_folder: Path) -> set[str]:
    import json

    try:
        return set(
            json.loads(
                (output_folder / BACKFILLED_CHANNELS_FILE).read_text(
                    encoding="utf-8"
                )
            )
        )
    except (OSError, ValueError):
        return set()


def _save_backfilled_channels(output_folder: Path, channels: set[str]) -> None:
    import json

    (output_folder / BACKFILLED_CHANNELS_FILE).write_text(
        json.dumps(sorted(channels), ensure_ascii=False), encoding="utf-8"
    )


def _mark_channel_backfilled(output_folder: Path, channel: str) -> None:
    """Atomically add a channel only after its history scan has completed."""
    with _BACKFILLED_CHANNELS_LOCK:
        _save_backfilled_channels(
            output_folder,
            _load_backfilled_channels(output_folder) | {channel},
        )


def queue_telegram_send(
    output_folder: Path,
    contact: str,
    text: str,
    job_link: str,
    delay_min_seconds: float,
    delay_max_seconds: float,
    resume_path: str = "",
    post: Optional[dict] = None,
    send_at: Optional[datetime] = None,
    draft: Optional[dict] = None,
) -> str:
    """В очередь отправки. send_at — точное время («Утром, в 10:00» в
    «Общении»), иначе — через случайную паузу. draft — черновик, из
    которого пришёл текст: при отмене он возвращается в «Общение»."""
    import json
    import random
    from datetime import datetime, timedelta

    path = output_folder / PENDING_SENDS_FILE
    send_after = send_at or datetime.now().astimezone() + timedelta(
        seconds=random.uniform(delay_min_seconds, delay_max_seconds)
    )
    seed = f"{contact}:{job_link}" + (
        f":{send_after.isoformat()}" if send_at else ""
    )
    entry_id = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    entry: dict[str, Any] = {
        "contact": contact,
        "text": text,
        "job_link": job_link,
        "send_after": send_after.isoformat(),
        "resume_path": resume_path,
        "post": post or {},
    }
    if send_at:
        entry["scheduled"] = True
    if draft:
        entry["draft"] = draft
    with state_file_lock(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data[entry_id] = entry
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return entry_id


def pending_telegram_sends(output_folder: Path) -> dict:
    import json

    try:
        data = json.loads(
            (output_folder / PENDING_SENDS_FILE).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def cancel_telegram_send(output_folder: Path, entry_id: str) -> Optional[dict]:
    """Отменить отложенное сообщение до отправки; возвращает его."""
    import json

    path = output_folder / PENDING_SENDS_FILE
    with state_file_lock(path):
        data = pending_telegram_sends(output_folder)
        entry = data.pop(entry_id, None)
        if entry is not None:
            path.write_text(
                json.dumps(data, ensure_ascii=False), encoding="utf-8"
            )
    return entry


def pending_telegram_sends_count(output_folder: Path) -> int:
    import json

    try:
        data = json.loads(
            (output_folder / PENDING_SENDS_FILE).read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return 0
    return len(data)


def flush_pending_telegram_sends(
    send_fn: Callable[[str, str], None],
    output_folder: Path,
    active_hours: tuple[int, int] | None,
    send_file_fn: Optional[Callable[[str, Any], Any]] = None,
    on_sent: Optional[Callable[[dict], None]] = None,
) -> None:
    """Отправляет то, чему пришло время, и мы в рабочих часах; остальное
    остаётся в очереди до следующего тика. send_fn(contact, text) уже
    должен быть синхронным и привязанным к живому подключению — сюда
    приходят из потока _poll_bot_forever, а сессия Telethon живёт на
    asyncio-луп шлюза (see TelegramWatcher.call — мост поток → луп).
    send_file_fn(contact, path) — резюме отдельным файлом сразу после
    текста, если оно было привязано при постановке в очередь (см.
    queue_telegram_send: ссылку в тексте больше не даём, только файл)."""
    import json
    from datetime import datetime

    from src.job_sources.telegram_conversations import TelegramConversations

    path = output_folder / PENDING_SENDS_FILE
    now = datetime.now().astimezone()
    if active_hours is not None and not (
        active_hours[0] <= now.hour < active_hours[1]
    ):
        return  # вне рабочих часов — вся очередь ждёт следующего тика
    # Забираем подошедшие под замком и сразу убираем из файла, отправляем
    # уже без него: две очереди (шлюз и проверка ответов, окно и бот в
    # фоне) не отправят одно сообщение дважды.
    with state_file_lock(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not data:
            return
        due_entries = {}
        remaining = {}
        for entry_id, entry in data.items():
            try:
                due = datetime.fromisoformat(entry["send_after"])
            except (KeyError, ValueError):
                continue
            if now < due:
                remaining[entry_id] = entry
            else:
                due_entries[entry_id] = entry
        if not due_entries:
            return
        path.write_text(
            json.dumps(remaining, ensure_ascii=False), encoding="utf-8"
        )
    conversations = TelegramConversations(
        output_folder / "telegram_conversations.json"
    )
    for entry_id, entry in due_entries.items():
        try:
            send_fn(entry["contact"], entry["text"])
            conversations.record_outbound(
                entry["contact"], entry["text"], job_link=entry["job_link"]
            )
            if on_sent is not None:
                on_sent(entry)
            logger.info(f"Автоотправка Telegram: @{entry['contact']}")
            resume_path = entry.get("resume_path")
            if resume_path and send_file_fn is not None:
                try:
                    send_file_fn(entry["contact"], resume_path)
                except Exception as e:
                    logger.warning(
                        f"Текст ушёл, но резюме не отправилось "
                        f"@{entry['contact']}: {e}"
                    )
        except Exception as e:
            logger.warning(
                f"Не удалось отправить отложенное сообщение "
                f"@{entry['contact']}: {e}"
            )


def remember_telegram_post_contact(
    output_folder: Path, contacts: list[dict], post: dict, sent: bool = True
) -> None:
    """Контакты из поста канала — в Базу, одной карточкой.

    Намеренно не на каждый прочитанный пост: @username или email в чужом
    посте ещё не значит, что это HR. Поводы: мы написали (sent=True —
    источник «отклик на пост»), ИИ выбрал email для отклика в проверенной
    вакансии или вы нажали «Не писать компании» (sent=False — «пост в»).
    post["company"] — если компания известна (поиск по расписанию разбирает
    пост ИИ): карточка называется по компании, а не по первому контакту.
    """
    contacts = [
        {"kind": c["kind"], "value": str(c["value"]).strip()}
        for c in contacts
        if str(c.get("value") or "").strip()
        and c.get("kind") in {"telegram", "email", "linkedin"}
    ]
    if not contacts:
        return
    channel = str(post.get("channel") or "").lstrip("@")
    link = str(post.get("link") or "")
    text = str(post.get("text") or "")
    title = str(post.get("title") or (text.splitlines()[0] if text else ""))
    source = ("отклик на пост в " if sent else "пост в ") + (
        f"@{channel}" if channel else "Telegram"
    )
    ContactBook(output_folder).add(
        str(post.get("company") or ""),
        [{**c, "source": source, "source_url": link} for c in contacts],
        vacancy=(
            {
                "title": title[:120],
                "link": link,
                "source": "telegram",
                "text": text[:4000],
            }
            if link
            else None
        ),
    )


def contact_notes(output_folder: Path, contacts: list[dict]) -> dict[str, str]:
    """Пометки для кнопок под вакансией: кому уже писали (и когда) или
    кто ждёт в очереди рассылки — чтобы кнопка и рассылка не написали
    одному HR дважды незаметно для вас. Ключ — value в нижнем регистре."""
    from src.direct.campaign import CampaignStore

    conversations = TelegramConversations(
        output_folder / "telegram_conversations.json"
    )
    emailed = {
        c["value"].lower(): c["sent_at"]
        for card in ContactBook(output_folder).all().values()
        for c in card["contacts"]
        if c.get("sent_at")
    }
    queued = {
        email: item
        for campaign in CampaignStore(output_folder).all().values()
        for email, item in campaign["items"].items()
    }
    notes = {}
    for contact in contacts:
        value = contact["value"].lower()
        if contact["kind"] == "telegram":
            conv = conversations.get(value) or {}
            sent_at = next(
                (
                    m["at"]
                    for m in reversed(conv.get("messages", []))
                    if m["direction"] == "out"
                ),
                "",
            )
        else:
            item = queued.get(value) or {}
            sent_at = emailed.get(value) or item.get("sent_at", "")
            if not sent_at and item.get("status") in ("pending", "draft"):
                notes[value] = "в очереди рассылки"
        if sent_at:
            notes[value] = f"писали {sent_at[8:10]}.{sent_at[5:7]}"
    return notes


# --- Кнопки под вакансией: посты, резюме и письма для Telegram ----------

WATCH_POSTS_FILE = ".watch_posts.json"
_WATCH_POSTS_LIMIT = 500
TELEGRAM_FOLDER = (
    "telegram"  # data_folder/telegram — резюме и письма для Telegram
)


def save_watch_post(output_folder: Path, post: dict) -> str:
    """Запоминает пост, под которым стоят кнопки, — id короткий, чтобы
    влезть в callback_data (≤64 байт)."""
    import json

    post_id = hashlib.sha1(post["link"].encode("utf-8")).hexdigest()[:10]
    if not post.get("saved_at"):
        from datetime import datetime

        post = {**post, "saved_at": datetime.now().astimezone().isoformat()}
    path = output_folder / WATCH_POSTS_FILE
    # Под замком: посты доставляются параллельно (run_in_executor, досмотр
    # истории каналов) — два write_text разом склеивали файл, следующее
    # чтение падало в {} и все старые кнопки отвечали «пост устарел».
    with state_file_lock(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        data[post_id] = post
        if len(data) > _WATCH_POSTS_LIMIT:
            data = dict(list(data.items())[-_WATCH_POSTS_LIMIT:])
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return post_id


def get_watch_post(output_folder: Path, post_id: str) -> Optional[dict]:
    import json

    path = output_folder / WATCH_POSTS_FILE
    try:
        with state_file_lock(path):
            return json.loads(path.read_text(encoding="utf-8")).get(post_id)
    except (OSError, ValueError):
        return None


def telegram_resumes(data_folder: Path) -> list[Path]:
    """Резюме для Telegram — PDF из data_folder/telegram (отдельно от
    основных resume.pdf/resume_linkedin.pdf), по кнопке на файл. Пусто —
    основное resume.pdf."""
    folder = data_folder / TELEGRAM_FOLDER
    resumes = sorted(folder.glob("*.pdf")) if folder.exists() else []
    if not resumes and (data_folder / "resume.pdf").exists():
        resumes = [data_folder / "resume.pdf"]
    return resumes


def save_telegram_letter(data_folder: Path, post: dict, text: str) -> Path:
    """Письмо, написанное под вакансию из Telegram, — файлом в
    data_folder/telegram/letters (архив по вашему запросу, вне 7-дневной
    очистки журнала откликов)."""
    from datetime import datetime

    folder = data_folder / TELEGRAM_FOLDER / "letters"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    name = re.sub(
        r"[^\w\-]+",
        "_",
        f"{stamp}_{post.get('channel', '')}_{post.get('title', '')}",
    )[:120]
    path = folder / f"{name.strip('_')}.txt"
    path.write_text(
        f"{post.get('title', '')}\n{post.get('link', '')}\n\n{text}\n",
        encoding="utf-8",
    )
    return path


def vacancy_keyboard(
    post_id: str,
    contacts: list[dict],
    resumes: list[Path],
    notes: Optional[dict[str, str]] = None,
) -> dict:
    """Кнопки под вакансией: для Telegram-контакта — «Здравствуйте»,
    «Здравствуйте + резюме» (по кнопке на файл резюме) и письмо LLM; для
    email — черновик письма LLM; «Не писать компании» — в Базе статус
    «не писать», в рассылки она не попадёт. notes — см. contact_notes."""
    rows: list[list[dict]] = []
    for index, contact in enumerate(contacts[:2]):
        note = (notes or {}).get(contact["value"].lower())
        suffix = f" · {note}" if note else ""
        if contact["kind"] == "telegram":
            who = f"@{contact['value']}"
            row = [
                {
                    "text": f"👋 {who}{suffix}",
                    "callback_data": f"q:{post_id}:{index}:-1",
                }
            ]
            row += [
                {
                    "text": f"👋 + 📎 {resume.stem}",
                    "callback_data": f"q:{post_id}:{index}:{r}",
                }
                for r, resume in enumerate(resumes[:3])
            ]
            rows.append(row)
            rows.append(
                [
                    {
                        "text": f"✍️ Сопроводительное для {who} (LLM)",
                        "callback_data": f"l:{post_id}:{index}",
                    }
                ]
            )
        elif contact["kind"] == "email":
            rows.append(
                [
                    {
                        "text": f"✍️ Письмо на {contact['value']} (LLM)"
                        f"{suffix}",
                        "callback_data": f"l:{post_id}:{index}",
                    }
                ]
            )
    if rows:
        rows.append(
            [
                {
                    "text": "🚫 Не писать компании",
                    "callback_data": f"n:{post_id}",
                }
            ]
        )
    return {"inline_keyboard": rows}


# --- Посты в «Общении», ночные вакансии -------------------------------------

WATCH_POSTS_HIDDEN_FILE = ".watch_posts_hidden.json"
NIGHT_POSTS_FILE = ".night_posts.json"
MORNING_HOUR = 10
# Без своих рабочих часов (Настройки → Telegram-парсер) ночь — 23:00–8:00.
DEFAULT_NIGHT = (23, 8)


def night_hold(tg_prefs: dict, now: Optional[datetime] = None) -> bool:
    """«Ночные вакансии — утром» включено и сейчас ночь: вне рабочих часов
    Telegram-парсера, а без них — с 23:00 до 8:00."""
    from datetime import datetime

    if not tg_prefs.get("night_to_morning"):
        return False
    hour = (now or datetime.now().astimezone()).hour
    start, end = tg_prefs.get("active_hours_start"), tg_prefs.get(
        "active_hours_end"
    )
    if start is not None and end is not None:
        return not (int(start) <= hour < int(end))
    return hour >= DEFAULT_NIGHT[0] or hour < DEFAULT_NIGHT[1]


def next_morning(
    now: Optional[datetime] = None, hour: int = MORNING_HOUR
) -> datetime:
    """Ближайшие 10:00: сегодня, если ещё не наступило, иначе завтра."""
    from datetime import datetime, timedelta

    now = now or datetime.now().astimezone()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


def _load_json_file(path: Path, default):
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return data if isinstance(data, type(default)) else default


def queue_night_post(
    output_folder: Path, post_id: str, matched: list[str]
) -> None:
    import json

    path = output_folder / NIGHT_POSTS_FILE
    with state_file_lock(path):
        items = _load_json_file(path, [])
        if all(i.get("post_id") != post_id for i in items):
            items.append({"post_id": post_id, "matched": matched})
        path.write_text(json.dumps(items[-200:]), encoding="utf-8")


def take_night_posts(output_folder: Path) -> list[dict]:
    path = output_folder / NIGHT_POSTS_FILE
    if not path.exists():
        return []
    with state_file_lock(path):
        items = _load_json_file(path, [])
        path.write_text("[]", encoding="utf-8")
    return items


def night_posts_count(output_folder: Path) -> int:
    return len(_load_json_file(output_folder / NIGHT_POSTS_FILE, []))


def hidden_watch_posts(output_folder: Path) -> set[str]:
    return set(_load_json_file(output_folder / WATCH_POSTS_HIDDEN_FILE, []))


def set_watch_post_hidden(
    output_folder: Path, post_id: str, hidden: bool
) -> None:
    """«Скрыть» вакансию в «Общении»: сам пост не удаляется."""
    import json

    path = output_folder / WATCH_POSTS_HIDDEN_FILE
    with state_file_lock(path):
        ids = set(_load_json_file(path, []))
        if hidden:
            ids.add(post_id)
        else:
            ids.discard(post_id)
        path.write_text(json.dumps(sorted(ids)), encoding="utf-8")


def all_watch_posts(output_folder: Path) -> dict:
    path = output_folder / WATCH_POSTS_FILE
    try:
        with state_file_lock(path):
            return _load_json_file(path, {})
    except Exception:
        return {}
