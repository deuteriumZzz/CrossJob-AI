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


def test_linkedin_defaults_keep_previous_hardcoded_behaviour():
    params = linkedin_search_params({})
    assert params == {"f_AL": "true", "f_WT": "2", "sortBy": "DD"}


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
