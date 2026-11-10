"""Tool loop robustness (T-11): FR-15, FR-16, FR-17, FR-18, NFR-8.

Every failure here becomes an error result for the LLM; the request itself
always returns 200 (FR-16).
"""

import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import ToolExecution
from tests.fake_llm import response, text_response, tool_use_block


def tool_round(*blocks):
    return response(*blocks, stop_reason="tool_use")


def send(client, content="Hi"):
    conversation = client.post("/conversations", json={}).json()["id"]
    return client.post(f"/conversations/{conversation}/messages", json={"content": content})


def executions(client):
    with client.app.state.session_factory() as session:
        return session.scalars(select(ToolExecution).order_by(ToolExecution.id)).all()


def last_results(request):
    """The tool_result blocks in the last user message of an LLM request."""
    return request["messages"][-1]["content"]


def patch_run(monkeypatch, app, tool_name, fake_run):
    """Replace a tool's `run` for one test only.

    The registry holds the tool modules' shared TOOL objects, so a plain
    assignment would leak into every later test; monkeypatch undoes it.
    """
    monkeypatch.setattr(app.state.registry.get(tool_name), "run", fake_run)


def test_ac_15_result_order(client, fake_llm, monkeypatch):
    real_run = client.app.state.registry.get("weather").run

    def slow_weather(**kwargs):
        time.sleep(0.2)
        return real_run(**kwargs)

    patch_run(monkeypatch, client.app, "weather", slow_weather)
    fake_llm.script(
        tool_round(
            tool_use_block("weather", {"location": "Paris"}, block_id="w"),
            tool_use_block("calculator", {"expression": "1+1"}, block_id="c"),
        ),
        text_response("done"),
    )

    reply = send(client)

    assert [t["tool"] for t in reply.json()["tools_used"]] == ["weather", "calculator"]
    assert [r["tool_use_id"] for r in last_results(fake_llm.requests[1])] == ["w", "c"]


def test_ac_17_invalid_params(client, fake_llm):
    fake_llm.script(
        tool_round(tool_use_block("calculator", {"expr": "1"})), text_response("Sorry")
    )

    reply = send(client)

    assert reply.status_code == 200
    [used] = reply.json()["tools_used"]
    assert used["success"] is False
    assert used["output"] is None
    assert used["error"].startswith("Invalid input:")
    [result] = last_results(fake_llm.requests[1])
    assert result["is_error"] is True and result["content"].startswith("Invalid input:")


def test_ac_17_unexpected_field(client, fake_llm, monkeypatch):
    ran = []
    patch_run(monkeypatch, client.app, "calculator", lambda **kwargs: ran.append(kwargs) or {})
    fake_llm.script(
        tool_round(tool_use_block("calculator", {"expression": "1+1", "precision": 2})),
        text_response("Sorry"),
    )

    reply = send(client)

    assert reply.status_code == 200
    [used] = reply.json()["tools_used"]
    assert (used["success"], used["error"]) == (
        False, "Invalid input: unexpected field 'precision'"
    )
    assert ran == []  # the tool never ran


def test_ac_18_unknown_tool(client, fake_llm):
    fake_llm.script(tool_round(tool_use_block("teleport", {"to": "Mars"})), text_response("No"))

    reply = send(client)

    assert reply.status_code == 200
    [used] = reply.json()["tools_used"]
    assert (used["success"], used["error"]) == (False, "Unknown tool: teleport")
    assert executions(client)[0].error_message == "Unknown tool: teleport"


@pytest.fixture
def slow_client(tmp_path, fake_llm, monkeypatch):
    """TOOL_TIMEOUT_S=1.0, and weather blocks until the test ends (spec §8)."""
    release = threading.Event()
    app = create_app(Settings(data_dir=tmp_path, tool_timeout_s=1.0), llm=fake_llm)
    patch_run(monkeypatch, app, "weather", lambda **kwargs: release.wait() or {})
    with TestClient(app) as test_client:
        yield test_client
    release.set()  # the blocked thread finishes, so no thread is left running


def test_ac_19_timeout_partial_results(slow_client, fake_llm):
    fake_llm.script(
        tool_round(
            tool_use_block("weather", {"location": "Paris"}),
            tool_use_block("calculator", {"expression": "2+2"}),
        ),
        text_response("Partly done"),
    )

    start = time.perf_counter()
    reply = send(slow_client)
    elapsed = time.perf_counter() - start

    assert reply.status_code == 200
    assert elapsed < 1.5  # NFR-8
    weather, calculator = reply.json()["tools_used"]
    assert (weather["success"], weather["error"], weather["output"]) == (
        False, "Timed out after 1s", None
    )
    assert (calculator["success"], calculator["output"]) == (True, {"result": 4.0})
    rows = executions(slow_client)
    assert [(r.tool_name, r.success) for r in rows] == [("weather", False), ("calculator", True)]


def test_ac_20_round_limit(client, fake_llm):
    fake_llm.script(
        *[tool_round(tool_use_block("calculator", {"expression": "1+1"})) for _ in range(6)],
        text_response("I stopped after 5 rounds."),
    )

    reply = send(client)

    assert reply.status_code == 200
    body = reply.json()
    assert body["message"]["content"] == "I stopped after 5 rounds."
    assert len(fake_llm.requests) == 7
    assert [r["tool_choice"] for r in fake_llm.requests] == [{"type": "auto"}] * 6 + [
        {"type": "none"}
    ]
    used = body["tools_used"]
    assert len(used) == 6
    assert all(u["success"] for u in used[:5])
    assert used[5] == {
        "tool": "calculator",
        "input": {"expression": "1+1"},
        "output": None,
        "success": False,
        "error": "Tool call limit reached",
        "execution_time_ms": 0,
    }
    # The 7th LLM call sees the limit error for the 6th call.
    [result] = last_results(fake_llm.requests[6])
    assert (result["is_error"], result["content"]) == (True, "Tool call limit reached")
    rows = executions(client)
    assert len(rows) == 6
    assert (rows[5].success, rows[5].error_message) == (False, "Tool call limit reached")


def test_fr_15_forced_last_call_always_ends_the_loop(client, fake_llm):
    # Even if the LLM asks for tools on the "none" call, nothing more runs. The
    # answer is not usable, so it ends as an unexpected response (FR-26, T-12).
    fake_llm.script(
        *[tool_round(tool_use_block("calculator", {"expression": "1+1"})) for _ in range(7)]
    )

    reply = send(client)

    assert reply.status_code == 502
    assert reply.json() == {"detail": "Unexpected LLM response"}
    assert len(fake_llm.requests) == 7
    assert len(executions(client)) == 6
