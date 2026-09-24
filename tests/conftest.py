import sys

from src.logging import logger

# Тесты не должны писать в рабочий log/app.log бота — иначе в нём
# вперемешку с настоящими прогонами оказываются тысячи строк от
# фейковых вакансий, и по логу уже не разобрать реальное падение.
logger.remove()
logger.add(sys.stderr, level="WARNING")
