"""
LLMLogger и LoggerChatModel — сквозная логика, общая для всех
LLM-классов пакета: логирование каждого вызова OpenAI (токены,
стоимость) и повтор при rate-limit, чтобы это не дублировалось
в каждом LLM-классе по отдельности.
"""

# app/libs/resume_and_cover_builder/utils.py
import json
from datetime import datetime
from typing import Any, Dict, List, cast

from langchain_core.messages import BaseMessage
from langchain_core.messages.ai import AIMessage
from langchain_core.prompt_values import StringPromptValue
from langchain_openai import ChatOpenAI

from .config import global_config


class LLMLogger:

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    @staticmethod
    def log_request(prompts, parsed_reply: Dict[str, Dict]):
        calls_log = global_config.LOG_OUTPUT_FILE_PATH / "open_ai_calls.json"
        if isinstance(prompts, StringPromptValue):
            prompts = prompts.text
        elif isinstance(prompts, Dict):
            # Преобразуем prompts в словарь, если формат не
            # совпадает с ожидаемым
            # ПРИМЕЧАНИЕ: старая, вероятно уже не достижимая ветка —
            # у обычного словаря нет атрибута .messages, поэтому
            # при реальном попадании сюда уже вылетел бы
            # AttributeError; логику ветвления не трогаем без
            # проверки на живой LLM-цепочке.
            prompts = {
                f"prompt_{i+1}": prompt.content
                for i, prompt in enumerate(
                    prompts.messages  # type: ignore[attr-defined]
                )
            }
        else:
            prompts = {
                f"prompt_{i+1}": prompt.content
                for i, prompt in enumerate(prompts.messages)
            }

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Извлекаем данные о расходе токенов из ответа
        token_usage = parsed_reply["usage_metadata"]
        output_tokens = token_usage["output_tokens"]
        input_tokens = token_usage["input_tokens"]
        total_tokens = token_usage["total_tokens"]

        # Извлекаем данные о модели из ответа
        model_name = parsed_reply["response_metadata"]["model_name"]
        prompt_price_per_token = 0.00000015
        completion_price_per_token = 0.0000006

        # Считаем полную стоимость вызова API
        total_cost = (input_tokens * prompt_price_per_token) + (
            output_tokens * completion_price_per_token
        )

        # Формируем запись лога со всеми нужными данными
        log_entry = {
            "model": model_name,
            "time": current_time,
            "prompts": prompts,
            "replies": parsed_reply["content"],  # текст ответа
            "total_tokens": total_tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_cost": total_cost,
        }

        # Дописываем запись лога в JSON-файл
        with open(calls_log, "a", encoding="utf-8") as f:
            json_string = json.dumps(log_entry, ensure_ascii=False, indent=4)
            f.write(json_string + "\n")


class LoggerChatModel:

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm

    def __call__(self, messages: List[Dict[str, str]]) -> BaseMessage:
        """Раньше здесь был свой цикл до 15 повторов с растущей паузой
        (10с, 20с, 40с...) на 429/любую ошибку — вслепую поверх
        llm_provider.get_chat_llm(), который уже сам переключается на
        другого провайдера при рейт-лимите (см. _ChatModelWithFallbacks
        и max_retries=0 там же). Два независимых слоя ретраев на одну
        и ту же ошибку складывались: получасовая генерация одного
        письма на живом прогоне (подтверждено сегодня на HH и
        GetMatch) — не рейт-лимит сам по себе, а именно этот старый
        цикл, слепо повторяющий уже провалившийся с обеих сторон вызов
        по 10-20 минут вместо того, чтобы просто отдать ошибку вызывающему
        коду (там уже есть свой try/except — "Failed to generate cover
        letter... skipping")."""
        # Объявленный тип возврата ChatOpenAI.invoke — общий
        # BaseMessage, но chat-модель на практике всегда возвращает
        # AIMessage; сужение типа здесь фиксирует это допущение, а не
        # просто глушит проверку mypy.
        reply = cast(AIMessage, self.llm.invoke(messages))
        parsed_reply = self.parse_llmresult(reply)
        LLMLogger.log_request(prompts=messages, parsed_reply=parsed_reply)
        return reply

    def parse_llmresult(self, llmresult: AIMessage) -> Dict[str, Any]:
        # Приводим результат LLM к структурированному виду
        content = llmresult.content
        response_metadata = llmresult.response_metadata
        id_ = llmresult.id
        usage_metadata: Dict[str, Any] = dict(llmresult.usage_metadata or {})

        parsed_result = {
            "content": content,
            "response_metadata": {
                "model_name": response_metadata.get("model_name", ""),
                "system_fingerprint": response_metadata.get(
                    "system_fingerprint", ""
                ),
                "finish_reason": response_metadata.get("finish_reason", ""),
                "logprobs": response_metadata.get("logprobs", None),
            },
            "id": id_,
            "usage_metadata": {
                "input_tokens": usage_metadata.get("input_tokens", 0),
                "output_tokens": usage_metadata.get("output_tokens", 0),
                "total_tokens": usage_metadata.get("total_tokens", 0),
            },
        }
        return parsed_result
