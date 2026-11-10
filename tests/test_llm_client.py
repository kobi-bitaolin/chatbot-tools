"""The Gemini LLM client (T-7b, spec v0.7): FR-37, FR-25, NFR-12.

A recording stub stands in for the Gemini SDK (`sdk.models.generate_content`),
so nothing is sent anywhere. These are the only tests that know Gemini's format;
every other test uses the fake LLM and the internal format.
"""

import base64
from dataclasses import fields, is_dataclass

import pytest
from google.genai import errors, types

from app.llm.client import LLMClient
from app.llm.result import LLMResult, LLMToolCall, LLMUnavailableError
from tests.fake_llm import FakeLLM, text_response

PLAIN_TYPES = (str, int, float, bool, type(None))
SIG1 = base64.b64encode(b"sig1").decode()


def gemini_response(*parts, finish="STOP", prompt=12, candidates=5, thoughts=3):
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=list(parts)),
                finish_reason=types.FinishReason[finish],
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt,
            candidates_token_count=candidates,
            thoughts_token_count=thoughts,
        ),
    )


class RecordingSDK:
    """Looks like `genai.Client` for our calls: `sdk.models.generate_content(...)`."""

    def __init__(self, reply=None, error=None):
        self.reply = reply if reply is not None else gemini_response(types.Part(text="ok"))
        self.error = error
        self.requests = []
        self.models = self

    def generate_content(self, **request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.reply


def complete(sdk, messages=None, tools=None, tool_choice=None):
    client = LLMClient(api_key="unused", model="test-model", sdk=sdk)
    return client.complete(
        system="sys",
        messages=messages or [{"role": "user", "content": "Hi"}],
        tools=tools or [],
        tool_choice=tool_choice or {"type": "auto"},
    )


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
    reply = gemini_response(
        types.Part(text="hmm", thought=True, thought_signature=b"sig1"),
        types.Part(text="Let me "),
        types.Part(text="calculate."),
        types.Part(function_call=types.FunctionCall(id="c1", name="calculator", args={"expression": "2+2"})),
    )

    result = complete(RecordingSDK(reply))

    assert isinstance(result, LLMResult)
    assert result.text == "Let me calculate."  # thought text is not part of the answer
    assert result.tool_calls == [LLMToolCall(id="c1", name="calculator", input={"expression": "2+2"})]
    assert [b["type"] for b in result.blocks] == ["thinking", "text", "text", "tool_use"]
    assert_plain(result)


def test_ac_60_fake_llm_returns_llm_result():
    fake = FakeLLM()
    fake.script(text_response("hi"))

    result = fake.complete(system="s", messages=[], tools=[], tool_choice={"type": "auto"})

    assert isinstance(result, LLMResult)
    assert result.text == "hi"
    assert_plain(result)


def test_ac_60_sdk_errors_become_llm_unavailable():
    """NFR-12 / FR-25: the service only ever sees our own error type."""
    sdk_error = errors.ServerError(503, {"error": {"message": "overloaded"}})
    with pytest.raises(LLMUnavailableError) as caught:
        complete(RecordingSDK(error=sdk_error))
    assert caught.value.__cause__ is sdk_error  # the original stays available for the log

    no_key = LLMClient(api_key=None, model="test-model")  # no stub: the real SDK client
    with pytest.raises(LLMUnavailableError):
        no_key.complete(system="s", messages=[{"role": "user", "content": "Hi"}], tools=[], tool_choice={"type": "auto"})


def test_ac_62_gemini_request_translation():
    sdk = RecordingSDK()
    messages = [
        {"role": "user", "content": "Weather in Tokyo and 1/0?"},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "", "signature": SIG1},
                {"type": "text", "text": "Checking."},
                {"type": "tool_use", "id": "c1", "name": "weather", "input": {"location": "Tokyo"}},
                {"type": "tool_use", "id": "c2", "name": "calculator", "input": {"expression": "1/0"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "c1", "content": '{"temperature": 14}'},
                {"type": "tool_result", "tool_use_id": "c2", "content": "Division by zero", "is_error": True},
            ],
        },
    ]

    complete(sdk, messages=messages)

    [request] = sdk.requests
    contents = request["contents"]
    assert [c.role for c in contents] == ["user", "model", "user"]
    assert contents[0].parts[0].text == "Weather in Tokyo and 1/0?"

    thought, text, call_1, call_2 = contents[1].parts
    assert thought.thought is True and thought.thought_signature == b"sig1"
    assert text.text == "Checking."
    assert (call_1.function_call.id, call_1.function_call.name) == ("c1", "weather")
    assert call_1.function_call.args == {"location": "Tokyo"}
    assert (call_2.function_call.id, call_2.function_call.name) == ("c2", "calculator")

    # FR-13: ONE user Content with both results, in order, paired by id.
    result_1, result_2 = (part.function_response for part in contents[2].parts)
    assert (result_1.id, result_1.name, result_1.response) == ("c1", "weather", {"result": {"temperature": 14}})
    assert (result_2.id, result_2.name, result_2.response) == ("c2", "calculator", {"error": "Division by zero"})


