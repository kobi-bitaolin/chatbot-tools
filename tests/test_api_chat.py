"""Basic chat tests (T-3): FR-8, FR-9, FR-11, FR-20, FR-24, FR-7.

The fake LLM answers every call, so no network or API key is needed.
"""

from datetime import datetime

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.chat import APP_INSTRUCTIONS
from tests.conftest import TickingClock
from tests.fake_llm import FakeLLM, text_response

UNKNOWN_ID = "conv_000000000000"
DEFAULT_SYSTEM = APP_INSTRUCTIONS + "\n\nYou are a helpful assistant."


def create(client, **body):
    response = client.post("/conversations", json=body)
    assert response.status_code == 201
    return response.json()["id"]


def send(client, conversation_id, content):
    return client.post(f"/conversations/{conversation_id}/messages", json={"content": content})


def test_ac_10_basic_chat_no_tools(client, fake_llm):
    """Required test 1 (S1:349): a plain answer, no tools."""
    conversation = create(client)
    fake_llm.script(text_response("Hello!", input_tokens=10, output_tokens=5))

    response = send(client, conversation, "Hi")

    assert response.status_code == 200
    assert response.json() == {
        "message": {"role": "assistant", "content": "Hello!"},
        "tools_used": [],
        "tokens_used": 15,
    }
    assert len(fake_llm.requests) == 1  # exactly one LLM call
    assert fake_llm.requests[0]["tool_choice"] == {"type": "auto"}
    # The "5 tools in every request" check is added in T-6, when the tools exist.


def test_ac_2_default_system_prompt(client, fake_llm):
    none_given = create(client)
    blank = create(client, system_prompt="   ")
    fake_llm.script(text_response("a"), text_response("b"))

    send(client, none_given, "Hi")
    send(client, blank, "Hi")

    assert fake_llm.requests[0]["system"] == DEFAULT_SYSTEM
    assert fake_llm.requests[1]["system"] == DEFAULT_SYSTEM
    assert client.get(f"/conversations/{none_given}").json()["system_prompt"] is None
    assert client.get(f"/conversations/{blank}").json()["system_prompt"] is None


def test_ac_3_system_prompt_stable(client, fake_llm):
    conversation = create(client, system_prompt="Answer in French.")
    fake_llm.script(text_response("Bonjour"), text_response("Ça va"))

    send(client, conversation, "Hi")
    send(client, conversation, "How are you?")

    first, second = (request["system"] for request in fake_llm.requests)
    assert first == second  # byte-identical on every call
    assert first == APP_INSTRUCTIONS + "\n\nAnswer in French."


def test_ac_22_first_message(client, fake_llm):
    conversation = create(client)
    fake_llm.script(text_response("a"), text_response("b"))

    send(client, conversation, "Hi")
    assert fake_llm.requests[0]["messages"] == [{"role": "user", "content": "Hi"}]

    # After a reset, the next message is again the only one sent.
    client.post(f"/conversations/{conversation}/reset")
    send(client, conversation, "Fresh start")
    assert fake_llm.requests[1]["messages"] == [{"role": "user", "content": "Fresh start"}]


def test_ac_11_content_validation(client, fake_llm):
    conversation = create(client)

    for bad in ["", "   ", "a" * 10_001]:
        assert send(client, conversation, bad).status_code == 422, repr(bad[:10])
    assert client.post(f"/conversations/{conversation}/messages", json={}).status_code == 422
    assert fake_llm.requests == []  # invalid input never reaches the LLM

    # The limits themselves are allowed, and content is stripped before saving.
    fake_llm.script(text_response("ok"), text_response("ok"))
    assert send(client, conversation, "a" * 10_000).status_code == 200
    assert send(client, conversation, "  padded  ").status_code == 200
    assert fake_llm.requests[1]["messages"][-1]["content"] == "padded"
    user_messages = [
        m for m in client.get(f"/conversations/{conversation}").json()["messages"]
        if m["role"] == "user"
    ]
    assert user_messages[-1]["content"] == "padded"


def test_ac_12_validation_before_404(client):
    # Body validation runs before the conversation lookup.
    assert send(client, UNKNOWN_ID, "").status_code == 422


def test_ac_9_last_message_at(settings):
    fake_llm = FakeLLM()
    with TestClient(create_app(settings, clock=TickingClock(), llm=fake_llm)) as client:
        conversation = create(client)
        fake_llm.script(text_response("Hello!"))

        send(client, conversation, "Hi")

        history = client.get(f"/conversations/{conversation}").json()
        user, assistant = history["messages"]
        assert user["content"] == "Hi"
        assert assistant["content"] == "Hello!"
        assert assistant["status"] == "complete"
        assert assistant["tools_used"] == []
        assert assistant["tokens_used"] == 15
        listed = client.get("/conversations").json()["conversations"][0]
        last_message_at = datetime.fromisoformat(listed["last_message_at"])
        assert last_message_at >= datetime.fromisoformat(assistant["created_at"])
