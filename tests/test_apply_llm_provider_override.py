import pytest

import main
from src.job_sources.llm_provider import get_chat_llm, set_provider_override


@pytest.fixture(autouse=True)
def _reset_provider_override():
    yield
    set_provider_override(None)


def test_apply_override_from_llm_block():
    main.apply_llm_provider_override(
        {"llm": {"provider": "openai", "model": "gpt-4o"}}
    )
    llm = get_chat_llm("sk-test")
    assert llm.model_name == "gpt-4o"


def test_apply_override_with_no_llm_block_resets():
    set_provider_override("openai", "gpt-4o")
    main.apply_llm_provider_override({})
    llm = get_chat_llm("sk-test")
    assert llm.model_name == "gpt-4o-mini"


def test_apply_override_with_empty_llm_block_resets():
    set_provider_override("openai", "gpt-4o")
    main.apply_llm_provider_override({"llm": None})
    llm = get_chat_llm("sk-test")
    assert llm.model_name == "gpt-4o-mini"
