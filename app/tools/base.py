"""Shared tool pieces (architecture §3.1). The Tool class is added in T-6."""


class ToolError(Exception):
    """A tool failed in an expected way. The message is the error text the LLM sees."""
