"""geekjob.apply() раньше только кликало "Откликнуться" и оставляло
geekjob подставлять его дефолтный quick-apply (шаблон "Меня
заинтересовала вакансия..., резюме по ссылке...", БЕЗ письма) —
сгенерированный cover_letter никуда не передавался (см. main.py
search_geekjob). Теперь после клика ищем textarea, чистим её (поле
приходит с этим самым дефолтным шаблоном, уже заполненным — без
clear() письмо дописывалось бы после шаблона, а не вместо него,
подтверждено вживую) и вписываем письмо перед "Отправить"."""

from unittest.mock import MagicMock, patch

import pytest

from src.job_sources.geekjob.client import GeekjobClient


def test_apply_fills_textarea_when_present():
    with patch(
        "src.job_sources.geekjob.client.init_browser"
    ) as mock_init, patch(
        "src.job_sources.geekjob.client.raise_if_blocked"
    ), patch(
        "src.job_sources.geekjob.client.visible_text", return_value=""
    ), patch(
        "src.job_sources.geekjob.client.time.sleep"
    ):
        driver = mock_init.return_value
        respond_button = MagicMock()
        textarea = MagicMock()
        submit_button = MagicMock()

        def find_elements(by, value):
            if "Откликнуться" in value:
                return [respond_button]
            if "Отправить" in value:
                return [submit_button]
            return [textarea]  # By.TAG_NAME, "textarea"

        driver.find_elements.side_effect = find_elements

        client = GeekjobClient(profile_dir="profile")
        applied = client.apply(
            "https://geekjob.ru/vacancy/abc", "profile", "Здравствуйте!"
        )

        assert applied is True
        respond_button.click.assert_called_once()
        textarea.clear.assert_called_once()
        textarea.send_keys.assert_called_once_with("Здравствуйте!")
        submit_button.click.assert_called_once()


def test_apply_refuses_to_submit_without_letter_field():
    with patch(
        "src.job_sources.geekjob.client.init_browser"
    ) as mock_init, patch(
        "src.job_sources.geekjob.client.raise_if_blocked"
    ), patch(
        "src.job_sources.geekjob.client.visible_text", return_value=""
    ), patch(
        "src.job_sources.geekjob.client.time.sleep"
    ):
        driver = mock_init.return_value
        respond_button = MagicMock()

        def find_elements(by, value):
            if "Откликнуться" in value:
                return [respond_button]
            return []  # no textarea, no submit button

        driver.find_elements.side_effect = find_elements

        client = GeekjobClient(profile_dir="profile")
        # Поля письма нет — отклик НЕ отправляется (иначе уйдёт шаблон).
        with pytest.raises(RuntimeError, match="поле сопроводительного"):
            client.apply(
                "https://geekjob.ru/vacancy/abc", "profile", "Здравствуйте!"
            )

        respond_button.click.assert_not_called()
