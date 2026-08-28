![CrossJob-AI](assets/banner.svg)

[![Guide](https://img.shields.io/badge/📖_Guide-docs%2FGUIDE.md-2ea44f)](docs/GUIDE.md)
[![RU](https://img.shields.io/badge/🇷🇺-RU-blue.svg)](README.md)
[![EN](https://img.shields.io/badge/🇬🇧-EN-red.svg)](README.en.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A bot that searches and auto-applies to job postings on Russian job boards, plus search and optional cold outreach to contacts found in Telegram channels.

> The setup guide ([docs/GUIDE.md](docs/GUIDE.md)) is Russian-only for now — this README covers the same ground in English, but for full setup detail you may need to translate that page.

## What's new (2026-08-27)

- Telegram is no longer search-only: if a channel post contains exactly one unambiguous `@username` contact, the bot can message them a short greeting first (`telegram.auto_message`), with a human-like pause (2-10 minutes), a daily cap, and an active-hours window — not the whole cover letter, so it doesn't read as a mass mailing. The rest of the conversation lives in a new dashboard tab, **"Telegram" → "Conversations"** (per-contact message history, an unread badge, replying manually right from the dashboard); there's no auto-reply to incoming messages, by design. Posts older than `telegram.max_post_age_days` (7 by default) are skipped entirely, and channels can be given as a full link (`https://t.me/...`) as well as a bare username.
- Dashboard: a dedicated "Telegram" tab (channels, post freshness, auto-messaging, conversations) split out of the general "Search" panel — platforms and Telegram are now separate parts of the UI.
- Positions/locations can now be overridden per platform (Telegram included) without touching the shared list — empty on a platform means "use the shared list" (see `effective_list` in GUIDE.md).
- HeadHunter: handles one more application-questionnaire variant — a separate `/applicant/vacancy_response` page (previously only the same-page modal was recognized).
- A notification fires if not a single LLM call succeeded during a whole run (a sign of an exhausted free-tier limit) — vacancies still get scored via a fallback in that case, without a real LLM check.
- Dashboard: a "🎲 Distribute across platforms" button splits the total daily application limit across every platform with scheduling enabled, in random shares (LinkedIn gets half the weight of the rest); a new "Salary expectations" panel keeps HH (RUB/month) and LinkedIn (USD/year) as separate fields for their separate markets.

## What it does

- Searches for jobs matching your criteria (`work_preferences.yaml`) across connected platforms, Telegram channels included.
- Writes a personalized cover letter for each vacancy with an LLM, based on your PDF resume (`data_folder/resume.pdf`) — the resume file itself is never rewritten.
- Applies automatically (or in dry-run mode, without actually sending anything) and keeps an application history — including a readable HTML report (`data_folder/output/applications.html`) with day/week/month stats and a table with salary and company website (where the platform publishes them), so you always know who got what and when a reply might arrive. History can be exported to TXT or PDF via the "Export application history" menu item.
- In Telegram channels, where there's no "apply" button — optionally messages the contact found in a post first (a short greeting, not the whole letter) and keeps a conversation with them in its own dashboard section — see "What's new" above.
- Protects the account from bans: a random 30-90s pause between real applications (2-10 minutes between cold Telegram messages), a daily per-platform application limit (`DAILY_APPLICATION_LIMIT`) plus an optional total limit shared across every platform, and an optional `apply_once_at_company` (never apply to the same company twice).
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
| wellfound.com  | ✅ search (verified live 2026-08-28, schema.org JobPosting — 25/25 results for a test position) + best-effort auto-apply (manual login/signup; real apply is NOT verified on a live logged-in account — if the form still asks for a password after clicking "Apply Now", the job is silently recorded as dry-run, see [GUIDE.md](docs/GUIDE.md) (RU)). Search matches wellfound's own role taxonomy, not free text — not every position will find a match |
| careerist.ru   | ✅ search (verified live 2026-08-28, schema.org JobPosting, search via the `/jobs-{query}/` SEO redirect — the site transliterates Cyrillic itself; the site occasionally returns sporadic 502s, one retry built in) + best-effort auto-apply (manual login; real apply is NOT verified on a live logged-in account — anonymously the submit button redirects to registration, see [GUIDE.md](docs/GUIDE.md) (RU)) |
| Habr Career    | ✅ search + auto-apply (no usable official API for personal bots — manual login via Habr's SSO, including Google; for a logged-in user "Откликнуться" is an instant one-click submit, no form and no cover letter) — verified on a live account 2026-08-28, a real application was confirmed and correctly recognized by the bot |
| careerspace.app| planned, low priority (confirmed: `/jobs` is a small personalized feed — no keyword search, no pagination; "Ссылка на отклик" requires login and where it leads is unconfirmed) |
| hirify.me      | planned (job aggregator, including Telegram channels) |
| himalayas.app  | planned (search only — apply redirects to the company's external ATS, no auto-apply) |
| Telegram channels | ✅ search + optional cold outreach to contacts found in posts (personal account via the official Telegram API; no auto-reply to incoming messages — replying is manual, from the dashboard, see [GUIDE.md](docs/GUIDE.md) (RU)) |
| LinkedIn       | ✅ search (worldwide/by-country, remote only) + Easy Apply auto-apply (`undetected-chromedriver`, LLM answers screening questions in English) — verified on a live account 2026-08-23, see [GUIDE.md](docs/GUIDE.md) (RU) |

## Chances of landing a job, by platform (based on 2026 data)

The table above is about what the bot can technically do. This one is about the platform's actual market effectiveness — what candidates are saying about it right now and what public 2026 statistics show. These are rough estimates (every candidate's situation differs), but they help prioritize where to look first.

| Platform | Chance | Why |
|---|---|---|
| HeadHunter | 🟢 High | The largest database in Russia — 70M resumes, market leader ([Similarweb](https://www.similarweb.com/ru/website/hh.ru/competitors/), July 2026) |
| SuperJob | 🟢 High | ~29M monthly users (2025), a quality/active audience, strong in the public sector/manufacturing/education ([rb.ru](https://rb.ru/reviews/gde-iskat-rabotu-v-2026/)) |
| Habr Career | 🟢 High (for IT) | One of the clearest platforms specifically for IT job search, a mature ecosystem (company ratings, salaries, a journal) — now integrated into the bot, search and auto-apply verified on a live account |
| Telegram channels | 🟢 High (digital/marketing/sales) | Per HR-community data, over 60% of marketing specialists find jobs via Telegram rather than classic job sites — direct contact with HR, no middlemen ([vc.ru](https://vc.ru/hr___/2878466-luchshie-telegram-kanaly-dlya-udalyonnoy-rabotyi)) |
| GetMatch | 🟡 Medium-high (IT) | Open salaries, honest rules of the game, but an expensive platform for employers and high competition — averages ~92 applications per listing ([vc.ru](https://vc.ru/id5887884/2870166-saity-dlya-poiska-raboty-v-it)) |
| rabota.ru | 🟡 Medium | Reliable listings from stable companies, but there are complaints about stale postings and fewer interview invitations than on hh.ru ([otzovik.com](https://otzovik.com/reviews/rabota_ru-internet-servis_po_poisku_raboti_i_podboru_personala/)) |
| LinkedIn | 🟡 Medium | 87% of recruiters call LinkedIn the best tool for vetting candidates, but the response rate on direct applications is only 3-13% — 85% of actual hires close through networking/referrals, not job-posting applications ([Zippia](https://www.zippia.com/advice/linkedin-statistics/), [LinkedCraft](https://linkedcraft.io/blog/linkedin-networking-statistics-2026)) |
| geekjob.ru | 🟡 Medium-low (IT) | A niche platform (averages 15-20 listings/month across classic IT tracks), HR experts are more skeptical of it than of hh.ru/Habr Career — useful as a secondary channel, not a primary one ([hrtime.ru](https://hrtime.ru/material/geekjob-ploshchadka-rabotaet-ili-net-59698/)) |
| Wellfound (AngelList) | 🟠 Low-medium | Good for discovering startup roles and direct founder contact, but per Scale.jobs' 2026 analysis most applications expire before an employer even reviews them — low apply-to-offer conversion ([remote100k.com](https://remote100k.com/blog/is-wellfound-legit), [whatjobs.com](https://www.whatjobs.com/news/wellfound-angellist-review-2026-the-startup-holy-grail-or-tech-bubble/)) |
| careerist.ru | 🔴 Low | Reviews are mixed and often negative: email spam, and real listings are mixed in with dubious ones (network marketing, forex, lending) — worth double-checking every listing before applying ([otzovik.com](https://otzovik.com/reviews/careerist_ru-internet-servis_po_poisku_raboti_i_podboru_personala/), [eto-razvod.ru](https://eto-razvod.ru/review/careerist/)) |
| zarplata.ru | 🔴 Low | Based on this project's own usage experience — a low real-reply rate (same underlying platform as HH, but a smaller, less active audience) |

## Limits & anti-ban

The daily limit and per-run limit are **our own** settings (pacing, so the account doesn't look like a bot) — not official platform numbers, which are either undocumented publicly (HH says outright: exceed it and you get a 429, contact api@hh.ru for higher volume) or don't apply (geekjob/rabota.ru/GetMatch have no official API at all, only scraping; Telegram is a personal account, not an API integration with platform-side limits).

The values below are defaults from `config.py`. You can change them on the fly, without restarting or editing code, in the dashboard: **Settings → Application Limits** tab — either globally (all platforms at once, including a separate total daily limit `limits.total_daily_application_limit` and a "🎲 Distribute across platforms" button), or overridden per platform (or by hand — the `limits:` block, or `job_max_applications`/`daily_application_limit` inside that platform's own block in `work_preferences.yaml`). Higher values mean a higher chance the platform flags the automation; the dashboard shows this risk right next to the setting, but the decision is yours.

| Platform | Daily application limit | Per run | Platform's official limit |
|----------|------------------------|-----------------|------------------------------|
| HeadHunter | `DAILY_APPLICATION_LIMIT` = 15 (±random 70-100%) | `JOB_MAX_APPLICATIONS` = 5 | Not publicly documented (429 if exceeded) |
| SuperJob | 15 (±70-100%) | 5 | Not publicly documented |
| zarplata.ru | 15 (±70-100%) | 5 | Not documented (same platform as HH) |
| geekjob.ru | No daily limit of its own — uses `job_max_applications` per run | 5 vacancies per run | No official API — 24h cooldown on captcha/ban signs (`block_detection.py`) |
| rabota.ru | No daily limit of its own — uses `job_max_applications` per run | 5 | No official API — same cooldown |
| GetMatch | No daily limit of its own — uses `job_max_applications` per run | 5 | No official API — same cooldown |
| Telegram channels | `telegram.daily_message_limit` = 15 cold messages/day (only if `auto_message` is on) | `messages_per_channel` = 100 messages per channel per run | Personal account, not an API integration — no platform limit; the risk is Telegram itself limiting the account for spam-like behavior |
| LinkedIn | `LINKEDIN_DAILY_APPLICATION_LIMIT` = 8 (±70-100%) | 5 | No official API — automation is against ToS, see the caveat in [GUIDE.md](docs/GUIDE.md) (RU) |
| wellfound.com | `limits.daily_application_limit` (shared default, ±70-100%) | 5 | No official API — apply is best-effort, not verified on a live account |
| careerist.ru | `limits.daily_application_limit` (shared default, ±70-100%) | 5 | No official API — apply is best-effort, not verified on a live account |

`±70-100%` is `randomized_daily_limit()`: the real limit for the day is picked randomly within this range once per run, so the daily limit isn't identical every single day (see [GUIDE.md](docs/GUIDE.md) (RU) on anti-ban).

"Per run" (`job_max_applications`) is a shared limit across all platforms at once, changed with a single dashboard setting.

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
python main.py --auto headhunter   # or --auto superjob / --auto zarplata / --auto geekjob / --auto rabota_ru / --auto telegram / --auto getmatch / --auto linkedin / --auto wellfound / --auto careerist
python main.py --auto check_telegram_replies   # checks for new replies in Telegram conversations (notification only)
```

Instead of an external cron job you can use the built-in scheduler
(`python main.py --daemon`) or the desktop app with a web dashboard
(`python desktop_app.py`, requires `pip install -r
requirements-desktop.txt`) — platform status, history, employer replies,
Telegram conversations, and settings all in one window instead of
hand-editing YAML. The dashboard can also handle first-time setup from
scratch (its own web wizard — no need for `data_folder/` to exist
beforehand), and targeted changes without restarting: edit
positions/locations/blacklists (Settings → Search tab) — including a
"Generate positions from resume" button (the LLM suggests 2-4 matching
positions from your PDF resume, no manual `work_preferences.yaml`
editing needed), configure Telegram on its own tab (channels,
auto-messaging, conversations), distribute the daily application limit
across platforms with one button, set salary expectations separately
for HH and LinkedIn, rebuild `plain_text_resume.yaml` from the PDF,
export `applied_log.json` as a backup, get a Telegram notification when
daily LLM spend crosses a set threshold (or when every LLM provider is
unavailable), and switch the LLM provider/model
(OpenAI/Groq/Gemini/DeepSeek/NVIDIA NIM/OpenRouter/Ollama) with your own
API key for each — no `config.py` editing needed. Details in
[docs/GUIDE.md](docs/GUIDE.md) (RU).

## Configuration

- `data_folder/secrets.yaml` — your LLM key (`llm_api_key`, defaults to OpenAI) and, for each platform, its own keys (HeadHunter needs no secrets — login is browser-based, by phone number and SMS, see GUIDE.md; SuperJob — https://api.superjob.ru/register/, Zarplata.ru — the same idea HH used to use, Telegram — https://my.telegram.org/apps, see GUIDE.md). The LLM provider doesn't have to be OpenAI — Groq/Gemini/DeepSeek/NVIDIA NIM/OpenRouter/Ollama are all supported, each with its own key under the `llm_api_keys:` block (switching provider, picking a model, and entering keys — all in the dashboard's Settings tab, no `config.py` editing). **Default recommendation — Groq, model `openai/gpt-oss-120b`** (marked with a crown 👑 in the model picker): free, and good enough for scoring vacancies/writing letters — at this call volume a paid provider would add up to a noticeable daily bill.
- `data_folder/work_preferences.yaml` — positions, locations, company/title/location blacklists, filters by experience/employment type/date, and optional `headhunter:`/`superjob:`/`zarplata:` blocks (`auto_apply`, `resume_id`) and a `telegram:` block (`channels`, `auto_message`, `daily_message_limit`, `max_post_age_days`, `intro_message_template`). Any platform, Telegram included, can override `positions`/`locations` just for itself inside its own block — empty there means "use the shared list above".
- `data_folder/resume.pdf` — your resume as-is; used only to generate cover letters.

The first run of each platform's action opens a browser for a one-time login (OAuth); the token refreshes automatically after that. For Telegram, instead of a browser, it's a phone number and login code typed into the console on the first search run.

## License

[MIT](LICENSE).
