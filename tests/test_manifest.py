"""T7, T44, T45, T46 — reading a manifest from disk."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchdiff.errors import ConfigError
from benchdiff.manifest import default_manifest_path, load_manifest

FIXTURES = Path(__file__).parent / "fixtures"


def test_bom_and_crlf_parse_like_lf(tmp_path: Path) -> None:
    """T7: a UTF-8 BOM and CRLF endings must not change the parsed manifest."""
    text = (FIXTURES / "minimal.toml").read_text(encoding="utf-8")
    plain = tmp_path / "plain.toml"
    plain.write_text(text, encoding="utf-8")
    windows = tmp_path / "windows.toml"
    windows.write_bytes(b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode())

    expected = load_manifest(FIXTURES / "minimal.toml").raw
    assert load_manifest(plain).raw == expected
    assert load_manifest(windows).raw == expected


def test_missing_manifest_names_the_searched_path(tmp_path: Path) -> None:
    """T44: a missing manifest is an error that names the path it looked at."""
    missing = tmp_path / "benchdiff.toml"
    with pytest.raises(ConfigError) as excinfo:
        load_manifest(missing)

    message = str(excinfo.value)
    assert str(missing) in message
    assert "manifest not found" in message


def test_manifest_path_that_is_a_directory_is_rejected(tmp_path: Path) -> None:
    """T45: a directory is not a manifest."""
    with pytest.raises(ConfigError, match="found a directory"):
        load_manifest(tmp_path)


def test_malformed_toml_surfaces_the_parser_message(tmp_path: Path) -> None:
    """T46: syntax errors keep the parser's own message, including the line."""
    broken = tmp_path / "benchdiff.toml"
    broken.write_text("[bench\ncommand = 1\n", encoding="utf-8")

    with pytest.raises(ConfigError) as excinfo:
        load_manifest(broken)

    message = str(excinfo.value)
    assert "invalid TOML" in message
    assert "line 1" in message


def test_default_manifest_path_sits_in_the_target(tmp_path: Path) -> None:
    assert default_manifest_path(tmp_path) == tmp_path / "benchdiff.toml"
