# BenchDiff

Benchmark a Git range.
BenchDiff measures the same benchmark at two revisions and reports the delta with its uncertainty.
The design is written down in [`docs/vision.md`](docs/vision.md).

## Usage

The only command implemented so far is `resolve`: it reads a manifest, merges CLI overrides and
prints the run plan. It does not clone, check out or run anything.

    benchdiff resolve --path ../my-repo --baseline main --optimized HEAD
    benchdiff resolve --path ../my-repo --baseline main --optimized HEAD --format json

The manifest lives at `<path>/benchdiff.toml`:

```toml
[project]
name = "banking-core"
language = "go"

[bench]
command = "go test -bench=. -benchmem -count=1 ./internal/billing/..."
samples = 20
timeout = "5m"

[[bench.metrics]]
name = "latency"
unit = "ns/op"
direction = "lower_is_better"
extract = { regex = '^\S+\s+\d+\s+([\d.]+) ns/op' }
```

Precedence is CLI flag > manifest > built-in default. Manifests are strict: an unknown key, an
unknown table or a wrong type is an error on stderr with exit code 2, never a silently applied
default.

## Development

    uv sync
    uv run pytest
    uv run ruff check .
    uv run ruff format --check .
    uv run benchdiff --version

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).
