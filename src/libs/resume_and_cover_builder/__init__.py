__version__ = "0.1"

# Реэкспорт для main.py (`from ... import ResumeFacade, ...`) —
# перечислены явно в __all__, чтобы flake8 не счёл импорты
# неиспользуемыми.
from .resume_facade import ResumeFacade
from .resume_generator import ResumeGenerator
from .style_manager import StyleManager

__all__ = ["ResumeFacade", "ResumeGenerator", "StyleManager"]
