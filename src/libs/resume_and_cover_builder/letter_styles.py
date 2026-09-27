"""3 стиля сопроводительных писем для откликов на площадках (HH и т.п.)
— НЕ затрагивает email-рассылку (hr_replies.generate_company_email) и
Telegram-парсер (hr_replies.generate_first_message), у них свои промты.

- "memorable" (Запоминающийся, высокая конверсия) — уже существующий
  промт в plain_cover_letter_prompt(_en)/strings.py: называет слабое
  место кандидата и переосмысливает его. Смелее, но рискованнее.
- "neutral" (Нейтральный, средняя конверсия) — тот же костяк без
  признания слабого места, просто уверенное совпадение с вакансией.
- "classic" (Классический, чуть ниже средней конверсии) — привычная
  деловая структура с приветствием и вежливым завершением.
"""

from __future__ import annotations

from src.libs.resume_and_cover_builder.anti_ai_rules import (
    ANTI_AI_STRUCTURE_EN,
    ANTI_AI_STRUCTURE_RU,
)

STYLE_LABELS = {
    "memorable": "Запоминающийся (высокая конверсия на приглашения)",
    "neutral": "Нейтральный (средняя конверсия на приглашения)",
    "classic": "Классический (чуть ниже средней конверсии)",
}

_NEUTRAL_RU = (
    """
Напиши сопроводительное письмо к этой вакансии, используя моё резюме и
описание вакансии ниже — так, как реальный кандидат печатает его прямо в
текстовое поле отклика на площадке, а не оформленное деловое письмо.

Правила:
1. Начни с одного предложения, которое показывает, что ты понимаешь их
   самую важную текущую задачу в этой роли. Используй описание вакансии
   как подсказку.
2. Второй абзац: 2–3 конкретных примера из резюме, которые прямо
   соответствуют их требованиям — с цифрами, масштабом, результатом, а
   не просто перечислением навыков.
3. Заверши одной конкретной причиной, почему кандидат хочет работать
   именно в ЭТОЙ компании, а не просто в любой компании — без общей
   фразы "с нетерпением жду возможности обсудить".

Тон: уверенный, по делу, без слабых мест и оправданий.
Объём: до 200 слов, два-три коротких абзаца.

## Дополнительные правила:
- Пиши ВСЁ письмо на русском языке, независимо от того, на каком языке
  описание вакансии, резюме или что-либо ещё ниже.
- Не добавляй никаких вступлений, пояснений или другой информации, кроме
  самого письма.
- Не добавляй приветствие, подпись, дату или блок с контактами — площадка
  уже показывает имя и контакты кандидата отдельно. Начинай сразу с
  первого предложения письма.
- Только простой текст — без HTML-тегов, без Markdown, без звёздочек и
  любой другой разметки. Абзацы разделяй одной пустой строкой.
- Не используй плейсхолдеры вроде "[Название компании]".
- Избегай штампов и клише ИИ — письмо должно читаться как написанное
  живым человеком, а не типовой ИИ-текст.
"""
    + ANTI_AI_STRUCTURE_RU
    + """
## Детали:
- **Описание вакансии:**
```
{job_description}
```
- **Моё резюме:**
```
{resume}
```
"""
)

_CLASSIC_RU = (
    """
Напиши сопроводительное письмо к этой вакансии, используя моё резюме и
описание вакансии ниже — обычное деловое письмо-отклик, как принято на
российских job-площадках.

Правила:
1. Начни с приветствия ("Здравствуйте!") и одного предложения о том, на
   какую вакансию откликаешься.
2. Второй абзац: релевантный опыт и навыки из резюме, которые подходят
   под требования вакансии — с конкретикой, но без чрезмерных деталей.
3. Третий абзац: коротко, почему интересна именно эта позиция/компания.
4. Заверши вежливой фразой готовности обсудить детали на собеседовании.

Тон: вежливый, деловой, стандартная деловая переписка.
Объём: до 200 слов, три-четыре коротких абзаца.

## Дополнительные правила:
- Пиши ВСЁ письмо на русском языке, независимо от того, на каком языке
  описание вакансии, резюме или что-либо ещё ниже.
- Не добавляй подпись, дату или блок с контактами — площадка уже
  показывает имя и контакты кандидата отдельно.
- Только простой текст — без HTML-тегов, без Markdown, без звёздочек и
  любой другой разметки. Абзацы разделяй одной пустой строкой.
- Не используй плейсхолдеры вроде "[Название компании]".
- Избегай явных клише ИИ (списки ниже), но обычные вежливые деловые
  обороты ("буду рад обсудить", "спасибо за внимание к моему отклику")
  здесь допустимы — это ожидаемый тон классического письма, не ИИ-штамп.
"""
    + ANTI_AI_STRUCTURE_RU
    + """
## Детали:
- **Описание вакансии:**
```
{job_description}
```
- **Моё резюме:**
```
{resume}
```
"""
)

