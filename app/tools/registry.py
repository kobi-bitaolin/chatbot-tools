"""The tool registry (architecture §3.1, FR-32, FR-33).

It holds the tools in a fixed order and gives their definitions to two
places, in the format each one needs:
- `GET /tools` gets the S1 format: `{name, description, parameters}`.
- The LLM gets the Anthropic format: the same schema under the key
  `input_schema` (the only difference between the two formats).
"""

from app.tools import calculator, weather, web_search
from app.tools.base import Tool


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {tool.name: tool for tool in tools}  # dicts keep insertion order

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def list_tools(self) -> list[dict]:
        """FR-32: the S1 format, for GET /tools."""
        return [
            {"name": t.name, "description": t.description, "parameters": t.parameters}
            for t in self._tools.values()
        ]

    def api_definitions(self) -> list[dict]:
        """FR-33: the Anthropic format, for every LLM request."""
        return [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in self._tools.values()
        ]


def default_registry() -> ToolRegistry:
    # datetime (T-9) and database_query (T-10) are added here.
    return ToolRegistry([calculator.TOOL, web_search.TOOL, weather.TOOL])
