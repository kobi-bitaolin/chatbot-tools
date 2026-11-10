"""The neutral result of one LLM call (NFR-12, AC-60).

The chat service only ever sees these plain dataclasses, never SDK objects,
so switching LLM provider means changing app/llm/ only.
"""

from dataclasses import dataclass


@dataclass
class LLMToolCall:
    """One tool the LLM asked for. `id` pairs it with its tool_result (FR-13)."""

    id: str
    name: str
    input: dict


@dataclass
class LLMResult:
    text: str  # the text blocks, joined
    tool_calls: list[LLMToolCall]  # in the order the LLM asked for them
    stop_reason: str
    input_tokens: int
    output_tokens: int
    # Every block exactly as received, as plain dicts (thinking included, FR-22).
    # They are sent back to the LLM as-is in the next round.
    blocks: list[dict]
