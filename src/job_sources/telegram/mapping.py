from src.job import Job

TITLE_PREVIEW_LENGTH = 120


def telegram_message_to_job(channel: str, message) -> Job:
    """Преобразует сообщение Telethon из канала в Job. Структурированных
    полей title/company/location здесь нет — это свободнотекстовый
    пост."""
    text = (message.text or "").strip()
    title_preview = text.split("\n", 1)[0][:TITLE_PREVIEW_LENGTH]

    return Job(
        role=title_preview,
        company="",
        location="",
        link=f"https://t.me/{channel}/{message.id}",
        description=text,
        source="telegram",
        external_id=f"{channel}_{message.id}",
        apply_method="telegram_manual",
    )