_NEUTRAL_EN = (
    """
Write a cover letter for this job posting, using my resume and the job
description below — the way a real candidate would type it directly into
a job board's application text box, not a formatted business letter.

Rules:
1. Start with one sentence that shows I understand their single most
   important current problem. Use the job description as the hint.
2. Second paragraph: 2-3 concrete examples from my resume that directly
   match their needs — with numbers, scale, and outcomes.
3. Close with one specific reason I want to work at THIS company
   specifically — avoid the generic "looking forward to discussing
   further."

Tone: confident, on-point, no admitted weaknesses or excuses.
Length: under 200 words, two to three short paragraphs.

## Additional rules:
- Write the ENTIRE letter in English, regardless of what language the
  job description or resume happen to be in.
- Do not include any introductions, explanations, or additional
  information outside the letter itself.
- Do not include a greeting, a signature, a date, or a contact block —
  the platform already shows the candidate's name and contacts
  separately. Start directly with the first sentence.
- Plain text only — no HTML tags, no Markdown, no asterisks or other
  markup of any kind.
- Avoid placeholders — never write things like "[Company Name]".
- Avoid AI-cliché filler phrases — the letter must read like it was
  written by a person, not generic AI output.
"""
    + ANTI_AI_STRUCTURE_EN
    + """
## Details:
- **Job Description:**
```
{job_description}
```
- **My resume:**
```
{resume}
```
"""
)

_CLASSIC_EN = (
    """
Write a cover letter for this job posting, using my resume and the job
description below — a conventional business-letter style application.

Rules:
1. Start with a greeting ("Dear Hiring Team,") and one sentence about
   which role I'm applying for.
2. Second paragraph: relevant experience and skills from my resume that
   match the role's requirements.
3. Third paragraph: briefly, why this specific role/company interests me.
4. Close with a polite line about being glad to discuss further in an
   interview.

Tone: polite, professional, standard business correspondence.
Length: under 200 words, three to four short paragraphs.

## Additional rules:
- Write the ENTIRE letter in English, regardless of what language the
  job description or resume happen to be in.
- Do not include a signature, date, or contact block — the platform
  already shows the candidate's name and contacts separately.
- Plain text only — no HTML tags, no Markdown, no asterisks or other
  markup of any kind.
- Avoid placeholders — never write things like "[Company Name]".
- Avoid obvious AI clichés (see list below), but ordinary polite
  business phrasing ("I would welcome the opportunity to discuss further"
  or "thank you for considering my application") is fine here — that is
  the expected tone of a classic letter, not an AI tell.
"""
    + ANTI_AI_STRUCTURE_EN
    + """
## Details:
- **Job Description:**
```
{job_description}
```
- **My resume:**
```
{resume}
```
"""
)

_OVERRIDES = {
    ("neutral", "ru"): _NEUTRAL_RU,
    ("classic", "ru"): _CLASSIC_RU,
    ("neutral", "en"): _NEUTRAL_EN,
    ("classic", "en"): _CLASSIC_EN,
}


def cover_letter_template_for(
    style: str, language: str, default_template: str
) -> str:
    """default_template — то, что уже загружено из strings.py (стиль
    "memorable"). Для "neutral"/"classic" возвращает альтернативный
    шаблон того же языка; неизвестный стиль — как "memorable"."""
    return _OVERRIDES.get((style, language), default_template)
