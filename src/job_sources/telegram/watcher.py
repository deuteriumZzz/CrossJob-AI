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
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from src.job_sources.contact_book import ContactBook, contacts_from_text
from src.job_sources.telegram.client import normalize_channel
from src.job_sources.telegram_conversations import TelegramConversations
from src.job_sources.telegram_notify import (
    bot_credentials,
    bot_request,
    notify_from_secrets,
)
from src.logging import logger

_ACTIVE: Optional["TelegramWatcher"] = None
RECONNECT_DELAY_SECONDS = 30
_SEEN_LIMIT = 3000
# Слова, по которым сама по себе должность ничего не говорит.
_GENERIC_WORDS = {
    "developer", "разработчик", "engineer", "инженер", "программист",
    "senior", "middle", "junior", "lead", "specialist", "специалист",
}


def active_watcher() -> Optional["TelegramWatcher"]:
    return _ACTIVE if _ACTIVE is not None and _ACTIVE.connected else None


def default_keywords(positions: list[str]) -> list[str]:
    """Если слова не заданы — значимые слова из ваших должностей
    ("Python разработчик" → "python")."""
    words: list[str] = []
    for position in positions:
        for word in re.findall(r"[\w+#.]+", position.casefold()):
            if word not in _GENERIC_WORDS and len(word) > 2 and word not in words:
                words.append(word)
    return words


def match_keywords(text: str, keywords: list[str], stop_words: list[str]) -> list[str]:
    """Совпавшие ключевые слова (по вхождению, без учёта регистра) или
    пустой список, если совпадений нет или есть стоп-слово."""
    lowered = text.casefold()
    if any(stop.casefold() in lowered for stop in stop_words if stop.strip()):
        return []
    return [k for k in keywords if k.strip() and k.casefold() in lowered]


def _fingerprint(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.casefold())[:400]
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


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
        self._settings_checked_at = time.monotonic()
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
                target=self._poll_bot_forever, name="telegram-bot-inbox", daemon=True
            ).start()
        try:
            while not self._stopping.is_set():
                try:
                    self.loop.run_until_complete(self._serve())
                except Exception as e:
                    logger.warning(f"Telegram-шлюз: обрыв ({e}), переподключаюсь…")
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

        token = self.bot[0]
        while not self._stopping.is_set():
            try:
                updates = poll_bot_updates(token, self.output_folder, timeout=25)
                if updates:
                    from main import handle_bot_updates

                    handle_bot_updates(self.parameters, self.llm_api_key, updates)
            except Exception as e:
                logger.warning(f"Telegram-бот: не удалось прочитать обновления: {e}")
                self._stopping.wait(5)

    def call(self, factory: Callable[[Any], Awaitable[Any]], timeout: float = 60) -> Any:
        """Выполнить действие через подключение шлюза из другого потока."""
        future = asyncio.run_coroutine_threadsafe(factory(self.client), self.loop)
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
        chats = []
        for channel in self.channels:
            try:
                chats.append(await self.client.get_input_entity(channel))
            except Exception as e:
                logger.warning(f"Telegram-шлюз: канал @{channel} недоступен: {e}")
        self.client.add_event_handler(self._on_channel_post, events.NewMessage(chats=chats))
        self.client.add_event_handler(
            self._on_private_message,
            events.NewMessage(incoming=True, func=lambda e: e.is_private),
        )
        self.connected = True
        logger.info(
            f"Telegram-шлюз: слушаю {len(chats)} каналов, слова: "
            f"{', '.join(self.keywords) or '—'}"
        )
        await self.client.run_until_disconnected()

    def _refresh_settings(self) -> None:
        """Ключевые и стоп-слова меняются в дашборде на ходу — перечитываем
        их из work_preferences.yaml не чаще раза в минуту, без перезапуска."""
        if time.monotonic() - self._settings_checked_at < 60:
            return
        self._settings_checked_at = time.monotonic()
        import yaml

        try:
            prefs = yaml.safe_load(
                (Path(self.parameters["dataFolder"]) / "work_preferences.yaml").read_text(encoding="utf-8")
            ) or {}
        except (OSError, KeyError, yaml.YAMLError):
            return
        telegram = prefs.get("telegram") or {}
        self.keywords = telegram.get("watch_keywords") or self.keywords
        self.stop_words = telegram.get("watch_stop_words") or []

    async def _on_channel_post(self, event) -> None:
        text = (event.message.message or "").strip()
        if not text:
            return
        self._refresh_settings()
        matched = match_keywords(text, self.keywords, self.stop_words)
        if not matched:
            return
        fingerprint = _fingerprint(text)
        if fingerprint in self._seen:
            return  # тот же пост, репостнутый в другой канал
        self._seen[fingerprint] = None
        if len(self._seen) > _SEEN_LIMIT:
            self._seen.popitem(last=False)

        chat = await event.get_chat()
        channel = getattr(chat, "username", None) or str(event.chat_id)
        link = f"https://t.me/{channel}/{event.message.id}"
        contacts = contacts_from_text(text, exclude=(channel,))
        self.matched_count += 1
        if self.bot is not None:
            # Через бота — чтобы под вакансией были кнопки быстрого ответа.
            post = {
                "channel": channel, "link": link, "text": text[:4000],
                "title": text.splitlines()[0][:120],
                "contacts": [{"kind": c["kind"], "value": c["value"]} for c in contacts],
            }
            await asyncio.get_event_loop().run_in_executor(
                None, self._deliver_via_bot, post, matched
            )
            self._remember_contacts(channel, link, text, contacts)
            return
        try:
            forwarded = await self.client.forward_messages(self.forward_to, event.message)
            header = [f"🎯 {', '.join(matched)} · @{channel}"]
            if contacts:
                header.append(
                    "Контакты: "
                    + ", ".join(
                        f"@{c['value']}" if c["kind"] == "telegram" else c["value"]
                        for c in contacts
                    )
                )
            await self.client.send_message(
                self.forward_to, "\n".join(header), reply_to=forwarded.id,
                link_preview=False,
            )
        except Exception as e:
            logger.warning(f"Telegram-шлюз: не удалось переслать {link}: {e}")
        self._remember_contacts(channel, link, text, contacts)

    def _deliver_via_bot(self, post: dict, matched: list[str]) -> None:
        token, chat_id = self.bot
        post_id = save_watch_post(self.output_folder, post)
        contacts_line = ", ".join(
            f"@{c['value']}" if c["kind"] == "telegram" else c["value"]
            for c in post["contacts"]
        ) or "не найдены — откройте пост"
        body = post["text"] if len(post["text"]) <= 3000 else post["text"][:3000] + "…"
        try:
            bot_request(token, "sendMessage", {
                "chat_id": chat_id,
                "text": f"🎯 {', '.join(matched)} · @{post['channel']}\n"
                        f"Контакты: {contacts_line}\n{post['link']}\n\n{body}",
                "disable_web_page_preview": True,
                "reply_markup": vacancy_keyboard(
                    post_id, post["contacts"], telegram_resumes(Path(self.parameters["dataFolder"]))
                ),
            })
        except Exception as e:
            logger.warning(f"Telegram-шлюз: бот не отправил вакансию {post['link']}: {e}")

    def _remember_contacts(self, channel: str, link: str, text: str, contacts: list[dict]) -> None:
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
        conversations.record_inbound(username, text, event.message.id, event.message.date)
        notify_from_secrets(self.parameters, f"✈️ Ответ HR @{username}: {text}")


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
        secrets = yaml.safe_load(Path(parameters["secretsFile"]).read_text(encoding="utf-8")) or {}
    except OSError:
        return None
    tg = secrets.get("telegram") or {}
    if not tg.get("api_id") or not tg.get("api_hash"):
        logger.warning("Telegram-шлюз: нет telegram.api_id/api_hash в secrets.yaml.")
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


