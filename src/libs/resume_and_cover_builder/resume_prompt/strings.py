from src.libs.resume_and_cover_builder.anti_ai_rules import ANTI_AI_STRUCTURE_EN
from src.libs.resume_and_cover_builder.template_base import (
    prompt_achievements_template,
    prompt_additional_skills_template,
    prompt_certifications_template,
    prompt_core_strengths_template,
    prompt_education_template,
    prompt_header_template,
    prompt_projects_template,
    prompt_summary_template,
    prompt_working_experience_template,
)

prompt_header = (
    """
Act as an HR expert and resume writer specializing in ATS-friendly resumes.
Your task is to create a professional and polished header for the resume. The
header should:

1. **Contact Information**: Include your full name, city and country, phone
number, email address, LinkedIn profile, and GitHub profile. Exclude any
information that is not provided.
2. **Formatting**: Ensure the contact details are presented clearly and are
easy to read.
3. **Target Job Title**: Directly below the name, a short professional title
line describing the role the candidate is positioning themselves for. Use the
hint below if it is given (polish the wording if needed); otherwise infer the
single most fitting title from the information provided.

- **My information:**
  {personal_information}

- **Likely target role (hint, may be empty):**
  {target_role_hint}
"""
    + prompt_header_template
)


prompt_summary = (
    """
Act as an HR expert and resume writer specializing in ATS-friendly resumes.
Your task is to write a concise professional summary (2-4 sentences) that:

1. Opens with years of experience and core professional identity.
2. Highlights the strongest, most quantifiable achievements or areas of
expertise from the data below.
3. Uses natural, keyword-rich language that mirrors common terminology for
this field — no jargon-stuffing, it must read naturally.
4. Avoids generic filler ("hard-working team player") — every sentence must
carry real information from the data below, never invented.

- **My information:**
  {personal_information}
  {experience_details}
"""
    + prompt_summary_template
)


prompt_core_strengths = (
    """
Act as an HR expert and resume writer specializing in ATS-friendly resumes.
Your task is to extract 6-10 short core-strength keywords/phrases (2-4 words
each) that best represent the candidate's expertise — the kind of terms an
ATS keyword match or a recruiter skimming the page would look for. Pull them
from the work experience and education below, not generic buzzwords, and
never invent a skill that isn't supported by the data.

- **My information:**
  {experience_details}
  {education_details}
"""
    + prompt_core_strengths_template
)


prompt_education = (
    """
Act as an HR expert and resume writer with a specialization in creating
ATS-friendly resumes. Your task is to articulate the educational background for
a resume. For each educational entry, ensure you include:

1. **Institution Name and Location**: Specify the university or educational
institution’s name and location.
2. **Degree and Field of Study**: Clearly indicate the degree earned and the
field of study.
3. **Grade**: Include your Grade if it is strong and relevant.
4. **Relevant Coursework**: List key courses with their grades to showcase your
academic strengths.

- **My information:**
  {education_details}
"""
    + prompt_education_template
)


prompt_working_experience = (
    """
Act as an HR expert and resume writer with a specialization in creating
ATS-friendly resumes. Your task is to detail the work experience for a resume.
For each job entry, ensure you include:

1. **Company Name and Location**: Provide the name of the company and its
location.
2. **Job Title**: Clearly state your job title.
3. **Dates of Employment**: Include the start and end dates of your employment.
4. **Responsibilities and Achievements**: Describe your key responsibilities
and notable achievements as individual bullet points, following ALL of these
rules:
   - Use the Google XYZ formula for each bullet: "Achieved [X], as measured
     by [Y], by doing [Z]".
   - Start every bullet with a strong action verb. Never use "Responsible
     for" or "Helped with".
   - Add specific numbers wherever the source data supports it (scale,
     percentage, team size, time saved, revenue, etc).
   - Each bullet is at most 1-2 lines — hiring managers skim, dense
     paragraphs get skipped.
   - Order bullets within each job by the strength of the result, not by
     chronology — the single most impressive result comes first.
   - Every bullet must be grounded in the work experience details actually
     provided below — never invent responsibilities, achievements, numbers,
     or years of experience that aren't supported by that data.

- **My information:**
  {experience_details}
"""
    + ANTI_AI_STRUCTURE_EN
    + prompt_working_experience_template
)


prompt_projects = (
    """
Act as an HR expert and resume writer with a specialization in creating
ATS-friendly resumes. Your task is to highlight notable side projects. For each
project, ensure you include:

1. **Project Name and Link**: Provide the name of the project and include a
link to the GitHub repository or project page.
2. **Project Details**: Describe any notable recognition or achievements
related to the project, such as GitHub stars or community feedback.
3. **Technical Contributions**: Highlight your specific contributions and the
technologies used in the project.

- **My information:**
  {projects}
"""
    + prompt_projects_template
)


prompt_achievements = (
    """
Act as an HR expert and resume writer with a specialization in creating
ATS-friendly resumes. Your task is to list significant achievements. For each
achievement, ensure you include:

1. **Award or Recognition**: Clearly state the name of the award, recognition,
scholarship, or honor.
2. **Description**: Provide a brief description of the achievement and its
relevance to your career or academic journey.

- **My information:**
  {achievements}
"""
    + prompt_achievements_template
)


prompt_certifications = (
    """
Act as an HR expert and resume writer with a specialization in creating
ATS-friendly resumes. Your task is to list significant certifications based on
the provided details. For each certification, ensure you include:

1. **Certification Name**: Clearly state the name of the certification.
2. **Description**: Provide a brief description of the certification and its
relevance to your professional or academic career.

Ensure that the certifications are clearly presented and effectively highlight
your qualifications.

To implement this:

If any of the certification details (e.g., descriptions) are not provided
(i.e., None), omit those sections when filling out the template.

- **My information:**
  {certifications}

"""
    + prompt_certifications_template
)


prompt_additional_skills = (
    """
Act as an HR expert and resume writer with a specialization in creating
ATS-friendly resumes. Your task is to list additional skills relevant to the
job. For each skill, ensure you include:

1. **Skill Category**: Clearly state the category or type of skill.
2. **Specific Skills**: List the specific skills or technologies within each
category.
3. **Proficiency and Experience**: Briefly describe your experience and
proficiency level.

- **My information:**
  {languages}
  {interests}
  {skills}
"""
    + prompt_additional_skills_template
)
