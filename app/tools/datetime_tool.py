"""Datetime tool (FR-31, FR-17 datetime part, S1:210-219).

Three operations: `current`, `convert` and `calculate`. The output is always
`{"result": "<ISO 8601>"}`. Like the weather tool's random generator, the
clock is a parameter, so tests pass a fixed clock and get the same result.

The per-operation checks (which fields each operation needs) live here,
because they are rules of this tool. They raise ToolError with
"Invalid input: ...", the same prefix the executor's schema check uses (T-11).

The module is imported as `dt` because the tool's own parameters are called
`datetime` and `timezone` (the names in the spec), which would hide the
standard names inside `run`.
"""

import datetime as dt
from collections.abc import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.tools.base import Tool, ToolError


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        # ValueError covers names that aren't even valid paths, e.g. "" or "../x".
        raise ToolError(f"Unknown timezone: {name}") from None


def _parse(text: str) -> dt.datetime:
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        raise ToolError("Invalid input: datetime must be ISO 8601") from None


def run(
    operation: str,
    timezone: str | None = None,
    datetime: str | None = None,
    from_tz: str | None = None,
    to_tz: str | None = None,
    days: int | None = None,
    hours: int | None = None,
    minutes: int | None = None,
    clock: Callable[[], dt.datetime] = utc_now,
) -> dict:
    if operation == "current":
        now = clock().astimezone(_zone(timezone or "UTC"))
        return {"result": now.isoformat()}

    if operation == "convert":
        if datetime is None or from_tz is None or to_tz is None:
            raise ToolError("Invalid input: convert needs datetime, from_tz and to_tz")
        moment = _parse(datetime)
        if moment.tzinfo is not None:
            raise ToolError("Invalid input: datetime must not include an offset for convert")
        local = moment.replace(tzinfo=_zone(from_tz))
        return {"result": local.astimezone(_zone(to_tz)).isoformat()}

    if operation == "calculate":
        if datetime is None:
            raise ToolError("Invalid input: calculate needs datetime")
        if days is None and hours is None and minutes is None:
            raise ToolError("Invalid input: calculate needs at least one of days, hours, minutes")
        moment = _parse(datetime)
        # The result keeps the input's offset, or has none if the input had none (FR-31).
        moment += dt.timedelta(days=days or 0, hours=hours or 0, minutes=minutes or 0)
        return {"result": moment.isoformat()}

    # The schema's enum catches this first once T-11 adds validation.
    raise ToolError("Invalid input: operation must be current, convert or calculate")


TOOL = Tool(
    name="datetime",
    description=(
        "Current date/time, timezone conversion, or adding/subtracting time. "
        "Timezones are IANA names like Europe/London."
    ),
    parameters={
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["current", "convert", "calculate"],
                "description": "current: now; convert: between timezones; calculate: add/subtract",
            },
            "timezone": {"type": "string", "description": "For current, default UTC"},
            "datetime": {
                "type": "string",
                "description": "ISO 8601, e.g. '2026-11-10T12:00:00'. For convert: no offset",
            },
            "from_tz": {"type": "string", "description": "For convert"},
            "to_tz": {"type": "string", "description": "For convert"},
            "days": {"type": "integer", "description": "For calculate, may be negative"},
            "hours": {"type": "integer", "description": "For calculate, may be negative"},
            "minutes": {"type": "integer", "description": "For calculate, may be negative"},
        },
        "required": ["operation"],
    },
    run=run,
)
