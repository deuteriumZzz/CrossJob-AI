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
import json
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional

from src.job_sources.contact_book import ContactBook, contacts_from_text
from src.job_sources.hr_replies import _looks_russian, generate_first_message
from src.job_sources.resume_routing import resolve_resume
from src.job_sources.telegram.client import normalize_channel
from src.job_sources.telegram_conversations import TelegramConversations
from src.job_sources.telegram_notify import (
    bot_credentials,
    bot_request,
    get_or_create_topic,
    notify_from_secrets,
)
from src.logging import logger

_ACTIVE: Optional["TelegramWatcher"] = None
RECONNECT_DELAY_SECONDS = 30
_SEEN_LIMIT = 3000
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
CANDIDATE_SELF_POST_MARKERS = (
    "ищу работу",
    "ищу вакансию",
    "в поиске работы",
    "рассматриваю предложения",
    "рассматриваю офферы",
    "open to work",
    "резюме:",
    "моё резюме",
    "мое резюме",
    "мой резюме",
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
    "Пост из Telegram-канала о работе. Это объявление вакансии (ищут "
    "сотрудника), а не резюме/реклама/вопрос? Ответь одним словом: "
    "ДА или НЕТ.\n\nПост:\n{text}"
)


# Секунды ожидания перед каждым повтором при rate limit — не растёт
# бесконечно (лимиты обычно сбрасываются за минуты, не часы), суммарно
# держит один пост в очереди не больше ~100с, пока идёт reset окна
# лимита у провайдера. Другие посты (свои executor-потоки) это не
# блокирует — см. run_in_executor в _handle_post.
RATE_LIMIT_RETRY_DELAYS_SECONDS = (10, 30, 60)
RATE_LIMIT_MARKERS = ("429", "rate limit", "rate_limit", "too many requests")


def _llm_says_vacancy(text: str, llm_api_key: str) -> bool:
    """Короткий LLM-классификатор поверх стоп-слов (telegram.
    llm_vacancy_filter, выключен по умолчанию) — вызывается только для
    постов, уже прошедших match_keywords, не на весь поток каналов;
    промпт и ответ в одно слово держат токены к минимуму.

    Rate limit — не сразу fail-open: 50+ каналов легко дают всплеск
    запросов разом, а лимит провайдера обычно сбрасывается за минуты —
    ждём и пробуем снова (см. RATE_LIMIT_RETRY_DELAYS_SECONDS), чтобы
    не пропускать проверку молча именно в момент нагрузки, когда она
    нужнее всего. Любая другая ошибка (плохой ключ, сеть, пустой
    ответ) — fail-open сразу, как и раньше (_auto_message_text), нет
    смысла ждать то, что само не пройдёт."""
    if not llm_api_key:
        return True
    from src.job_sources.llm_provider import get_chat_llm

    prompt = _VACANCY_CLASSIFIER_PROMPT.format(text=text[:600])
    attempts = len(RATE_LIMIT_RETRY_DELAYS_SECONDS) + 1
    for attempt in range(attempts):
        try:
            llm = get_chat_llm(llm_api_key, temperature=0)
            answer = llm.invoke(prompt)
            content = str(getattr(answer, "content", answer)).strip().lower()
            return not content.startswith("нет")
        except Exception as e:
            is_rate_limit = any(
                m in str(e).lower() for m in RATE_LIMIT_MARKERS
            )
            if not is_rate_limit or attempt == attempts - 1:
                logger.warning(
                    f"Telegram-парсер: LLM-классификатор недоступен "
                    f"(попытка {attempt + 1}/{attempts}): {e}"
                )
                return True
            delay = RATE_LIMIT_RETRY_DELAYS_SECONDS[attempt]
            logger.info(
                f"Telegram-парсер: LLM rate limit, повтор через {delay}с "
                f"(попытка {attempt + 1}/{attempts})"
            )
            time.sleep(delay)
    return True


# Структурные сигналы реальной вакансии — зарплата и формат работы
# почти всегда есть в тексте вакансии, у постов "ищу работу"/рекламы
# реже. Не замена LLM-классификатору, а способ не тратить на него
# токены, когда пост и так явно похож на вакансию.
_SALARY_RE = re.compile(
    r"\d[\d\s]{2,}\s?(?:₽|руб|\$|usd|eur|€|k\b)|\bот\s+\d{2,}", re.IGNORECASE
)
_WORK_FORMAT_RE = re.compile(
    r"удал[её]нн?о|remote|гибрид|офис|hybrid|on-?site", re.IGNORECASE
)


def _has_vacancy_structure(text: str) -> bool:
    return bool(_SALARY_RE.search(text)) and bool(_WORK_FORMAT_RE.search(text))


