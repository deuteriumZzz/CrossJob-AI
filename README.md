# CrossJob-AI

Форк [AIHawk](https://github.com/feder-cr/Jobs_Applier_AI_Agent_AIHawk), переработанный под поиск и автоотклик на вакансии на российских площадках, плюс поиск по Telegram-каналам.

## Что делает

- Ищет вакансии по вашим критериям (`work_preferences.yaml`) на подключённых площадках.
- Пишет персональное сопроводительное письмо под каждую вакансию с помощью LLM, на основе вашего PDF-резюме (`data_folder/resume.pdf`) — само резюме не переписывается.
- Откликается автоматически (или в режиме dry-run, без реальной отправки) и ведёт историю откликов — включая читаемый HTML-отчёт (`data_folder/output/applications.html`) со статистикой за день/неделю/месяц и таблицей с зарплатой и сайтом компании (где площадка их публикует), чтобы всегда было видно, кому и что отправлено, когда придёт ответ. Историю можно экспортировать в TXT или PDF через пункт меню "Export application history".
- Защищается от бана аккаунта: случайная пауза 30-90с между реальными откликами, суточный лимит откликов на площадку (`DAILY_APPLICATION_LIMIT`), опциональный `apply_once_at_company` (не откликаться в одну компанию дважды).
- Перед письмом/откликом LLM оценивает соответствие резюме вакансии (1-10, порог `JOB_SUITABILITY_SCORE` в `config.py`) — плохо подходящие вакансии пропускаются, не тратя реальный отклик.

## Площадки

| Площадка       | Статус                              |
|----------------|--------------------------------------|
| HeadHunter     | ✅ поиск + автоотклик (официальный API) |
| SuperJob       | ✅ поиск + автоотклик (официальный API) |
| zarplata.ru    | ✅ поиск + автоотклик (API HeadHunter Group, см. оговорку в [GUIDE.md](docs/GUIDE.md)) |
| geekjob        | ✅ только поиск (скрейпинг; автоотклик пока невозможен — см. [GUIDE.md](docs/GUIDE.md)) |
| rabota.ru      | ✅ только поиск (скрейпинг; автоотклик пока невозможен — см. [GUIDE.md](docs/GUIDE.md)) |
| GetMatch       | ✅ только поиск (SPA на Next.js — рендерится реальным Selenium-браузером; автоотклик — мастер из 5 шагов, вероятно с логином, не реализован) |
| Хабр Карьера   | план (есть API, но регистрация приложения — по ручному одобрению Хабра) |
| Telegram-каналы| ✅ только поиск по ключевым словам (официальный API Telegram; автоответ невозможен — там обычно пишут напрямую в личку) |
| LinkedIn       | ✅ поиск + автоотклик Easy Apply (`undetected-chromedriver`, LLM отвечает на вопросы анкеты) — лучший из всех best-effort: не проверен на живом аккаунте, см. [GUIDE.md](docs/GUIDE.md) |

Подробный гайд по настройке (куда класть резюме, как заполнять `secrets.yaml`/`work_preferences.yaml`, что делает бот на каждом шаге) — [docs/GUIDE.md](docs/GUIDE.md).

## Установка

```bash
pip install -r requirements.txt
cp -r data_folder_example data_folder
# заполните data_folder/secrets.yaml и data_folder/work_preferences.yaml
# положите своё резюме как data_folder/resume.pdf
python main.py
```

Неинтерактивный запуск (для cron):

```bash
python main.py --auto headhunter   # или --auto superjob / --auto zarplata / --auto geekjob / --auto rabota_ru / --auto telegram / --auto getmatch / --auto linkedin
```

## Конфигурация

- `data_folder/secrets.yaml` — ключ LLM (`llm_api_key`) и, для каждой площадки, свои ключи (HeadHunter — https://dev.hh.ru/admin, SuperJob — https://api.superjob.ru/register/, Zarplata.ru — тот же принцип, что у HH, Telegram — https://my.telegram.org/apps, см. GUIDE.md).
- `data_folder/work_preferences.yaml` — позиции (они же ключевые слова для Telegram), локации, чёрные списки компаний/названий/локаций, фильтры по опыту/типу занятости/дате, и опциональные блоки `headhunter:`/`superjob:`/`zarplata:` (`auto_apply`, `resume_id`) и `telegram:` (`channels`).
- `data_folder/resume.pdf` — резюме как есть; используется только для генерации сопроводительных писем.

Первый запуск действия по каждой площадке откроет браузер для одноразового входа (OAuth); дальше токен обновляется автоматически.
