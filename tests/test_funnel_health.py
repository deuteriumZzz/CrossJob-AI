"""Самоконтроль площадок: если поиск много прогонов подряд находит 0
вакансий (вёрстка/парсинг сломались), или отклики идут, но ни один не
подтверждается (кнопка отклика сломалась), — один алерт вместо тихого
молчания в логах."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import main


def _params(tmp_path: Path, source: str = "headhunter", auto_apply=True):
    return {
        "outputFileDirectory": tmp_path,
        source: {"auto_apply": auto_apply},
    }


def test_zero_found_streak_alerts_once_at_threshold():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = _params(Path(tmp))
        with patch("main.notify") as mock_notify:
            for _ in range(main.FUNNEL_ZERO_FOUND_THRESHOLD - 1):
                main._update_funnel_health(
                    parameters, "headhunter", found=0, applied=0, dry_run=0
                )
            mock_notify.assert_not_called()
            main._update_funnel_health(
                parameters, "headhunter", found=0, applied=0, dry_run=0
            )
            mock_notify.assert_called_once()
            # Ещё один прогон с 0 — второй раз не спамит.
            main._update_funnel_health(
                parameters, "headhunter", found=0, applied=0, dry_run=0
            )
            mock_notify.assert_called_once()


def test_zero_found_streak_resets_on_recovery():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = _params(Path(tmp))
        with patch("main.notify") as mock_notify:
            for _ in range(main.FUNNEL_ZERO_FOUND_THRESHOLD):
                main._update_funnel_health(
                    parameters, "headhunter", found=0, applied=0, dry_run=0
                )
            mock_notify.assert_called_once()
            main._update_funnel_health(
                parameters, "headhunter", found=5, applied=1, dry_run=0
            )
            for _ in range(main.FUNNEL_ZERO_FOUND_THRESHOLD - 1):
                main._update_funnel_health(
                    parameters, "headhunter", found=0, applied=0, dry_run=0
                )
            # Стрик начался заново — второй алерт ещё не должен уйти.
            assert mock_notify.call_count == 1


def test_stuck_streak_alerts_when_dry_run_but_never_applied():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = _params(Path(tmp))
        with patch("main.notify") as mock_notify:
            for _ in range(main.FUNNEL_STUCK_THRESHOLD):
                main._update_funnel_health(
                    parameters, "headhunter", found=10, applied=0, dry_run=3
                )
            mock_notify.assert_called_once()
            assert "прогонов подряд" in mock_notify.call_args[0][1]


def test_no_stuck_alert_when_auto_apply_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        parameters = _params(Path(tmp), auto_apply=False)
        with patch("main.notify") as mock_notify:
            for _ in range(main.FUNNEL_STUCK_THRESHOLD + 2):
                main._update_funnel_health(
                    parameters, "headhunter", found=10, applied=0, dry_run=3
                )
            mock_notify.assert_not_called()


def test_no_stuck_alert_when_low_fit_explains_zero_applied():
    """found>0, applied=0, dry_run=0 (все skipped_low_fit) — это не
    поломка, это нормальный фильтр по score, алерта быть не должно."""
    with tempfile.TemporaryDirectory() as tmp:
        parameters = _params(Path(tmp))
        with patch("main.notify") as mock_notify:
            for _ in range(main.FUNNEL_STUCK_THRESHOLD + 2):
                main._update_funnel_health(
                    parameters, "headhunter", found=10, applied=0, dry_run=0
                )
            mock_notify.assert_not_called()
