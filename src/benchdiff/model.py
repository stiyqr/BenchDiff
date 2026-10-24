"""The values that cross stage boundaries.

Everything in this module is a frozen slotted dataclass. Constructing one does not touch the
filesystem or the process; the invariants in ``__post_init__`` are a backstop for code that builds
a spec directly. User-facing validation (with key paths) happens first, in ``validate``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

MIN_SAMPLES = 1
MAX_SAMPLES = 1000
DEFAULT_SAMPLES = 10
DEFAULT_WARMUP = 1
DEFAULT_TIMEOUT_SECONDS = 300.0
METRIC_NAME_PATTERN = re.compile(r"[a-z0-9_]+")


class Direction(StrEnum):
    """Which way a metric has to move to count as an improvement."""

    LOWER_IS_BETTER = "lower_is_better"
    HIGHER_IS_BETTER = "higher_is_better"


class Mode(StrEnum):
    """Comparison modes. Only ``optimize`` exists in v1."""

    OPTIMIZE = "optimize"


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """One declared metric: what to extract, from where, and which way is good."""

    name: str
    label: str
    unit: str
    direction: Direction
    pattern: re.Pattern[str]
    group: int = 1

    def __post_init__(self) -> None:
        if not METRIC_NAME_PATTERN.fullmatch(self.name):
            raise ValueError(f"metric name must match [a-z0-9_]+, got {self.name!r}")
        if not self.label:
            raise ValueError(f"metric {self.name!r} has an empty label")
        if not self.unit:
            raise ValueError(f"metric {self.name!r} has an empty unit")
        if not isinstance(self.direction, Direction):
            raise ValueError(f"metric {self.name!r} has an invalid direction")
        if not isinstance(self.pattern, re.Pattern):
            raise ValueError(f"metric {self.name!r} must carry a compiled pattern")
        if not 1 <= self.group <= self.pattern.groups:
            raise ValueError(
                f"metric {self.name!r} selects group {self.group}, "
                f"but its pattern has {self.pattern.groups} capture group(s)"
            )


@dataclass(frozen=True, slots=True)
class BenchSpec:
    """How to measure: one command, N declared metrics, sampling parameters."""

    command: str
    metrics: tuple[MetricSpec, ...]
    samples: int = DEFAULT_SAMPLES
    warmup: int = DEFAULT_WARMUP
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    overlay: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.command.strip():
            raise ValueError("bench command must not be empty")
        if not self.metrics:
            raise ValueError("at least one metric is required")
        names = [metric.name for metric in self.metrics]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate metric name in {names}")
        if not MIN_SAMPLES <= self.samples <= MAX_SAMPLES:
            raise ValueError(f"samples must be between {MIN_SAMPLES} and {MAX_SAMPLES}")
        if self.warmup < 0:
            raise ValueError("warmup must be 0 or greater")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout must be greater than 0")


@dataclass(frozen=True, slots=True)
class ProjectSpec:
    """Who we are measuring. ``language`` is advisory and never branches logic."""

    name: str
    language: str | None = None
    mode: Mode = Mode.OPTIMIZE

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("project name must not be empty")
        if not isinstance(self.mode, Mode):
            raise ValueError(f"project mode must be a Mode, got {self.mode!r}")


@dataclass(frozen=True, slots=True)
class RunSpec:
    """A fully resolved run plan: everything a later stage needs, and nothing more."""

    project: ProjectSpec
    bench: BenchSpec
    target: Path
    manifest: Path
    baseline: str
    optimized: str
    out_dir: Path

    def __post_init__(self) -> None:
        for name in ("target", "manifest", "out_dir"):
            if not getattr(self, name).is_absolute():
                raise ValueError(f"{name} must be an absolute path")
        for name in ("baseline", "optimized"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
