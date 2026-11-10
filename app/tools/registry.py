"""The tool registry (architecture §3.1, FR-32, FR-33).

It holds the tools in a fixed order and gives their definitions to two
places, in the format each one needs:
- `GET /tools` gets the S1 format (`parameters`, all limits included).
- The LLM gets the Anthropic format (`input_schema`, `strict: true`), with
  the keywords strict mode doesn't support removed.
"""

from app.tools import calculator, weather, web_search
from app.tools.base import Tool

# FR-33: keywords strict tool schemas don't support. They stay in `parameters`,
# so GET /tools shows them and the executor still enforces them (T-11).
STRICT_UNSUPPORTED = {"maxLength", "minLength", "minimum", "maximum", "multipleOf"}


def strict_schema(schema: dict) -> dict:
    """A copy of `schema` without STRICT_UNSUPPORTED, and with closed objects."""
    result = {key: value for key, value in schema.items() if key not in STRICT_UNSUPPORTED}
    if "properties" in result:
        # Recurse into each property's schema. Property names themselves are
        # never removed, even one called "minimum".
        result["properties"] = {
            name: strict_schema(sub) for name, sub in result["properties"].items()
        }
    if "items" in result:
        result["items"] = strict_schema(result["items"])
    if result.get("type") == "object":
        result["additionalProperties"] = False
    return result


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
            {
                "name": t.name,
                "description": t.description,
                "input_schema": strict_schema(t.parameters),
                "strict": True,
            }
            for t in self._tools.values()
        ]


def default_registry() -> ToolRegistry:
    # datetime (T-9) and database_query (T-10) are added here.
    return ToolRegistry([calculator.TOOL, web_search.TOOL, weather.TOOL])
