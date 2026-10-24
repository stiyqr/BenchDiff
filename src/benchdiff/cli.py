"""Command-line entry point for BenchDiff."""

from __future__ import annotations

import argparse
import sys

from benchdiff import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchdiff",
        description="Benchmark a Git range.",
    )
    parser.add_argument("--version", action="version", version=f"benchdiff {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
