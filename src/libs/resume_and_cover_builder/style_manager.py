import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Раньше здесь был logging.basicConfig(level=DEBUG) — он на импорте
# перенастраивал root-логгер всего процесса на DEBUG, из-за чего
# httpx начинал логировать полные URL запросов вместе с секретами в
# пути (например токен Telegram-бота в /bot<TOKEN>/sendMessage) в
# log/desktop_app.log. Уровень и обработчики root-логгера настраивает
# src/logging.py — этот модуль не должен их переопределять.

_CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _select_block(css_text: str, selector: str) -> str:
    """Тело ПЕРВОГО CSS-правила, у которого ровно этот селектор
    (после split по запятой) — не префиксные варианты вроде
    .entry-header при поиске .entry. Все текущие resume_style/*.css —
    плоский, не вложенный CSS (только один uncommented @media-блок в
    конце каждого файла), поэтому разбор по []{}[^{}]* без стека
    вложенности достаточен и не требует полноценного CSS-парсера."""
    for raw_selectors, body in _CSS_RULE_RE.findall(css_text):
        selectors = {s.strip() for s in raw_selectors.split(",")}
        if selector in selectors:
            return body
    return ""


def _is_multi_column(block: str) -> bool:
    """display:grid с 2+ треками или display:flex без
    flex-direction:column — оба варианта кладут дочерние элементы в
    ряд side-by-side вместо друг под другом."""
    if not block:
        return False
    grid_match = re.search(r"grid-template-columns\s*:\s*([^;]+);", block)
    if grid_match and len(grid_match.group(1).split()) >= 2:
        return True
    return bool(re.search(r"display\s*:\s*flex", block)) and not re.search(
        r"flex-direction\s*:\s*column", block
    )


def analyze_ats_risks(css_text: str) -> List[str]:
    """Точечные эвристики по трём известным точкам риска в
    ФИКСИРОВАННОМ HTML-скелете резюме, который LLM обязан
    воспроизводить (см. template_base.py — классы .entry/.two-column/
    .contact-info одинаковы для всех стилей, разное только CSS) — не
    полноценный ATS-симулятор, а проверка того, что конкретно ломает
    построчное извлечение текста из PDF: колонки внутри записи
    опыта/образования, колонки в списке навыков, иконки-без-текста в
    контактах. PDF — это плоский холст позиционированных глифов без
    DOM, большинство экстракторов текста (в т.ч. pdfminer, которым
    сам бот читает resume.pdf) сортируют по Y/X-позиции — колонка с
    коротким текстом слева и колонка с длинным текстом справа
    оказываются на разной высоте и перемешиваются построчно."""
    risks = []
    if _is_multi_column(_select_block(css_text, ".entry")):
        risks.append(
            "Опыт работы/образование выводятся в несколько колонок — "
            "при извлечении текста из PDF строки могут перепутаться "
            "местами."
        )
    if _is_multi_column(_select_block(css_text, ".two-column")):
        risks.append(
            "Навыки выводятся в несколько колонок — та же проблема "
            "порядка текста при извлечении из PDF."
        )
    if ".contact-info" in css_text and not re.search(
        r"\.contact-info[^{}]*\{[^{}]*content\s*:\s*[\"']", css_text
    ):
        risks.append(
            "Контакты (адрес/телефон/почта) подписаны только иконками "
            "без текстовой замены — если шрифт иконок не извлечётся "
            "как текст, ATS не увидит эти поля вообще."
        )
    return risks


class StyleManager:
    def __init__(self):
        self.selected_style: Optional[str] = None
        # В PyInstaller-сборке (desktop_app.spec) __file__ этого
        # модуля не указывает на реальную папку с забандленными CSS
        # (resume_style) — они распакованы в sys._MEIPASS. Тот же
        # приём, что main._project_root().
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            project_root = Path(meipass)
        else:
            current_file = Path(__file__).resolve()
            project_root = current_file.parent.parent.parent.parent
        self.styles_directory = (
            project_root
            / "src"
            / "libs"
            / "resume_and_cover_builder"
            / "resume_style"
        )

        logging.debug(f"Project root determined as: {project_root}")
        logging.debug(f"Styles directory set to: {self.styles_directory}")

    def get_styles(self) -> Dict[str, Tuple[str, str]]:
        """
        Стили — обычные CSS-файлы, где первая строка в формате
        `/* Имя $ Автор */` служит и названием, и атрибуцией: так
        не нужен отдельный файл-манифест со списком стилей.
        """
        styles_to_files: Dict[str, Tuple[str, str]] = {}
        if not self.styles_directory:
            logging.warning("Styles directory is not set.")
            return styles_to_files
        logging.debug(f"Reading styles directory: {self.styles_directory}")
        try:
            files = [f for f in self.styles_directory.iterdir() if f.is_file()]
            logging.debug(f"Files found: {[f.name for f in files]}")
            for file_path in files:
                logging.debug(f"Processing file: {file_path}")
                with file_path.open("r", encoding="utf-8") as file:
                    first_line = file.readline().strip()
                    logging.debug(
                        f"First line of file {file_path.name}: {first_line}"
                    )
                    if first_line.startswith("/*") and first_line.endswith(
                        "*/"
                    ):
                        content = first_line[2:-2].strip()
                        if "$" in content:
                            style_name, author_link = content.split("$", 1)
                            style_name = style_name.strip()
                            author_link = author_link.strip()
                            styles_to_files[style_name] = (
                                file_path.name,
                                author_link,
                            )
                            logging.info(
                                f"Added style: {style_name} by {author_link}"
                            )
        except FileNotFoundError:
            logging.error(f"Directory {self.styles_directory} not found.")
        except PermissionError:
            logging.error(
                f"Permission denied for accessing {self.styles_directory}."
            )
        except Exception as e:
            logging.error(f"Unexpected error while reading styles: {e}")
        return styles_to_files

    def format_choices(
        self, styles_to_files: Dict[str, Tuple[str, str]]
    ) -> List[str]:
        """Формирует подписи для интерактивного выбора стиля — имя
        и автор в одной строке."""
        return [
            f"{style_name} (style author -> {author_link})"
            for style_name, (file_name, author_link) in styles_to_files.items()
        ]

    def set_selected_style(self, selected_style: str):
        """Сохраняет выбранное имя стиля."""
        self.selected_style = selected_style
        logging.info(f"Selected style set to: {self.selected_style}")

    def get_style_path(self) -> Optional[Path]:
        """
        Возвращает None вместо исключения при ошибке — вызывающий
        код (ResumeFacade) сам решает, поднимать ли ValueError,
        когда стиль ещё не выбран.
        """
        try:
            styles = self.get_styles()
            if self.selected_style not in styles:
                raise ValueError(f"Style '{self.selected_style}' not found.")
            file_name, _ = styles[self.selected_style]
            return self.styles_directory / file_name
        except Exception as e:
            logging.error(f"Error retrieving selected style: {e}")
            return None

    def get_ats_report(self) -> Dict[str, List[str]]:
        """Риски ATS (см. analyze_ats_risks) по каждому доступному
        стилю — пустой список значит стиль не задевает ни одну из
        трёх известных точек риска. Разовая статическая проверка CSS,
        не привязана к конкретному сгенерированному резюме."""
        report: Dict[str, List[str]] = {}
        for style_name, (file_name, _) in self.get_styles().items():
            try:
                css_text = (self.styles_directory / file_name).read_text(
                    encoding="utf-8"
                )
            except OSError as e:
                logging.error(f"Error reading style {file_name}: {e}")
                continue
            report[style_name] = analyze_ats_risks(css_text)
        return report
