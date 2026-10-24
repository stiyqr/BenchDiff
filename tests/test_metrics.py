"""T3, T6, T23-T29, T37-T39 — metric declaration and extraction rules."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest

from benchdiff.errors import ConfigError
from benchdiff.manifest import load_manifest
from benchdiff.model import Direction, MetricSpec
from benchdiff.validate import validate_manifest

FIXTURES = Path(__file__).parent / "fixtures"

BASE = r"""[project]
name = "app"

[bench]
command = "run"

[[bench.metrics]]
name = "latency"
unit = "ns/op"
direction = "lower_is_better"
extract = { regex = '([0-9.]+)' }
"""

REGEX = r"""extract = { regex = '([0-9.]+)' }"""


def edited(old: str, new: str) -> str:
    if old not in BASE:
        raise AssertionError(f"base manifest does not contain {old!r}")
    return BASE.replace(old, new, 1)


def test_two_metrics_are_both_compiled_in_order() -> None:
    """T3: declared order is preserved and every pattern is compiled."""
    loaded = load_manifest(FIXTURES / "two_metrics.toml")
    data = validate_manifest(loaded.raw, source=str(loaded.path))

    assert [metric.name for metric in data.metrics] == ["latency", "throughput"]
    assert [metric.direction for metric in data.metrics] == [
        Direction.LOWER_IS_BETTER,
        Direction.HIGHER_IS_BETTER,
    ]
    assert data.metrics[0].pattern.search("bench took 42.5 ns")
    assert data.metrics[1].pattern.search("bench did 900 req/s")


def test_capture_group_can_be_selected() -> None:
    """T6: a three-group pattern with ``group = 2`` keeps the second group."""
    text = edited(
        REGEX,
        r"""extract = { regex = '(a)-(b)-(c)' }
group = 2""",
    )
    data = validate_manifest(tomllib.loads(text), source="benchdiff.toml")

    metric = data.metrics[0]
    assert metric.pattern.groups == 3
    assert metric.group == 2


def test_metric_spec_cannot_hold_a_string_pattern() -> None:
    """The plan's invariant: a compiled pattern is the only shape that exists."""
    with pytest.raises(ValueError, match="compiled pattern"):
        MetricSpec(
            name="latency",
            label="latency",
            unit="ns/op",
            direction=Direction.LOWER_IS_BETTER,
            pattern="([0-9.]+)",  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class ErrorCase:
    row: str
    text: str
    expected: tuple[str, ...]


SECOND_METRIC = """
[[bench.metrics]]
name = "latency"
unit = "B/op"
direction = "lower_is_better"
extract = { regex = '(\\d+)' }
"""

ERROR_CASES = [
    ErrorCase(
        "T23",
        BASE + SECOND_METRIC,
        ("bench.metrics[1].name", 'duplicate metric name "latency"'),
    ),
    ErrorCase(
        "T24",
        edited('name = "latency"', 'name = "Latency Per Op"'),
        ("bench.metrics[0].name", "[a-z0-9_]+", "Latency Per Op"),
    ),
    ErrorCase(
        "T25",
        edited('unit = "ns/op"\n', ""),
        ("bench.metrics[0].unit", "is required"),
    ),
    ErrorCase(
        "T26",
        edited('direction = "lower_is_better"', 'direction = "faster"'),
        (
            "bench.metrics[0].direction",
            '"faster" is not valid',
            "lower_is_better, higher_is_better",
        ),
    ),
    ErrorCase(
        "T27",
        edited(REGEX, r"""extract = { regex = '(' }"""),
        ("bench.metrics[0].extract.regex", "invalid pattern", "unterminated subpattern"),
    ),
    ErrorCase(
        "T28",
        edited(REGEX, r"""extract = { regex = '\d+' }"""),
        ("bench.metrics[0].extract.regex", "at least one capture group"),
    ),
    ErrorCase(
        "T29",
        edited(
            REGEX,
            r"""extract = { regex = '(\d+)' }
group = 3""",
        ),
        ("bench.metrics[0].group", "group 3 does not exist"),
    ),
    ErrorCase(
        "X-group-zero",
        edited(
            REGEX,
            r"""extract = { regex = '(\d+)' }
group = 0""",
        ),
        ("bench.metrics[0].group", "1 or greater"),
    ),
    ErrorCase(
        "T37",
        edited(REGEX, r"""extract = { regex = '(\d+)', json_path = "$.t" }"""),
        ("bench.metrics[0].extract", "exactly one extractor", "json_path, regex"),
    ),
    ErrorCase(
        "T38",
        edited(REGEX, "extract = {}"),
        ("bench.metrics[0].extract", "exactly one extractor"),
    ),
    ErrorCase(
        "T39",
        edited(REGEX, r"""extract = { json_path = "$.t" }"""),
        ("bench.metrics[0].extract.json_path", "not implemented", "phase 3"),
    ),
    ErrorCase(
        "X-unknown-extractor",
        edited(REGEX, r"""extract = { regexx = "$.t" }"""),
        ("bench.metrics[0].extract", 'unknown extractor "regexx"', 'did you mean "regex"'),
    ),
    ErrorCase(
        "X-empty-label",
        edited('name = "latency"', 'name = "latency"\nlabel = ""'),
        ("bench.metrics[0].label", "must not be empty"),
    ),
]


@pytest.mark.parametrize("case", ERROR_CASES, ids=[case.row for case in ERROR_CASES])
def test_invalid_metric_is_rejected(case: ErrorCase) -> None:
    with pytest.raises(ConfigError) as excinfo:
        validate_manifest(tomllib.loads(case.text), source="benchdiff.toml")

    message = str(excinfo.value)
    for fragment in case.expected:
        assert fragment in message
