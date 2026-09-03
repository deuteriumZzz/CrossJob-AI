from src.libs.resume_and_cover_builder.anti_ai_rules import \
    ANTI_AI_STRUCTURE_RU

# Не наследуем summarize_prompt_template из cover_letter_prompt — там
# явно "Write your entire analysis in the SAME language as the job
# description" (нужно для auto_plain/html, где язык определяется по
# вакансии). Для ru_plain это конфликтовало с cover_letter_template
# ниже: summary уходил на языке вакансии, а письмо потом просили
# писать по-русски поверх него — язык мог поплыть (тот же класс
# бага, что и в plain_cover_letter_prompt_en/strings.py).
summarize_prompt_template = """
As a seasoned HR expert, your task is to identify and outline the key skills
and requirements necessary for the position of this job. Use the provided job
description as input to extract all relevant information. This will involve
conducting a thorough analysis of the job's responsibilities and the industry
standards. You should consider both the technical and soft skills needed to
excel in this role. Additionally, specify any educational qualifications,
certifications, or experiences that are essential. Your analysis should also
reflect on the evolving nature of this role, considering future trends and how
they might affect the required competencies.

Rules:
Remove boilerplate text
Include only relevant information to match the job description against the
resume
Write your entire analysis in Russian, regardless of what language the job
description below happens to be in — the candidate applies to a
Russian-language job board and this analysis feeds directly into a
Russian-only cover letter. Company and job-title names themselves stay
exactly as written (do not translate proper names) — only the surrounding
analysis text must be Russian.
Start your analysis with a line "Company: <exact company name>" and a line
"Role: <exact job title>", copied verbatim from the job description as
written — never invent, translate, or normalize either.

# Analysis Requirements
Your analysis should include the following sections:
Technical Skills: List all the specific technical skills required for the role
based on the responsibilities described in the job description.
Soft Skills: Identify the necessary soft skills, such as communication
abilities, problem-solving, time management, etc.
Educational Qualifications and Certifications: Specify the essential
educational qualifications and certifications for the role.
Professional Experience: Describe the relevant work experiences that are
required or preferred.
Role Evolution: Analyze how the role might evolve in the future, considering
industry trends and how these might influence the required skills.

# Final Result:
Your analysis should be structured in a clear and organized document with
distinct sections for each of the points listed above. Each section should
contain:
This comprehensive overview will serve as a guideline for the recruitment
process, ensuring the identification of the most qualified candidates.

# Job Description:
```
{text}
```

---

# Job Description Summary"""

# ponytail: отдельный от cover_letter_prompt/strings.py шаблон — тот
# добавляет к письму HTML-"бланк" (prompt_cover_letter_template из
# template_base.py: адрес/телефон, "Dear [Recipient Team]",
# "Sincerely" и т.п.), нужный только для PDF-версии письма
# (дашборд, resume_facade.py — там реально нужен оформленный
# документ-бланк). Для отклика через обычное поле <textarea> на
# HH/GetMatch и т.п. такой бланк не нужен и выглядит неестественно
# (подтверждено живым прогоном — сгенерированное письмо содержало
# буквально "Dear Hiring Team" и вымышленное название компании из
# примера в бланке вместо реального текста) — здесь просто обычный
# текст, как будто его напечатал сам кандидат в поле отклика.
# Содержание письма (структура из 4 пунктов) — пользовательский промпт
# "Сопроводительное письмо — версия сайта"; правила про plain text/
# отсутствие HTML-тегов и подписи сохранены из прежней версии — тот же
# баг с протекающей разметкой актуален для любого текста в этом шаблоне,
# не только для прежнего.
cover_letter_template = (
    """
Напиши сопроводительное письмо к этой вакансии, используя моё резюме и
описание вакансии ниже — так, как реальный кандидат печатает его прямо в
текстовое поле отклика на площадке, а не оформленное деловое письмо.

Правила:
1. Начни с одного предложения, которое показывает, что ты понимаешь их
   самую важную текущую проблему. Используй описание вакансии как
   подсказку.
2. Второй абзац: 2–3 конкретных примера из резюме, которые прямо
   соответствуют их потребностям — с цифрами, масштабом, результатом, а
   не просто перечислением навыков.
3. Третий абзац: прямо назови один очевидный пробел или слабое место
   кандидата относительно вакансии и покажи его с другой стороны — не
   делай вид, что пробела нет.
4. Заверши одной конкретной причиной, почему кандидат хочет работать
   именно в ЭТОЙ компании, а не просто в любой компании — без общей
   фразы "с нетерпением жду возможности обсудить".

Тон: уверенный, прямой, без воды и модных слов.
Объём: до 250 слов, не больше трёх коротких абзацев.

## Дополнительные правила:
- Пиши ВСЁ письмо на русском языке, независимо от того, на каком языке
  описание вакансии, резюме или что-либо ещё ниже — кандидат откликается
  на русскоязычной площадке и всегда пишет работодателям по-русски.
- Не добавляй никаких вступлений, пояснений или другой информации, кроме
  самого письма.
- Не добавляй приветствие ("Здравствуйте", "Уважаемые коллеги" и
  подобное), подпись, дату или блок с контактами — площадка уже
  показывает имя и контакты кандидата отдельно; поле письма — только для
  текста самого сообщения. Начинай сразу с первого предложения письма.
- Только простой текст — без HTML-тегов, без Markdown, без звёздочек и
  любой другой разметки. Абзацы разделяй одной пустой строкой, как
  человек, печатающий прямо в текстовое поле.
- Не используй плейсхолдеры вроде "[Название компании]".
- Избегай штампов и клише ИИ — письмо должно читаться как один из
  по-настоящему хорошо написанных живым человеком примеров, а не как
  типовой ИИ-текст. В частности избегай: "хотел(а) бы выразить свою
  заинтересованность", "буду рад(а) обсудить", "уверен(а), что смогу",
  "эффективно решать задачи", "внести вклад в развитие компании",
  "динамично развивающаяся компания", "командный игрок",
  "стрессоустойчив(а)", "с нетерпением жду возможности", "хотелось бы
  отметить", "в связи с тем что", "на постоянной основе" — и любые
  другие шаблонные фразы. Каждое предложение должно звучать так, будто
  его написал человек, который реально делал то, что описывает, а не
  собрал из резюме-клише.
- Письмо должно быть достаточно сильным само по себе, чтобы у HR сразу
  возник интерес именно к этому кандидату — конкретное, немного
  неожиданное, не просто компетентное и легко забываемое.
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
