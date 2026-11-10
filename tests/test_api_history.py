"""Conversation history (T-8): FR-21, FR-22, FR-23.

Includes required test 5 (S1:353, AC-23). Each test checks the exact
messages the fake LLM received, so the replay rule is tested without a
real LLM.
"""

from sqlalchemy import select

from app.models import Message
from tests.fake_llm import response, text_block, text_response, thinking_block, tool_use_block


def create(client):
    response_ = client.post("/conversations", json={})
    assert response_.status_code == 201
    return response_.json()["id"]


def send(client, conversation_id, content):
    reply = client.post(f"/conversations/{conversation_id}/messages", json={"content": content})
    assert reply.status_code == 200
    return reply


def tool_round(*blocks):
    return response(*blocks, stop_reason="tool_use")


def test_ac_23_multi_turn_history(client, fake_llm):
    """Required test 5 (S1:353): turn 2 sees turn 1, tool call and result included."""
    conversation = create(client)
    call = tool_use_block("weather", {"location": "Paris"}, block_id="tu_paris")
    fake_llm.script(
        tool_round(text_block("Let me check."), call),
        text_response("It's 18°C and sunny in Paris."),
        text_response("Yes, 18°C is pleasantly warm."),
    )

    send(client, conversation, "What's the weather in Paris?")
    send(client, conversation, "And is that warm?")

    assert len(fake_llm.requests) == 3
    messages = fake_llm.requests[2]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant", "user"]
    assert messages[0] == {"role": "user", "content": "What's the weather in Paris?"}
    assert messages[1] == {"role": "assistant", "content": [text_block("Let me check."), call]}
    [result] = messages[2]["content"]
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "tu_paris"
    assert "Paris" in result["content"]
    assert messages[3] == {"role": "assistant", "content": "It's 18°C and sunny in Paris."}
    assert messages[4] == {"role": "user", "content": "And is that warm?"}

    history = client.get(f"/conversations/{conversation}").json()["messages"]
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "What's the weather in Paris?"),
        ("assistant", "It's 18°C and sunny in Paris."),
        ("user", "And is that warm?"),
        ("assistant", "Yes, 18°C is pleasantly warm."),
    ]
    assert [t["tool"] for t in history[1]["tools_used"]] == ["weather"]
    assert history[3]["tools_used"] == []


def test_ac_24_thinking_blocks(client, fake_llm):
    """FR-22: thinking goes back unchanged within the turn, is stored, and is not replayed later."""
    conversation = create(client)
    thought = thinking_block("I need the calculator.", signature="sig1")
    call = tool_use_block("calculator", {"expression": "2+2"}, block_id="tu_think")
    fake_llm.script(
        tool_round(thought, call),
        text_response("4"),
        text_response("You asked about 2+2."),
    )

    send(client, conversation, "What is 2+2?")

    # Round 2 of the same turn: the thinking block is sent back byte for byte.
    round_2 = fake_llm.requests[1]["messages"]
    assert round_2[1] == {"role": "assistant", "content": [thought, call]}

    # Stored as received, thinking included.
    with client.app.state.session_factory() as session:
        assistant = session.scalars(select(Message).where(Message.role == "assistant")).one()
        assert assistant.llm_blocks[0]["content"][0] == thought

    send(client, conversation, "What did I ask?")

    # The next turn's request has no thinking blocks, but keeps the tool call.
    next_turn = fake_llm.requests[2]["messages"]
    blocks = [b for m in next_turn if isinstance(m["content"], list) for b in m["content"]]
    assert all(b["type"] != "thinking" for b in blocks)
    assert next_turn[1] == {"role": "assistant", "content": [call]}


def test_ac_25_history_trim(client, fake_llm):
    """FR-23: only the last 20 complete turns are sent, cut at a turn boundary."""
    conversation = create(client)
    for n in range(1, 26):
        fake_llm.script(text_response(f"answer {n}"))
        send(client, conversation, f"turn {n}")

    fake_llm.script(text_response("answer 26"))
    send(client, conversation, "turn 26")

    messages = fake_llm.requests[-1]["messages"]
    expected = []
    for n in range(6, 26):
        expected += [
            {"role": "user", "content": f"turn {n}"},
            {"role": "assistant", "content": f"answer {n}"},
        ]
    expected.append({"role": "user", "content": "turn 26"})
    assert messages == expected
    assert messages[0]["role"] == "user"