_CHANNEL_TRUST_FILE = ".channel_trust.json"
# Меньше — можно наказать канал по паре случайных совпадений; больше —
# долго терпим откровенно мусорный канал, пока не наберётся данных.
_TRUST_MIN_SAMPLES = 5
_TRUST_REJECT_THRESHOLD = 0.5


def _record_channel_verdict(
    output_folder: Path, channel: str, is_vacancy: bool
) -> None:
    """Копит долю отклонённых LLM-классификатором постов на канал —
    основа для _channel_is_untrusted. Пишется только когда
    llm_vacancy_filter реально вызвал LLM (см. _handle_post), не на
    каждый матч по ключевым словам."""
    path = output_folder / _CHANNEL_TRUST_FILE
    try:
        data = (
            json.loads(path.read_text(encoding="utf-8"))
            if path.exists()
            else {}
        )
    except (OSError, json.JSONDecodeError):
        data = {}
    entry = data.setdefault(channel, {"checked": 0, "rejected": 0})
    entry["checked"] += 1
    if not is_vacancy:
        entry["rejected"] += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _channel_is_untrusted(output_folder: Path, channel: str) -> bool:
    """Канал с высокой долей отклонённых постов (не менее
    _TRUST_MIN_SAMPLES проверок) теряет право на "скидку" по
    _has_vacancy_structure — для него LLM-проверка идёт всегда, даже
    если структурные сигналы выглядят убедительно."""
    path = output_folder / _CHANNEL_TRUST_FILE
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    entry = data.get(channel)
    if not entry or entry["checked"] < _TRUST_MIN_SAMPLES:
        return False
    return entry["rejected"] / entry["checked"] >= _TRUST_REJECT_THRESHOLD


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
        self.matched_count = 0
        self._settings_task: Optional[asyncio.Task] = None
        self._stopping = threading.Event()
        self._seen: OrderedDict[str, None] = OrderedDict()

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
            except Exception as e:
                logger.warning(
                    f"Telegram-бот: не удалось прочитать обновления: {e}"
                )
                self._stopping.wait(5)

    def _flush_pending_sends(self) -> None:
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
        )

    def call(
        self,
        factory: Callable[[Any], Coroutine[Any, Any, Any]],
        timeout: float = 60,
    ) -> Any:
        """Выполнить действие через подключение шлюза из другого потока."""
        assert self.loop is not None, "шлюз ещё не запущен"
        future = asyncio.run_coroutine_threadsafe(
            factory(self.client), self.loop
        )
        return future.result(timeout)

    # --- работа ---------------------------------------------------------

    async def _serve(self) -> None:
        from telethon import events

        await self.client.connect()
        # _serve повторяется при переподключении — без снятия старых
        # обработчиков каждый пост приходил бы по несколько раз.
        self.client.remove_event_handler(self._on_channel_post)
        self.client.remove_event_handler(self._on_private_message)
        if not await self.client.is_user_authorized():
            logger.error(
                "Telegram-шлюз: сессия не авторизована — войдите во вкладке "
                "«Общение → Telegram»."
            )
            self._stopping.set()
            return
        await self._subscribe()
        self.client.add_event_handler(
            self._on_private_message,
            events.NewMessage(incoming=True, func=lambda e: e.is_private),
        )
        self.connected = True
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
        newly_backfilled = []
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
                if channel not in backfilled:
                    newly_backfilled.append(channel)
                    asyncio.ensure_future(
                        self._backfill_channel(entity, channel)
                    )
            except Exception as e:
                logger.warning(
                    f"Telegram-шлюз: канал @{channel} недоступен: {e}"
                )
        if newly_backfilled:
            # Помечаем сразу, до завершения самого досмотра — иначе
            # повторный вызов _subscribe (смена ключевых слов и т.п.)
            # раньше, чем досмотр закончится, запустил бы его ещё раз.
            _save_backfilled_channels(
                self.output_folder, backfilled | set(newly_backfilled)
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
        if not days:
            return
        from datetime import datetime, timedelta, timezone

        since = datetime.now(timezone.utc) - timedelta(days=days)
        found = 0
        try:
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

        tg_prefs = self.parameters.get("telegram") or {}
        if tg_prefs.get("llm_vacancy_filter") and (
            _channel_is_untrusted(self.output_folder, channel)
            or not _has_vacancy_structure(text)
        ):
            is_vacancy = await asyncio.get_event_loop().run_in_executor(
                None, _llm_says_vacancy, text, self.llm_api_key
            )
            _record_channel_verdict(self.output_folder, channel, is_vacancy)
            if not is_vacancy:
                return

        link = f"https://t.me/{channel}/{message.id}"
        contacts = contacts_from_text(text, exclude=(channel,))
        self.matched_count += 1

        telegram_contacts = [c for c in contacts if c["kind"] == "telegram"]
        if tg_prefs.get("auto_message") and len(telegram_contacts) == 1:
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
                title = text.splitlines()[0][:120]
                (
                    intro_text,
                    resume_path,
                ) = await asyncio.get_event_loop().run_in_executor(
                    None, self._auto_message_text, title, text, link
                )
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
                )
                logger.info(
                    f"Telegram auto_message: в очередь для @{contact_value}"
                )
                self._remember_contacts(channel, link, text, contacts)
                return

        if self.bot is not None:
            # Через бота — чтобы под вакансией были кнопки быстрого ответа.
            post = {
                "channel": channel,
                "link": link,
                "text": text[:4000],
                "title": text.splitlines()[0][:120],
                "contacts": [
                    {"kind": c["kind"], "value": c["value"]} for c in contacts
                ],
            }
            await asyncio.get_event_loop().run_in_executor(
                None, self._deliver_via_bot, post, matched
            )
            self._remember_contacts(channel, link, text, contacts)
            return
        try:
            forwarded = await self.client.forward_messages(
                self.forward_to, message
            )
            header = [f"🎯 {', '.join(matched)} · @{channel}"]
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
        self._remember_contacts(channel, link, text, contacts)

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
            "text": f"🎯 {', '.join(matched)} · @{post['channel']}\n"
            f"Контакты: {contacts_line}\n{post['link']}\n\n{body}",
            "disable_web_page_preview": True,
            "reply_markup": vacancy_keyboard(
                post_id,
                post["contacts"],
                [routed_resume] if routed_resume is not None else [],
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

    def _remember_contacts(
        self, channel: str, link: str, text: str, contacts: list[dict]
    ) -> None:
        if contacts:
            ContactBook(self.output_folder).add(
                "",
                [
                    {**c, "source": f"пост в @{channel}", "source_url": link}
                    for c in contacts
                ],
                vacancy={
                    "title": text.splitlines()[0][:120],
                    "link": link,
                    "source": "telegram",
                    "text": text[:4000],
                },
            )

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


def queue_telegram_send(
    output_folder: Path,
    contact: str,
    text: str,
    job_link: str,
    delay_min_seconds: float,
    delay_max_seconds: float,
    resume_path: str = "",
) -> None:
    import json
    import random
    from datetime import datetime, timedelta

    path = output_folder / PENDING_SENDS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    send_after = datetime.now().astimezone() + timedelta(
        seconds=random.uniform(delay_min_seconds, delay_max_seconds)
    )
    entry_id = hashlib.sha1(
        f"{contact}:{job_link}".encode("utf-8")
    ).hexdigest()[:10]
    data[entry_id] = {
        "contact": contact,
        "text": text,
        "job_link": job_link,
        "send_after": send_after.isoformat(),
        "resume_path": resume_path,
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


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
    send_file_fn: Optional[Callable[[str, str], None]] = None,
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
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not data:
        return
    now = datetime.now().astimezone()
    if active_hours is not None and not (
        active_hours[0] <= now.hour < active_hours[1]
    ):
        return  # вне рабочих часов — вся очередь ждёт следующего тика
    conversations = TelegramConversations(
        output_folder / "telegram_conversations.json"
    )
    remaining = {}
    for entry_id, entry in data.items():
        try:
            due = datetime.fromisoformat(entry["send_after"])
        except (KeyError, ValueError):
            continue
        if now < due:
            remaining[entry_id] = entry
            continue
        try:
            send_fn(entry["contact"], entry["text"])
            conversations.record_outbound(
                entry["contact"], entry["text"], job_link=entry["job_link"]
            )
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
    path.write_text(
        json.dumps(remaining, ensure_ascii=False), encoding="utf-8"
    )


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
    path = output_folder / WATCH_POSTS_FILE
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

    try:
        return json.loads(
            (output_folder / WATCH_POSTS_FILE).read_text(encoding="utf-8")
        ).get(post_id)
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
    post_id: str, contacts: list[dict], resumes: list[Path]
) -> dict:
    """Кнопки под вакансией: для Telegram-контакта — «Здравствуйте»,
    «Здравствуйте + резюме» (по кнопке на файл резюме) и письмо LLM; для
    email — черновик письма LLM; «Не писать компании» — в Базе статус
    «не писать», в рассылки она не попадёт."""
    rows: list[list[dict]] = []
    for index, contact in enumerate(contacts[:2]):
        if contact["kind"] == "telegram":
            who = f"@{contact['value']}"
            row = [
                {
                    "text": f"👋 {who}",
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
                        "text": f"✍️ Письмо на {contact['value']} (LLM)",
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
