import os
import shutil
import time
import urllib
from pathlib import Path
from typing import Callable, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

from src.logging import logger


def clear_stale_chrome_lock(profile_dir: Path, force: bool = False) -> None:
    """Chrome пишет SingletonLock/-Cookie/-Socket в папку профиля на
    время своей работы; если процесс убили/он упал (сеть моргнула,
    OOM, форс-килл), эти файлы остаются висеть и указывают на мёртвый
    PID. Следующий запуск с тем же --user-data-dir тогда молча не
    может достучаться до Chrome ("session not created: chrome not
    reachable") вместо того, чтобы просто стартовать — живой Chrome
    создаёт эти файлы заново сам, удалять их для него не проблема.

    force=True убивает PID из лока, даже если он жив, вместо того
    чтобы оставить лок нетронутым. Использовать только когда мы точно
    знаем, что это не второй легитимный Chrome, а осиротевший процесс
    от нашей же предыдущей неудачной попытки (см. init_browser): она
    могла успеть запустить Chrome и создать лок до того, как упасть на
    более позднем шаге, а 5-секундная пауза перед ретраем не всегда
    достаточна, чтобы такой осиротевший процесс сам успел умереть."""
    lock = profile_dir / "SingletonLock"
    if not lock.is_symlink():
        return
    try:
        target = os.readlink(lock)
        pid = int(target.rsplit("-", 1)[-1])
        os.kill(pid, 0)
        if not force:
            return  # PID жив — не наш случай, второй Chrome и правда работает
        os.kill(pid, 9)
    except (OSError, ValueError):
        pass
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        (profile_dir / name).unlink(missing_ok=True)
    logger.debug(f"Cleared stale Chrome singleton lock in {profile_dir}")


# ponytail: Chrome сам пересоздаёт эти каталоги по требованию — это чистый
# HTTP/JS-кэш, не сессия. Без очистки постоянный профиль растёт без
# остановки на каждом плановом запуске (найдено: 516M у .linkedin_profile,
# из них 336M — Cache и Code Cache). Cookies/Login Data/IndexedDB (сама
# сессия входа) лежат в Default/ рядом и не трогаются — вход не сбрасывается.
_STALE_CACHE_SUBDIRS = (
    "Default/Cache",
    "Default/Code Cache",
    "Default/GPUCache",
    "Default/Service Worker",
)

# ponytail: найдено вживую — .chrome_profile_himalayas распух до 746MB,
# из них 505MB — Default/Extensions (сами компоненты Chrome вроде
# Widevine/SafeBrowsing, не наши расширения — --disable-extensions их
# не останавливает, это отдельный от обычных расширений механизм) и
# ещё ~120MB component_crx_cache/optimization_guide_model_store/
# WasmTtsEngine/OnDeviceHeadSuggestModel — Chrome сам фоном докачивает
# это на каждый постоянный профиль и никогда не чистит. Раздутый
# постоянный профиль — задокументированная здесь же причина крашей
# (см. _reset_bloated_preferences ниже, тот же класс проблемы). Ничего
# из этого не сессия входа (та в Cookies/IndexedDB/Local Storage —
# не трогается), поэтому безопасно удалять целиком.
_STALE_ROOT_SUBDIRS = (
    "component_crx_cache",
    "optimization_guide_model_store",
    "WasmTtsEngine",
    "OnDeviceHeadSuggestModel",
    "Default/Extensions",
)


def clear_profile_cache(profile_dir: Path) -> None:
    for rel in (*_STALE_CACHE_SUBDIRS, *_STALE_ROOT_SUBDIRS):
        shutil.rmtree(profile_dir / rel, ignore_errors=True)
    _reset_bloated_preferences(profile_dir)