# --- Кнопки под вакансией: посты, резюме и письма для Telegram ----------

WATCH_POSTS_FILE = ".watch_posts.json"
_WATCH_POSTS_LIMIT = 500
TELEGRAM_FOLDER = "telegram"  # data_folder/telegram — резюме и письма для Telegram


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
        return json.loads((output_folder / WATCH_POSTS_FILE).read_text(encoding="utf-8")).get(post_id)
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
    name = re.sub(r"[^\w\-]+", "_", f"{stamp}_{post.get('channel', '')}_{post.get('title', '')}")[:120]
    path = folder / f"{name.strip('_')}.txt"
    path.write_text(f"{post.get('title', '')}\n{post.get('link', '')}\n\n{text}\n", encoding="utf-8")
    return path


def vacancy_keyboard(post_id: str, contacts: list[dict], resumes: list[Path]) -> dict:
    """Кнопки под вакансией: для Telegram-контакта — «Здравствуйте»,
    «Здравствуйте + резюме» (по кнопке на файл резюме) и письмо LLM; для
    email — черновик письма LLM."""
    rows: list[list[dict]] = []
    for index, contact in enumerate(contacts[:2]):
        if contact["kind"] == "telegram":
            who = f"@{contact['value']}"
            row = [{"text": f"👋 {who}", "callback_data": f"q:{post_id}:{index}:-1"}]
            row += [
                {"text": f"👋 + 📎 {resume.stem}", "callback_data": f"q:{post_id}:{index}:{r}"}
                for r, resume in enumerate(resumes[:3])
            ]
            rows.append(row)
            rows.append([{"text": f"✍️ Сопроводительное для {who} (LLM)", "callback_data": f"l:{post_id}:{index}"}])
        elif contact["kind"] == "email":
            rows.append([{"text": f"✍️ Письмо на {contact['value']} (LLM)", "callback_data": f"l:{post_id}:{index}"}])
    return {"inline_keyboard": rows}
