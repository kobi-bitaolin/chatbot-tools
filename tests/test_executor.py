"""Tool executor core (T-6, architecture §3.2): parallel run, request order, error catching.

Parallelism is checked with Events, not timing, so the tests are never flaky.
Unknown tools, schema validation and timeouts are T-11.
"""

import logging
import threading

from app.tools.base import Tool, ToolError
from app.tools.executor import ToolCall, ToolExecutor
from app.tools.registry import ToolRegistry

SCHEMA = {"type": "object", "properties": {}}


def make_tool(name, run):
    return Tool(name=name, description=name, parameters=SCHEMA, run=run)


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
    executor = ToolExecutor(ToolRegistry([make_tool("echo", lambda text: {"text": text})]))

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
