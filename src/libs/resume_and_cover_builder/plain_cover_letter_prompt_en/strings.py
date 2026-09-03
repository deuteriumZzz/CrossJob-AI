from src.libs.resume_and_cover_builder.anti_ai_rules import \
    ANTI_AI_STRUCTURE_EN

# Не наследуем summarize_prompt_template из cover_letter_prompt — там
# явно "Write your entire analysis in the SAME language as the job
# description" (нужно для auto_plain/html, где язык определяется по
# вакансии). Для en_plain это конфликтовало с cover_letter_template
# ниже: summary уходил на языке вакансии, а письмо потом просили
# писать по-английски поверх него — язык мог поплыть.
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
Write your entire analysis in English, regardless of what language the job
description below happens to be in — the candidate applies to
English-language job boards and this analysis feeds directly into an
English-only cover letter. Company and job-title names themselves stay
exactly as written (do not translate proper names) — only the surrounding
analysis text must be English.
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

# English counterpart of plain_cover_letter_prompt/strings.py — used for
# wellfound.com/himalayas.app, which take a plain <textarea>/log entry,
# not a rendered PDF like LinkedIn (cover_letter_prompt). Kept as a
# separate template rather than force_russian=False + strip-HTML-after
# so the LLM never writes the HTML letterhead in the first place — the
# plain-text/no-markup rule below is what prevents that leak, keep it
# whenever this template's content changes.
cover_letter_template = (
    """
Write a cover letter for this job posting, using my resume and the job
description below — the way a real candidate would type it directly into
a job board's application text box, not a formatted business letter.

Rules:
1. Start with one sentence that shows I understand their single most
   important current problem. Use the job description as the hint.
2. Second paragraph: 2-3 concrete examples from my resume that directly
   match their needs — with numbers, scale, and outcomes, not just a
   list of skills.
3. Third paragraph: directly name one obvious gap or weak point relative
   to this job and reframe it — do not pretend the gap doesn't exist.
4. Close with one specific reason I want to work at THIS company
   specifically, not just any company — avoid the generic "looking
   forward to discussing further."

Tone: confident, direct, no filler, no buzzwords.
Length: under 250 words, no more than three short paragraphs.

## Additional rules:
- Write the ENTIRE letter in English, regardless of what language the
  job description, the resume, or anything else below happens to be in —
  the candidate is applying on an English-language job board and always
  writes to employers in English there.
- Do not include any introductions, explanations, or additional
  information outside the letter itself.
- Do not include a greeting ("Dear Hiring Team" and the like), a
  signature, a date, or a name/address/contact block — the platform
  already shows the candidate's name and contact details separately; the
  letter box is only for the message body. Start directly with the first
  sentence of the letter.
- Plain text only — no HTML tags, no Markdown, no asterisks or other
  markup of any kind. Separate paragraphs with a single blank line, like
  a person typing directly into a text box would.
- Avoid placeholders — never write things like "[Company Name]".
- Avoid AI-cliché filler phrases and transitions — the letter must read
  like one of the genuinely well-written human cover letters found
  online, not like generic AI output. Specifically avoid: "I am excited
  to apply", "I would welcome the opportunity", "I am confident that I
  can", "effectively tackle challenges", "contribute to the growth of the
  company", "fast-paced environment", "team player", "detail-oriented",
  "I look forward to the possibility", "I wanted to reach out", "on an
  ongoing basis" — and any other stock phrase from a generic template.
  Every sentence should sound like it was written by someone who actually
  did the work being described, not assembled from résumé boilerplate.
- The letter must be strong enough on its own that an HR person reading
  it immediately gets curious about this specific candidate — sharp,
  concrete, a little unexpected, not just competent and forgettable.
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
