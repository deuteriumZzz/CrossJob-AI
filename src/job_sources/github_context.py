from __future__ import annotations

from typing import Optional

import httpx

GITHUB_API_BASE = "https://api.github.com"


def fetch_github_summary(username: str, token: Optional[str] = None) -> str:
    """Короткая текстовая сводка публичного GitHub-профиля (био +
    до 5 репозиториев по последней активности) для контекста LLM при
    ответе на технические вопросы работодателя. Не аутентифицируется,
    если token не передан — публичный GitHub API даёт 60 запросов/час
    без токена, этого достаточно на разовый вызов за прогон.
    При любой сетевой ошибке возвращает пустую строку — GitHub-контекст
    опциональный, его отсутствие не должно ронять генерацию ответа."""
    headers = {"Authorization": f"token {token}"} if token else {}
    try:
        with httpx.Client(
            base_url=GITHUB_API_BASE, headers=headers, timeout=10
        ) as client:
            user = client.get(f"/users/{username}")
            user.raise_for_status()
            profile = user.json()

            repos = client.get(
                f"/users/{username}/repos",
                params={"sort": "pushed", "per_page": 5},
            )
            repos.raise_for_status()
            repo_list = repos.json()
    except httpx.HTTPError:
        return ""

    lines = [f"GitHub: {profile.get('html_url', '')}"]
    if profile.get("bio"):
        lines.append(f"Bio: {profile['bio']}")
    for repo in repo_list:
        name = repo.get("name", "")
        language = repo.get("language") or "?"
        description = repo.get("description") or ""
        lines.append(f"- {name} ({language}): {description}")
    return "\n".join(lines)
