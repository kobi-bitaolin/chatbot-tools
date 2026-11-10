"""Datetime tool tests (T-9): FR-31, FR-17 (datetime part)."""

from datetime import datetime, timezone

import pytest

from app.tools import datetime_tool
from app.tools.base import ToolError


def fixed_clock():
    return datetime(2026, 11, 10, 12, 0, 0, tzinfo=timezone.utc)


def run(**kwargs):
    return datetime_tool.run(clock=fixed_clock, **kwargs)


def test_ac_40_datetime_operations():
    assert run(operation="current", timezone="Asia/Tokyo") == {
        "result": "2026-11-10T21:00:00+09:00"
    }
    assert run(
        operation="convert",
        datetime="2026-11-10T12:00:00",
        from_tz="Europe/London",
        to_tz="Asia/Tokyo",
    ) == {"result": "2026-11-10T21:00:00+09:00"}
    assert run(operation="calculate", datetime="2026-11-10T12:00:00", days=30) == {
        "result": "2026-12-10T12:00:00"
    }
    assert run(operation="calculate", datetime="2026-11-10T12:00:00", days=-10) == {
        "result": "2026-10-31T12:00:00"
    }


def test_fr_31_defaults_and_offsets():
    # current without a timezone is UTC, with an offset.
    assert run(operation="current") == {"result": "2026-11-10T12:00:00+00:00"}
    # A summer clock too: London is UTC+0 in November, so only July tells them apart.
    summer = lambda: datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)  # noqa: E731
    assert datetime_tool.run(operation="current", clock=summer) == {
        "result": "2026-07-01T12:00:00+00:00"
    }
    # calculate keeps the input's offset; hours and minutes may be negative.
    assert run(
        operation="calculate", datetime="2026-11-10T12:00:00+02:00", hours=-1, minutes=30
    ) == {"result": "2026-11-10T11:30:00+02:00"}


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"operation": "current", "timezone": "Mars/Base"}, "Unknown timezone: Mars/Base"),
        (
            {"operation": "convert", "datetime": "2026-11-10T12:00:00",
             "from_tz": "Mars/Base", "to_tz": "UTC"},
            "Unknown timezone: Mars/Base",
        ),
        (
            {"operation": "convert", "datetime": "2026-11-10T12:00:00+02:00",
             "from_tz": "Europe/London", "to_tz": "Asia/Tokyo"},
            "Invalid input: datetime must not include an offset for convert",
        ),
    ],
)
def test_ac_41_datetime_exact_errors(kwargs, message):
    with pytest.raises(ToolError) as exc:
        run(**kwargs)
    assert str(exc.value) == message


@pytest.mark.parametrize(
    "kwargs",
    [
        # convert without to_tz
        {"operation": "convert", "datetime": "2026-11-10T12:00:00", "from_tz": "UTC"},
        # calculate without days/hours/minutes
        {"operation": "calculate", "datetime": "2026-11-10T12:00:00"},
        # calculate without datetime
        {"operation": "calculate", "days": 1},
        # not ISO 8601
        {"operation": "calculate", "datetime": "next Tuesday", "days": 1},
    ],
)
def test_ac_41_datetime_errors(kwargs):
    with pytest.raises(ToolError) as exc:
        run(**kwargs)
    assert str(exc.value).startswith("Invalid input:")


def test_ac_41_success_output_has_only_result():
    outputs = [
        run(operation="current"),
        run(operation="convert", datetime="2026-11-10T12:00:00", from_tz="UTC", to_tz="UTC"),
        run(operation="calculate", datetime="2026-11-10T12:00:00", minutes=5),
    ]
    for output in outputs:
        assert set(output) == {"result"}


def test_fr_31_tool_definition():
    tool = datetime_tool.TOOL
    assert tool.name == "datetime"
    assert tool.parameters["required"] == ["operation"]
    assert tool.parameters["properties"]["operation"]["enum"] == [
        "current", "convert", "calculate"
    ]
