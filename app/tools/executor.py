"""The tool executor (architecture §3.2): runs one round of tool calls.

All calls of a round run at the same time on one shared thread pool, and the
results come back in the order the LLM asked for them. The executor never
raises: every failure becomes a ToolResult with success false (FR-16):
- an unknown tool name: "Unknown tool: X",
- an input that breaks the tool's JSON Schema, or has a field the schema
  doesn't list: "Invalid input: ..." (FR-17),
- a call still running at the round's deadline: "Timed out after Ns" (FR-18),
- a ToolError from the tool: its message; any other exception: a fixed text.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

import jsonschema

from app.tools.base import ToolError
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Created once for the whole app, never per request. A `with` block would
# wait for every thread on exit, which would defeat the T-11 timeout.
_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="tool")

UNEXPECTED_ERROR = "Tool failed unexpectedly"


@dataclass
class ToolCall:
    name: str
    input: dict


@dataclass
class ToolResult:
    """S1:121-131 plus `error` (G3, FR-14)."""

    tool: str
    input: dict
    output: dict | None
    success: bool
    error: str | None
    execution_time_ms: int

    def to_dict(self) -> dict:
        return asdict(self)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, timeout_s: float = 5.0):
        self._registry = registry
        self._timeout_s = timeout_s  # TOOL_TIMEOUT_S, passed in by app/main.py

    def run_round(self, calls: list[ToolCall]) -> list[ToolResult]:
        start = time.perf_counter()
        deadline = start + self._timeout_s  # ONE deadline for the whole round (FR-18)
        futures = [_POOL.submit(self._run_one, call) for call in calls]
        results = []
        # Waiting in request order gives results in request order,
        # whichever call finishes first.
        for call, future in zip(calls, futures):
            remaining = max(0.0, deadline - time.perf_counter())
            try:
                results.append(future.result(timeout=remaining))
            except TimeoutError:
                # Python can't stop a thread: the call finishes in the
                # background, and its result is ignored (architecture §3.2).
                elapsed_ms = round((time.perf_counter() - start) * 1000)
                results.append(
                    _failed(call, f"Timed out after {self._timeout_s:g}s", elapsed_ms)
                )
        return results

    def _run_one(self, call: ToolCall) -> ToolResult:
        start = time.perf_counter()
        output, error = None, None
        try:
            tool = self._registry.get(call.name)
            if tool is None:
                raise ToolError(f"Unknown tool: {call.name}")
            try:
                jsonschema.validate(call.input, tool.parameters)
            except jsonschema.ValidationError as exc:
                raise ToolError(f"Invalid input: {exc.message}") from None
            # The schemas allow extra fields (spec v0.6), but `run` would crash
            # on an argument it doesn't have, so extras are rejected here (FR-17).
            for field in call.input:
                if field not in tool.parameters["properties"]:
                    raise ToolError(f"Invalid input: unexpected field '{field}'")
            output = tool.run(**call.input)
        except ToolError as exc:
            error = str(exc)  # an expected failure: its message is meant for the LLM
        except Exception:
            # A bug: log the traceback, but don't show internals to the LLM.
            logger.exception("Tool %s failed unexpectedly", call.name)
            error = UNEXPECTED_ERROR
        elapsed_ms = round((time.perf_counter() - start) * 1000)
        return ToolResult(
            tool=call.name,
            input=call.input,
            output=output if error is None else None,
            success=error is None,
            error=error,
            execution_time_ms=elapsed_ms,
        )


def _failed(call: ToolCall, error: str, execution_time_ms: int) -> ToolResult:
    return ToolResult(
        tool=call.name,
        input=call.input,
        output=None,
        success=False,
        error=error,
        execution_time_ms=execution_time_ms,
    )
