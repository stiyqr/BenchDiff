"""T4 — duration parsing, the smallest pure function in the phase."""

from __future__ import annotations

import pytest

from benchdiff.duration import parse_duration

# T4: timeout accepts int, float and unit-suffixed strings.
DURATION_ROWS: list[tuple[object, float]] = [
    (300, 300.0),
    (300.0, 300.0),
    ("300s", 300.0),
    ("5m", 300.0),
    ("1h", 3600.0),
    ("0.5s", 0.5),
    ("1.5h", 5400.0),
    ("2m", 120.0),
]

DURATION_ERROR_ROWS: list[tuple[object, str]] = [
    ("fast", "invalid duration"),
    ("300", "invalid duration"),  # a bare string has no unit
    ("5S", "invalid duration"),  # units are lowercase
    ("1h30m", "invalid duration"),  # one unit per duration
    ("", "invalid duration"),
    (0, "greater than 0"),
    (-5, "greater than 0"),
    ("0s", "greater than 0"),
    (True, "expected a number"),
    (None, "expected a number"),
    ([300], "expected a number"),
    ({"seconds": 300}, "expected a number"),
]


@pytest.mark.parametrize(("value", "expected"), DURATION_ROWS, ids=repr)
def test_duration_is_converted_to_seconds(value: object, expected: float) -> None:
    assert parse_duration(value) == expected


@pytest.mark.parametrize(("value", "fragment"), DURATION_ERROR_ROWS, ids=repr)
def test_invalid_duration_is_rejected(value: object, fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        parse_duration(value)
