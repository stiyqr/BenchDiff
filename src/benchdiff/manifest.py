"""Locate and read ``benchdiff.toml`` without interpreting it.

This is the only phase-1 module that touches the filesystem. Interpreting the parsed dict is
``validate``'s job, so TOML syntax errors never get confused with schema errors.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from benchdiff.errors import ConfigError

MANIFEST_FILENAME = "benchdiff.toml"


@dataclass(frozen=True, slots=True)
class Manifest:
    """A manifest that exists on disk and parses as TOML. Not yet validated."""

    path: Path
    raw: dict[str, object]


def default_manifest_path(target: Path) -> Path:
    """The manifest a target repository is expected to carry."""
    return target / MANIFEST_FILENAME


def load_manifest(path: Path) -> Manifest:
    """Read and parse ``path``, or raise ``ConfigError`` naming the path."""
    location = str(path)
    if path.is_dir():
        raise ConfigError("expected a file, found a directory", location=location)
    if not path.exists():
        raise ConfigError("manifest not found", location=location)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ConfigError(f"could not read manifest: {exc}", location=location) from exc
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConfigError(f"manifest is not valid UTF-8: {exc}", location=location) from exc
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML: {exc}", location=location) from exc
    return Manifest(path=path, raw=raw)
