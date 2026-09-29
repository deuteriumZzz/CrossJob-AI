from src.job_sources.avito.mapping import parse_search_html


def _card(
    item_id,
    href,
    title,
    price="",
    location="",
    specific_params="",
    description="",
    company="",
    has_resume_apply=True,
):
    """Форма карточки поиска, подтверждённая вживую 2026-09-29 на
    avito.ru/all/vakansii — data-marker атрибуты стабильны (Avito сам
    использует их для своих e2e-тестов), классы вокруг — CSS-modules
    хэши, меняющиеся от сборки к сборке."""
    apply_marker = (
        "<p>Отклик с резюме</p>" if has_resume_apply else "<p>Написать</p>"
    )
    company_html = (
        f'<div class="userInfoStep-abc123">'
        f'<a href="/c/{company}">{company}</a></div>'
        if company
        else ""
    )
    price_html = f'<span data-marker="item-price-value">{price}</span>'
    return f"""
    <div data-marker="item" data-item-id="{item_id}">
      <a data-marker="item-title" href="{href}">{title}</a>
      <p data-marker="item-price">{price_html}</p>
      {apply_marker}
      <p data-marker="item-specific-params">{specific_params}</p>
      <div data-marker="item-location">{location}</div>
      <p>{description}</p>
      {company_html}
    </div>
    """


def test_parse_search_html_extracts_resume_apply_vacancy():
    html = _card(
        "8323526383",
        "/rezh/vakansii/rabota_programmist_8323526383",
        "Работа программист",
        price="80 000 — 100 000 ₽",
        location="Свердловская обл., Реж",
        specific_params="Фиксированный график · Опыт более года",
        description=(
            "Обязательно посещение и работа в офисе предприятия. "
            "Введение на предприятии в работу программы."
        ),
        company="ИПК Лазурь",
    )
    jobs = parse_search_html(html)
    assert len(jobs) == 1
    job = jobs[0]
    assert job.external_id == "8323526383"
    assert job.role == "Работа программист"
    assert job.company == "ИПК Лазурь"
    assert job.location == "Свердловская обл., Реж"
    assert job.salary == "80 000 — 100 000 ₽"
    assert job.link == (
        "https://www.avito.ru/rezh/vakansii/rabota_programmist_8323526383"
    )
    assert job.source == "avito"
    assert job.apply_method == "avito_resume_apply"
    assert "Обязательно посещение" in job.description


def test_parse_search_html_includes_chat_only_vacancies_too():
    """Метка "Отклик с резюме" в списке нестабильна/редка (подтверждено
    вживую), а кнопка "Откликнуться" почти всегда есть на самой
    странице вакансии независимо от неё — парсер больше не отбрасывает
    карточки без этой метки, решение остаётся за apply.py на
    детальной странице."""
    html = _card(
        "111",
        "/moskva/vakansii/repetitor_111",
        "Репетитор по математике",
        has_resume_apply=False,
    )
    jobs = parse_search_html(html)
    assert len(jobs) == 1
    assert jobs[0].role == "Репетитор по математике"


def test_parse_search_html_dedupes_repeated_ids():
    html = _card("222", "/spb/vakansii/dev_222", "Backend Developer")
    jobs = parse_search_html(html + html)
    assert len(jobs) == 1


def test_parse_search_html_skips_items_without_id_or_link():
    jobs = parse_search_html(
        '<div data-marker="item"><p>Отклик с резюме</p></div>'
    )
    assert jobs == []
