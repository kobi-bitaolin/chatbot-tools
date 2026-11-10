"""The tool loop (T-7): FR-12, FR-13, FR-14, FR-16, FR-19, FR-34, FR-3.

Includes 4 of the 6 required tests (S1:348-354): single tool (AC-13),
multiple tools (AC-14), tool error (AC-16) and logging (AC-44).
The fake LLM scripts each round, so no network or API key is needed.
"""

from sqlalchemy import select

from app.models import ToolExecution
from tests.fake_llm import response, text_block, text_response, tool_use_block


def create(client):
    response_ = client.post("/conversations", json={})
    assert response_.status_code == 201
    return response_.json()["id"]


def send(client, conversation_id, content):
    return client.post(f"/conversations/{conversation_id}/messages", json={"content": content})


def tool_round(*blocks, **kwargs):
    """An LLM response that asks for tools."""
    return response(*blocks, stop_reason="tool_use", **kwargs)


def last_user_message(request):
    message = request["messages"][-1]
    assert message["role"] == "user"
    return message


def test_ac_13_single_tool(client, fake_llm):
    """Required test 2 (S1:350): one tool call, then the final answer."""
    conversation = create(client)
    call = tool_use_block("calculator", {"expression": "25/100*180"}, block_id="tu_calc")
    fake_llm.script(tool_round(call), text_response("45"))

    reply = send(client, conversation, "What's 25% of 180?")

    assert reply.status_code == 200
    body = reply.json()
    assert body["message"] == {"role": "assistant", "content": "45"}
    [used] = body["tools_used"]
    assert used["tool"] == "calculator"
    assert used["input"] == {"expression": "25/100*180"}
    assert used["output"] == {"result": 45.0}
    assert used["success"] is True
    assert used["error"] is None
    assert used["execution_time_ms"] >= 0

    assert len(fake_llm.requests) == 2
    second = fake_llm.requests[1]
    # The assistant's tool_use turn is sent back before the results.
    assert second["messages"][-2]["role"] == "assistant"
    assert second["messages"][-2]["content"][0]["id"] == "tu_calc"
    [result] = last_user_message(second)["content"]
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "tu_calc"
    assert result.get("is_error", False) is False


def test_ac_14_multiple_tools(client, fake_llm):
    """Required test 3 (S1:351): two tools in one round, results in ONE message, in order."""
    conversation = create(client)
    fake_llm.script(
        tool_round(
            tool_use_block("weather", {"location": "Tokyo"}, block_id="tu_1"),
            tool_use_block("calculator", {"expression": "85*0.15"}, block_id="tu_2"),
        ),
        text_response("It's mild in Tokyo, and a 15% tip on $85 is $12.75."),
    )

    reply = send(client, conversation, "Weather in Tokyo, and 15% tip on $85?")

    assert reply.status_code == 200
    tools_used = reply.json()["tools_used"]
    assert [t["tool"] for t in tools_used] == ["weather", "calculator"]
    assert all(t["success"] for t in tools_used)
    assert tools_used[1]["output"] == {"result": 12.75}

    results = last_user_message(fake_llm.requests[1])["content"]
    assert [r["type"] for r in results] == ["tool_result", "tool_result"]
    assert [r["tool_use_id"] for r in results] == ["tu_1", "tu_2"]


def test_ac_16_tool_error_handled(client, fake_llm):
    """Required test 4 (S1:352): a tool error doesn't fail the request; the LLM sees it."""
    conversation = create(client)
    fake_llm.script(
        tool_round(tool_use_block("calculator", {"expression": "1/0"})),
        text_response("You can't divide by zero."),
    )

    reply = send(client, conversation, "What's 1/0?")

    assert reply.status_code == 200
    [used] = reply.json()["tools_used"]
    assert used["success"] is False
    assert used["output"] is None
    assert used["error"] == "Division by zero"

    [result] = last_user_message(fake_llm.requests[1])["content"]
    assert result["is_error"] is True
    assert "Division by zero" in result["content"]


def test_ac_21_token_sum(client, fake_llm):
    conversation = create(client)
    fake_llm.script(
        tool_round(
            tool_use_block("calculator", {"expression": "2+2"}), input_tokens=10, output_tokens=5
        ),
        text_response("4", input_tokens=20, output_tokens=7),
    )

    reply = send(client, conversation, "2+2?")

    assert reply.json()["tokens_used"] == 42
    assistant = client.get(f"/conversations/{conversation}").json()["messages"][-1]
    assert assistant["tokens_used"] == 42


def test_ac_5_get_history(client, fake_llm):
    conversation = create(client)
    fake_llm.script(
        tool_round(tool_use_block("calculator", {"expression": "2+2"})),
        text_response("4"),
    )
    send(client, conversation, "2+2?")

    messages = client.get(f"/conversations/{conversation}").json()["messages"]

    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert all("created_at" in m for m in messages)
    assistant = messages[1]
    assert assistant["status"] == "complete"
    assert assistant["content"] == "4"
    assert len(assistant["tools_used"]) == 1
    assert assistant["tokens_used"] == 30  # 2 calls of (10 in + 5 out)


def test_ac_44_tool_execution_logging(client, fake_llm):
    """Required test 6 (S1:354): every tool call is a ToolExecution row."""
    conversation = create(client)
    fake_llm.script(
        tool_round(
            tool_use_block("calculator", {"expression": "2+2"}),
            tool_use_block("calculator", {"expression": "1/0"}),
        ),
        text_response("4, and 1/0 has no answer."),
    )
    send(client, conversation, "2+2 and 1/0?")

    with client.app.state.session_factory() as session:
        rows = session.scalars(select(ToolExecution).order_by(ToolExecution.id)).all()
        assistant_id = rows[0].message.id
        assert rows[0].message.role == "assistant"

        assert len(rows) == 2
        assert all(row.message_id == assistant_id for row in rows)
        ok, failed = rows
        assert ok.tool_name == "calculator"
        assert ok.input == {"expression": "2+2"}
        assert ok.success is True
        assert ok.output == {"result": 4.0}
        assert ok.error_message is None
        assert failed.success is False
        assert failed.output is None
        assert failed.error_message == "Division by zero"
        assert all(row.execution_time_ms >= 0 for row in rows)
        assert all(row.created_at is not None for row in rows)


def test_tool_rounds_repeat_until_final_answer(client, fake_llm):
    """FR-12: tool rounds repeat until the LLM answers; each round's blocks go back."""
    conversation = create(client)
    fake_llm.script(
        tool_round(text_block("Let me check."), tool_use_block("calculator", {"expression": "2+2"})),
        tool_round(tool_use_block("calculator", {"expression": "4*10"})),
        text_response("40"),
    )

    reply = send(client, conversation, "(2+2)*10?")

    assert reply.json()["message"]["content"] == "40"
    assert [t["output"] for t in reply.json()["tools_used"]] == [{"result": 4.0}, {"result": 40.0}]
    assert len(fake_llm.requests) == 3
    third = fake_llm.requests[2]["messages"]
    # user, assistant (round 1), user (results 1), assistant (round 2), user (results 2)
    assert [m["role"] for m in third] == ["user", "assistant", "user", "assistant", "user"]
    assert third[1]["content"][0] == {"type": "text", "text": "Let me check."}
    assert all(r["tool_choice"] == {"type": "auto"} for r in fake_llm.requests)
