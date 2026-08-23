import re

_TAG_RE = re.compile(r"<[^>]+>")
_BLOCK_BREAK_RE = re.compile(r"</p>|<br\s*/?>", re.IGNORECASE)


def strip_html(html: str) -> str:
    return _TAG_RE.sub(" ", html or "").strip()


def html_letter_to_plain_text(html: str) -> str:
    """generate_cover_letter_for_job() всегда возвращает HTML (нужен
    для рендера в PDF на дашборде) — но поля на GetMatch/hh.ru под
    сопроводительное письмо самые обычные <textarea>, не rich-text:
    вставленные теги вроде "<p>" показываются буквально как текст, а
    не форматированием (подтверждено на реальном отправленном
    отклике на GetMatch). Переносы строк из </p>/<br> сохраняем как
    настоящие переводы строк, остальные теги — просто убираем."""
    text = _BLOCK_BREAK_RE.sub("\n\n", html or "")
    # Тег чистим по всему тексту ЦЕЛИКОМ, а не построчно: у некоторых
    # тегов атрибуты переносятся на несколько строк (подтверждено на
    # реальном ответе LLM — например многострочный <div style="...">
    # из template_base.py), и построчная регулярка такой тег не видит,
    # потому что не встречает ">" на той же строке, где встретила "<".
    text = _TAG_RE.sub(" ", text)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    # Каждая непустая строка исходной разметки (div-обёртки без явных
    # </p>/<br>) даёт свой перенос строки — без схлопывания несколько
    # подряд идущих пустых строк из самой разметки шаблона.
    return re.sub(r"\n{2,}", "\n\n", text).strip()
