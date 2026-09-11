from unittest.mock import MagicMock, patch

from src.job_sources.linkedin.dynamic_form import (
    TEXT_INPUT_SELECTOR,
    ScrapedField,
    _closest_option,
    _field_max_length,
    _FieldAnswer,
    _fill_text_field,
    _group_label,
    _label_text_for,
    _radio_label,
    _text_like_inputs,
    apply_answers,
    check_required_consent_checkboxes,
    scrape_visible_fields,
)


def test_closest_option_exact_match_case_insensitive():
    assert _closest_option("Yes", ["Yes", "No"]) == "Yes"
    assert _closest_option("yes", ["Yes", "No"]) == "Yes"


def test_closest_option_partial_match():
    assert (
        _closest_option("3-5 years", ["0-2 years", "3-5 years", "6+ years"])
        == "3-5 years"
    )


def test_closest_option_falls_back_to_first_option():
    assert (
        _closest_option(
            "something completely unrelated", ["Option A", "Option B"]
        )
        == "Option A"
    )


def test_field_max_length_reads_maxlength_attribute():
    field = MagicMock()
    field.get_attribute.return_value = "20"
    assert _field_max_length(field) == 20


def test_field_max_length_none_when_attribute_missing():
    field = MagicMock()
    field.get_attribute.return_value = None
    assert _field_max_length(field) is None


def test_field_max_length_none_when_attribute_not_numeric():
    field = MagicMock()
    field.get_attribute.return_value = ""
    assert _field_max_length(field) is None


def test_label_text_for_uses_label_element():
    driver = MagicMock()
    field = MagicMock()
    field.get_attribute.side_effect = lambda name: {"id": "loc"}.get(name)
    label = MagicMock()
    label.text = "Location (city)*"
    driver.find_elements.return_value = [label]
    assert _label_text_for(driver, field) == "Location (city)"


def test_label_text_for_falls_back_to_placeholder():
    driver = MagicMock()
    field = MagicMock()
    field.get_attribute.side_effect = lambda name: {
        "placeholder": "Enter city or location"
    }.get(name)
    driver.find_elements.return_value = []
    assert _label_text_for(driver, field) == "Enter city or location"


def test_radio_label_prefers_aria_labelledby_over_aria_label():
    """aria-label на самом [role='radio'] иногда возвращает текст
    ВОПРОСА, не варианта ответа (подтверждено живьём 2026-09-09) —
    aria-labelledby (ссылка на элемент с текстом варианта) должен
    браться первым, когда есть."""
    option_span = MagicMock()
    option_span.text = "Yes"

    driver = MagicMock()
    driver.find_element.return_value = option_span

    radio = MagicMock()
    radio.get_attribute.side_effect = lambda name: {
        "aria-labelledby": "option-1",
        "aria-label": "Are you comfortable working remotely?",
    }.get(name)

    assert _radio_label(driver, radio) == "Yes"


def test_radio_label_falls_back_to_aria_label_without_labelledby():
    driver = MagicMock()
    radio = MagicMock()
    radio.get_attribute.side_effect = lambda name: {
        "aria-label": "Yes"
    }.get(name)

    assert _radio_label(driver, radio) == "Yes"


def test_fill_text_field_selects_autocomplete_suggestion_if_present():
    """"Location (city)" и подобные поля — автокомплит: LinkedIn считает
    поле невалидным, пока не выбран вариант из выпадающего списка, даже
    если текст уже напечатан (подтверждено живьём 2026-09-09)."""
    field = MagicMock()
    field.get_attribute.side_effect = lambda name: {
        "aria-controls": "loc-listbox"
    }.get(name)

    option = MagicMock()
    option.is_displayed.return_value = True

    driver = MagicMock()
    driver.find_elements.return_value = [option]

    with patch("src.job_sources.linkedin.dynamic_form.time.sleep"):
        _fill_text_field(driver, field, "Bali, Indonesia")

    field.send_keys.assert_called_once_with("Bali, Indonesia")
    driver.execute_script.assert_called_once()


def test_text_like_inputs_includes_untyped_input_excludes_checkbox():
    """<input> без атрибута type — браузер считает его текстовым по
    умолчанию, но старый allowlist (type='text'/'tel'/...) такое поле
    не находил вообще (подтверждено живьём 2026-09-10: "Location
    (city)" оставалось невидимым, scrape_visible_fields находил 0
    полей на шаге, форма зависала на "stuck"). Denylist должен
    находить untyped-поле и по-прежнему игнорировать чекбоксы."""
    untyped = MagicMock()
    untyped.tag_name = "input"
    untyped.get_attribute.return_value = None

    checkbox = MagicMock()
    checkbox.tag_name = "input"
    checkbox.get_attribute.return_value = "checkbox"

    textarea = MagicMock()
    textarea.tag_name = "textarea"

    container = MagicMock()
    container.find_elements.return_value = [untyped, checkbox, textarea]

    result = _text_like_inputs(container)

    assert untyped in result
    assert textarea in result
    assert checkbox not in result


