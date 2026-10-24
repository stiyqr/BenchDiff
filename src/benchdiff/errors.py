"""User-facing configuration errors and the formatting they share."""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Sequence


class ConfigError(Exception):
    """A configuration problem the user can fix.

    ``location`` says where the offending value lives: a rendered manifest key path
    (``benchdiff.toml: [bench]``) or a CLI flag (``--samples``). ``str(error)`` renders the
    one-line message the CLI prints to stderr.
    """

    def __init__(self, message: str, *, location: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.location = location

    def __str__(self) -> str:
        if self.location is None:
            return self.message
        return f"{self.location} {self.message}"


def format_key_path(parts: Sequence[str | int]) -> str:
    """Render key parts as a TOML-ish path: ``bench.metrics[0].direction``."""
    rendered = ""
    for part in parts:
        if isinstance(part, int):
            rendered = f"{rendered}[{part}]"
        elif rendered:
            rendered = f"{rendered}.{part}"
        else:
            rendered = part
    return rendered


def key_location(source: str, parts: Sequence[str | int]) -> str:
    """Render ``source`` plus a key path, e.g. ``benchdiff.toml: [bench.samples]``."""
    path = format_key_path(parts)
    if not path:
        return source
    return f"{source}: [{path}]"


def did_you_mean(value: str, candidates: Iterable[str]) -> str:
    """Return `` (did you mean "x"?)`` or an empty string when nothing is close."""
    matches = difflib.get_close_matches(value, list(candidates), n=1, cutoff=0.6)
    if not matches:
        return ""
    return f' (did you mean "{matches[0]}"?)'


def describe_value(value: object) -> str:
    """Describe a TOML value the way the user wrote it, for type-error messages."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "an array"
    if isinstance(value, dict):
        return "a table"
    return type(value).__name__
