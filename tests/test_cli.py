"""T15, T47-T49 — the CLI contract: exit codes, streams and the JSON plan."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from benchdiff import __version__
from benchdiff.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory with a valid manifest, used as the invocation directory."""
    monkeypatch.chdir(tmp_path)
    shutil.copyfile(FIXTURES / "full.toml", tmp_path / "benchdiff.toml")
    return tmp_path


def test_version_flag_prints_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])

    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"benchdiff {__version__}"


def test_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: benchdiff" in capsys.readouterr().out


def test_missing_baseline_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    """T15: argparse owns usage errors: exit 2, message on stderr, nothing on stdout."""
    with pytest.raises(SystemExit) as excinfo:
        main(["resolve", "--optimized", "HEAD"])

    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--baseline" in captured.err


def test_json_plan_has_the_documented_shape(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """T47: --format json is valid JSON with exactly the documented keys."""
    exit_code = main(
        [
            "resolve",
            "--baseline",
            "main",
            "--optimized",
            "HEAD",
            "--samples",
            "7",
            "--format",
            "json",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert set(payload) == {
        "target",
        "manifest",
        "baseline",
        "optimized",
        "out_dir",
        "project",
        "bench",
    }
    assert Path(payload["target"]) == repo
    assert Path(payload["manifest"]) == repo / "benchdiff.toml"
    assert payload["baseline"] == "main"
    assert payload["optimized"] == "HEAD"
    assert Path(payload["out_dir"]) == repo / ".benchdiff"
    assert payload["project"] == {
        "name": "banking-core",
        "language": "go",
        "mode": "optimize",
    }
    assert payload["bench"]["samples"] == 7
    assert payload["bench"]["warmup"] == 2
    assert payload["bench"]["timeout_seconds"] == 300.0
    assert payload["bench"]["overlay"] == ["bench/", "scripts/seed_test_db.sql"]
    assert payload["bench"]["metrics"][0] == {
        "name": "latency",
        "label": "execution latency",
        "unit": "ns/op",
        "direction": "lower_is_better",
        "group": 1,
        "pattern": r"^\S+\s+\d+\s+([\d.]+) ns/op",
    }


def test_error_message_goes_to_stderr_only(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """T48: any config error keeps stdout empty."""
    (repo / "benchdiff.toml").write_text(
        '[project]\nname = "app"\n\n[bench]\ncommand = "run"\nsample = 1\n', encoding="utf-8"
    )

    exit_code = main(["resolve", "--baseline", "main", "--optimized", "HEAD"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert "unknown key" in captured.err
    assert "benchdiff.toml" in captured.err


def test_success_prints_the_plan_and_exits_zero(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """T49: a successful resolve is exit 0 with the plan on stdout."""
    exit_code = main(["resolve", "--baseline", "main", "--optimized", "HEAD"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert "target:" in captured.out
    assert "go test -bench=." in captured.out
    assert "latency" in captured.out
