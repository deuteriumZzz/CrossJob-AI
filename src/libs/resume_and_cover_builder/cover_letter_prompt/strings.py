from src.libs.resume_and_cover_builder.anti_ai_rules import \
    ANTI_AI_STRUCTURE_EN
from src.libs.resume_and_cover_builder.template_base import \
    prompt_cover_letter_template

cover_letter_template = (
    """
Write a cover letter for this role. Rules:
1. First paragraph: name the company and the role. Mention one specific
   thing about the company that made me want to apply — a recent product
   launch, a news item, or a company value I genuinely connect with. Do
   NOT write generic phrases.
2. Second paragraph: pick 2-3 requirements from the job description that
   my experience matches best. For each, give one concrete result from my
   resume — with numbers.
3. Third paragraph: directly name the single biggest gap between my
   resume and the job description. Explain how my transferable skills or
   adjacent experience close it. Do not pretend the gap doesn't exist.
4. Closing: one sentence. Ask for an interview. No filler. Do not use the
   phrase "I would welcome the opportunity to discuss".

Total length: under 250 words.
Tone: confident, specific, human.

## Rules:
- Do not include any introductions, explanations, or additional information.
- Write the entire letter in the SAME language as the Job Description
  below. Detect that language from the job description text itself —
  ignore what language the resume happens to be written in. A
  Russian-language job posting must get a Russian-language letter
  even if the resume below is in English, and vice versa.
"""
    + ANTI_AI_STRUCTURE_EN
    + """
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
    + prompt_cover_letter_template
)


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
Write your entire analysis in the SAME language as the job description
below — do not translate it into English or any other language.
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
