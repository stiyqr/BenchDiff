# BenchDiff

Benchmark a Git range.
BenchDiff measures the same benchmark at two revisions and reports the delta with its uncertainty.

## Development

    uv sync
    uv run pytest
    uv run ruff check .
    uv run benchdiff --version

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).