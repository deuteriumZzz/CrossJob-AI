# Правила «писать как человек, а не нейросеть» для всего, что уходит
# работодателю: письма рассылки, сообщения HR, сопроводительные, ответы в
# чате. Выжимка скилла github.com/blader/humanizer v3 (основан на
# Wikipedia «Signs of AI writing»), адаптированная под деловые письма и
# дополненная русскими словами-маркерами.
#
# Два уровня защиты:
# 1) правила ниже вклеиваются в промты — модель сразу пишет без них;
# 2) ai_tells() ищет оставшиеся признаки в готовом тексте, и humanize()
#    отдаёт его на одну правку по тем же правилам — как в скилле:
#    отметить → переписать → проверить.
#
# Без фигурных скобок { } в правилах — они склеиваются в
# ChatPromptTemplate, где { } — плейсхолдеры.

from __future__ import annotations

import re

ANTI_AI_STRUCTURE_RU = """
Пиши как живой человек, а не нейросеть. Каждое предложение должно
сообщать что-то новое; всё, что только «звучит важно», убирай.
- Без «не просто X, а Y», «не только… но и», «это не X, это Y», «а не X»:
  говори прямо, что есть.
- Без финальных фраз-выводов, повторяющих сказанное, и без рубленых
  фрагментов («Никаких компромиссов. Только результат.»).
- Без псевдоглубоких формулировок: «суть в том», «по-настоящему важно»,
  «X это язык Y».
- Без разгона перед мыслью: «Давайте разберёмся», «Скажу честно»,
  «Позвольте представиться», «Хочу обратить ваше внимание».
- Не спорь с возражением, которого никто не высказывал («Я не утверждаю,
  что…», «Может показаться, что…»).
- Не перечисляй всё тройками, если по смыслу пунктов два или четыре.
- Не начинай подряд несколько предложений одинаково («Я… Я… Я…»).
- Не используй длинное или короткое тире как связку между частями мысли:
  ставь точку, запятую, двоеточие или перестрой предложение.
- Не громозди оговорки («возможно, в некоторой степени, вероятно»).
- Не раздувай значимость: «играет ключевую роль», «важная веха»,
  «уникальная возможность», «динамично развивающаяся компания»,
  «в современном мире», «вносить вклад в развитие».
- Слова-маркеры нейросети не используй: ключевой, уникальный,
  инновационный, передовой, синергия, страсть, увлечённость, «с большим
  интересом», «внимательно изучив», «идеально подхожу», «с нетерпением
  жду». Для английского текста: delve, crucial, pivotal, leverage, robust,
  seamless, cutting-edge, dynamic, fast-paced, passionate, excited,
  thrilled, showcase, testament, landscape, foster, underscore,
  meticulous, additionally, align with, proven track record, spearheaded.
- Без рекламного тона и чужого авторитета («эксперты считают»).
- Простые глаголы: «это», «у меня есть», «сделал» вместо «выступает в
  роли», «является», «представляет собой».
- Без жирного шрифта, заголовков, списков с метками, эмодзи и стрелок.
- Без остатков чат-бота: «Надеюсь, это поможет», «Буду рад ответить на
  любые вопросы», «Если нужно что-то ещё», «Конечно!».
- Не заканчивай абстракцией о компании или индустрии: заканчивай
  конкретным фактом или конкретной просьбой.
- Разная длина предложений: короткие чередуются с длинными.
- Только факты из резюме и данных о компании: никаких придуманных цифр,
  имён, дат и фактов. Приветствие и подпись в письме уместны.
"""

ANTI_AI_STRUCTURE_EN = """
Write like a person, not a language model. Every sentence must add
something new; cut anything that only sounds important.
- No "not X but Y", "not just/only/merely X, but Y", "it's not X, it's Y",
  "X rather than Y": state the point directly.
- No one-line closers that restate the paragraph, no dramatic fragments
  ("No compromises. Just results.").
- No deep-sounding sayings: "at its core", "what really matters", "the
  real question is", "X is the language of Y".
- No run-up before the point: "Let me introduce myself", "Here's the
  thing", "Honestly,".
- Do not argue with objections nobody raised ("I'm not saying...", "You
  might think...").
- Do not force lists into threes when the meaning has two or four items.
- Do not start several sentences in a row the same way ("I... I... I...").
- Do not use em or en dashes or a double hyphen as connectors: use a
  period, comma, colon, or rewrite the sentence.
- No stacked qualifiers ("could potentially, arguably, in some cases").
- No inflated significance: "plays a key role", "pivotal moment",
  "unique opportunity", "fast-paced environment", "evolving landscape".
- Avoid AI words: delve, crucial, pivotal, key (adjective), leverage,
  robust, seamless, cutting-edge, dynamic, passionate, excited, thrilled,
  showcase, testament, landscape, foster, underscore, meticulous,
  additionally, align with, vibrant, enhance, valuable, proven track
  record, spearheaded, synergy.
- No sales tone and no borrowed authority ("experts agree").
- Use plain verbs: "is", "has", "built" instead of "serves as",
  "stands as", "boasts".
- No bold, headings, labeled lists, emojis, or arrows.
- No chatbot leftovers: "I hope this helps", "Let me know if",
  "Feel free to", "I'd be happy to answer any questions", "Certainly!".
- Do not end on an abstract line about the company or industry; end on a
  concrete fact or a concrete ask.
- Vary sentence length: mix short and long sentences.
- Only facts from the resume and the company data: never invent numbers,
  names, dates, or claims. A greeting and a sign-off are fine in a letter.
"""

