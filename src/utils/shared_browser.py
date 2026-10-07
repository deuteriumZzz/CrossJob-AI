"""Один общий Chrome на все обычные (Selenium) площадки.

Раньше каждая площадка открывала и закрывала свой максимизированный
Chrome — при параллельной работе за компьютером окно постоянно лезло
на передний план. Теперь `init_browser(profile_dir)` отдаёт не новый
браузер, а вкладку в одном общем (свёрнутом), а `.quit()` вкладки её
просто закрывает. Остальной код площадок не меняется.

ponytail: все площадки делят один профиль (SHARED_PROFILE_NAME) — логин
на каждой нужно пройти один раз заново. Вызовы разных потоков
сериализует RLock на каждый вызов, но элементы (WebElement) идут мимо
прокси — полноценной параллельной работы двух потоков в браузере нет,
как и не было нужды (прогон площадок идёт по очереди)."""

import atexit
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from src.logging import logger

# Профиль HH взят как общий намеренно: логин и "доверие" hh.ru к
# браузеру сохраняются, перелогиниваться придётся на остальных.
SHARED_PROFILE_NAME = ".chrome_profile_headhunter"
IDLE_CLOSE_SECONDS = 15 * 60

_lock = threading.RLock()
_driver: Any = None
_busy: set = set()
_idle_timer: Optional[threading.Timer] = None
_visible = False


def _alive(driver) -> bool:
    try:
        _ = driver.window_handles
        return True
    except Exception:
        return False


def _hide(driver) -> None:
    try:
        driver.minimize_window()
    except Exception as e:
        logger.debug(f"Could not minimize the shared browser: {e}")


def _hide_unless_visible(driver) -> None:
    """Chrome разворачивает окно при создании/переключении вкладки —
    сворачиваем снова, если оно не показано специально (ручной вход)."""
    if not _visible:
        _hide(driver)


_extra_windows: list = []


def hide_extra_window(driver):
    """Отдельные браузеры (undetected-chromedriver: LinkedIn, Himalayas,
    Avito) тоже сворачиваем сразу после запуска и запоминаем — для ручного
    входа reveal_shared_browser() разворачивает и их. Возвращает driver."""
    _hide(driver)
    _extra_windows.append(driver)
    return driver


def _shutdown() -> None:
    global _driver, _visible
    with _lock:
        driver, _driver = _driver, None
        _busy.clear()
        _visible = False
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass


def _close_if_idle() -> None:
    with _lock:
        if _busy:
            return
    _shutdown()


def _schedule_idle_close() -> None:
    global _idle_timer
    if _idle_timer is not None:
        _idle_timer.cancel()
    _idle_timer = threading.Timer(IDLE_CLOSE_SECONDS, _close_if_idle)
    _idle_timer.daemon = True
    _idle_timer.start()


atexit.register(_shutdown)


def reveal_shared_browser() -> None:
    """Показывает свёрнутое окно — для ручного входа/капчи. Снова
    сворачивается, когда вкладка, которая его просила, закроется."""
    global _visible
    with _lock:
        for extra in list(_extra_windows):
            try:
                extra.maximize_window()
            except Exception:
                _extra_windows.remove(extra)  # окно уже закрыто
        if _driver is None:
            return
        try:
            _driver.maximize_window()
            _visible = True
        except Exception as e:
            logger.debug(f"Could not reveal the shared browser: {e}")


class SharedTab:
    """Драйверо-подобная обёртка вокруг одной вкладки общего Chrome:
    каждый вызов сначала переключается на свою вкладку."""

    def __init__(self, driver, handle: str):
        object.__setattr__(self, "_real", driver)
        object.__setattr__(self, "_handle", handle)

    def _focus(self) -> None:
        if self._real.current_window_handle != self._handle:
            self._real.switch_to.window(self._handle)
            _hide_unless_visible(self._real)

    def __getattr__(self, name: str):
        with _lock:
            self._focus()
            attr = getattr(self._real, name)
        if not callable(attr):
            return attr

        def call(*args, **kwargs):
            with _lock:
                self._focus()
                return attr(*args, **kwargs)

        return call

    def __setattr__(self, name: str, value) -> None:
        setattr(self._real, name, value)

    def quit(self) -> None:
        global _visible
        with _lock:
            if self._real is not _driver:
                return  # браузер уже пересоздан/закрыт
            try:
                _busy.discard(self._handle)
                if len(_driver.window_handles) > 1:
                    self._focus()
                    _driver.close()
                    _driver.switch_to.window(_driver.window_handles[0])
                    _hide_unless_visible(_driver)
                else:
                    # последнюю вкладку не закрываем — иначе умрёт окно
                    # и между площадками браузер будет открываться заново
                    _driver.get("about:blank")
                if _visible and not _busy:
                    _visible = False
                    _hide(_driver)
            except Exception as e:
                logger.debug(f"Shared tab close failed: {e}")
            _schedule_idle_close()


def open_tab(profile_dir: Path, launch: Callable[[Path], Any]) -> SharedTab:
    """launch(path) — создаёт настоящий Chrome (chrome_utils). Общий
    профиль лежит рядом с профилями площадок."""
    global _driver
    with _lock:
        if _driver is None or not _alive(_driver):
            _driver = launch(profile_dir.parent / SHARED_PROFILE_NAME)
            _busy.clear()
            _hide(_driver)
            logger.info("Общий браузер запущен (свёрнут).")
        free = [h for h in _driver.window_handles if h not in _busy]
        if free:
            handle = free[0]
        else:
            _driver.switch_to.new_window("tab")
            handle = _driver.current_window_handle
            _hide_unless_visible(_driver)
        _busy.add(handle)
        return SharedTab(_driver, handle)
