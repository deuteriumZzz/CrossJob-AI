from src.scheduler import _idle_interval_hours

GAP = 3 / 60


def test_idle_streak_does_not_slow_the_platform_down():
    """9.10: «пусто → реже заглядываем» отключено — бот идёт дальше и
    сканирует, а не ждёт часами."""
    for streak in (0, 1, 2, 3, 10):
        assert _idle_interval_hours(GAP, streak) == GAP
