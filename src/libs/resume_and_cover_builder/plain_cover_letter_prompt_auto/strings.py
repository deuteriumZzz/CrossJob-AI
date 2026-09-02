from src.libs.resume_and_cover_builder.cover_letter_prompt import (
    strings as _base_strings,
)

summarize_prompt_template = _base_strings.summarize_prompt_template

# Plain-text counterpart of cover_letter_prompt/strings.py — used for
# LinkedIn's Easy Apply flow (see main.search_and_apply_linkedin),
# which has no PDF-attachment field for a cover letter at all: the
# letter is only stored in applied_log for the dashboard viewer. The
# HTML letterhead template (cover_letter_prompt, "Dear [Recipient
# Team]", "[Your Name]", <div style="..."> wrapper) was never meant
# for that — it showed up as literal tags/unfilled placeholders in the
# dashboard. Unlike plain_cover_letter_prompt(_en), language here is
# still auto-detected from the job description rather than forced,
# since LinkedIn postings aren't reliably in one language.
cover_letter_template = """
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

## Rules:
- Write the ENTIRE letter in the SAME language as the Job Description
  below. Detect that language from the job description text itself —
  ignore what language the resume happens to be written in. A
  Russian-language job posting must get a Russian-language letter even if
  the resume below is in English, and vice versa.
- Do not include any introductions, explanations, or additional
  information outside the letter itself.
- Do not include a greeting ("Dear Hiring Team" and the like), a
  signature, a date, or a name/address/contact block — this is a plain
  text field, not a formatted letter; the letter box is only for the
  message body. Start directly with the first sentence of the letter.
- Plain text only — no HTML tags, no Markdown, no asterisks or other
  markup of any kind. Separate paragraphs with a single blank line, like
  a person typing directly into a text box would.
- Avoid placeholders — never write things like "[Company Name]".
- Avoid AI-cliché filler phrases and transitions in whichever language
  you write in — the letter must read like one of the genuinely
  well-written human cover letters found online, not like generic AI
  output (e.g. avoid the equivalents of "I am excited to apply", "I would
  welcome the opportunity", "fast-paced environment", "team player",
  "хотел(а) бы выразить свою заинтересованность", "командный игрок", and
  any other stock phrase from a generic template). Every sentence should
  sound like it was written by someone who actually did the work being
  described, not assembled from résumé boilerplate.
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
