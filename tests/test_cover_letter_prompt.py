from src.libs.resume_and_cover_builder.cover_letter_prompt.strings import (
    cover_letter_template,
)


def test_cover_letter_prompt_instructs_matching_job_language():
    """Резюме и вакансия могут быть на разных языках (например резюме
    на английском, вакансия на hh.ru на русском) — без явной
    инструкции LLM может ориентироваться на язык резюме и написать
    письмо не на том языке, на котором работодатель ждёт отклик."""
    assert "{job_description}" in cover_letter_template
    assert "{resume}" in cover_letter_template
    assert "SAME language as the Job Description" in cover_letter_template


def test_cover_letter_prompt_renders_without_error():
    rendered = cover_letter_template.format(
        job_description="Ищем Python-разработчика.", resume="Опыт: 5 лет."
    )
    assert "Ищем Python-разработчика." in rendered
    assert "Опыт: 5 лет." in rendered


if __name__ == "__main__":
    test_cover_letter_prompt_instructs_matching_job_language()
    test_cover_letter_prompt_renders_without_error()
    print("All tests passed.")
