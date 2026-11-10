"""Thin wrapper around the Anthropic SDK (architecture §2).

The chat service only calls `complete(...)`. Tests swap this class for the
fake LLM in tests/fake_llm.py, which has the same method.

It gets plain values (key, model, effort), not the app's Settings, so it
doesn't depend on the rest of the app (NFR-12). app/main.py does the wiring.
"""

import anthropic
from anthropic.types import Message

MAX_TOKENS = 16_000  # FR-36


class LLMClient:
    def __init__(self, api_key: str | None, model: str, effort: str, sdk=None):
        """`sdk` replaces the real `anthropic.Anthropic` client (tests pass a recording stub)."""
        self._api_key = api_key
        self._model = model
        self._effort = effort
        self._sdk = sdk

    def _client(self) -> anthropic.Anthropic:
        # Created on first use, not at startup, so the app (and the tests)
        # start without an API key (AC-47).
        if self._sdk is None:
            self._sdk = anthropic.Anthropic(api_key=self._api_key)
        return self._sdk

    def complete(self, system: str, messages: list, tools: list, tool_choice: dict) -> Message:
        """One LLM call. SDK errors (anthropic.APIError) are passed to the caller."""
        request = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "thinking": {"type": "adaptive"},  # FR-36: the model decides how much to think
            "output_config": {"effort": self._effort},
            "system": system,
            "messages": messages,
        }
        if tools:  # the API rejects tool_choice when no tools are sent
            request["tools"] = tools
            request["tool_choice"] = tool_choice
        return self._client().messages.create(**request)
