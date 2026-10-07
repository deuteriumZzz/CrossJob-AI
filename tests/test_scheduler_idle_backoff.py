from src.scheduler import _idle_interval_hours

GAP = 3 / 60


def test_idle_backoff_grows_then_resets():
    assert _idle_interval_hours(GAP, 0) == GAP
    assert _idle_interval_hours(GAP, 1) == GAP  # один пустой ход — не страшно
    assert _idle_interval_hours(GAP, 2) == 0.25
    assert _idle_interval_hours(GAP, 3) == 0.5
    assert _idle_interval_hours(GAP, 10) == 1.0
