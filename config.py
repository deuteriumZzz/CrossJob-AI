# В этом файле задаются настройки приложения.

from src.utils.constants import ERROR

# Настройки логирования должны иметь префикс LOG_
LOG_LEVEL = "INFO"
LOG_SELENIUM_LEVEL = ERROR
LOG_TO_FILE = False
LOG_TO_CONSOLE = True

MINIMUM_WAIT_TIME_IN_SECONDS = 60

JOB_APPLICATIONS_DIR = "job_applications"
JOB_SUITABILITY_SCORE = 7
# Ниже этого балла отклика вообще не будет (см. classify_fit в
# job_fit.py) — между JOB_MIN_SCORE и JOB_SUITABILITY_SCORE отклик всё
# ещё отправляется, но помечается как слабый матч в статистике.
JOB_MIN_SCORE = 4

JOB_MAX_APPLICATIONS = 5
JOB_MIN_APPLICATIONS = 1

# Дневной лимит для каждого источника, поверх JOB_MAX_APPLICATIONS (он
# ограничивает только один запуск) — защищает от того, что cron
# несколько раз в день запустит один и тот же источник и незаметно
# наберёт заявок гораздо больше, чем нужно.
DAILY_APPLICATION_LIMIT = 15

# Отдельно для LinkedIn: лимит значительно строже, чем у остальных
# источников — по решению самого пользователя, так как LinkedIn
# гораздо агрессивнее блокирует автоматическую активность Easy
# Apply, чем HH/SuperJob/Zarplata.
LINKEDIN_DAILY_APPLICATION_LIMIT = 8

LLM_MODEL_TYPE = "openai"
LLM_MODEL = "gpt-4o-mini"
# Требуется только для моделей OLLAMA
LLM_API_URL = ""