# ponytail: found live — LinkedIn's persistent profile hit 2.3GB in
# "Default/Preferences" alone (whole profile 2.5GB) and Chrome could no
# longer start at all ("session not created: cannot connect to chrome").
# The file's "name" field was a multi-gigabyte string that looked like
# repeated UTF-8-as-Latin-1 mojibake (Ã... repeating) — each
# rewrite of an already-mangled value roughly doubles it, so a per-launch
# encoding bug compounds into gigabytes within days. Preferences holds only
# browser-level settings, not the site login session (that's Cookies/
# IndexedDB/Local Storage, untouched here), so it's safe to drop outright —
# Chrome regenerates a fresh default one and the site stays logged in.
# 20MB is a generous ceiling: every healthy profile observed in this project
# stays under 25KB. Upgrade path if a legitimate profile ever needs more:
# reset just the oversized key instead of the whole file.
_MAX_PREFERENCES_BYTES = 20 * 1024 * 1024


def _reset_bloated_preferences(profile_dir: Path) -> None:
    prefs = profile_dir / "Default" / "Preferences"
    try:
        size = prefs.stat().st_size
    except FileNotFoundError:
        return
    if size > _MAX_PREFERENCES_BYTES:
        logger.warning(
            f"{prefs} is {size / 1_048_576:.0f}MB "
            f"(>{_MAX_PREFERENCES_BYTES // 1_048_576}MB) — looks corrupted, "
            "resetting to defaults."
        )
        prefs.unlink(missing_ok=True)


def is_driver_dead(driver) -> bool:
    """Общая проверка живости для клиентов, кеширующих один driver на
    весь прогон площадки (десятки driver.get() подряд по страницам/
    карточкам) — Chrome может умереть посреди прогона ("invalid
    session id: session deleted as the browser has closed the
    connection"). Раньше проверка была только в
    HeadHunterBrowserClient; GetMatch/HabrCareer/Geekjob кешируют
    driver тем же способом и были подвержены той же дыре — без неё
    вызывающий код продолжает отдавать мёртвую сессию до конца
    прогона. Не пересоздаёт сам — только гасит мёртвый driver;
    вызывающий код зовёт свой уже импортированный init_browser тем же
    profile_dir."""
    try:
        _ = driver.current_url
        return False
    except Exception:
        logger.warning(
            "Chrome-сессия умерла посреди прогона — пересоздаю "
            "браузер тем же профилем."
        )
        try:
            driver.quit()
        except Exception:
            pass
        return True


def chrome_browser_options(profile_dir: Optional[Path] = None):
    """`--incognito` раньше стоял всегда — но постоянно новый, пустой
    отпечаток браузера на каждый запуск выглядит подозрительнее для
    анти-бот защиты площадок, чем обычный профиль с историей.
    profile_dir (если передан) вместо этого даёт Chrome постоянную
    папку профиля через --user-data-dir, как уже делает
    src/job_sources/linkedin/browser.py::init_linkedin_browser."""
    logger.debug("Setting Chrome browser options")
    options = Options()
    # ponytail: "normal" (Selenium default) ждёт события load, включая все
    # рекламные/трекинговые скрипты страницы (TargetAds, Adfox, hybrid.ai на
    # HH) — именно они подвешивали renderer до PAGE_LOAD_TIMEOUT_SECONDS.
    # "eager" возвращает управление по DOMContentLoaded, не дожидаясь их.
    options.page_load_strategy = "eager"
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-extensions")
    # ponytail: Chrome сам фоном докачивает "компоненты" (Widevine,
    # SafeBrowsing, optimization_guide model store и т.п.) в
    # component_crx_cache/Default/Extensions на каждый постоянный
    # профиль независимо от --disable-extensions — это и раздувало
    # профили до сотен МБ (см. _STALE_ROOT_SUBDIRS в clear_profile_
    # cache). Флаг останавливает саму докачку, а не только чистит
    # то, что уже накопилось.
    options.add_argument("--disable-component-update")
    options.add_argument(
        "--disable-gpu"
    )  # Опционально, полезно в некоторых окружениях
    options.add_argument("window-size=1200x800")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-translate")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-autofill")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-animations")
    options.add_argument("--disable-cache")
    options.add_argument(
        "--allow-file-access-from-files"
    )  # Разрешает доступ к локальным файлам
    options.add_argument(
        "--disable-web-security"
    )  # Отключает веб-безопасность
    # ponytail: без этого navigator.webdriver в JS остаётся true — первое,
    # что проверяет почти любой антибот-скрипт (вероятно, и SmartCaptcha на
    # hh.ru) — и Chrome сам показывает баннер "управляется автоматизированным
    # ПО тестирования". На поведение Selenium (клики/заполнение форм/
    # навигация — это отдельный, более низкоуровневый протокол) не влияет,
    # только на то, что браузер сообщает о себе странице. undetected_
    # chromedriver (LinkedIn) уже патчит это сам — здесь для остальных 4
    # источников на обычном Selenium этого не было вовсе.
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    if profile_dir is not None:
        profile_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_dir}")
        logger.debug(f"Using persistent Chrome profile at {profile_dir}")

    return options


