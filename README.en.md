<div align="center">

![CrossJob-AI](assets/banner.svg)

### Finds work for you: applications on job boards, Telegram vacancies within seconds, and your own company base with Gmail outreach

[![CI](https://github.com/deuteriumZzz/CrossJob-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/deuteriumZzz/CrossJob-AI/actions/workflows/ci.yml)
[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/License-PolyForm%20Noncommercial%201.0.0-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](requirements.txt)
[![Platform](https://img.shields.io/badge/OS-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)](docs/GUIDE.md#сборка-в-exe-macos-и-windows)
[![Guide](https://img.shields.io/badge/📖_Guide-docs%2FGUIDE.md-2ea44f)](docs/GUIDE.md)

[🇷🇺 Русский](README.md) · [🇬🇧 English](README.en.md)

</div>

---

> The full setup guide ([docs/GUIDE.md](docs/GUIDE.md)) is in Russian for now. This README covers the same ground in English; the dashboard itself is in Russian.

**CrossJob-AI** is a personal job-search assistant with a clear dashboard. It takes over the
routine: finds vacancies, scores how well you fit each one, writes a cover letter for every
vacancy, and keeps the conversation going. Decisions stay with you: messages to HR and emails
to companies go out only after you press the button.

## Download

Current alpha release: **[v0.1.0-alpha](https://github.com/deuteriumZzz/CrossJob-AI/releases/tag/v0.1.0-alpha)**.

- [Download for macOS](https://github.com/deuteriumZzz/CrossJob-AI/releases/download/v0.1.0-alpha/CrossJob-AI-macOS.zip)
- [Download for Windows](https://github.com/deuteriumZzz/CrossJob-AI/releases/download/v0.1.0-alpha/CrossJob-AI-Windows.zip)
- [All releases and release notes](https://github.com/deuteriumZzz/CrossJob-AI/releases)

This is an experimental alpha. Read the warnings on the release page before using it.

## Table of contents

- [Three ways to reach an employer](#three-ways-to-reach-an-employer)
- [Features](#features)
- [Platforms](#platforms)
- [Chances of landing a job, by platform](#chances-of-landing-a-job-by-platform-2026)
- [Quick start](#quick-start)
- [Dashboard](#dashboard)
- [CrossJob bot in Telegram](#crossjob-bot-in-telegram)
- [Building a company base with AI](#building-a-company-base-with-ai)
- [Outreach without getting Gmail blocked](#outreach-without-getting-gmail-blocked)
- [Letters that read like a human wrote them](#letters-that-read-like-a-human-wrote-them)
- [Data & safety](#data--safety)
- [Limits & anti-ban](#limits--anti-ban)
- [Configuration](#configuration)
- [How smart are the models](#how-smart-are-the-models)
- [Development](#development)
- [License](#license)

## Three ways to reach an employer

Use one of them or all at once.

| | How it works | What you do |
|---|---|---|
| **1. Job boards** | On a schedule, the bot searches 9 platforms, an LLM scores resume fit (1–10), writes a cover letter and applies by itself — or only shows what it found | Turn platforms on and pick a mode: "Applies by itself" or "Search only" |
| **2. Telegram parser** | Listens to job channels non-stop. A post with your keywords reaches your CrossJob bot within seconds, with "Hello", "+ resume" and "Cover letter" buttons | Press a button — the message goes to HR from your personal account |
| **3. Your own company base and outreach** | The base fills itself — from the Telegram parser and the "🏢 Company sites" channel — plus your own lists (Excel, CSV, PDF, open datasets such as [careerLauncher](https://github.com/byborh/careerLauncher)). Outreach writes a personal email to every company and sends it from your Gmail with your resume attached — one by one, during working hours, like a person would | Upload a list, review the emails, press "Start sending" |

The third way end to end: **companies land in the Base → "Outreach" writes the emails → the bot sends them in daily batches → replies show up in the Inbox**.

## Features

**Search and applications**
- 🔍 Search by your positions and cities on 9 platforms, blacklists for companies, words and locations, a "US/Europe only" remote filter.
- 🎯 Fit scoring: an LLM gives a 1–10 score and explains what's missing; weak matches don't burn an application.
- 🚀 Auto-apply or "Search only" mode, daily limits, pauses between applications; one vacancy posted on several platforms gets one application.
- 🧪 "Check platforms without sending anything" — a dry run to see what the bot would find.
- 🔝 Scheduled bump of your hh resume and your Djinni profile.

**Telegram parser**
- ⚡ A persistent connection to channels: a vacancy arrives within seconds, not once every N hours.
- 📨 Buttons in the CrossJob bot: "Hello", "+ resume" (your own PDFs for different roles), "Cover letter for this vacancy".
- 📇 HR contacts from posts go straight into the company base; new channels are picked up on the fly, and the parser joins channels your account isn't in yet.

**Companies and outreach**
- 🗂 Company base: a sortable table with statuses (not contacted / draft / written / replied / bounced / do not contact), the source of each contact and its history. The base only grows — it never deletes anything by itself.
- 🔄 Statuses update by themselves, wherever an email was sent from: outreach, the Telegram parser or the Inbox. A company you already wrote to won't get a second email from outreach; replies and bounces are picked up from Gmail.
- 🏢 "Company sites" collects companies with matching vacancies (Greenhouse, Lever, Ashby, Workable, We Work Remotely, HN "Who is hiring") into the base and looks for an HR email: in the vacancy text, on the company website, via Hunter.
- 📥 Import your own list: Excel, CSV, Markdown, PDF, Word, TXT. Tables are read by column headers, a table in a PDF — by cell positions, without an LLM; free text is split by an LLM, but an email is taken only if it's literally in the file. Domains are checked for MX, complaint and accessibility inboxes (accessibility@, fraud@…) are dropped, and everything is shown in a preview before saving. Where to get a list — [a prompt for AI](#building-a-company-base-with-ai).
- 📚 Thousands of companies: pages of 50/100/200, "Select all matching the filter", filters by status, source, a specific file and whether there's an email, search.
- ✉️ Outreach: a personal email for every company (who I am → why you → 2–3 achievements → a call, 150–180 words), addressing HR by name. Companies in Russia and the CIS (a .ru/.by/.kz… domain or a Russian vacancy) get Russian, everyone else gets English. Emails are written in batches sized to the daily limit; the next batch is prepared automatically.
- 🛡 Sending without getting Gmail blocked: mailbox warm-up, working hours, random pauses, a stop on bounces — [details](#outreach-without-getting-gmail-blocked). A follow-up in the same thread to anyone silent for 7+ days.
- 🧹 Duplicate companies are merged by website or email domain (several HR people at one company — one card and one email), Excel export, a daily backup.

**Conversations and replies**
- 📬 Inbox: invitations, HR questions and email replies in plain words; "Important" by default, rejections in a separate filter.
- ✍️ Draft replies to HR in Telegram and in hh chat for your approval, an optional hh chat auto-reply.
- 🎤 Interview prep: a brief on the vacancy, a practice trainer with feedback on your answers, a calendar event.

**Analytics**
- 📊 7-day results per source: sent, replied, interviews, response rate.
- The funnel up to an offer, skills demand vs. your resume, market salaries, what's missing most often, blacklist candidates.

## Platforms

| Platform | Search | Apply | Verified live |
|---|---|---|---|
| **HeadHunter** | ✅ browser, SMS login | ✅ auto-apply, application statuses, chat auto-reply, resume bump | ✅ |
| **Habr Career** | ✅ via Habr SSO | ✅ one-click apply | ✅ 2026-08-28 |
| **GetMatch** | ✅ login with a code from Telegram | ✅ | ✅ |
| **geekjob** | ✅ | ✅ best-effort | 🟡 login not verified |
| **Telegram channels** | ⚡ real-time Telegram parser + scheduled search | buttons in the CrossJob bot, optional auto-messages | ✅ |
| **LinkedIn** | ✅ remote, by country | ✅ Easy Apply, an LLM answers the screening questions | ✅ 2026-08-23 |
| **Djinni** | ✅ public listings, no browser | ✅ a message to the recruiter with the cover letter; vacancies Djinni won't let you apply to (experience, country, English, salary) are filtered out up front with the reason; profile bump every 7 days | ✅ 2026-09-25: search, login, filtering, bump |
| **Wellfound** | ✅ JSON-LD | 🟡 best-effort | 🟡 applying not verified |
| **Himalayas** | 🟡 | 🟡 | 🟡 the site is behind an anti-bot check |
| **🏢 Company sites** | ✅ company career pages (Greenhouse, Lever, Ashby, Workable), We Work Remotely, HN "Who is hiring" | doesn't apply — adds companies with an HR email to the Base for one-button outreach | ✅ 2026-09-24 |

You log in to platforms only by hand, once, in the browser window that opens; the session is remembered after that. The bot never types passwords or creates accounts. Per-platform details are in [GUIDE.md](docs/GUIDE.md) (RU).

## Chances of landing a job, by platform (2026)

The table above is about what the bot can do. This one is about the platforms themselves, based on public 2026 statistics; the estimate is approximate.

| Platform | Chance | Why |
|---|---|---|
| HeadHunter | 🟢 High | The largest database in Russia — 70M resumes ([Similarweb](https://www.similarweb.com/ru/website/hh.ru/competitors/), July 2026) |
| Habr Career | 🟢 High (IT) | A clear platform built for IT: company ratings and salaries |
| Telegram channels | 🟢 High | Direct contact with HR, no middlemen; over 60% of marketers find jobs via Telegram ([vc.ru](https://vc.ru/hr___/2878466-luchshie-telegram-kanaly-dlya-udalyonnoy-rabotyi)) |
| GetMatch | 🟡 Medium-high (IT) | Open salaries, but ~92 applications per listing ([vc.ru](https://vc.ru/id5887884/2870166-saity-dlya-poiska-raboty-v-it)) |
| LinkedIn | 🟡 Medium | 3–13% response to direct applications, 85% of hires come through networking ([Zippia](https://www.zippia.com/advice/linkedin-statistics/)) |
| Djinni | 🟡 Medium (IT, Ukraine and Europe) | Many Middle+ roles, often requiring English B2 and Europe/Ukraine; the strong side is that recruiters reach out to your anonymous profile |
| geekjob | 🟡 Medium-low | A niche platform, 15–20 IT listings a month ([hrtime.ru](https://hrtime.ru/material/geekjob-ploshchadka-rabotaet-ili-net-59698/)) |
| Wellfound | 🟡 Medium (startups) | Early and growth-stage startups, English-speaking market |
| Himalayas | 🟡 Medium (remote) | Remote-only: less competition than LinkedIn, but fewer listings too |

## Quick start

**The ready-made app** (macOS/Windows) — [download a release](#download) and open it. On first launch, a wizard on the Home page walks you through: resume → LLM key → platforms → CrossJob bot → Telegram → Gmail → "▶ Start".

**From source:**

```bash
git clone https://github.com/deuteriumZzz/CrossJob-AI.git
cd CrossJob-AI
pip install -r requirements.txt -r requirements-desktop.txt
python desktop_app.py
```

The dashboard in a regular browser (listens on `127.0.0.1` only):

```bash
uvicorn src.webui.api:app
```

Without the UI — a console menu or a scheduled run:

```bash
python main.py                    # menu
python main.py --auto headhunter  # or geekjob / getmatch / telegram / linkedin / habr_career / wellfound / himalayas / djinni / all
python main.py --daemon           # built-in scheduler instead of cron
```

On first run without a `data_folder/`, it's created from the `data_folder_example/` template. Step by step — in the [full guide](docs/GUIDE.md) (RU).

## Dashboard

Six sections, each with one job:

| Section | What's there |
|---|---|
| **Home** | A step-by-step setup wizard (while something isn't connected), "What to do now" (drafts, new replies, interviews, paused platforms), "Your channels" — "🏢 Companies & outreach" (the whole path in one card: a single next-step button — upload a list, write the emails, review and send, stop; reviewing emails and uploading a file happen in a side panel, without leaving the page) and "✈️ Telegram parser", platform cards with a toggle and a mode |
| **Vacancies** | Everything the bot found: status, stage, score, letter; each vacancy has "Actions" — find HR, interview prep, trainer, calendar, fill the form. Rejections are hidden by default |
| **Conversations** | Inbox (employer replies and "Waiting for your decision") · Telegram parser (how it works, account connection, dialogs) |
| **Companies** | Base (a table of companies and HR that handles thousands of rows, file import with the "Where to get a company list?" prompt, Excel export) · Outreach (base → emails → sending via Gmail, stats, follow-ups) |
| **Analytics** | 7-day results, funnel, skills, salaries, offers, blacklist candidates |
| **Settings** | Connections (every account and platform with its status, Hunter) · What I'm looking for · Platforms · Limits · ✈️ Telegram parser · 🏢 Company sites · Email and letters (Gmail, 🛡 mailbox protection, Hunter) · 🤖 CrossJob bot · LLM provider · More (autostart, LLM spend) · My resumes · Logs |

- One "▶ Start / Stop" button in the menu — search and applications on the platforms. Outreach doesn't depend on it: once you press "Start sending", emails keep going while the app is open.
- A "Now" line in the menu, visible from any page: 🔄 sending (7 of 25 today, next in ~9 min), ⏸ outreach is waiting (evening, weekend, daily limit), ⛔ stopped — with a "what to do" button. File parsing and platform checks show there too.
- Changes are visible right away: "Base updated: +N companies", new rows are highlighted for a couple of seconds, numbers on the cards count up smoothly.
- Settings save themselves; keys and passwords have their own button.
- The "?" button — a short "How to use" guide.
- Light and dark theme, works on narrow screens too.

## CrossJob bot in Telegram

Your personal notification bot (created in a minute via @BotFather). It writes only to you — HR never sees it.

- Vacancies from the Telegram parser with reply buttons.
- Outreach emails and follow-ups: "🚀 Send all" or "👀 Show one by one" with "Send / Skip / 🚫 Do not contact" under each email.
- "🚫 Do not contact this company" under a vacancy or an email — the company gets the "do not contact" status in the Base and drops out of outreach.
- Employer replies, invitations, drafts for approval, warnings (captcha, login, limits).
- ⛔ An outreach stop that needs you (Gmail rejected the password, 3 bounces in a day) — immediately and only once; routine pauses go into the digest.
- A morning digest; 🔕 quiet mode — non-urgent things only in the digest, HR replies and interviews arrive immediately.
- Commands: `/status`, `/pause hh`, `/resume hh` (after a captcha).

## Building a company base with AI

You can ask an AI for a list of companies with HR addresses, but **only in a mode with web search**: ChatGPT → Deep Research or Claude → Research. A plain chat without search invents addresses like `hr@company.com` — those emails bounce, and a wave of bounces hurts your Gmail sender reputation.

1. Open an AI with web search and paste the prompt below, changing what's in [brackets]. The same prompt (in Russian) is in the dashboard: **Companies → Base → "Where to get a company list?"** with a "Copy" button.
2. Ask it to save the table as an Excel or CSV file (or paste it into Google Sheets → "File → Download → CSV"). A table in a PDF works too.
3. Upload the file: **Companies → Base → "📥 Upload file"**.

```text
Find [30] IT companies that are currently hiring [Python developers] [remotely in Europe], and the public addresses they use for job applications.

Rules:
1. Use web search. Take emails only from official pages: the company website (Careers, Jobs, Contact pages), the vacancy page, the company's official profile.
2. Don't guess or build addresses from a pattern (e.g. hr@company.com). If no address is published, leave the cell empty.
3. Don't take addresses for complaints, accessibility or special requests (accessibility@, accommodations@, fraud@, eeo@).
4. For every row, give the link to the page where the email is published.

Answer with a single table and no text around it, columns in this order:
Company | Website | Email | Name | Position | Vacancy | Link | Source
"Position" is the job title of the person in the "Name" column; "Link" is the vacancy link, if any; "Source" is the page where the email is published.
```

**What happens on upload.** The bot reads the columns by their headers (English or Russian), checks that each domain has a mail server, drops complaint and accessibility inboxes, merges duplicates with what's already in the Base, and shows a preview — nothing is saved until you press "Add". The HR name and position go into the greeting, the vacancy into the letter, the source into the contact card.

**What gets imported and what doesn't.** Import fills the **company Base for outreach**. Vacancies from the file are saved in the company card and the email is written around them, but they don't appear under "Vacancies" and aren't used for auto-apply on the platforms.

**Ready-made open lists.** For example, [careerLauncher](https://github.com/byborh/careerLauncher) — public application addresses at tech companies, each with its source (the `data/companies.md` file, ODC-BY license — credit the source). Download it and upload it like any other file.

## Outreach without getting Gmail blocked

Outreach goes out through your personal Gmail, so it's built to look like emails from a real person, not spam. Everything is configured in **Settings → Email and letters → 🛡 Mailbox protection**.

| Protection | How it works | Default |
|---|---|---|
| **Daily limit** | At most N emails a day (up to 300) | 30 |
| **Mailbox warm-up** | Day one — 15 emails, then +5 for every day emails went out, until it reaches your limit. A sudden jump from zero to hundreds of emails is the main spam signal | on |
| **Sending hours** | Only during the set hours; in the evening and on weekends the bot waits and resumes by itself | weekdays, 9:00–19:00 |
| **Human-like pauses** | The day's remaining emails are spread across the remaining working time, ±50% at random, sometimes with a 10–25 minute break | — |
| **Stop on bounces** | 3 bounces in a day (addresses that don't exist) — sending stops until tomorrow and the bot messages you | — |
| **Gmail rejected the password** | Outreach stops right away instead of wasting the remaining emails; a new password in settings lifts the stop | — |

**How many emails a day is safe.** A regular Gmail account technically allows about 500 emails a day, but for emails to strangers 30–50 is reasonable. Go to 80–100 only on a mailbox that has been sending and getting replies for several weeks. Warm-up gets you to your limit gradually — don't turn it off on a new mailbox.

The LLM writes emails in batches sized to the daily limit: a list of a thousand companies doesn't turn into a thousand LLM requests at once, and emails don't go stale while they wait in line. How many days the whole campaign will take, warm-up included, is shown in "Outreach".

## Letters that read like a human wrote them

Everything sent to an employer is written by the rules of the [humanizer](https://github.com/blader/humanizer) skill (based on Wikipedia's "Signs of AI writing"), extended with Russian marker words: no "not just X, but Y", dash chains, templated triplets, inflated significance, promotional tone or chatbot leftovers; only facts from the resume.

Then a second pass, as in the skill itself: the code looks for remaining tells, and if there are any, the LLM rewrites the text once, keeping every fact. This covers outreach emails, Telegram messages to HR, cover letters, hh chat replies and text answers in hh questionnaires.

The name in the subject and signature comes from the same PDF resume that goes out as the attachment.

## Data & safety

- **Everything is stored on your computer** in `data_folder/`: the company base (`output/contact_book.json`), outreach, applications, conversations, drafts. None of it goes into git.
- **The Base only grows** — companies, contacts and history are never deleted by themselves, only by hand (with "Undo").
- **A backup copy** of the whole Base and the other files is made automatically once a day in `data_folder/backups/`; copies from the last 7 days are kept — in case a file gets corrupted or something was deleted by mistake.
- **Nothing reaches HR without your action** — Telegram messages, outreach emails and follow-ups go out only on a button press. The bot sends by itself only platform applications in "Applies by itself" mode.
- **The bot never types passwords:** you log in to the platforms and to Telegram yourself; for Gmail it's a Google app password, not your main password.
- Cover letters for applications are kept for 7 days; letters from Telegram buttons — in `data_folder/telegram/letters/`.

## Limits & anti-ban

These limits are our own pacing settings, not official platform numbers. They change in **Settings → Limits** without a restart; every run logs a per-platform funnel (found / already seen / filtered out / applied).

| Platform | Daily limit | Per run | Protection |
|---|---|---|---|
| HeadHunter | 15 (±70–100% at random) | 5 | 24h pause on a captcha or ban |
| LinkedIn | 8 (±70–100%) | 5 | No official API — see the caveat in [GUIDE.md](docs/GUIDE.md) (RU) |
| Habr Career, Wellfound, Himalayas, Djinni | the shared daily limit or the platform's own | 5 | 24h pause on a captcha or ban |
| geekjob, GetMatch | none of their own — the per-run limit | 5 | 24h pause on a captcha or ban |
| Telegram | 15 cold messages a day (if auto-messages are on) | — | Personal account |
| Email outreach | `email_daily_limit` (30 by default) with warm-up from 15 a day | one by one, random pauses across the working day | Sending hours, stop at 3 bounces a day — see [Outreach without getting Gmail blocked](#outreach-without-getting-gmail-blocked) |

Plus `apply_once_at_company` (never apply to the same company twice) and a shared ceiling `limits.total_daily_application_limit`.

## Configuration

Almost everything is configured in the dashboard. If you prefer files:

- **`data_folder/secrets.yaml`** — LLM keys (`llm_api_keys`, 14 providers; by default we recommend free Groq with the `openai/gpt-oss-120b` model), `telegram: {api_id, api_hash}` from [my.telegram.org](https://my.telegram.org/apps), the notification bot `notifications`, email `email: {address, app_password}`, optional `hunter_api_key`.
- **`data_folder/work_preferences.yaml`** — positions, locations, blacklists, filters; a block per platform (`schedule_enabled`, `interval_hours`, `auto_apply`, its own `positions`/`locations`, limits); `telegram:` (`channels`, `watch_enabled`, `watch_keywords`, `watch_stop_words`, greeting); `djinni:` (`country`, `experience_years`, `auto_bump_resume`); `headhunter.auto_bump_resume`, `headhunter.auto_reply`; `direct:` ("Company sites" and email: `schedule_enabled`, `companies`, `wwr`, `hn`, `email_daily_limit`, `warmup`, `send_from`, `send_to`, `weekdays_only`, `follow_up_days`); `digest: {enabled, hour, quiet}`; `excluded_remote_regions`.
- **Resumes** — `data_folder/resume.pdf` (main), `resume_linkedin.pdf` (international platforms and English emails), extra PDFs in `data_folder/telegram/` (Telegram buttons and the choice in outreach). Easier to upload in **Settings → My resumes**.
- **Logs** — `log/app.log` (10 MB rotation, one week), visible in **Settings → Logs**.

Every field is described in [GUIDE.md](docs/GUIDE.md) (RU).

## How smart are the models

Each provider has a default model (👑 in the model picker). Compared on the [Artificial Analysis Intelligence Index](https://artificialanalysis.ai/leaderboards/models), checked on 2026-08-29 — a snapshot at the time of checking.

![How smart are the models we use](assets/llm-intelligence.en.svg)

## Development

```bash
pip install -r requirements.txt -r requirements-desktop.txt
black --line-length 79 --check .
isort --profile black --line-length 79 --check .
flake8 --max-line-length=79 --select=E,F --extend-ignore=E704
mypy --ignore-missing-imports main.py src desktop_app.py
python -m pytest tests/ -q
```

The same checks run in CI on every push and PR to `main` ([ci.yml](.github/workflows/ci.yml)).

| Where | What |
|---|---|
| `main.py`, `desktop_app.py` | Entry points: console menu, scheduler, desktop window |
| `src/job_sources/` | One module per platform (`headhunter/`, `djinni/`, `telegram/`…) plus shared logic: fit scoring, letters, the company base, HR replies, anti-ban |
| `src/direct/` | "Company sites", file import (Excel, CSV, Markdown, PDF), outreach, email and its protection (`mail_guard.py`) |
| `src/webui/` | The FastAPI dashboard (`api.py`) and the UI (`static/`) |
| `src/libs/resume_and_cover_builder/` | Resume and cover letter generation, humanizer rules (`anti_ai_rules.py`) |
| `tests/` | Unit tests |

## License

[PolyForm Noncommercial 1.0.0](LICENSE) — Dmitry Vologdin, 2026. Use, modification and forks are permitted for any noncommercial purpose; embedding it in a commercial product or paid service is not.
