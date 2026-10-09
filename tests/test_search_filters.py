from src.job_sources.filters import (
    FILTER_SUPPORT,
    linkedin_search_params,
    remote_only,
    work_formats,
)


def test_work_formats_come_from_common_toggles():
    assert work_formats({"remote": True, "hybrid": False}) == ["remote"]
    assert work_formats({"remote": True, "onsite": True}) == [
        "remote",
        "onsite",
    ]


def test_common_formats_drive_every_platform():
    remote = {"remote": True, "hybrid": False, "onsite": False}
    for source in ("getmatch", "habr_career", "avito"):
        assert remote_only(remote, source) is True
        # свой флаг площадки не перебивает общий выбор
        assert (
            remote_only({**remote, source: {"remote_only": False}}, source)
            is True
        )
        assert remote_only({**remote, "hybrid": True}, source) is False


def test_platform_remote_only_used_only_when_no_common_format():
    assert remote_only({"getmatch": {"remote_only": True}}, "getmatch") is True
    assert remote_only({}, "avito") is False


def test_linkedin_without_chosen_format_does_not_restrict_it():
    params = linkedin_search_params({})
    assert params == {"f_AL": "true"}  # без sortBy=DD — по релевантности


def test_linkedin_follows_common_formats():
    assert (
        linkedin_search_params({"remote": True, "hybrid": True})["f_WT"]
        == "2,3"
    )
    assert linkedin_search_params({"onsite": True})["f_WT"] == "1"


def test_every_platform_is_described():
    for source in (
        "headhunter",
        "linkedin",
        "getmatch",
        "habr_career",
        "avito",
        "talanto",
    ):
        assert source in FILTER_SUPPORT


def test_djinni_employment_only_for_a_single_format():
    from src.job_sources.djinni.search import search_params
    from src.job_sources.filters import djinni_employment

    assert djinni_employment({"remote": True}) == "remote"
    assert djinni_employment({"onsite": True}) == "office"
    assert djinni_employment({"remote": True, "onsite": True}) is None
    assert djinni_employment({}) is None
    assert (
        search_params("Python Developer", 1, {"remote": True})["employment"]
        == "remote"
    )
    assert "employment" not in search_params("Python Developer", 1)


def test_talanto_formats_use_site_names():
    from src.job_sources.filters import talanto_work_formats

    assert talanto_work_formats({"remote": True, "onsite": True}) == [
        "remote",
        "office",
    ]


def test_levels_are_translated_for_each_platform():
    from src.job_sources.filters import (
        getmatch_seniority,
        habr_qualifications,
        hh_experience,
        levels,
        linkedin_search_params,
        talanto_levels,
    )

    prefs = {"levels": ["junior", "middle", "bogus"]}
    assert levels(prefs) == ["junior", "middle"]
    assert hh_experience(prefs) == [
        "noExperience",
        "between1And3",
        "between3And6",
    ]
    assert getmatch_seniority(prefs) == ["junior", "middle"]
    assert talanto_levels(prefs) == ["junior", "mid"]
    assert habr_qualifications(prefs) == ["junior", "middle"]
    assert linkedin_search_params(prefs)["f_E"] == "2,3,4"


def test_no_levels_means_no_level_filters():
    from src.job_sources.filters import (
        getmatch_seniority,
        hh_experience,
        linkedin_search_params,
    )

    assert hh_experience({}) == []
    assert getmatch_seniority({}) == []
    assert "f_E" not in linkedin_search_params({})


def test_remote_only_platforms_skipped_for_office_seekers():
    from src.job_sources.filters import skip_remote_only_platform

    assert skip_remote_only_platform({"onsite": True})
    assert skip_remote_only_platform({"onsite": True, "hybrid": True})
    assert not skip_remote_only_platform({"remote": True, "onsite": True})
    assert not skip_remote_only_platform({})


def test_employment_and_period_adapters():
    from src.job_sources.filters import (
        hh_employment,
        posted_within_days,
        single_employment,
    )

    prefs = {
        "employment_types": ["part", "internship"],
        "posted_within_days": 7,
    }
    assert hh_employment(prefs) == (["PART"], True)
    assert single_employment(prefs) == "part_time"
    assert single_employment({"employment_types": ["full", "part"]}) is None
    assert posted_within_days({"posted_within_days": 5}) == 0
    params = linkedin_search_params(
        {"employment_types": ["full", "project"], "posted_within_days": 1}
    )
    assert params["f_JT"] == "C,F" and params["f_TPR"] == "r86400"
    assert "f_JT" not in linkedin_search_params({})


