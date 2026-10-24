"""Strict manifest walker: raw TOML dict -> validated values.

D21: unknown table, unknown key, wrong type and missing key are all fatal.
D22: nothing here merges defaults. Optional scalars stay ``None`` so ``resolve`` can apply
built-in defaults only after the whole manifest is proven well-formed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import NoReturn

from benchdiff.duration import parse_duration
from benchdiff.errors import ConfigError, describe_value, did_you_mean, key_location
from benchdiff.model import (
    MAX_SAMPLES,
    METRIC_NAME_PATTERN,
    MIN_SAMPLES,
    Direction,
    MetricSpec,
    Mode,
)

_RESERVED_TABLES = {
    "scale": "reserved for phase 8 (scale mode); not implemented in v1",
    "ai": "reserved for phase 9 (AI layer); not implemented in v1",
    "exec": "reserved for phase 7 (docker executor); not implemented in v1",
}

_RESERVED_MODES = {
    "scale": '"scale" mode is not implemented; see roadmap phase 8',
    "macro": '"macro" mode is not implemented; see roadmap phase 10',
    "refactor": '"refactor" mode is not implemented; see docs/vision.md section 6.3',
}

_RESERVED_EXTRACTORS = {
    "json_path": (
        '"json_path" extraction is not implemented; v1 extracts with regex only '
        "(see roadmap phase 3)"
    ),
}

_PROJECT_REQUIRED = ("name",)
_PROJECT_OPTIONAL = ("language", "mode")
_BENCH_REQUIRED = ("command", "metrics")
_BENCH_OPTIONAL = ("samples", "warmup", "timeout", "overlay")
_METRIC_REQUIRED = ("name", "unit", "direction", "extract")
_METRIC_OPTIONAL = ("label", "group")


@dataclass(frozen=True, slots=True)
class ManifestData:
    """What the manifest said, with every override-able scalar still absent."""

    project_name: str
    language: str | None
    mode: Mode
    command: str
    metrics: tuple[MetricSpec, ...]
    samples: int | None
    warmup: int | None
    timeout_seconds: float | None
    overlay: tuple[str, ...]


def validate_manifest(raw: Mapping[str, object], *, source: str = "benchdiff.toml") -> ManifestData:
    """Validate ``raw`` strictly and return its values, without applying defaults."""
    return _Walker(source).manifest(raw)


def normalise_overlay_path(raw: str) -> str:
    """Normalise an overlay entry: relative, no ``..``, forward slashes kept."""
    if not raw:
        raise ValueError("overlay path must not be empty")
    if raw.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", raw):
        raise ValueError(f'overlay path must be relative, got "{raw}"')
    parts = [part for part in raw.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise ValueError(f'overlay path must not escape the target, got "{raw}"')
    normalised = "/".join(parts)
    if not normalised:
        raise ValueError(f'overlay path must not be empty, got "{raw}"')
    return f"{normalised}/" if raw.endswith("/") else normalised


class _Walker:
    def __init__(self, source: str) -> None:
        self._source = source

    def _fail(self, parts: Sequence[str | int], message: str) -> NoReturn:
        raise ConfigError(message, location=key_location(self._source, parts))

    # -- structure ---------------------------------------------------------------------

    def _table(
        self,
        value: object,
        parts: Sequence[str | int],
        *,
        required: Sequence[str] = (),
        optional: Sequence[str] = (),
        reserved: Mapping[str, str] | None = None,
    ) -> Mapping[str, object]:
        if not isinstance(value, dict):
            self._fail(parts, f"expected a table, got {describe_value(value)}")
        reserved = reserved or {}
        known = (*required, *optional)
        for key, item in value.items():
            if key in reserved:
                self._fail((*parts, key), reserved[key])
            if key not in known:
                kind = "table" if isinstance(item, dict) else "key"
                suggestion = did_you_mean(key, known)
                self._fail(parts, f'unknown {kind} "{key}"{suggestion}')
        for key in required:
            if key not in value:
                self._fail((*parts, key), "is required")
        return value

    # -- scalars -----------------------------------------------------------------------

    def _string(
        self, table: Mapping[str, object], parts: Sequence[str | int], key: str
    ) -> str | None:
        if key not in table:
            return None
        value = table[key]
        if not isinstance(value, str):
            self._fail((*parts, key), f"expected a string, got {describe_value(value)}")
        if not value.strip():
            self._fail((*parts, key), "must not be empty")
        return value

    def _required_string(
        self, table: Mapping[str, object], parts: Sequence[str | int], key: str
    ) -> str:
        value = self._string(table, parts, key)
        if value is None:  # unreachable: _table already required the key
            self._fail((*parts, key), "is required")
        return value

    def _int(
        self,
        table: Mapping[str, object],
        parts: Sequence[str | int],
        key: str,
        *,
        minimum: int,
        maximum: int | None = None,
    ) -> int | None:
        if key not in table:
            return None
        value = table[key]
        if isinstance(value, bool) or not isinstance(value, int):
            self._fail((*parts, key), f"expected an integer, got {describe_value(value)}")
        if maximum is not None and not minimum <= value <= maximum:
            self._fail((*parts, key), f"must be between {minimum} and {maximum}, got {value}")
        if maximum is None and value < minimum:
            self._fail((*parts, key), f"must be {minimum} or greater, got {value}")
        return value

    # -- sections ----------------------------------------------------------------------

    def manifest(self, raw: Mapping[str, object]) -> ManifestData:
        root = self._table(raw, (), required=("project", "bench"), reserved=_RESERVED_TABLES)
        project = self._table(
            root["project"], ("project",), required=_PROJECT_REQUIRED, optional=_PROJECT_OPTIONAL
        )
        bench = self._table(
            root["bench"], ("bench",), required=_BENCH_REQUIRED, optional=_BENCH_OPTIONAL
        )
        return ManifestData(
            project_name=self._required_string(project, ("project",), "name"),
            language=self._string(project, ("project",), "language"),
            mode=self._mode(project),
            command=self._required_string(bench, ("bench",), "command"),
            metrics=self._metrics(bench["metrics"], ("bench", "metrics")),
            samples=self._int(
                bench, ("bench",), "samples", minimum=MIN_SAMPLES, maximum=MAX_SAMPLES
            ),
            warmup=self._int(bench, ("bench",), "warmup", minimum=0),
            timeout_seconds=self._timeout(bench),
            overlay=self._overlay(bench),
        )

    def _mode(self, project: Mapping[str, object]) -> Mode:
        parts = ("project",)
        value = self._string(project, parts, "mode")
        if value is None:
            return Mode.OPTIMIZE
        if value in _RESERVED_MODES:
            self._fail((*parts, "mode"), _RESERVED_MODES[value])
        try:
            return Mode(value)
        except ValueError:
            allowed = ", ".join(mode.value for mode in Mode)
            self._fail((*parts, "mode"), f'"{value}" is not valid; expected one of: {allowed}')

    def _timeout(self, bench: Mapping[str, object]) -> float | None:
        if "timeout" not in bench:
            return None
        try:
            return parse_duration(bench["timeout"])
        except ValueError as exc:
            self._fail(("bench", "timeout"), str(exc))

    def _overlay(self, bench: Mapping[str, object]) -> tuple[str, ...]:
        if "overlay" not in bench:
            return ()
        value = bench["overlay"]
        if not isinstance(value, list):
            self._fail(
                ("bench", "overlay"), f"expected an array of strings, got {describe_value(value)}"
            )
        paths = []
        for index, item in enumerate(value):
            parts = ("bench", "overlay", index)
            if not isinstance(item, str):
                self._fail(parts, f"expected a string, got {describe_value(item)}")
            try:
                paths.append(normalise_overlay_path(item))
            except ValueError as exc:
                self._fail(parts, str(exc))
        return tuple(paths)

    # -- metrics -----------------------------------------------------------------------

    def _metrics(self, value: object, parts: Sequence[str | int]) -> tuple[MetricSpec, ...]:
        if not isinstance(value, list):
            self._fail(parts, f"expected an array of tables, got {describe_value(value)}")
        if not value:
            self._fail(parts, "must declare at least one metric")
        metrics = tuple(self._metric(item, (*parts, index)) for index, item in enumerate(value))
        seen: set[str] = set()
        for index, metric in enumerate(metrics):
            if metric.name in seen:
                self._fail((*parts, index, "name"), f'duplicate metric name "{metric.name}"')
            seen.add(metric.name)
        return metrics

    def _metric(self, value: object, parts: Sequence[str | int]) -> MetricSpec:
        table = self._table(value, parts, required=_METRIC_REQUIRED, optional=_METRIC_OPTIONAL)
        name = self._required_string(table, parts, "name")
        if not METRIC_NAME_PATTERN.fullmatch(name):
            self._fail((*parts, "name"), f'must match [a-z0-9_]+, got "{name}"')
        label = self._string(table, parts, "label") or name
        unit = self._required_string(table, parts, "unit")
        direction = self._direction(table, parts)
        pattern = self._extract(table["extract"], (*parts, "extract"))
        group = self._int(table, parts, "group", minimum=1) or 1
        if group > pattern.groups:
            self._fail(
                (*parts, "group"),
                f"group {group} does not exist in the pattern ({pattern.groups} capture group(s))",
            )
        return MetricSpec(
            name=name,
            label=label,
            unit=unit,
            direction=direction,
            pattern=pattern,
            group=group,
        )

    def _direction(self, table: Mapping[str, object], parts: Sequence[str | int]) -> Direction:
        value = self._required_string(table, parts, "direction")
        try:
            return Direction(value)
        except ValueError:
            allowed = ", ".join(direction.value for direction in Direction)
            self._fail((*parts, "direction"), f'"{value}" is not valid; expected one of: {allowed}')

    def _extract(self, value: object, parts: Sequence[str | int]) -> re.Pattern[str]:
        if not isinstance(value, dict):
            self._fail(parts, f"expected a table, got {describe_value(value)}")
        if len(value) != 1:
            keys = ", ".join(sorted(value)) or "none"
            self._fail(parts, f"exactly one extractor is required, got {len(value)} ({keys})")
        key, raw = next(iter(value.items()))
        if key in _RESERVED_EXTRACTORS:
            self._fail((*parts, key), _RESERVED_EXTRACTORS[key])
        if key != "regex":
            suggestion = did_you_mean(key, ("regex",))
            self._fail(parts, f'unknown extractor "{key}"{suggestion}')
        if not isinstance(raw, str):
            self._fail((*parts, "regex"), f"expected a string, got {describe_value(raw)}")
        try:
            pattern = re.compile(raw)
        except re.error as exc:
            self._fail((*parts, "regex"), f'invalid pattern "{raw}": {exc}')
        if pattern.groups < 1:
            self._fail((*parts, "regex"), 'must contain at least one capture group, e.g. "(\\d+)"')
        return pattern
