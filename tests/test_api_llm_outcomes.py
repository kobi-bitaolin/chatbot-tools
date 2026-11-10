"""LLM outcomes (T-12): FR-25, FR-26, FR-3 (error messages), FR-21 (refusal replay).

The fake LLM either raises LLMUnavailableError (what the real client raises
for any SDK or connection error, see AC-60) or returns a scripted stop reason.
"""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.llm.result import LLMUnavailableError
from app.main import create_app
from app.models import Message, ToolExecution
from tests.fake_llm import response, text_block, text_response, tool_use_block

UNAVAILABLE = {"detail": "LLM service unavailable"}
REFUSAL_TEXT = "I can't help with that request."


def create(client):
    return client.post("/conversations", json={}).json()["id"]


def send(client, conversation_id, content):
    return client.post(f"/conversations/{conversation_id}/messages", json={"content": content})


def history(client, conversation_id):
    return client.get(f"/conversations/{conversation_id}").json()["messages"]


def test_ac_26_failed_turn_skipped(client, fake_llm):
    """Turn 1 fails with 502; turn 2 is sent without it, but GET history keeps it."""
    conversation = create(client)
    fake_llm.script(LLMUnavailableError("503 from Gemini"), text_response("Hello again"))

    assert send(client, conversation, "first").status_code == 502
    assert send(client, conversation, "second").status_code == 200

    assert fake_llm.requests[1]["messages"] == [{"role": "user", "content": "second"}]
    messages = history(client, conversation)
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "first"),
        ("assistant", "LLM service unavailable"),
        ("user", "second"),
        ("assistant", "Hello again"),
    ]
    assert messages[1]["status"] == "error"


def test_ac_27_llm_failure_502(client, fake_llm, settings):
    """A failure in round 2: 502, status error, and round 1's tool run stays logged."""
    conversation = create(client)
    fake_llm.script(
        response(tool_use_block("calculator", {"expression": "1+1"}), stop_reason="tool_use"),
        LLMUnavailableError("connection reset"),
    )

    reply = send(client, conversation, "What is 1+1?")

    assert reply.status_code == 502
    assert reply.json() == UNAVAILABLE
    assistant = history(client, conversation)[1]
    assert (assistant["status"], assistant["content"]) == ("error", "LLM service unavailable")
    session = client.app.state.session_factory()
    try:
        [execution] = session.scalars(select(ToolExecution)).all()
        assert execution.tool_name == "calculator"
    finally:
        session.close()


def test_ac_58_no_api_key_502(settings):
    """The real LLMClient with no key: 502 and an `error` message, not a stuck `pending`."""
    with TestClient(create_app(settings)) as client:  # no fake: the real client
        conversation = create(client)

        reply = send(client, conversation, "Hello")

        assert reply.status_code == 502
        assert reply.json() == UNAVAILABLE
        assistant = history(client, conversation)[1]
        assert (assistant["status"], assistant["content"]) == ("error", "LLM service unavailable")


def test_ac_28_refusal(client, fake_llm):
    conversation = create(client)
    fake_llm.script(response(stop_reason="refusal"))

    reply = send(client, conversation, "Do something bad")

    assert reply.status_code == 200
    assert reply.json()["message"]["content"] == REFUSAL_TEXT
    assert history(client, conversation)[1]["status"] == "complete"


def test_ac_29_max_tokens(client, fake_llm):
    conversation = create(client)
    fake_llm.script(text_response("Partial", stop_reason="max_tokens"))

    reply = send(client, conversation, "Write a long essay")

    assert reply.status_code == 200
    assert reply.json()["message"]["content"] == "Partial [response cut off]"
    assert history(client, conversation)[1]["status"] == "complete"


def test_ac_30_unexpected_stop(client, fake_llm):
    conversation = create(client)
    fake_llm.script(text_response("Hmm", stop_reason="weird_value"))

    reply = send(client, conversation, "Hello")

    assert reply.status_code == 502
    assert reply.json() == {"detail": "Unexpected LLM response"}
    assistant = history(client, conversation)[1]
    assert (assistant["status"], assistant["content"]) == ("error", "Unexpected LLM response")


def test_ac_57_replay_refusal_turn(client, fake_llm):
    """A refused turn is replayed as its user text and the fixed refusal text."""
    conversation = create(client)
    fake_llm.script(response(stop_reason="refusal"), text_response("Fine."))

    send(client, conversation, "Do something bad")
    send(client, conversation, "Never mind")

    assert fake_llm.requests[1]["messages"] == [
        {"role": "user", "content": "Do something bad"},
        {"role": "assistant", "content": REFUSAL_TEXT},
        {"role": "user", "content": "Never mind"},
    ]
