from src.libs.resume_and_cover_builder.cover_letter_prompt import (
    strings as _base_strings,
)

summarize_prompt_template = _base_strings.summarize_prompt_template

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
cover_letter_template = """
Compose a brief, natural cover letter for a job application response field
on a job board — written exactly the way a real candidate would type it
directly into a plain text box, not a formatted business letter. The
letter should be no longer than three short paragraphs and should read
naturally, tailored to the job.

Analyze the job description to identify key qualifications and requirements.
Open with a specific, concrete achievement or result from the resume that
maps directly onto the role's top requirement — not a generic "I am writing
to express my interest" line, since a recruiter skims dozens of these and a
strong opener is what gets a letter actually read instead of skipped.
Highlight relevant skills and experiences from the resume that directly
match the job's demands, using specific examples (numbers, scale, outcomes)
to illustrate these qualifications rather than restating skills as a list.
The middle of the letter MUST also make an explicit, separate case for why
THIS company should pick THIS candidate over another applicant with a
similar resume — do not simply restate the achievements again in different
words. Name a concrete working trait (e.g. how you approach debugging,
how you collaborate with a team, how you handle ambiguous requirements) or
a genuine, specific reason this particular company/role stands out to the
candidate — something a bare skills match cannot show on its own.
Conclude with a short, direct call to action inviting the employer to
schedule an interview or a call — state the request plainly rather than a
vague "looking forward to discussing further."

## Rules:
- Write the ENTIRE letter in Russian, regardless of what language the job
  description, the resume, or your own analysis above happen to be in —
  the candidate is applying on a Russian-language job board and always
  writes to employers in Russian there.
- Do not include any introductions, explanations, or additional
  information outside the letter itself.
- Do not include a greeting ("Здравствуйте", "Уважаемые коллеги" and the
  like), a signature, a date, or a name/address/contact block — the
  platform already shows the candidate's name and contact details
  separately; the letter box is only for the message body. Start
  directly with the first sentence of the letter.
- Plain text only — no HTML tags, no Markdown, no asterisks or other
  markup of any kind. Separate paragraphs with a single blank line, like
  a person typing directly into a text box would.
- Avoid placeholders — never write things like "[Название компании]".
- Avoid AI-cliché filler phrases and transitions — the letter must read
  like one of the genuinely well-written human cover letters found
  online, not like generic AI output. Specifically avoid: "хотел(а) бы
  выразить свою заинтересованность", "буду рад(а) обсудить", "уверен(а),
  что смогу", "эффективно решать задачи", "внести вклад в развитие
  компании", "динамично развивающаяся компания", "командный игрок",
  "стрессоустойчив(а)", "с нетерпением жду возможности", "хотелось бы
  отметить", "в связи с тем что", "на постоянной основе" — and any other
  stock phrase from a generic template. Every sentence should sound like
  it was written by someone who actually did the work being described,
  not assembled from résumé boilerplate.
- The letter must be strong enough on its own that an HR person reading
  it immediately gets curious about this specific candidate — sharp,
  concrete, a little unexpected, not just competent and forgettable.

## Details :
- **Job Description:**
```
{job_description}
```
- **My resume:**
```
{resume}
```
"""
