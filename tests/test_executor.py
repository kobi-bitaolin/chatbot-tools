"""Tool executor core (T-6, architecture §3.2): parallel run, request order, error catching.

Parallelism is checked with Events, not timing, so the tests are never flaky.
T-11 adds: unknown tools, schema validation and the round deadline (below).
"""

import logging
import threading

from app.tools.base import Tool, ToolError
from app.tools.executor import ToolCall, ToolExecutor
from app.tools.registry import ToolRegistry

SCHEMA = {"type": "object", "properties": {}}


def make_tool(name, run, schema=SCHEMA):
    return Tool(name=name, description=name, parameters=schema, run=run)


def test_executor_runs_in_parallel_and_keeps_request_order():
    second_started = threading.Event()

    def first(**_):
        # Waits for the second tool. Run one after the other, this would time out.
        return {"saw_second": second_started.wait(timeout=2)}

    def second(**_):
        second_started.set()
        return {"done": True}

    executor = ToolExecutor(ToolRegistry([make_tool("first", first), make_tool("second", second)]))
    results = executor.run_round([ToolCall("first", {}), ToolCall("second", {})])

    assert [r.tool for r in results] == ["first", "second"]  # request order
    assert results[0].output == {"saw_second": True}  # both ran at the same time


def test_executor_success_result_shape():
    executor = ToolExecutor(ToolRegistry([make_tool(
        "echo",
        lambda text: {"text": text},
        {"type": "object", "properties": {"text": {"type": "string"}}},
    )]))

    [result] = executor.run_round([ToolCall("echo", {"text": "hi"})])

    assert result.to_dict() == {
        "tool": "echo",
        "input": {"text": "hi"},
        "output": {"text": "hi"},
        "success": True,
        "error": None,
        "execution_time_ms": result.execution_time_ms,
    }
    assert isinstance(result.execution_time_ms, int) and result.execution_time_ms >= 0


def test_executor_catches_tool_error():
    def fails(**_):
        raise ToolError("Division by zero")

    executor = ToolExecutor(ToolRegistry([make_tool("calc", fails)]))

    [result] = executor.run_round([ToolCall("calc", {})])

    assert (result.success, result.output, result.error) == (False, None, "Division by zero")


def test_executor_catches_unexpected_error_and_logs_it(caplog):
    def crashes(**_):
        raise RuntimeError("internal detail")

    executor = ToolExecutor(ToolRegistry([make_tool("buggy", crashes)]))

    with caplog.at_level(logging.ERROR):
        [result] = executor.run_round([ToolCall("buggy", {})])

    assert (result.success, result.error) == (False, "Tool failed unexpectedly")
    assert "internal detail" not in result.error  # internals never reach the LLM
    assert "internal detail" in caplog.text  # but the traceback is logged


def test_executor_real_calculator(tmp_path):
    from app.tools.registry import default_registry

    [result] = ToolExecutor(default_registry(tmp_path / "sample.db")).run_round([ToolCall("calculator", {"expression": "2+2"})])

    assert (result.success, result.output) == (True, {"result": 4.0})


def test_fr_18_timeout_message_uses_g_format():
    release = threading.Event()
    executor = ToolExecutor(
        ToolRegistry([make_tool("slow", lambda **_: release.wait() or {})]), timeout_s=0.5
    )
    try:
        [result] = executor.run_round([ToolCall("slow", {})])
    finally:
        release.set()
    assert (result.success, result.error, result.output) == (False, "Timed out after 0.5s", None)


def test_fr_18_one_deadline_for_the_whole_round():
    """Two slow calls share ONE deadline: the round takes ~1 timeout, not 2."""
    import time

    release = threading.Event()
    slow = make_tool("slow", lambda **_: release.wait() or {})
    executor = ToolExecutor(ToolRegistry([slow]), timeout_s=0.3)
    start = time.perf_counter()
    try:
        results = executor.run_round([ToolCall("slow", {}), ToolCall("slow", {})])
    finally:
        release.set()
    assert time.perf_counter() - start < 0.55
    assert [r.error for r in results] == ["Timed out after 0.3s"] * 2


def test_fr_17_schema_limits_are_checked(tmp_path):
    from app.tools.registry import default_registry

    executor = ToolExecutor(default_registry(tmp_path / "sample.db"))
    wrong_type, too_long = executor.run_round(
        [ToolCall("datetime", {"operation": "calculate", "datetime": "2026-11-10", "days": "3"}),
         ToolCall("calculator", {"expression": "1+" * 100 + "1"})]  # 201 characters
    )
    assert wrong_type.error.startswith("Invalid input:")
    # AC-33: the 201-char expression is stopped by the schema's maxLength, before the parser.
    assert too_long.error.startswith("Invalid input:")
    assert "too long" in too_long.error
