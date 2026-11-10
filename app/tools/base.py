"""Shared tool pieces (architecture §3.1)."""

from collections.abc import Callable
from dataclasses import dataclass


class ToolError(Exception):
    """A tool failed in an expected way. The message is the error text the LLM sees."""


@dataclass  # not frozen: tests replace `run` to simulate slow or broken tools (AC-19)
class Tool:
    name: str
    description: str  # tells the LLM when to use the tool (D1)
    parameters: dict  # JSON Schema in the S1:102-119 format, limits included
    run: Callable[..., dict]  # returns the output dict, or raises ToolError
