import time
import urllib

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

from src.logging import logger


def chrome_browser_options():
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
    options.add_argument("--incognito")
    options.add_argument(
        "--allow-file-access-from-files"
    )  # Разрешает доступ к локальным файлам
    options.add_argument(
        "--disable-web-security"
    )  # Отключает веб-безопасность
    logger.debug("Using Chrome in incognito mode")

    return options


def init_browser() -> webdriver.Chrome:
    try:
        options = chrome_browser_options()
        # webdriver_manager сам скачивает и обновляет подходящий
        # ChromeDriver, не требуя ручного управления версиями
        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options,
        )
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