def _make_group(radios=None, checkboxes=None, text_inputs=None):
    group = MagicMock()

    def fake_find_elements(by, selector):
        if selector == "[role='radio']":
            return radios or []
        if selector == "input[type='checkbox']":
            return checkboxes or []
        if selector == TEXT_INPUT_SELECTOR:
            return text_inputs or []
        return []

    group.find_elements.side_effect = fake_find_elements
    return group


def test_scrape_visible_fields_skips_step_title_paragraphs():
    """LinkedIn кладёт заголовок шага ("Additional Questions" и т.п.)
    достаточно близко к первому реальному вопросу, что его родитель
    тоже "видит" поле рядом — без фильтра заголовок дублировал
    реальный вопрос как отдельный (подтверждено живьём 2026-09-09)."""
    title_p = MagicMock()
    title_p.text = "Additional Questions"

    question_p = MagicMock()
    question_p.text = "Are you comfortable working remotely?*"

    radio = MagicMock()
    radio.get_attribute.side_effect = lambda name: {
        "aria-label": "Yes"
    }.get(name)

    group = _make_group(radios=[radio])
    question_p.find_element.return_value = group

    form = MagicMock()

    def fake_form_find_elements(by, selector):
        if selector == "p":
            return [title_p, question_p]
        return []  # no uncovered required text fields

    form.find_elements.side_effect = fake_form_find_elements

    driver = MagicMock()
    fields = scrape_visible_fields(driver, form)

    assert len(fields) == 1
    assert fields[0].text == "Are you comfortable working remotely?"
    assert fields[0].kind == "radio"
    assert fields[0].options == ["Yes"]


def test_scrape_visible_fields_drops_radio_when_all_labels_match_question():
    """Если aria-labelledby тоже подвёл и оба радио всё равно отдают
    текст вопроса — поле не должно попасть в результат вообще (LLM не
    получит мусорные options), а не крашить весь прогон, как раньше
    (подтверждено живьём 2026-09-09: оба радио в паре Yes/No отдавали
    один и тот же текст, совпадающий с вопросом)."""
    question_p = MagicMock()
    question_p.text = "Are you comfortable working remotely?*"

    radio = MagicMock()
    radio.get_attribute.side_effect = lambda name: {
        "aria-label": "Are you comfortable working remotely?"
    }.get(name)

    group = _make_group(radios=[radio, radio])
    question_p.find_element.return_value = group

    form = MagicMock()
    form.find_elements.side_effect = (
        lambda by, selector: [question_p] if selector == "p" else []
    )

    driver = MagicMock()
    assert scrape_visible_fields(driver, form) == []


def test_group_label_prefers_aria_label_over_ambiguous_paragraph():
    """Ближайший <p> у select-полей иногда оказывается заголовком
    СЕКЦИИ ("Preguntas adicionales"), не текстом конкретного вопроса —
    подтверждено живьём 2026-09-11: несколько разных select про
    уровень владения разными языками все отдавали один и тот же текст
    секции, бот не мог их различить. aria-label на самом поле должен
    побеждать такой фолбэк."""
    element = MagicMock()
    element.get_attribute.side_effect = lambda name: {
        "aria-label": "¿Cuál es tu dominio del idioma inglés?"
    }.get(name)

    driver = MagicMock()
    assert (
        _group_label(driver, element, fallback="Preguntas adicionales")
        == "¿Cuál es tu dominio del idioma inglés?"
    )


def test_group_label_falls_back_to_paragraph_when_no_accessible_name():
    element = MagicMock()
    element.get_attribute.return_value = None

    driver = MagicMock()
    driver.find_elements.return_value = []  # no <label for=...>

    assert _group_label(driver, element, fallback="Email") == "Email"


def test_scrape_visible_fields_detects_select_question():
    question_p = MagicMock()
    question_p.text = "Email*"

    option1 = MagicMock()
    option1.text = "me@example.com"
    select_el = MagicMock()
    select_el.get_attribute.return_value = None  # no aria-labelledby/-label

    group = MagicMock()

    def fake_find_elements(by, selector):
        return [select_el] if selector == "select" else []

    group.find_elements.side_effect = fake_find_elements
    question_p.find_element.return_value = group

    form = MagicMock()
    form.find_elements.side_effect = (
        lambda by, selector: [question_p] if selector == "p" else []
    )

    driver = MagicMock()
    driver.find_elements.return_value = []  # no <label for=...> either
    with patch(
        "src.job_sources.linkedin.dynamic_form.Select"
    ) as fake_select_cls:
        fake_select = MagicMock()
        fake_select.options = [option1]
        fake_select_cls.return_value = fake_select

        fields = scrape_visible_fields(driver, form)

    assert len(fields) == 1
    assert fields[0].kind == "select"
    assert fields[0].options == ["me@example.com"]


