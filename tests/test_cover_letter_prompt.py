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


def test_letter_style_override_renders_and_falls_back_to_memorable():
    from src.libs.resume_and_cover_builder.letter_styles import (
        cover_letter_template_for,
    )

    default_template = "memorable default {job_description} {resume}"

    # memorable — не подменяется, возвращается как есть.
    assert (
        cover_letter_template_for("memorable", "ru", default_template)
        == default_template
    )
    # Неизвестный стиль — тоже безопасный fallback на дефолтный шаблон.
    assert (
        cover_letter_template_for("bogus", "ru", default_template)
        == default_template
    )

    for style in ("neutral", "classic"):
        for language in ("ru", "en"):
            template = cover_letter_template_for(
                style, language, default_template
            )
            assert template != default_template
            rendered = template.format(
                job_description="Ищем Python-разработчика.",
                resume="Опыт: 5 лет.",
            )
            assert "Ищем Python-разработчика." in rendered
            assert "Опыт: 5 лет." in rendered


def test_cover_letter_style_setter_validates_and_defaults():
    from src.job_sources import cover_letter as cl

    cl.set_cover_letter_style("neutral")
    assert cl._cover_letter_style == "neutral"
    cl.set_cover_letter_style("not-a-real-style")
    assert cl._cover_letter_style == "memorable"


if __name__ == "__main__":
    test_cover_letter_prompt_instructs_matching_job_language()
    test_cover_letter_prompt_renders_without_error()
    print("All tests passed.")
