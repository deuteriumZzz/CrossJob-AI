import time
import urllib
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

from src.logging import logger


def chrome_browser_options(profile_dir: Optional[Path] = None):
    """`--incognito` раньше стоял всегда — но постоянно новый, пустой
    отпечаток браузера на каждый запуск выглядит подозрительнее для
    анти-бот защиты площадок, чем обычный профиль с историей.
    profile_dir (если передан) вместо этого даёт Chrome постоянную
    папку профиля через --user-data-dir, как уже делает
    src/job_sources/linkedin/browser.py::init_linkedin_browser."""
    logger.debug("Setting Chrome browser options")
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-extensions")
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


def init_browser(profile_dir: Optional[Path] = None) -> webdriver.Chrome:
    try:
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
    except Exception as e:
        logger.error(f"Failed to initialize browser: {str(e)}")
        raise RuntimeError(f"Failed to initialize browser: {str(e)}")


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
