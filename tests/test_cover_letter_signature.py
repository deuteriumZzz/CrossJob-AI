from src.job_sources.cover_letter import strip_signature


def test_strips_invented_sign_off_and_name():
    letter = "Первый абзац.\n\nГотов обсудить.  \n\nС уважением, Иван Иванов."
    assert strip_signature(letter) == "Первый абзац.\n\nГотов обсудить."


def test_strips_english_sign_off_on_separate_lines():
    assert strip_signature("Hello.\n\nBest regards,\nJohn") == "Hello."


def test_keeps_letter_without_sign_off():
    letter = (
        "С уважением к вашему продукту я хочу в команду.\n\nГотов к интервью."
    )
    assert strip_signature(letter) == letter
