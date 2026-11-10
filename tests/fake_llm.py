"""A fake LLM for tests (architecture §11).

It has the same `complete(...)` method as `app.llm.client.LLMClient`, but:
- returns scripted responses, one per call. Tests build them from blocks in
  the app's internal format (FR-37), the same `LLMResult` the real client
  returns after translating Gemini's response,
- records every request it receives, so tests can check exactly what was sent,
- can raise an exception instead of answering (for the error paths).

No network, no SDK and no API key are needed. The real translation to and
from Gemini is tested on its own in tests/test_llm_client.py.
"""

import copy
import itertools

from app.llm.result import LLMResult, LLMToolCall

_ids = itertools.count(1)


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def thinking_block(thinking: str = "", signature: str = "c2ln") -> dict:
    return {"type": "thinking", "thinking": thinking, "signature": signature}


def tool_use_block(name: str, tool_input: dict, block_id: str | None = None) -> dict:
    return {"type": "tool_use", "id": block_id or f"call_{next(_ids):04d}", "name": name, "input": tool_input}


def response(
    *blocks, stop_reason: str = "end_turn", input_tokens: int = 10, output_tokens: int = 5
) -> LLMResult:
    """A scripted LLM response. Any stop reason is allowed (for the "unexpected" path)."""
    return LLMResult(
        text="".join(b["text"] for b in blocks if b["type"] == "text"),
        tool_calls=[
            LLMToolCall(id=b["id"], name=b["name"], input=b["input"])
            for b in blocks
            if b["type"] == "tool_use"
        ],
        stop_reason=stop_reason,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        blocks=copy.deepcopy(list(blocks)),
    )


def text_response(text: str, **kwargs) -> LLMResult:
    return response(text_block(text), **kwargs)


class FakeLLM:
    def __init__(self):
        self.responses: list = []  # LLMResult objects, or exceptions to raise
        self.requests: list[dict] = []

    def script(self, *responses) -> None:
        """Queue responses; each LLM call takes the next one."""
        self.responses.extend(responses)

    def complete(self, system: str, messages: list, tools: list, tool_choice: dict) -> LLMResult:
        # Deep copy: the chat service keeps appending to `messages` after the
        # call, and tests must see the request exactly as it was sent.
        self.requests.append(
            copy.deepcopy(
                {"system": system, "messages": messages, "tools": tools, "tool_choice": tool_choice}
            )
        )
        if not self.responses:
            raise AssertionError("FakeLLM was called, but no response was scripted")
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item