# ponytail: без явного лимита Selenium может ждать driver.get() и
# скрипты страницы практически бесконечно (зависший запрос, модалка,
# перекрывающая рендер, и т.п.) — весь прогон площадки тогда "зависает"
# без единой ошибки в логе, что и наблюдалось на HH/GetMatch. Таймаут
# здесь общий для всех браузерных источников (HH/GetMatch/LinkedIn/
# rabota.ru/geekjob), т.к. все они идут через init_browser().
PAGE_LOAD_TIMEOUT_SECONDS = 45
SCRIPT_TIMEOUT_SECONDS = 30


# ponytail: один retry через фиксированную паузу — покрывает
# транзиентные сбои запуска Chrome (например, сразу после входа в
# систему/пробуждения Mac, пока графическая сессия ещё не готова),
# без диагностики конкретной причины. Причина не транзиентная (Chrome
# не установлен вовсе) — вторая попытка тоже упадёт и ошибка уйдёт
# наверх как раньше.
_BROWSER_INIT_RETRY_DELAY_SECONDS = 5


def _log_chrome_crash_diagnostics(exc: Exception) -> None:
    """ "chrome not reachable" сам по себе не говорит, почему Chrome
    упал при старте (SIGTRAP/EXC_BREAKPOINT из-за постоянного профиля,
    OOM, что-то ещё) — macOS всё равно пишет отчёт о падении в
    DiagnosticReports, просто лог селениума его не показывает.
    Подсвечиваем самый свежий такой отчёт, если он появился в
    последнюю минуту, чтобы в логе была причина, а не только сам факт
    "chrome not reachable"."""
    if "chrome not reachable" not in str(exc).lower():
        return
    reports_dir = Path.home() / "Library/Logs/DiagnosticReports"
    try:
        latest = max(
            reports_dir.glob("Google Chrome*.ips"),
            key=lambda p: p.stat().st_mtime,
            default=None,
        )
    except OSError:
        return
    if latest is not None and time.time() - latest.stat().st_mtime < 60:
        logger.warning(
            f"Похоже, Chrome упал при старте — см. отчёт macOS: {latest}"
        )


