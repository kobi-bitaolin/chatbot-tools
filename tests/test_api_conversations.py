"""Conversation management tests (T-2): FR-1..FR-7, NFR-4.

These tests insert turns straight into the database with `add_turn`, so
they don't depend on the chat endpoint (tested in test_api_chat.py).
"""

import re
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models import Message, ToolExecution
from tests.conftest import TickingClock

ID_PATTERN = re.compile(r"^conv_[0-9a-f]{12}$")
UNKNOWN_ID = "conv_000000000000"


def add_turn(client, conversation_id, with_tool=True):
    """Insert one finished turn (user message, assistant message, tool run)."""
    now = datetime.now(timezone.utc)
    with client.app.state.session_factory() as session:
        session.add(
            Message(conversation_id=conversation_id, role="user", content="hi", created_at=now)
        )
        assistant = Message(
            conversation_id=conversation_id,
            role="assistant",
            content="hello",
            status="complete",
            tokens_used=5,
            created_at=now,
        )
        session.add(assistant)
        session.flush()  # gives `assistant` its id
        if with_tool:
            session.add(
                ToolExecution(
                    message_id=assistant.id,
                    tool_name="calculator",
                    input={"expression": "2+2"},
                    output={"result": 4.0},
                    success=True,
                    execution_time_ms=1,
                    created_at=now,
                )
            )
        session.commit()


def count_rows(client, model):
    with client.app.state.session_factory() as session:
        return session.scalar(select(func.count()).select_from(model))


def create(client, **body):
    response = client.post("/conversations", json=body)
    assert response.status_code == 201
    return response.json()["id"]


def test_ac_1_create_conversation(client):
    response = client.post("/conversations", json={})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "created_at"}
    assert ID_PATTERN.match(body["id"])
    datetime.fromisoformat(body["created_at"])  # raises if not ISO 8601

    # The body is optional, and 4000 characters is the longest allowed prompt.
    assert client.post("/conversations").status_code == 201
    assert client.post("/conversations", json={"system_prompt": "a" * 4000}).status_code == 201
    assert client.post("/conversations", json={"system_prompt": "a" * 4001}).status_code == 422


def test_fr_1_system_prompt_is_stripped(client):
    padded = create(client, system_prompt="  Be brief.  ")
    blank = create(client, system_prompt="   ")

    assert client.get(f"/conversations/{padded}").json()["system_prompt"] == "Be brief."
    assert client.get(f"/conversations/{blank}").json()["system_prompt"] is None


def test_ac_4_list_conversations(settings):
    with TestClient(create_app(settings, clock=TickingClock())) as client:
        first = create(client)
        second = create(client)

        response = client.get("/conversations")

        assert response.status_code == 200
        items = response.json()["conversations"]
        assert [item["id"] for item in items] == [second, first]  # newest first
        for item in items:
            assert set(item) == {"id", "created_at", "last_message_at", "message_count"}
            assert item["message_count"] == 0
            assert item["last_message_at"] is None


def test_fr_2_message_count_counts_messages(client):
    conversation = create(client)
    add_turn(client, conversation)

    item = client.get("/conversations").json()["conversations"][0]

    assert item["message_count"] == 2


def test_fr_3_get_conversation_shape(client):
    conversation = create(client, system_prompt="X")
    add_turn(client, conversation)

    response = client.get(f"/conversations/{conversation}")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "system_prompt", "created_at", "messages"}
    user, assistant = body["messages"]  # insertion order
    assert set(user) == {"role", "content", "created_at"}
    assert user["role"] == "user"
    assert set(assistant) == {
        "role", "content", "created_at", "status", "tools_used", "tokens_used"
    }
    assert assistant["status"] == "complete"
    assert assistant["tokens_used"] == 5


def test_ac_6_delete_cascades(client):
    doomed = create(client)
    kept = create(client)
    add_turn(client, doomed)
    add_turn(client, kept)
    assert count_rows(client, Message) == 4
    assert count_rows(client, ToolExecution) == 2

    response = client.delete(f"/conversations/{doomed}")

    assert response.status_code == 204
    assert client.get(f"/conversations/{doomed}").status_code == 404
    # Only the other conversation's rows are left.
    assert count_rows(client, Message) == 2
    assert count_rows(client, ToolExecution) == 1
    assert client.get(f"/conversations/{kept}").status_code == 200


def test_ac_7_reset(client):
    conversation = create(client, system_prompt="X")
    add_turn(client, conversation)
    add_turn(client, conversation)

    response = client.post(f"/conversations/{conversation}/reset")

    assert response.status_code == 200
    assert response.json() == {"id": conversation, "message_count": 0}
    history = client.get(f"/conversations/{conversation}").json()
    assert history["messages"] == []
    assert history["system_prompt"] == "X"
    assert count_rows(client, Message) == 0
    assert count_rows(client, ToolExecution) == 0


def test_ac_8_unknown_conversation_404(client, fake_llm):
    assert client.get(f"/conversations/{UNKNOWN_ID}").status_code == 404
    assert client.delete(f"/conversations/{UNKNOWN_ID}").status_code == 404
    assert client.post(f"/conversations/{UNKNOWN_ID}/reset").status_code == 404
    send = client.post(f"/conversations/{UNKNOWN_ID}/messages", json={"content": "Hi"})
    assert send.status_code == 404
    assert send.json() == {"detail": "Conversation not found"}
    assert fake_llm.requests == []  # the LLM is never called for an unknown id


def test_ac_46_persistence_restart(settings):
    with TestClient(create_app(settings)) as first:
        conversation = create(first, system_prompt="Be brief.")
        add_turn(first, conversation)

    # A brand-new app on the same files, like a restart.
    with TestClient(create_app(settings)) as second:
        response = second.get(f"/conversations/{conversation}")

        assert response.status_code == 200
        body = response.json()
        assert body["system_prompt"] == "Be brief."
        assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