def test_getmatch_and_avito_office_hybrid_adapters():
    from src.job_sources.filters import (
        avito_click_format,
        getmatch_locations,
        getmatch_period,
    )

    assert getmatch_locations({}) == []
    assert getmatch_locations({"remote": True}) == ["remote"]
    office = getmatch_locations({"onsite": True})
    assert "remote" not in office and "moscow" in office
    # удалённо + офис/гибрид = все пять пунктов сайта = без фильтра
    assert getmatch_locations({"remote": True, "hybrid": True}) == []
    assert getmatch_locations({"hybrid": True, "onsite": True}) == office
    assert getmatch_period({"posted_within_days": 3}) == "3d"
    assert avito_click_format({"onsite": True}) == "office"
    assert avito_click_format({"hybrid": True}) == "hybrid"
    assert avito_click_format({"onsite": True, "hybrid": True}) == ""


def test_talanto_extra_query_has_types_period_salary():
    from src.job_sources.filters import talanto_extra_query

    assert talanto_extra_query({}) == ""
    query = talanto_extra_query(
        {
            "employment_types": ["full", "internship"],
            "posted_within_days": 3,
            "only_with_salary": True,
        }
    )
    assert "&work_types=full" in query and "&work_types=intern" in query
    assert "&period=three_days" in query and "salary_min=1" in query


def test_himalayas_query():
    from src.job_sources.filters import himalayas_query

    assert himalayas_query({}) == ""
    query = himalayas_query(
        {
            "employment_types": ["full", "internship"],
            "levels": ["junior", "senior"],
            "only_with_salary": True,
        }
    )
    assert query == (
        "&type=full-time,intern&experience=entry-level,senior"
        "&salary-required=true"
    )


def test_djinni_parttime_only_when_format_free():
    from src.job_sources.filters import djinni_employment

    part = {"employment_types": ["part"]}
    assert djinni_employment(part) == "parttime"
    assert djinni_employment({**part, "remote": True}) == "remote"
    assert djinni_employment({}) is None


def test_period_filter_by_vacancy_date_for_djinni_and_habr():
    import json
    from datetime import datetime, timedelta

    from src.job_sources.djinni.search import parse_jobs
    from src.job_sources.filters import posted_too_old
    from src.job_sources.habr_career.mapping import parse_search_dates

    prefs = {"posted_within_days": 3}
    fresh = (datetime.now() - timedelta(days=1)).isoformat()
    old = (datetime.now() - timedelta(days=9)).isoformat()
    assert not posted_too_old(fresh, prefs)
    assert posted_too_old(old, prefs)
    assert not posted_too_old("", prefs)  # дата неизвестна — не отсекаем
    assert not posted_too_old(old, {})  # период не выбран

    def ld(i, date):
        item = {
            "@type": "JobPosting",
            "url": f"https://djinni.co/jobs/{i}-x/",
            "title": "Dev",
            "identifier": i,
            "datePosted": date,
        }
        return (
            '<script type="application/ld+json">'
            f"{json.dumps(item)}</script>"
        )

    html = ld(1, fresh) + ld(2, old)
    jobs = parse_jobs(html, preferences=prefs)
    assert [j.external_id for j in jobs] == ["1"]
    assert len(parse_jobs(html)) == 2

    card = (
        '<div class="vacancy-card"><a class="vacancy-card__backdrop-link" '
        'href="/vacancies/42"></a>'
        '<time datetime="2026-10-07T17:43:25+03:00">7 октября</time></div>'
    )
    assert parse_search_dates(card) == {"42": "2026-10-07T17:43:25+03:00"}


def test_ru_date_and_geekjob_card_date():
    from datetime import date

    from src.job_sources.filters import parse_ru_date
    from src.job_sources.geekjob.mapping import parse_search_results

    today = date(2026, 10, 7)
    assert parse_ru_date("5 октября", today) == "2026-10-05"
    assert parse_ru_date("24 декабря", today) == "2025-12-24"
    assert parse_ru_date("вчера", today) == "2026-10-06"
    assert parse_ru_date("что-то", today) == ""
    html = (
        '<li class="collection-item"><p class="vacancy-name">'
        '<a class="title" href="/vacancy/abc">Dev</a></p>'
        '<p class="datetime-info">24 сентября</p></li>'
    )
    item = parse_search_results(html)[0]
    assert item["id"] == "abc" and item["posted_at"].endswith("-09-24")