def _location_field():
    field = MagicMock()
    field.id = "loc-field-1"
    field.is_displayed.return_value = True
    field.get_attribute.side_effect = lambda name: {
        "value": "",
        "required": "",
        "placeholder": "Enter city or location",
    }.get(name)
    return field


def test_scrape_visible_fields_finds_uncovered_required_text_field():
    """"Location (city)" — обязательное текстовое поле БЕЗ своего <p>,
    текст вопроса лежит в placeholder/label (см. _label_text_for)."""
    form = MagicMock()
    form.find_elements.side_effect = lambda by, selector: (
        [] if selector == "p" else [_location_field()]
    )

    driver = MagicMock()
    driver.find_elements.return_value = []  # no <label for=...>

    fields = scrape_visible_fields(driver, form)

    assert len(fields) == 1
    assert fields[0].kind == "text"
    assert fields[0].text == "Enter city or location"


def test_check_required_consent_checkboxes_clicks_unchecked_required():
    """"I agree to be contacted"-style чекбоксы часто идут без <p> —
    scrape_visible_fields их не видит вообще, LinkedIn не пускал
    дальше по валидации (подтверждено по логам демона 2026-09-09: 3 из
    3 реальных вакансий в одном заходе упёрлись в "stuck (no
    Next/Submit)" без единого краша)."""
    required_unchecked = MagicMock()
    required_unchecked.is_displayed.return_value = True
    required_unchecked.is_selected.return_value = False
    required_unchecked.get_attribute.side_effect = lambda name: {
        "required": ""
    }.get(name)

    already_checked = MagicMock()
    already_checked.is_displayed.return_value = True
    already_checked.is_selected.return_value = True

    optional = MagicMock()
    optional.is_displayed.return_value = True
    optional.is_selected.return_value = False
    optional.get_attribute.return_value = None

    form = MagicMock()
    form.find_elements.return_value = [
        required_unchecked,
        already_checked,
        optional,
    ]

    driver = MagicMock()
    check_required_consent_checkboxes(driver, form)

    driver.execute_script.assert_called_once_with(
        "arguments[0].click();", required_unchecked
    )


def test_apply_answers_fills_text_field():
    field_el = MagicMock()
    field = ScrapedField(0, "Years of experience?", "text", [], field_el)
    answer = _FieldAnswer(index=0, text_answer="5")

    driver = MagicMock()
    with patch(
        "src.job_sources.linkedin.dynamic_form._fill_text_field"
    ) as fake_fill:
        apply_answers(driver, [field], {0: answer})

    fake_fill.assert_called_once_with(driver, field_el, "5")


def test_apply_answers_clicks_matching_radio():
    radio_yes = MagicMock()
    radio_no = MagicMock()
    group = _make_group(radios=[radio_yes, radio_no])

    field = ScrapedField(0, "Remote ok?", "radio", ["Yes", "No"], group)
    answer = _FieldAnswer(index=0, selected_option="Yes")

    driver = MagicMock()
    with patch(
        "src.job_sources.linkedin.dynamic_form._radio_label",
        side_effect=["Yes", "No"],
    ):
        apply_answers(driver, [field], {0: answer})

    driver.execute_script.assert_called_once_with(
        "arguments[0].click();", radio_yes
    )


def test_apply_answers_skips_field_with_no_answer():
    field_el = MagicMock()
    field = ScrapedField(0, "Years of experience?", "text", [], field_el)

    driver = MagicMock()
    with patch(
        "src.job_sources.linkedin.dynamic_form._fill_text_field"
    ) as fake_fill:
        apply_answers(driver, [field], {})

    fake_fill.assert_not_called()


if __name__ == "__main__":
    test_text_like_inputs_includes_untyped_input_excludes_checkbox()
    test_closest_option_exact_match_case_insensitive()
    test_closest_option_partial_match()
    test_closest_option_falls_back_to_first_option()
    test_field_max_length_reads_maxlength_attribute()
    test_field_max_length_none_when_attribute_missing()
    test_field_max_length_none_when_attribute_not_numeric()
    test_label_text_for_uses_label_element()
    test_label_text_for_falls_back_to_placeholder()
    test_radio_label_prefers_aria_labelledby_over_aria_label()
    test_radio_label_falls_back_to_aria_label_without_labelledby()
    test_fill_text_field_selects_autocomplete_suggestion_if_present()
    test_scrape_visible_fields_skips_step_title_paragraphs()
    test_scrape_visible_fields_drops_radio_when_all_labels_match_question()
    test_group_label_prefers_aria_label_over_ambiguous_paragraph()
    test_group_label_falls_back_to_paragraph_when_no_accessible_name()
    test_scrape_visible_fields_detects_select_question()
    test_scrape_visible_fields_finds_uncovered_required_text_field()
    test_check_required_consent_checkboxes_clicks_unchecked_required()
    test_apply_answers_fills_text_field()
    test_apply_answers_clicks_matching_radio()
    test_apply_answers_skips_field_with_no_answer()
    print("All tests passed.")
