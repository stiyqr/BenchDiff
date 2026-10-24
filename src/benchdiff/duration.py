"""Parse durations such as ``300``, ``"300s"``, ``"5m"`` and ``"1h"`` into seconds."""

from __future__ import annotations

import re

from benchdiff.errors import describe_value

_DURATION = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>[smh])")
_SECONDS_PER_UNIT = {"s": 1.0, "m": 60.0, "h": 3600.0}


def parse_duration(value: object) -> float:
    """Return ``value`` in seconds, or raise ``ValueError`` with a user-facing message."""
    seconds = _to_seconds(value)
    if seconds <= 0:
        raise ValueError(f"duration must be greater than 0, got {describe_value(value)}")
    return seconds


def _to_seconds(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError(f"expected a number or a duration string, got {describe_value(value)}")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = _DURATION.fullmatch(value)
        if match is None:
            raise ValueError(
                f"invalid duration {value!r}; expected a number with a unit, "
                'e.g. "300s", "5m" or "1h"'
            )
        return float(match["value"]) * _SECONDS_PER_UNIT[match["unit"]]
    raise ValueError(f"expected a number or a duration string, got {describe_value(value)}")
