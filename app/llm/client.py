"""Thin wrapper around the Anthropic SDK (architecture §2).

The chat service only calls `complete(...)`. Tests swap this class for the
fake LLM in tests/fake_llm.py, which has the same method.
"""

import anthropic
from anthropic.types import Message

from app.config import Settings

MAX_TOKENS = 16_000  # FR-36; the rest of the FR-36 request settings come in T-6


class LLMClient:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._sdk: anthropic.Anthropic | None = None

    def _client(self) -> anthropic.Anthropic:
        # Created on first use, not at startup, so the app (and the tests)
        # start without an API key (AC-47).
        if self._sdk is None:
            self._sdk = anthropic.Anthropic(api_key=self._settings.anthropic_api_key)
        return self._sdk

    def complete(self, system: str, messages: list, tools: list, tool_choice: dict) -> Message:
        """One LLM call. SDK errors (anthropic.APIError) are passed to the caller."""
        request = {
            "model": self._settings.llm_model,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": messages,
        }
        if tools:  # the API rejects tool_choice when no tools are sent
            request["tools"] = tools
            request["tool_choice"] = tool_choice
        return self._client().messages.create(**request)
