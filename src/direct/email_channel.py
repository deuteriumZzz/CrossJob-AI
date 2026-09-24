"""Письма HR с вашей почты (Gmail): отправка через SMTP и проверка
ответов через IMAP — стандартной библиотекой, без новых зависимостей.
Нужен пароль приложения Google (https://myaccount.google.com/apppasswords)
в secrets.yaml: email: {address: ..., app_password: ...} — его вводит
сам пользователь, бот пароль не запрашивает и никуда не передаёт.
Идеи лимита/напоминания в той же ветке/проверки ответа — из
codesarthak/prospector (MIT)."""

from __future__ import annotations

import imaplib
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
IMAP_HOST = "imap.gmail.com"


def build_message(
    sender: str,
    to: str,
    subject: str,
    body: str,
    attachment: Path | None = None,
    in_reply_to: str = "",
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = make_msgid()
    if in_reply_to:
        # Напоминание уходит в ту же ветку — у HR это одна переписка.
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to
    message.set_content(body)
    if attachment is not None and attachment.exists():
        message.add_attachment(
            attachment.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=attachment.name,
        )
    return message


def send_email(credentials: dict, message: EmailMessage) -> str:
    """Отправляет письмо, возвращает его Message-ID (для напоминания)."""
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.login(credentials["address"], credentials["app_password"])
        smtp.send_message(message)
    return message["Message-ID"]


def senders_replied(credentials: dict, addresses: list[str], days: int = 60) -> set[str]:
    """Кто из addresses написал нам за последние days дней (только
    чтение ящика, письма не помечаются прочитанными)."""
    if not addresses:
        return set()
    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    replied = set()
    with imaplib.IMAP4_SSL(IMAP_HOST) as imap:
        imap.login(credentials["address"], credentials["app_password"])
        imap.select("INBOX", readonly=True)
        for address in addresses:
            status, data = imap.search(None, f'(FROM "{address}" SINCE {since})')
            if status == "OK" and data and data[0].split():
                replied.add(address)
    return replied