@pytest.mark.parametrize(
    ("finish", "stop_reason"),
    [
        ("STOP", "end_turn"),
        ("MAX_TOKENS", "max_tokens"),
        ("SAFETY", "refusal"),
        ("PROHIBITED_CONTENT", "refusal"),
        ("BLOCKLIST", "refusal"),
        ("SPII", "refusal"),
        ("OTHER", "OTHER"),  # unexpected: FR-26 turns it into a 502
    ],
)
def test_ac_63_finish_reason_mapping(finish, stop_reason):
    result = complete(RecordingSDK(gemini_response(types.Part(text="x"), finish=finish)))
    assert result.stop_reason == stop_reason


def test_ac_63_gemini_response_mapping():
    # Gemini reports STOP even when it calls tools; a function_call part means tool_use.
    reply = gemini_response(
        types.Part(function_call=types.FunctionCall(id="c1", name="weather", args={"location": "Tokyo"}),
                   thought_signature=b"sig1"),
        types.Part(function_call=types.FunctionCall(id="c2", name="calculator", args={"expression": "85*0.15"})),
        finish="STOP", prompt=12, candidates=5, thoughts=3,
    )

    result = complete(RecordingSDK(reply))

    assert result.stop_reason == "tool_use"
    assert [(c.id, c.name, c.input) for c in result.tool_calls] == [
        ("c1", "weather", {"location": "Tokyo"}),
        ("c2", "calculator", {"expression": "85*0.15"}),
    ]
    assert result.blocks[0]["signature"] == SIG1  # kept, to go back on the same part (A3)
    assert "signature" not in result.blocks[1]
    assert (result.input_tokens, result.output_tokens) == (12, 5 + 3)

    # Missing counts are 0 (Gemini leaves thoughts_token_count empty when it didn't think).
    result = complete(RecordingSDK(gemini_response(types.Part(text="ok"), thoughts=None)))
    assert result.output_tokens == 5


def test_ac_63_blocked_prompt_is_refusal():
    blocked = types.GenerateContentResponse(
        candidates=[],
        prompt_feedback=types.GenerateContentResponsePromptFeedback(block_reason=types.BlockedReason.SAFETY),
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=7),
    )

    result = complete(RecordingSDK(blocked))

    assert result.stop_reason == "refusal"
    assert (result.text, result.tool_calls, result.blocks) == ("", [], [])
    assert (result.input_tokens, result.output_tokens) == (7, 0)


def test_ac_63_signature_round_trip():
    """A signature read from a response goes back byte-identical on the next request."""
    reply = gemini_response(
        types.Part(function_call=types.FunctionCall(id="c1", name="calculator", args={"expression": "2+2"}),
                   thought_signature=b"\x00\xffopaque"),
    )
    sdk = RecordingSDK(reply)
    first = complete(sdk)

    complete(sdk, messages=[
        {"role": "user", "content": "2+2?"},
        {"role": "assistant", "content": first.blocks},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": '{"result": 4.0}'}]},
    ])

    sent = sdk.requests[1]["contents"][1].parts[0]
    assert sent.thought_signature == b"\x00\xffopaque"
