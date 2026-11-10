"""A fake LLM for tests (architecture §11).

It has the same `complete(...)` method as `app.llm.client.LLMClient`, but:
- returns scripted responses, one per call, built from the real SDK types,
- records every request it receives, so tests can check exactly what was sent,
- can raise an exception instead of answering (for the error paths).

No network and no API key are needed.
"""

import copy
import itertools

from anthropic.types import Message, TextBlock, ThinkingBlock, ToolUseBlock, Usage

_ids = itertools.count(1)


def text_block(text: str) -> TextBlock:
    return TextBlock(type="text", text=text)


def thinking_block(thinking: str = "", signature: str = "sig") -> ThinkingBlock:
    return ThinkingBlock(type="thinking", thinking=thinking, signature=signature)


def tool_use_block(name: str, tool_input: dict, block_id: str | None = None) -> ToolUseBlock:
    return ToolUseBlock(
        type="tool_use", id=block_id or f"toolu_{next(_ids):04d}", name=name, input=tool_input
    )


def response(
    *blocks, stop_reason: str = "end_turn", input_tokens: int = 10, output_tokens: int = 5
) -> Message:
    """A scripted LLM response.

    `model_construct` skips validation, so tests can also use stop reasons
    the SDK doesn't list (the "unexpected stop reason" path).
    """
    return Message.model_construct(
        id=f"msg_{next(_ids):04d}",
        type="message",
        role="assistant",
        model="fake-model",
        content=list(blocks),
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
    )


def text_response(text: str, **kwargs) -> Message:
    return response(text_block(text), **kwargs)


class FakeLLM:
    def __init__(self):
        self.responses: list = []  # Message objects, or exceptions to raise
        self.requests: list[dict] = []

    def script(self, *responses) -> None:
        """Queue responses; each LLM call takes the next one."""
        self.responses.extend(responses)

    def complete(self, system: str, messages: list, tools: list, tool_choice: dict) -> Message:
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
