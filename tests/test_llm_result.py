"""AC-60 (NFR-12): the LLM client returns a neutral LLMResult, never SDK objects.

A recording stub stands in for the Anthropic SDK, so nothing is sent anywhere.
"""

from dataclasses import fields, is_dataclass

from app.llm.client import LLMClient
from app.llm.result import LLMResult, LLMToolCall
from tests.fake_llm import FakeLLM, response, text_block, thinking_block, tool_use_block

PLAIN_TYPES = (str, int, float, bool, type(None))


class RecordingSDK:
    """Looks like `anthropic.Anthropic` for one call: `sdk.messages.create(**request)`."""

    def __init__(self, reply):
        self.reply = reply
        self.requests = []
        self.messages = self

    def create(self, **request):
        self.requests.append(request)
        return self.reply


def assert_plain(value, path="result"):
    """Only our dataclasses and plain Python values; no SDK (Pydantic) objects."""
    if is_dataclass(value):
        for field in fields(value):
            assert_plain(getattr(value, field.name), f"{path}.{field.name}")
    elif isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str), path
            assert_plain(item, f"{path}[{key!r}]")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_plain(item, f"{path}[{index}]")
    else:
        assert type(value) in PLAIN_TYPES, f"{path} is a {type(value).__name__}"


def test_ac_60_llm_result():
    sdk_reply = response(
        thinking_block("hmm", signature="sig1"),
        text_block("Let me "),
        text_block("calculate."),
        tool_use_block("calculator", {"expression": "2+2"}, block_id="tu_1"),
        stop_reason="tool_use",
        input_tokens=12,
        output_tokens=8,
    )
    client = LLMClient(api_key="unused", model="test-model", sdk=RecordingSDK(sdk_reply))

    result = client.complete(system="s", messages=[], tools=[], tool_choice={"type": "auto"})

    assert isinstance(result, LLMResult)
    assert result.text == "Let me calculate."
    assert result.tool_calls == [
        LLMToolCall(id="tu_1", name="calculator", input={"expression": "2+2"})
    ]
    assert result.stop_reason == "tool_use"
    assert (result.input_tokens, result.output_tokens) == (12, 8)
    # Every block as received, thinking included with its signature (FR-22).
    assert [b["type"] for b in result.blocks] == ["thinking", "text", "text", "tool_use"]
    assert result.blocks[0]["signature"] == "sig1"
    assert_plain(result)


def test_ac_60_fake_llm_returns_llm_result():
    fake = FakeLLM()
    fake.script(response(text_block("hi")))

    result = fake.complete(system="s", messages=[], tools=[], tool_choice={"type": "auto"})

    assert isinstance(result, LLMResult)
    assert result.text == "hi"
    assert_plain(result)
