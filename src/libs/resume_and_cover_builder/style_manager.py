import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Настраиваем логирование
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)


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
