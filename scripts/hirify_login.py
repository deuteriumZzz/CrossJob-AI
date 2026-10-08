"""Один раз войти в аккаунт hirify.me в окне бота.

Запуск: venv/bin/python scripts/hirify_login.py
Откроется окно с профилем бота (`.chrome_profile_hirify`): войдите (или
зарегистрируйтесь, это бесплатно) и закройте окно. Пароль скрипт не видит и
не вводит: вход вы делаете сами. После этого бот видит контакты HR и
названия Telegram-каналов в вакансиях Hirify."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.chrome_utils import init_browser  # noqa: E402

PROFILE = Path(__file__).resolve().parent.parent / (
    "data_folder/output/.chrome_profile_hirify"
)


def main() -> None:
    driver = init_browser(PROFILE)
    driver.get("https://hirify.me/")
    print("Войдите в hirify.me в открывшемся окне и закройте его.")
    try:
        while True:
            time.sleep(2)
            driver.title  # noqa: B018 — падает, когда окно закрыли
    except Exception:
        print("Окно закрыто, вход сохранён в профиле.")


if __name__ == "__main__":
    main()
