from langchain_core.language_models.fake_chat_models import FakeListChatModel

import src.job_sources.llm_provider as lp
from src.libs.resume_and_cover_builder import anti_ai_rules as rules


def test_detects_ai_tells_and_leaves_human_text_alone():
    ai = "Я Python-разработчик — не просто пишу код, а решаю задачи. Надеюсь, это поможет."
    assert rules.ai_tells(ai) == ["тире как связка", "«не просто X, а Y»", "остатки чат-бота"]
    assert "слова-маркеры нейросети" in rules.ai_tells("I am passionate about robust systems.")
    human = "Здравствуйте, Анна. Я пять лет пишу бэкенд на Python, последние два года в финтехе."
    assert rules.ai_tells(human) == []


def test_humanize_rewrites_only_when_needed(monkeypatch):
    calls = []

    def fake_llm(*a, **k):
        calls.append(1)
        return FakeListChatModel(responses=["Я пишу бэкенд на Python и решаю задачи бизнеса."])

    monkeypatch.setattr(lp, "get_chat_llm", fake_llm)
    clean = "Я пишу бэкенд на Python пять лет."
    assert rules.humanize(clean, "key") == clean and not calls
    assert rules.humanize("Я не просто пишу код — я решаю задачи.", "key") == "Я пишу бэкенд на Python и решаю задачи бизнеса."


def test_humanize_keeps_text_when_ai_fails_or_bloats(monkeypatch):
    text = "Я не просто пишу код — я решаю задачи."

    def broken(*a, **k):
        raise RuntimeError("нет ключа")

    monkeypatch.setattr(lp, "get_chat_llm", broken)
    assert rules.humanize(text, "key") == text
    monkeypatch.setattr(lp, "get_chat_llm", lambda *a, **k: FakeListChatModel(responses=[text * 3]))
    assert rules.humanize(text, "key") == text  # раздуло втрое — не рискуем


def test_rules_have_no_template_braces():
    # Правила склеиваются в ChatPromptTemplate — фигурные скобки сломали бы его.
    assert "{" not in rules.ANTI_AI_STRUCTURE_RU and "{" not in rules.ANTI_AI_STRUCTURE_EN
