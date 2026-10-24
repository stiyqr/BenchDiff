"""T1, T2, T8-T14, T16 — precedence, paths and the final RunSpec."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchdiff.errors import ConfigError
from benchdiff.model import Mode, RunSpec
from benchdiff.resolve import Overrides, resolve

FIXTURES = Path(__file__).parent / "fixtures"

MANIFEST = """\
[project]
name = "app"

[bench]
command = "run"
samples = 10

[[bench.metrics]]
name = "latency"
unit = "ns/op"
direction = "lower_is_better"
extract = { regex = "([0-9.]+)" }
"""


def plan(tmp_path: Path, text: str = MANIFEST, **kwargs: object) -> RunSpec:
    """Write the manifest into ``tmp_path`` and resolve against it."""
    (tmp_path / "benchdiff.toml").write_text(text, encoding="utf-8")
    return resolve(baseline="main", optimized="HEAD", target=tmp_path, cwd=tmp_path, **kwargs)


def plan_fixture(name: str, **kwargs: object) -> RunSpec:
    return resolve(
        baseline="main",
        optimized="HEAD",
        target=FIXTURES,
        manifest=FIXTURES / name,
        **kwargs,
    )


def test_minimal_manifest_gets_defaults() -> None:
    """T1: absent scalars are filled from the built-in defaults."""
    spec = plan_fixture("minimal.toml")

    assert spec.bench.samples == 10
    assert spec.bench.warmup == 1
    assert spec.bench.timeout_seconds == 300.0
    assert spec.bench.overlay == ()
    assert spec.project.mode is Mode.OPTIMIZE
    assert spec.project.name == "tiny"
    assert spec.project.language is None


def test_fully_populated_manifest_is_honoured() -> None:
    """T2: every declared value survives, metrics keep their order."""
    spec = plan_fixture("full.toml")

    assert spec.project.name == "banking-core"
    assert spec.project.language == "go"
    assert spec.project.mode is Mode.OPTIMIZE
    assert spec.bench.command == "go test -bench=. -benchmem -count=1 ./internal/billing/..."
    assert spec.bench.samples == 20
    assert spec.bench.warmup == 2
    assert spec.bench.timeout_seconds == 300.0
    assert spec.bench.overlay == ("bench/", "scripts/seed_test_db.sql")
    assert [metric.name for metric in spec.bench.metrics] == ["latency", "allocs"]
    assert spec.bench.metrics[0].label == "execution latency"
    assert spec.bench.metrics[1].label == "allocs"


def test_cli_samples_override_manifest(tmp_path: Path) -> None:
    """T8: --samples beats the manifest value."""
    spec = plan(tmp_path, overrides=Overrides(samples=20))

    assert spec.bench.samples == 20


def test_no_override_no_manifest_value_uses_default(tmp_path: Path) -> None:
    """T9: neither source means the built-in default."""
    spec = plan(tmp_path, MANIFEST.replace("samples = 10\n", ""))

    assert spec.bench.samples == 10


def test_cli_timeout_override_manifest(tmp_path: Path) -> None:
    """T10: --timeout 5m beats ``timeout = 60``."""
    spec = plan(
        tmp_path,
        MANIFEST.replace("samples = 10", "samples = 10\ntimeout = 60"),
        overrides=Overrides(timeout="5m"),
    )

    assert spec.bench.timeout_seconds == 300.0


def test_manifest_flag_selects_the_file(tmp_path: Path) -> None:
    """T11: --manifest is used and recorded on the spec."""
    custom = tmp_path / "custom.toml"
    custom.write_text(MANIFEST, encoding="utf-8")

    spec = resolve(
        baseline="main",
        optimized="HEAD",
        target=tmp_path,
        manifest="custom.toml",
        cwd=tmp_path,
    )

    assert spec.manifest == custom.resolve()


def test_relative_path_becomes_absolute(tmp_path: Path) -> None:
    """T12: --path is resolved against the invocation directory."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "benchdiff.toml").write_text(MANIFEST, encoding="utf-8")

    spec = resolve(baseline="main", optimized="HEAD", target="repo", cwd=tmp_path)

    assert spec.target == repo.resolve()
    assert spec.target.is_absolute()
    assert spec.manifest == repo / "benchdiff.toml"


def test_out_dir_defaults_to_cwd(tmp_path: Path) -> None:
    """T13: no --out means <cwd>/.benchdiff."""
    spec = plan(tmp_path)

    assert spec.out_dir == tmp_path / ".benchdiff"
    assert spec.out_dir.is_absolute()


def test_relative_out_dir_is_resolved_against_cwd(tmp_path: Path) -> None:
    """T14: a relative --out is anchored to the invocation directory, not the target."""
    spec = plan(tmp_path, overrides=Overrides(out="results/"))

    assert spec.out_dir == tmp_path / "results"


def test_empty_revision_is_a_config_error(tmp_path: Path) -> None:
    """T16: an empty revision names the flag, nothing else."""
    (tmp_path / "benchdiff.toml").write_text(MANIFEST, encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        resolve(baseline="main", optimized="", target=tmp_path, cwd=tmp_path)

    assert "--optimized" in str(excinfo.value)


OVERRIDE_ERROR_ROWS: list[tuple[Overrides, str]] = [
    (Overrides(samples=0), "--samples must be between 1 and 1000"),
    (Overrides(samples=1001), "--samples must be between 1 and 1000"),
    (Overrides(warmup=-1), "--warmup must be 0 or greater"),
    (Overrides(timeout="fast"), "--timeout"),
    (Overrides(timeout=0), "--timeout"),
]


@pytest.mark.parametrize(("overrides", "fragment"), OVERRIDE_ERROR_ROWS, ids=repr)
def test_invalid_override_is_a_config_error(
    tmp_path: Path, overrides: Overrides, fragment: str
) -> None:
    with pytest.raises(ConfigError, match=fragment):
        plan(tmp_path, overrides=overrides)
