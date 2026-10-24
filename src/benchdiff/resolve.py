"""Merge defaults, the validated manifest and CLI overrides into a ``RunSpec``.

Precedence is per field: CLI flag > manifest > built-in default. The manifest has already been
validated by ``validate``, which is what D22 buys: no default can mask a typo.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from benchdiff.duration import parse_duration
from benchdiff.errors import ConfigError
from benchdiff.manifest import default_manifest_path, load_manifest
from benchdiff.model import (
    DEFAULT_SAMPLES,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_WARMUP,
    MAX_SAMPLES,
    MIN_SAMPLES,
    BenchSpec,
    ProjectSpec,
    RunSpec,
)
from benchdiff.validate import validate_manifest

DEFAULT_OUT_DIR = ".benchdiff"


@dataclass(frozen=True, slots=True)
class Overrides:
    """Scalars the CLI is allowed to override. ``None`` means "not passed"."""

    samples: int | None = None
    warmup: int | None = None
    timeout: str | float | None = None
    out: str | Path | None = None


def resolve(
    *,
    baseline: str,
    optimized: str,
    target: str | Path = ".",
    manifest: str | Path | None = None,
    overrides: Overrides | None = None,
    cwd: str | Path | None = None,
) -> RunSpec:
    """Build the run plan, or raise ``ConfigError`` with a fixable message."""
    base = (Path(cwd) if cwd is not None else Path.cwd()).resolve()
    overrides = overrides or Overrides()
    _require_revision(baseline, "--baseline")
    _require_revision(optimized, "--optimized")

    target_path = _absolute(target, base)
    manifest_path = (
        _absolute(manifest, base) if manifest is not None else default_manifest_path(target_path)
    )
    loaded = load_manifest(manifest_path)
    data = validate_manifest(loaded.raw, source=str(loaded.path))

    bench = BenchSpec(
        command=data.command,
        metrics=data.metrics,
        samples=_samples(overrides.samples, data.samples),
        warmup=_warmup(overrides.warmup, data.warmup),
        timeout_seconds=_timeout(overrides.timeout, data.timeout_seconds),
        overlay=data.overlay,
    )
    project = ProjectSpec(name=data.project_name, language=data.language, mode=data.mode)
    out_dir = (
        _absolute(overrides.out, base) if overrides.out is not None else base / DEFAULT_OUT_DIR
    )
    return RunSpec(
        project=project,
        bench=bench,
        target=target_path,
        manifest=manifest_path,
        baseline=baseline,
        optimized=optimized,
        out_dir=out_dir,
    )


def _absolute(value: str | Path, base: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _require_revision(value: str, flag: str) -> None:
    if not value.strip():
        raise ConfigError(f"{flag} must not be empty")


def _samples(override: int | None, declared: int | None) -> int:
    if override is not None:
        if not MIN_SAMPLES <= override <= MAX_SAMPLES:
            raise ConfigError(
                f"--samples must be between {MIN_SAMPLES} and {MAX_SAMPLES}, got {override}"
            )
        return override
    return declared if declared is not None else DEFAULT_SAMPLES


def _warmup(override: int | None, declared: int | None) -> int:
    if override is not None:
        if override < 0:
            raise ConfigError(f"--warmup must be 0 or greater, got {override}")
        return override
    return declared if declared is not None else DEFAULT_WARMUP


def _timeout(override: str | float | None, declared: float | None) -> float:
    if override is not None:
        try:
            return parse_duration(override)
        except ValueError as exc:
            raise ConfigError(f"--timeout: {exc}") from exc
    return declared if declared is not None else DEFAULT_TIMEOUT_SECONDS