# Признаки, которые чаще всего переживают генерацию (скилл, шаг 3), —
# ищем в готовом тексте. ponytail: регулярки по словам — эвристика, как и
# сам список в скилле; ложное срабатывание стоит одной лишней правки.
_TELLS = [
    ("тире как связка", r"[—–]|\s--\s"),
    ("«не просто X, а Y»", r"\bне просто\b|\bне только\b[^.]*\bно и\b|\bnot (just|only|merely)\b|\bit'?s not\b|\brather than\b"),
    ("остатки чат-бота", r"надеюсь, это|буду рад ответить на любые|если (вам )?нужно что-то ещё|\bi hope this\b|\blet me know if\b|\bfeel free to\b|happy to answer any|\bcertainly!"),
    ("разгон перед мыслью", r"позвольте представиться|давайте разбер[её]мся|скажу честно|let me introduce myself|here'?s the thing"),
    ("раздутая значимость", r"играет (ключевую|важную) роль|уникальн\w* возможност|динамично развивающ|в современном мире|plays a (key|crucial|pivotal) role|fast-paced|evolving landscape"),
    ("слова-маркеры нейросети", r"(?<!\w)(ключев\w*|инновационн\w*|передов\w*|синерги\w*|страст\w*|увлеч[её]нн\w*|с большим интересом|внимательно изучив|идеально подхож\w*|с нетерпением)(?!\w)|\b(delve\w*|crucial|pivotal|leverag\w*|robust|seamless\w*|cutting-edge|passionate|thrilled|excited to|showcas\w*|testament|tapestry|foster\w*|underscor\w*|meticulous\w*|additionally|align with|vibrant|proven track record|spearhead\w*|synerg\w*)\b"),
    ("разметка и эмодзи", r"\*\*|^#+\s|^\s*[-•]\s+[^:\n]{1,30}:|[\U0001F300-\U0001FAFF→]"),
]


def ai_tells(text: str) -> list[str]:
    """Какие признаки текста от нейросети остались (пусто — чисто)."""
    return [name for name, pattern in _TELLS if re.search(pattern, text, re.IGNORECASE | re.MULTILINE)]


_REWRITE_PROMPT = """
Отредактируй текст ниже, чтобы он звучал как написанный человеком.
Найденные признаки текста от нейросети: {tells}.

Правила:
{rules}

Сохрани смысл, все факты, имена, цифры, обращение и подпись. Не добавляй
ничего, чего нет в тексте. Язык и объём как в исходнике. Верни только
итоговый текст, без пояснений.

Текст:
{text}
"""


def humanize(text: str, llm_api_key: str) -> str:
    """Одна правка по правилам скилла, если в тексте остались признаки.
    Без признаков или при ошибке ИИ возвращает текст как есть."""
    tells = ai_tells(text)
    if not tells or not text.strip():
        return text
    try:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate

        from src.job_sources.llm_provider import get_chat_llm

        russian = len(re.findall(r"[а-яё]", text, re.IGNORECASE)) > len(text) * 0.3
        chain = (
            ChatPromptTemplate.from_template(_REWRITE_PROMPT)
            | get_chat_llm(llm_api_key, temperature=0.3)
            | StrOutputParser()
        )
        rewritten = chain.invoke({
            "tells": ", ".join(tells),
            "rules": ANTI_AI_STRUCTURE_RU if russian else ANTI_AI_STRUCTURE_EN,
            "text": text,
        }).strip()
    except Exception as e:
        from src.logging import logger

        logger.warning(f"Правка «как человек» не удалась, оставляю текст как есть: {e}")
        return text
    # Пустой ответ или текст раздуло больше чем в полтора раза — не рискуем.
    if not rewritten or len(rewritten) > len(text) * 1.6:
        return text
    return rewritten
