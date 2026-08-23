![CrossJob-AI](assets/banner.svg)

[![Guide](https://img.shields.io/badge/📖_Guide-docs%2FGUIDE.md-2ea44f)](docs/GUIDE.md)
[![RU](https://img.shields.io/badge/🇷🇺-RU-blue.svg)](README.md)
[![EN](https://img.shields.io/badge/🇬🇧-EN-red.svg)](README.en.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A bot that searches and auto-applies to job postings on Russian job boards, plus keyword search across Telegram channels.

> The setup guide ([docs/GUIDE.md](docs/GUIDE.md)) is Russian-only for now — this README covers the same ground in English, but for full setup detail you may need to translate that page.

## What it does

- Searches for jobs matching your criteria (`work_preferences.yaml`) across connected platforms.
- Writes a personalized cover letter for each vacancy with an LLM, based on your PDF resume (`data_folder/resume.pdf`) — the resume file itself is never rewritten.
- Applies automatically (or in dry-run mode, without actually sending anything) and keeps an application history — including a readable HTML report (`data_folder/output/applications.html`) with day/week/month stats and a table with salary and company website (where the platform publishes them), so you always know who got what and when a reply might arrive. History can be exported to TXT or PDF via the "Export application history" menu item.
- Protects the account from bans: a random 30-90s pause between real applications, a daily per-platform application limit (`DAILY_APPLICATION_LIMIT`), and an optional `apply_once_at_company` (never apply to the same company twice).
- Before writing a letter or applying, an LLM scores how well the resume fits the vacancy (1-10, threshold `JOB_SUITABILITY_SCORE` in `config.py`) — poorly matching vacancies are skipped without spending a real application.

## Platforms

| Platform       | Status                              |
|----------------|--------------------------------------|
| HeadHunter     | ✅ search + auto-apply (browser session, login via phone number + SMS — the official API requires HH app approval and isn't used; verified on a live account, see [GUIDE.md](docs/GUIDE.md) (RU)) |
| SuperJob       | ✅ search + auto-apply (official API) |
| zarplata.ru    | ✅ search + auto-apply (HeadHunter Group API, see the caveat in [GUIDE.md](docs/GUIDE.md) (RU)) |
| geekjob        | ✅ search + auto-apply (scraping; manual OAuth login only — best-effort, not verified on a live account, see [GUIDE.md](docs/GUIDE.md) (RU)) |
| rabota.ru      | ✅ search + auto-apply (scraping; manual OAuth/code login only — best-effort, not verified on a live account, see [GUIDE.md](docs/GUIDE.md) (RU)) |
| GetMatch       | ✅ search + auto-apply (Next.js SPA — rendered via a real Selenium browser; login via a Telegram code, not a password) |
| Habr Career    | planned (has an API, but app registration needs Habr's manual approval) |
| Telegram channels | ✅ keyword search only (official Telegram API; auto-reply isn't possible — people there usually message the poster directly) |
| LinkedIn       | ✅ search (worldwide/by-country, remote only) + Easy Apply auto-apply (`undetected-chromedriver`, LLM answers screening questions in English) — verified on a live account 2026-08-23, see [GUIDE.md](docs/GUIDE.md) (RU) |

## Limits & anti-ban

The daily limit and per-run limit are **our own** settings (pacing, so the account doesn't look like a bot) — not official platform numbers, which are either undocumented publicly (HH says outright: exceed it and you get a 429, contact api@hh.ru for higher volume) or don't apply (geekjob/rabota.ru/GetMatch have no official API at all, only scraping).

The values below are defaults from `config.py`. You can change them on the fly, without restarting or editing code, in the dashboard: **Settings → Application Limits** tab — either globally (all platforms at once) or overridden per platform (or by hand — the `limits:` block, or `job_max_applications`/`daily_application_limit` inside that platform's own block in `work_preferences.yaml`). Higher values mean a higher chance the platform flags the automation; the dashboard shows this risk right next to the setting, but the decision is yours.

| Platform | Daily application limit | Per run | Platform's official limit |
|----------|------------------------|-----------------|------------------------------|
| HeadHunter | `DAILY_APPLICATION_LIMIT` = 15 (±random 70-100%) | `JOB_MAX_APPLICATIONS` = 5 | Not publicly documented (429 if exceeded) |
| SuperJob | 15 (±70-100%) | 5 | Not publicly documented |
| zarplata.ru | 15 (±70-100%) | 5 | Not documented (same platform as HH) |
| geekjob.ru | No daily limit of its own — uses `job_max_applications` per run | 5 vacancies per run | No official API — 24h cooldown on captcha/ban signs (`block_detection.py`) |
| rabota.ru | No daily limit of its own — uses `job_max_applications` per run | 5 | No official API — same cooldown |
| GetMatch | No daily limit of its own — uses `job_max_applications` per run | 5 | No official API — same cooldown |
| Telegram channels | — (search only) | `messages_per_channel` = 100 messages per channel per run | Official Telegram API, no separate limits configured |
| LinkedIn | `LINKEDIN_DAILY_APPLICATION_LIMIT` = 8 (±70-100%) | 5 | No official API — automation is against ToS, see the caveat in [GUIDE.md](docs/GUIDE.md) (RU) |

`±70-100%` is `randomized_daily_limit()`: the real limit for the day is picked randomly within this range once per run, so the daily limit isn't identical every single day (see [GUIDE.md](docs/GUIDE.md) (RU) on anti-ban).

"Per run" (`job_max_applications`) is a shared limit across all platforms at once, changed with a single dashboard setting.

Also available is a **total daily limit shared across every platform combined** (`limits.total_daily_application_limit`, dashboard: same Settings panel) — if you'd rather cap the whole day's applications regardless of which platform they came from, instead of (or on top of) each platform's own limit.

A detailed setup guide (where to put your resume, how to fill in `secrets.yaml`/`work_preferences.yaml`, what the bot does at each step) — [docs/GUIDE.md](docs/GUIDE.md) (Russian only).

## Installation

```bash
pip install -r requirements.txt
python main.py
```

On first run without a `data_folder/`, the bot offers to create one from
the template and asks for an LLM key (press Enter to skip and fill it in
later). Everything else (platforms, resume) — by hand, following the
steps below or [docs/GUIDE.md](docs/GUIDE.md) (RU). The same result by hand:

```bash
cp -r data_folder_example data_folder
# fill in data_folder/secrets.yaml and data_folder/work_preferences.yaml
# place your resume as data_folder/resume.pdf
```

Non-interactive run (for cron):

```bash
python main.py --auto headhunter   # or --auto superjob / --auto zarplata / --auto geekjob / --auto rabota_ru / --auto telegram / --auto getmatch / --auto linkedin
```

Instead of an external cron job you can use the built-in scheduler
(`python main.py --daemon`) or the desktop app with a web dashboard
(`python desktop_app.py`, requires `pip install -r
requirements-desktop.txt`) — platform status, history, employer replies,
and settings all in one window instead of hand-editing YAML. The
dashboard can also handle first-time setup from scratch (its own web
wizard — no need for `data_folder/` to exist beforehand), and targeted
changes without restarting: edit positions/locations/blacklists (Settings
→ Search tab) — including a "Generate positions from resume" button (the
LLM suggests 2-4 matching positions from your PDF resume, no manual
`work_preferences.yaml` editing needed), rebuild `plain_text_resume.yaml`
from the PDF, export `applied_log.json` as a backup, get a Telegram
notification when daily LLM spend crosses a set threshold, and switch
the LLM provider/model (OpenAI/Groq/Gemini/DeepSeek/NVIDIA NIM/OpenRouter/Ollama) with your own
API key for each — no `config.py` editing needed. Details in
[docs/GUIDE.md](docs/GUIDE.md) (RU).

## Configuration

- `data_folder/secrets.yaml` — your LLM key (`llm_api_key`, defaults to OpenAI) and, for each platform, its own keys (HeadHunter needs no secrets — login is browser-based, by phone number and SMS, see GUIDE.md; SuperJob — https://api.superjob.ru/register/, Zarplata.ru — the same idea HH used to use, Telegram — https://my.telegram.org/apps, see GUIDE.md). The LLM provider doesn't have to be OpenAI — Groq/Gemini/DeepSeek/NVIDIA NIM/OpenRouter/Ollama are all supported, each with its own key under the `llm_api_keys:` block (switching provider, picking a model, and entering keys — all in the dashboard's Settings tab, no `config.py` editing). **Default recommendation — Groq, model `openai/gpt-oss-120b`** (marked with a crown 👑 in the model picker): free, and good enough for scoring vacancies/writing letters — at this call volume a paid provider would add up to a noticeable daily bill.
- `data_folder/work_preferences.yaml` — positions (also used as Telegram search keywords), locations, company/title/location blacklists, filters by experience/employment type/date, and optional `headhunter:`/`superjob:`/`zarplata:` blocks (`auto_apply`, `resume_id`) and a `telegram:` block (`channels`).
- `data_folder/resume.pdf` — your resume as-is; used only to generate cover letters.

The first run of each platform's action opens a browser for a one-time login (OAuth); the token refreshes automatically after that.

## License

[MIT](LICENSE).
