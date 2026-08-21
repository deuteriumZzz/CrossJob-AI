import main


def test_daily_limit_falls_back_to_config_default():
    assert main._daily_limit({}) == main.DAILY_APPLICATION_LIMIT


def test_daily_limit_uses_override_from_work_preferences():
    parameters = {"limits": {"daily_application_limit": 40}}
    assert main._daily_limit(parameters) == 40


def test_linkedin_daily_limit_falls_back_to_config_default():
    assert (
        main._linkedin_daily_limit({}) == main.LINKEDIN_DAILY_APPLICATION_LIMIT
    )


def test_linkedin_daily_limit_uses_override():
    parameters = {"limits": {"linkedin_daily_application_limit": 20}}
    assert main._linkedin_daily_limit(parameters) == 20


def test_job_max_applications_falls_back_to_config_default():
    assert main._job_max_applications({}) == main.JOB_MAX_APPLICATIONS


def test_job_max_applications_uses_override():
    parameters = {"limits": {"job_max_applications": 12}}
    assert main._job_max_applications(parameters) == 12


def test_limits_block_missing_entirely_does_not_error():
    parameters = {"limits": None}
    assert main._daily_limit(parameters) == main.DAILY_APPLICATION_LIMIT
    assert main._job_max_applications(parameters) == main.JOB_MAX_APPLICATIONS


def test_job_max_applications_per_source_override_wins_over_global():
    parameters = {
        "limits": {"job_max_applications": 5},
        "headhunter": {"job_max_applications": 15},
    }
    assert main._job_max_applications(parameters, "headhunter") == 15
    # другая площадка без своего override — берёт общий дефолт
    assert main._job_max_applications(parameters, "superjob") == 5


def test_job_max_applications_per_source_falls_back_without_override():
    parameters = {
        "limits": {"job_max_applications": 7},
        "headhunter": {"auto_apply": True},
    }
    assert main._job_max_applications(parameters, "headhunter") == 7


def test_job_max_applications_per_source_falls_back_to_config_default():
    parameters = {"headhunter": {"auto_apply": True}}
    assert (
        main._job_max_applications(parameters, "headhunter")
        == main.JOB_MAX_APPLICATIONS
    )


def test_job_max_applications_no_source_uses_global_only():
    parameters = {"headhunter": {"job_max_applications": 99}}
    # без указания source override конкретной площадки не должен
    # применяться — это поведение "общего" вызова
    assert main._job_max_applications(parameters) == main.JOB_MAX_APPLICATIONS


def test_daily_limit_per_source_override_wins_over_global():
    parameters = {
        "limits": {"daily_application_limit": 15},
        "headhunter": {"daily_application_limit": 40},
    }
    assert main._daily_limit(parameters, "headhunter") == 40
    assert main._daily_limit(parameters, "superjob") == 15


def test_daily_limit_per_source_falls_back_to_config_default():
    parameters = {"headhunter": {"auto_apply": True}}
    assert (
        main._daily_limit(parameters, "headhunter")
        == main.DAILY_APPLICATION_LIMIT
    )


def test_linkedin_daily_limit_still_uses_own_default_via_daily_limit():
    parameters = {}
    assert (
        main._daily_limit(parameters, "linkedin")
        == main.LINKEDIN_DAILY_APPLICATION_LIMIT
    )


def test_linkedin_daily_limit_per_source_override():
    parameters = {"linkedin": {"daily_application_limit": 3}}
    assert main._daily_limit(parameters, "linkedin") == 3
    # обёртка тоже видит override, раз делегирует в _daily_limit
    assert main._linkedin_daily_limit(parameters) == 3


def test_linkedin_daily_limit_wrapper_matches_daily_limit_with_source():
    parameters = {"limits": {"linkedin_daily_application_limit": 11}}
    assert main._linkedin_daily_limit(parameters) == main._daily_limit(
        parameters, "linkedin"
    )