def launch_chrome_with_retry(
    build_driver: Callable[[], webdriver.Chrome],
    profile_dir: Optional[Path],
    attempts: int = 2,
) -> webdriver.Chrome:
    """Общий retry для запуска Chrome — используется и обычным Selenium
    (init_browser), и undetected-chromedriver (linkedin/browser.py).
    Раньше оба места копировали один и тот же цикл по отдельности и
    успели разойтись в деталях незамеченно (chrome_utils форсировал
    чистку зависшего SingletonLock на повторной попытке, LinkedIn —
    нет), вынесено сюда, чтобы такого дрейфа больше не было."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        if profile_dir is not None:
            clear_stale_chrome_lock(profile_dir, force=attempt > 1)
        try:
            return build_driver()
        except Exception as e:
            last_exc = e
            _log_chrome_crash_diagnostics(e)
            if attempt < attempts:
                logger.warning(
                    f"Chrome failed to start (attempt {attempt}/{attempts}), "
                    f"retrying in {_BROWSER_INIT_RETRY_DELAY_SECONDS}s: {e}"
                )
                time.sleep(_BROWSER_INIT_RETRY_DELAY_SECONDS)
    logger.error(f"Failed to initialize browser: {last_exc}")
    raise RuntimeError(
        f"Failed to initialize browser: {last_exc}"
    ) from last_exc


def init_browser(profile_dir: Optional[Path] = None) -> webdriver.Chrome:
    if profile_dir is not None:
        clear_profile_cache(profile_dir)

    def _build() -> webdriver.Chrome:
        options = chrome_browser_options(profile_dir)
        # webdriver_manager сам скачивает и обновляет подходящий
        # ChromeDriver, не требуя ручного управления версиями
        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options,
        )
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SECONDS)
        driver.set_script_timeout(SCRIPT_TIMEOUT_SECONDS)
        logger.debug("Chrome browser initialized successfully.")
        return driver

    return launch_chrome_with_retry(_build, profile_dir)


def HTML_to_PDF(html_content, driver):
    """
    Печатает HTML через уже открытый WebDriver командой CDP
    Page.printToPDF — так итоговый PDF получает те же стили и
    рендеринг, что видит браузер, без отдельной PDF-библиотеки.

    :param html_content: HTML-код для конвертации.
    :param driver: экземпляр Selenium WebDriver.
    :return: PDF в виде строки base64.
    :raises ValueError: если html_content — не непустая строка.
    :raises RuntimeError: если WebDriver выбросил исключение.
    """
    # Проверка HTML-содержимого
    if not isinstance(html_content, str) or not html_content.strip():
        raise ValueError(
            "Il contenuto HTML deve essere una stringa non vuota."
        )

    # Кодируем HTML в data-URL, чтобы открыть его без временного
    # файла на диске
    encoded_html = urllib.parse.quote(html_content)
    data_url = f"data:text/html;charset=utf-8,{encoded_html}"

    try:
        driver.get(data_url)
        # Ждём полной загрузки страницы — для сложного HTML это
        # время может понадобиться увеличить
        time.sleep(2)

        # Выполняем CDP-команду печати страницы в PDF
        pdf_base64 = driver.execute_cdp_cmd(
            "Page.printToPDF",
            {
                # Включать фон при печати
                "printBackground": True,
                # Вертикальная печать (False — портретная ориентация)
                "landscape": False,
                # Ширина листа в дюймах (A4)
                "paperWidth": 8.27,
                # Высота листа в дюймах (A4)
                "paperHeight": 11.69,
                # Верхнее поле в дюймах (примерно 2 см)
                "marginTop": 0.8,
                # Нижнее поле в дюймах (примерно 2 см)
                "marginBottom": 0.8,
                # Левое поле в дюймах (примерно 1.27 см)
                "marginLeft": 0.5,
                # Правое поле в дюймах (примерно 1.27 см)
                "marginRight": 0.5,
                # Не показывать колонтитулы
                "displayHeaderFooter": False,
                # Использовать размеры страницы из CSS
                "preferCSSPageSize": True,
                # Не создавать оглавление документа
                "generateDocumentOutline": False,
                # Не создавать тегированный PDF
                "generateTaggedPDF": False,
                # Вернуть PDF в виде строки base64
                "transferMode": "ReturnAsBase64",
            },
        )
        return pdf_base64["data"]
    except Exception as e:
        logger.error(f"Si è verificata un'eccezione WebDriver: {e}")
        raise RuntimeError(f"Si è verificata un'eccezione WebDriver: {e}")
