# Общий блок структурных анти-ИИ правил (см. github.com/blader/humanizer —
# чек-лист "Signs of AI writing"), подключаемый во все промты писем/чата
# вместо копирования вручную в каждый strings.py. Существующие в каждом
# шаблоне списки клише-слов ("хотел бы выразить заинтересованность" /
# "I am excited to apply" и т.п.) уже ловили лексику; здесь — паттерны
# формы, которые проявились в реальных письмах из applied_log.json
# (тире как связка мысли и "не просто X, а Y" — в первом же предложении
# письма для MAGNIT TECH; шаблонная абстрактная концовка — в письмах для
# Совкомбанка и MAGNIT TECH), а не только словарь.
#
# Без фигурных скобок { } — оба текста склеиваются в шаблоны, которые
# потом идут в ChatPromptTemplate.from_template() и парсят { } как
# плейсхолдеры.

ANTI_AI_STRUCTURE_RU = """
- Не используй тире (—) как связку между частями мысли внутри
  предложения — замени точкой, запятой, двоеточием или перепиши
  предложение без тире.
- Не используй конструкцию "не просто X, а Y" и её варианты.
- Не заканчивай текст абстрактным обобщением о компании или индустрии
  (например "где цена ошибки высока", "где технологии двигают индустрию
  вперёд") — заканчивай на конкретном факте или конкретной причине.
- Не собирай перечисления ровно в три пункта, если естественнее подходит
  два или четыре.
"""

ANTI_AI_STRUCTURE_EN = """
- Do not use an em dash or en dash (—, –) as a connector between clauses
  inside a sentence — replace it with a period, comma, colon, or rewrite
  the sentence without it.
- Do not use the "not just X, but Y" construction or its variants.
- Do not end the text on an abstract generalization about the company
  or industry (e.g. "where the cost of failure is high", "where
  technology drives the industry forward") — end on a concrete fact or
  reason instead.
- Do not force lists into exactly three items when two or four reads
  more naturally.
"""
