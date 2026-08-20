from src.job_sources.apply_pacing import randomized_daily_limit


def test_randomized_daily_limit_stays_within_bounds():
    for _ in range(200):
        result = randomized_daily_limit(15)
        assert 10 <= result <= 15


def test_randomized_daily_limit_never_goes_below_one():
    for _ in range(200):
        assert randomized_daily_limit(1) >= 1


if __name__ == "__main__":
    test_randomized_daily_limit_stays_within_bounds()
    test_randomized_daily_limit_never_goes_below_one()
    print("All tests passed.")
