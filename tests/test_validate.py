"""T1, T2, T5, T17-T22, T30-T36, T40-T43 — the strict manifest walker.

Every error row also asserts the message names the source and the offending key path, which is the
starred contract in ``docs/phase-1.md``.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import pytest

from benchdiff.errors import ConfigError
from benchdiff.manifest import load_manifest
from benchdiff.model import Mode
from benchdiff.validate import validate_manifest

FIXTURES = Path(__file__).parent / "fixtures"

BASE = """\
[project]
name = "app"

[bench]
command = "run"
"""

METRICS = """\
[[bench.metrics]]
name = "latency"
unit = "ns/op"
direction = "lower_is_better"
extract = { regex = "([0-9.]+)" }
"""

VALID = BASE + "\n" + METRICS


def edited(old: str, new: str) -> str:
    """The valid manifest with one literal substitution."""
    if old not in VALID:
        raise AssertionError(f"base manifest does not contain {old!r}")
    return VALID.replace(old, new, 1)


def appended(block: str) -> str:
    return f"{VALID}\n{block}"


def test_minimal_manifest_merges_no_defaults() -> None:
    """T1 at the validate layer: absent scalars stay absent so D22 can hold."""
    data = validate_manifest(tomllib.loads(VALID), source="benchdiff.toml")

    assert data.samples is None
    assert data.warmup is None
    assert data.timeout_seconds is None
    assert data.overlay == ()
    assert data.mode is Mode.OPTIMIZE
    assert data.project_name == "app"
    assert data.language is None


def test_full_manifest_values_are_honoured() -> None:
    """T2 at the validate layer: every declared value survives unchanged."""
    loaded = load_manifest(FIXTURES / "full.toml")
    data = validate_manifest(loaded.raw, source=str(loaded.path))

    assert data.project_name == "banking-core"
    assert data.language == "go"
    assert data.command.startswith("go test -bench=.")
    assert data.samples == 20
    assert data.warmup == 2
    assert data.timeout_seconds == 300.0
    assert data.overlay == ("bench/", "scripts/seed_test_db.sql")
    assert [metric.name for metric in data.metrics] == ["latency", "allocs"]
    assert data.metrics[0].label == "execution latency"
    assert data.metrics[1].label == "allocs"


def test_overlay_paths_are_normalised() -> None:
    """T5: a leading ``./`` is dropped, a trailing slash is kept."""
    text = edited('command = "run"', 'command = "run"\noverlay = ["./bench/", "scripts/seed.sql"]')
    data = validate_manifest(tomllib.loads(text), source="benchdiff.toml")

    assert data.overlay == ("bench/", "scripts/seed.sql")


@dataclass(frozen=True, slots=True)
class ErrorCase:
    row: str
    text: str
    expected: tuple[str, ...]


ERROR_CASES = [
    # -- structure ---------------------------------------------------------------------
    ErrorCase("T17", edited('name = "app"\n', ""), ("project.name", "is required")),
    ErrorCase("T18", edited('command = "run"', ""), ("bench.command", "is required")),
    ErrorCase("T19", VALID.replace(METRICS, ""), ("bench.metrics", "is required")),
    ErrorCase("T20", edited("[bench]", "[benchmark]"), ("unknown table", '"benchmark"', '"bench"')),
    ErrorCase(
        "T21",
        edited('command = "run"', 'command = "run"\nsample = 10'),
        ("bench", 'unknown key "sample"', "samples"),
    ),
    ErrorCase(
        "T22",
        edited('name = "app"', 'name = "app"\ndirection = "faster"'),
        ("project", 'unknown key "direction"'),
    ),
    ErrorCase(
        "X-project-type",
        edited('name = "app"', "name = 7"),
        ("project.name", "expected a string, got 7"),
    ),
    # -- values ------------------------------------------------------------------------
    ErrorCase(
        "T30a",
        edited('command = "run"', 'command = "run"\nsamples = 0'),
        ("bench.samples", "between 1 and 1000"),
    ),
    ErrorCase(
        "T30b",
        edited('command = "run"', 'command = "run"\nsamples = -1'),
        ("bench.samples", "between 1 and 1000"),
    ),
    ErrorCase(
        "T30c",
        edited('command = "run"', 'command = "run"\nsamples = 1001'),
        ("bench.samples", "between 1 and 1000"),
    ),
    ErrorCase(
        "T31",
        edited('command = "run"', 'command = "run"\nsamples = 1.5'),
        ("bench.samples", "expected an integer, got 1.5"),
    ),
    ErrorCase(
        "T32",
        edited('command = "run"', 'command = "run"\nsamples = true'),
        ("bench.samples", "expected an integer, got true"),
    ),
    ErrorCase(
        "T33",
        edited('command = "run"', 'command = "run"\nwarmup = -1'),
        ("bench.warmup", "0 or greater"),
    ),
    ErrorCase(
        "T34a",
        edited('command = "run"', 'command = "run"\ntimeout = "fast"'),
        ("bench.timeout", "invalid duration"),
    ),
    ErrorCase(
        "T34b",
        edited('command = "run"', 'command = "run"\ntimeout = 0'),
        ("bench.timeout", "greater than 0"),
    ),
    ErrorCase(
        "T34c",
        edited('command = "run"', 'command = "run"\ntimeout = -5'),
        ("bench.timeout", "greater than 0"),
    ),
    ErrorCase(
        "T35",
        edited('command = "run"', 'command = "run"\noverlay = ["/etc/passwd"]'),
        ("bench.overlay[0]", "must be relative", "/etc/passwd"),
    ),
    ErrorCase(
        "T36",
        edited('command = "run"', 'command = "run"\noverlay = ["../outside"]'),
        ("bench.overlay[0]", "must not escape", "../outside"),
    ),
    # -- reserved features -------------------------------------------------------------
    ErrorCase(
        "T40",
        edited('name = "app"', 'name = "app"\nmode = "scale"'),
        ("project.mode", "phase 8"),
    ),
    ErrorCase("T41", appended("[scale]\nsteps = [100, 1000]\n"), ("[scale]", "phase 8")),
    ErrorCase("T42", appended("[ai]\nenabled = true\n"), ("[ai]", "phase 9")),
    ErrorCase("T43", appended('[exec]\nexecutor = "local"\n'), ("[exec]", "phase 7")),
]


@pytest.mark.parametrize("case", ERROR_CASES, ids=[case.row for case in ERROR_CASES])
def test_invalid_manifest_is_rejected(case: ErrorCase) -> None:
    with pytest.raises(ConfigError) as excinfo:
        validate_manifest(tomllib.loads(case.text), source="benchdiff.toml")

    message = str(excinfo.value)
    assert message.startswith("benchdiff.toml")
    for fragment in case.expected:
        assert fragment in message
