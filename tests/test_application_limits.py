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
