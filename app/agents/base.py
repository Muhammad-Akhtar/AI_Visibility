"""Shared OpenAI JSON completion helper for all agents."""

from __future__ import annotations

import logging
from typing import TypeVar

from flask import current_app, has_app_context
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from app.utils.api_debug import print_api_request, print_api_response
from app.utils.json import JSONParseError, parse_llm_json

logger = logging.getLogger("app.agents")

OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"

T = TypeVar("T", bound=BaseModel)


class AgentOutputError(RuntimeError):
    """Raised when an agent cannot produce valid structured output."""


class BaseAgent:
    name = "base"
    model = "gpt-4o"
    temperature = 0.4

    def __init__(self, client: OpenAI | None = None, model: str | None = None) -> None:
        self.client = client or OpenAI()
        if model:
            self.model = model
        elif has_app_context():
            self.model = current_app.config.get("OPENAI_MODEL", self.model)
        self.last_tokens = 0

    def complete_json(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: type[T],
        run_uuid: str = "-",
    ) -> T:
        """Call GPT-4o in JSON mode, validate with Pydantic, retry once on failure."""
        content, tokens = self._chat(system_prompt, user_prompt)
        self.last_tokens = tokens
        extra = {"run_uuid": run_uuid}

        try:
            return self._parse(content, schema)
        except (JSONParseError, ValidationError) as first_error:
            logger.warning(
                "%s.invalid_json retrying error=%s",
                self.name,
                first_error,
                extra=extra,
            )
            repair_user = (
                f"{user_prompt}\n\n"
                "Your previous response was invalid and could not be parsed.\n"
                f"Error: {first_error}\n"
                "Return ONLY valid JSON that matches the schema in the system prompt. "
                "Do not include markdown fences or commentary."
            )
            content, tokens = self._chat(system_prompt, repair_user)
            self.last_tokens += tokens
            try:
                return self._parse(content, schema)
            except (JSONParseError, ValidationError) as second_error:
                logger.error(
                    "%s.json_failed error=%s",
                    self.name,
                    second_error,
                    extra=extra,
                )
                raise AgentOutputError(
                    f"{self.name} produced invalid JSON after retry: {second_error}"
                ) from second_error

    def _chat(self, system_prompt: str, user_prompt: str) -> tuple[str, int]:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        print_api_request(
            provider="OpenAI",
            operation=f"{self.name} — chat.completions.create",
            method="POST",
            url=OPENAI_CHAT_URL,
            payload=payload,
            extra={"auth": "Bearer OPENAI_API_KEY from env"},
        )
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        tokens = 0
        if response.usage is not None:
            tokens = int(response.usage.total_tokens or 0)
        print_api_response(
            provider="OpenAI",
            operation=f"{self.name} — chat.completions.create",
            url=OPENAI_CHAT_URL,
            status=200,
            response={
                "model": response.model,
                "content": content,
                "usage": {
                    "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
                    "completion_tokens": getattr(response.usage, "completion_tokens", None),
                    "total_tokens": tokens,
                },
            },
        )
        return content, tokens

    @staticmethod
    def _parse(content: str, schema: type[T]) -> T:
        data = parse_llm_json(content)
        return schema.model_validate(data)
