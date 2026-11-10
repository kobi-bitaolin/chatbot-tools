"""Tool registry, GET /tools and the LLM request settings (T-6).

FR-32 (AC-42), FR-33 + FR-36 (AC-43), NFR-12 + FR-24 (AC-61).
"""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import build_llm, create_app
from app.tools import calculator
from app.tools.registry import ToolRegistry
from tests.conftest import EXPECTED_TOOLS
from tests.fake_llm import FakeLLM, text_response

STRICT_UNSUPPORTED = {"maxLength", "minLength", "minimum", "maximum", "multipleOf"}


def keys_anywhere(schema) -> set:
    """Every dict key in a nested schema."""
    if isinstance(schema, dict):
        return set(schema) | set().union(*(keys_anywhere(v) for v in schema.values()))
    if isinstance(schema, list):
        return set().union(*(keys_anywhere(v) for v in schema))
    return set()


def start_turn(client, content="Hi"):
    conversation = client.post("/conversations", json={}).json()["id"]
    return client.post(f"/conversations/{conversation}/messages", json={"content": content})


def test_ac_42_list_tools(client):
    response = client.get("/tools")

    assert response.status_code == 200
    tools = response.json()["tools"]
    assert [t["name"] for t in tools] == EXPECTED_TOOLS
    for tool in tools:
        assert set(tool) == {"name", "description", "parameters"}
        assert tool["description"]
        assert tool["parameters"]["type"] == "object"
    # GET /tools shows the full S1 schema, limits included (FR-33).
    calculator_tool = tools[0]
    assert calculator_tool["parameters"]["properties"]["expression"]["maxLength"] == 200


class RecordingSDK:
    """Stands in for `anthropic.Anthropic`: records the request, answers "ok"."""

    def __init__(self):
        self.requests = []
        self.messages = self  # so `sdk.messages.create(...)` works

    def create(self, **request):
        self.requests.append(request)
        return text_response("ok")


def request_sent(settings) -> dict:
    sdk = RecordingSDK()
    with TestClient(create_app(settings, llm=build_llm(settings, sdk=sdk))) as client:
        assert start_turn(client).status_code == 200
    [request] = sdk.requests
    return request


def test_ac_43_llm_request_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_EFFORT", "low")
    request = request_sent(Settings(data_dir=tmp_path / "a"))

    assert request["model"] == "test-model"
    assert request["max_tokens"] == 16_000
    assert request["thinking"] == {"type": "adaptive"}
    assert request["output_config"] == {"effort": "low"}
    assert request["tool_choice"] == {"type": "auto"}

    tools = request["tools"]
    assert [t["name"] for t in tools] == EXPECTED_TOOLS
    for tool in tools:
        assert set(tool) == {"name", "description", "input_schema", "strict"}
        assert tool["strict"] is True
        assert tool["input_schema"]["additionalProperties"] is False
        assert not keys_anywhere(tool["input_schema"]) & STRICT_UNSUPPORTED

    # Defaults when neither variable is set.
    monkeypatch.delenv("LLM_MODEL")
    monkeypatch.delenv("LLM_EFFORT")
    request = request_sent(Settings(data_dir=tmp_path / "b"))
    assert request["model"] == "claude-opus-5-5"
    assert request["output_config"] == {"effort": "medium"}


def test_ac_61_prompt_tools_from_registry(settings):
    fake = FakeLLM()
    only_calculator = ToolRegistry([calculator.TOOL])
    with TestClient(create_app(settings, llm=fake, registry=only_calculator)) as client:
        fake.script(text_response("ok"))
        start_turn(client)
    system = fake.requests[0]["system"]
    assert "calculator" in system
    for other in EXPECTED_TOOLS[1:]:
        assert other not in system


def test_ac_61_full_registry_names_every_tool_in_order(client, fake_llm):
    fake_llm.script(text_response("ok"))
    start_turn(client)

    assert "Available tools: " + ", ".join(EXPECTED_TOOLS) + "." in fake_llm.requests[0]["system"]
