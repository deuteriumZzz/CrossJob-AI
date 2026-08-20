"""Разведка перед интеграцией с GetMatch-ботом (@g_jobbot).

Не пишет никакого кода интеграции — просто открывает диалог с ботом
через тот же личный Telegram-аккаунт (Telethon-сессия), что уже
используется для поиска по каналам, и печатает всё, что бот
присылает: текст сообщений и подписи/callback_data инлайн-кнопок.
Нужно вручную потыкать основные кнопки (посмотреть вакансию,
откликнуться и т.д.) и посмотреть, что бот отвечает на каждом шаге —
без этого писать клиента вслепую значит гадать, как уже решили не
делать с сайтом GetMatch.

Запуск (из корня проекта, с уже заполненным secrets.yaml):
    python scripts/explore_getmatch_bot.py

Первый запуск — как и `--auto telegram` — попросит номер телефона и
код входа в консоли; дальше сессия переиспользуется.
"""

import asyncio
from pathlib import Path

import yaml
from telethon import TelegramClient, events

GETMATCH_BOT = "g_jobbot"
DATA_FOLDER = Path("data_folder")


def _load_telegram_credentials() -> tuple[int, str]:
    secrets = yaml.safe_load(
        (DATA_FOLDER / "secrets.yaml").read_text(encoding="utf-8")
    )
    telegram = secrets.get("telegram") or {}
    api_id = telegram.get("api_id")
    api_hash = telegram.get("api_hash")
    if not api_id or not api_hash:
        raise SystemExit(
            "telegram.api_id/api_hash не заданы в data_folder/secrets.yaml "
            "(https://my.telegram.org/apps)."
        )
    return int(api_id), str(api_hash)


def _dump_buttons(buttons) -> str:
    if not buttons:
        return ""
    rows = []
    for row in buttons:
        rows.append(
            " | ".join(
                f"[{b.text!r} -> {getattr(b, 'data', b.url)!r}]" for b in row
            )
        )
    return "\nКнопки:\n  " + "\n  ".join(rows)


async def main() -> None:
    api_id, api_hash = _load_telegram_credentials()
    session_path = DATA_FOLDER / "output" / ".telegram_session"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session_path), api_id, api_hash)

    @client.on(events.NewMessage(from_users=GETMATCH_BOT))
    async def _on_message(event):
        print("\n--- Сообщение от бота ---")
        print(event.raw_text)
        print(_dump_buttons(event.message.buttons))

    async with client:
        print(f"Отправляю /start боту @{GETMATCH_BOT}...")
        await client.send_message(GETMATCH_BOT, "/start")
        print(
            "Слушаю ответы. Потыкайте кнопки/команды вручную в "
            "приложении Telegram под этим же аккаунтом — ответы бота "
            "будут печататься здесь. Ctrl+C для выхода."
        )
        await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
