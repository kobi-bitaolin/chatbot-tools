"""The tool executor (architecture §3.2): runs one round of tool calls.

All calls of a round run at the same time on one shared thread pool, and the
results come back in the order the LLM asked for them. The executor never
raises: every failure becomes a ToolResult with success false.

T-11 adds: unknown-tool message, JSON Schema validation, the round timeout.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

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
    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    def run_round(self, calls: list[ToolCall]) -> list[ToolResult]:
        futures = [_POOL.submit(self._run_one, call) for call in calls]
        # Waiting in request order gives results in request order,
        # whichever call finishes first.
        return [future.result() for future in futures]

    def _run_one(self, call: ToolCall) -> ToolResult:
        start = time.perf_counter()
        output, error = None, None
        try:
            tool = self._registry.get(call.name)
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
