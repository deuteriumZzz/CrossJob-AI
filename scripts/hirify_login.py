"""Один раз войти в аккаунт hirify.me в окне бота.

Запуск: venv/bin/python scripts/hirify_login.py
Откроется окно браузера бота на hirify.me: войдите (или зарегистрируйтесь,
это бесплатно). Пароль скрипт не видит и не вводит. Скрипт завершится,
когда вы закроете вкладку hirify или создадите файл /tmp/hirify_login_done
(так его завершает ассистент после вашего «вошёл»). Вход сохраняется в
профиле браузера бота: после этого бот видит контакты HR и названия
Telegram-каналов в вакансиях Hirify."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.chrome_utils import init_browser  # noqa: E402
from src.utils.shared_browser import reveal_shared_browser  # noqa: E402

PROFILE = Path(__file__).resolve().parent.parent / (
    "data_folder/output/.chrome_profile_hirify"
)
DONE_FILE = Path("/tmp/hirify_login_done")
MAX_WAIT_SECONDS = 15 * 60


def main() -> None:
    DONE_FILE.unlink(missing_ok=True)
    driver = init_browser(PROFILE)
    driver.get("https://hirify.me/")
    reveal_shared_browser()
    print("Войдите в hirify.me в открывшемся окне.", flush=True)
    waited = 0
    while waited < MAX_WAIT_SECONDS and not DONE_FILE.exists():
        time.sleep(2)
        waited += 2
        try:
            driver.title  # noqa: B018 — падает, когда вкладку закрыли
        except Exception:
            break
    print("Готово, вход сохранён в профиле.", flush=True)


if __name__ == "__main__":
    main()
