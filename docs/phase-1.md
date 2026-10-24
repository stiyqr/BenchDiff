# Phase 0 + Phase 1 — Scaffolding and configuration resolution

**Goal:** by the end of phase 1, `benchdiff resolve` reads a real `benchdiff.toml` plus CLI flags and
prints the exact run plan it *would* execute. Nothing is benchmarked, nothing is cloned, no process
is spawned.

**Why this first:** every later stage consumes one object, `RunSpec`. If that shape is wrong, it is
wrong in seven places. And this is the cheapest point in the project to get a fast feedback loop.

---

## Phase 0 — prerequisite checklist

Mechanical. No design decisions.

- [ ] `git init`, first commit
- [ ] `.gitignore` (Python + `.benchdiff/` + `*.egg-info`)
- [ ] `pyproject.toml` — package `benchdiff`, script entry point `benchdiff`, requires-python `>=3.11`
- [ ] `uv` for environments and commands (or plain `venv` + `pip` if preferred — pick one, write it in the README)
- [ ] `ruff` configured (lint + format), `pytest` configured with `testpaths`
- [ ] `src/benchdiff/__init__.py` with `__version__`
- [ ] `src/benchdiff/cli.py` — stub: `--version` and `--help` only
- [ ] `tests/test_cli.py` — one real test (`--version` exits 0 and prints the version)
- [ ] `README.md` — one paragraph, install + usage stub, link to `docs/vision.md`
- [ ] GitHub Actions: lint + test on push and PR
- [ ] commit

**Done when:** `uv run pytest` passes, `uv run ruff check` is clean, `uv run benchdiff --version` works,
CI is green.

---

## Phase 1 — the contract

```text
benchdiff.toml  ─┐
CLI flags       ─┼─▶  RunSpec   (frozen dataclass, fully validated)
defaults        ─┘
```

One rule governs the whole phase:

> **Validate the manifest first, then merge. Never merge, then validate.**

A typo'd key must fail before defaults can quietly fill in for it. This ordering is the difference
between a strict tool and a tool that only looks strict.

### The data model (`src/benchdiff/model.py`)

All frozen dataclasses with `slots=True`. Regexes are compiled at construction time, so an invalid
pattern cannot exist in a `RunSpec`.

```python
class Direction(StrEnum):
    LOWER_IS_BETTER = "lower_is_better"
    HIGHER_IS_BETTER = "higher_is_better"

class Mode(StrEnum):
    OPTIMIZE = "optimize"          # only implemented mode in v1

@dataclass(frozen=True, slots=True)
class MetricSpec:
    name: str                      # slug: [a-z0-9_]+
    label: str                     # human name for reports, defaults to name
    unit: str                      # "ns/op", "B/op", "ms", "rps"
    direction: Direction
    pattern: re.Pattern[str]
    group: int                     # capture group index, default 1

@dataclass(frozen=True, slots=True)
class BenchSpec:
    command: str
    metrics: tuple[MetricSpec, ...]        # >= 1, unique names
    samples: int = 10
    warmup: int = 1
    timeout_seconds: float = 300.0
    overlay: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class ProjectSpec:
    name: str
    language: str | None = None
    mode: Mode = Mode.OPTIMIZE

@dataclass(frozen=True, slots=True)
class RunSpec:
    project: ProjectSpec
    bench: BenchSpec
    target: Path                   # absolute, resolved
    manifest: Path                 # absolute path of the manifest actually used
    baseline: str                  # opaque revision string; existence checked in phase 2
    optimized: str
    out_dir: Path                  # absolute; default <cwd>/.benchdiff
```

### Manifest schema (v1, strict)

| Key | Type | Required | Default | Rule |
|---|---|---|---|---|
| `project.name` | string | yes | — | non-empty |
| `project.language` | string | no | `null` | advisory only; never branches logic |
| `project.mode` | string | no | `optimize` | enum; anything else is a clear "not in this version" error |
| `bench.command` | string | yes | — | non-empty |
| `bench.samples` | integer | no | `10` | 1–1000; `true`/`1.5` are type errors |
| `bench.warmup` | integer | no | `1` | ≥ 0 |
| `bench.timeout` | int / float / string | no | `300` | > 0; `300`, `"300s"`, `"5m"`, `"1h"` |
| `bench.overlay` | array of string | no | `[]` | relative, no `..` escape, no absolute paths |
| `bench.metrics` | array of tables | yes | — | ≥ 1, unique names |
| `metric.name` | string | yes | — | `[a-z0-9_]+` |
| `metric.label` | string | no | = `name` | non-empty |
| `metric.unit` | string | yes | — | non-empty |
| `metric.direction` | string | yes | — | `lower_is_better` \| `higher_is_better` |
| `metric.extract` | table | yes | — | exactly one key; only `regex` implemented |
| `metric.extract.regex` | string | — | — | must compile, must contain ≥ 1 capture group |
| `metric.group` | integer | no | `1` | must exist in the pattern |

Reserved-but-unimplemented, rejected with an explicit message rather than silently ignored:
`mode = "scale"`, `mode = "macro"`, `[scale]`, `metric.extract.json_path`, `[ai]`, `[exec]`.

### Strictness rules (D21, accepted)

1. Unknown **keys** → error, with a did-you-mean suggestion.
2. Unknown **tables** → error, same.
3. Wrong **type** → error. No coercion of `"10"` to `10`; TOML is typed, so respect it.
4. Missing required key → error.
5. Reserved feature → error that names the phase it lands in.
6. **No escape hatch.** There is no `--allow-unknown`. A manifest that passes validation is a manifest
   we can trust.

Forward-compatibility cost, accepted: a manifest written for v2 fails on v1. The error says so
("unknown key `json_path` — this manifest may target a newer BenchDiff") instead of guessing.

### Error format

```text
benchdiff.toml: [bench] unknown key "sample" (did you mean "samples"?)
benchdiff.toml: [bench.metrics[0].direction] "faster" is not valid; expected one of: lower_is_better, higher_is_better
benchdiff.toml: [bench.metrics[0].extract.regex] invalid pattern "(" : missing ), unterminated subpattern at position 0
benchdiff.toml: [bench.samples] expected an integer, got 1.5
```

Errors go to **stderr**, exit code **2**, nothing on stdout. `0` on success.

**Known limitation, accepted:** `tomllib` does not expose line numbers after parsing, so semantic
errors identify the *key path*, not the line. TOML syntax errors keep the parser's message (which
does include line info). Revisit only if it becomes annoying in practice — a raw-text line scan
could add it later without changing the error type.

### Precedence

**CLI flag > manifest > built-in default.** Per field, not per section.

Flags that can override scalars in v1: `--samples`, `--warmup`, `--timeout`, `--out`.
Metrics and `command` come from the manifest only (a `--command` override invites quoting bugs and
shell-injection confusion for zero benefit; if it is ever wanted, it is a separate feature).

### CLI surface added in this phase

```text
benchdiff resolve [--path DIR] [--manifest FILE] [--baseline REV] [--optimized REV]
                  [--samples N] [--warmup N] [--timeout DUR] [--out DIR]
                  [--format text|json]
```

- `--path` defaults to `.`; `--manifest` defaults to `<path>/benchdiff.toml`.
- `--baseline` and `--optimized` are required. Their *existence* is phase 2's job; phase 1 only
  checks they are non-empty.
- `--format json` exists from day one: it is the debugging aid and it makes CLI-level testing trivial.

Example output:

```json
{
  "target": "D:/repos/banking-core",
  "manifest": "D:/repos/banking-core/benchdiff.toml",
  "baseline": "main",
  "optimized": "HEAD",
  "out_dir": "D:/repos/BenchDiff/.benchdiff",
  "project": { "name": "banking-core", "language": "go", "mode": "optimize" },
  "bench": {
    "command": "go test -bench=. -benchmem -count=1 ./internal/billing/...",
    "samples": 20,
    "warmup": 1,
    "timeout_seconds": 300.0,
    "overlay": ["bench/"],
    "metrics": [
      {
        "name": "latency",
        "label": "execution latency",
        "unit": "ns/op",
        "direction": "lower_is_better",
        "group": 1,
        "pattern": "^\\S+\\s+\\d+\\s+([\\d.]+) ns/op"
      }
    ]
  }
}
```

### File layout at the end of phase 1

```text
src/benchdiff/
  __init__.py     # __version__
  cli.py          # argparse → dispatch → exit codes
  errors.py       # ConfigError, key-path formatting, did-you-mean
  model.py        # enums + frozen dataclasses
  manifest.py     # discovery, read, surface TOML syntax errors
  validate.py     # raw dict → model, strict walker
  resolve.py      # defaults → manifest → CLI merge, path resolution
tests/
  fixtures/       # .toml files used by the table tests
  test_manifest.py
  test_validate.py
  test_metrics.py
  test_resolve.py
  test_duration.py
  test_cli.py
```

### Test table

Every row is a test. Rows marked ✱ also assert the error message names the offending key path.

**Happy path**

| # | Given | Expect |
|---|---|---|
| T1 | minimal valid manifest | defaults applied: samples 10, warmup 1, timeout 300.0, mode optimize, overlay `[]` |
| T2 | fully populated manifest | every value honoured, metrics in declared order |
| T3 | two metrics | both compiled, both retained, order preserved |
| T4 | `timeout = 300` / `"300s"` / `"5m"` / `"1h"` / `"0.5s"` | 300.0 / 300.0 / 300.0 / 3600.0 / 0.5 |
| T5 | `overlay = ["./bench/", "scripts/seed.sql"]` | normalised to `["bench/", "scripts/seed.sql"]` |
| T6 | regex with 3 groups, `group = 2` | pattern compiled, group 2 selected |
| T7 | manifest with CRLF line endings and a UTF-8 BOM | parses identically to the LF version |

**Precedence**

| # | Given | Expect |
|---|---|---|
| T8 | manifest `samples = 10`, `--samples 20` | 20 |
| T9 | neither manifest nor flag | 10 |
| T10 | `--timeout 5m` over manifest `timeout = 60` | 300.0 |
| T11 | `--manifest custom.toml` | that file used, `spec.manifest` points at it |
| T12 | `--path` relative | `spec.target` is absolute |
| T13 | no `--out` | `spec.out_dir` = `<cwd>/.benchdiff`, absolute |
| T14 | `--out results/` relative | resolved against cwd |
| T15 | missing `--baseline` | usage error, exit 2 |
| T16 | empty string `--optimized ""` | config error ✱ |

**Validation — structure**

| # | Given | Expect |
|---|---|---|
| T17 | missing `project.name` | error ✱ `project.name` |
| T18 | missing `bench.command` | error ✱ |
| T19 | no `bench.metrics` | error ✱ |
| T20 | unknown table `[benchmark]` | error ✱ with did-you-mean `[bench]` |
| T21 | unknown key `sample` under `[bench]` | error ✱ with did-you-mean `samples` |
| T22 | unknown key `direction` under `[project]` | error ✱ |
| T23 | duplicate metric names | error ✱ naming the duplicate |
| T24 | `metric.name = "Latency Per Op"` | error ✱ slug rule |
| T25 | metric missing `unit` | error ✱ |

**Validation — values**

| # | Given | Expect |
|---|---|---|
| T26 | `direction = "faster"` | error ✱ listing both allowed values |
| T27 | `extract.regex = "("` | error ✱ including the `re` message |
| T28 | `extract.regex = "\\d+"` (no group) | error ✱ requiring a capture group |
| T29 | `group = 3` but pattern has 1 group | error ✱ |
| T30 | `samples = 0` / `-1` / `1001` | error ✱ range |
| T31 | `samples = 1.5` | type error ✱ |
| T32 | `samples = true` | type error ✱ (bool is not an int here) |
| T33 | `warmup = -1` | error ✱ |
| T34 | `timeout = "fast"` / `0` / `-5` | error ✱ |
| T35 | `overlay = ["/etc/passwd"]` | error ✱ absolute path |
| T36 | `overlay = ["../outside"]` | error ✱ escape |
| T37 | `extract = { regex = "...", json_path = "x" }` | error ✱ exactly one extractor |
| T38 | `extract = {}` | error ✱ |
| T39 | `extract = { json_path = "$.t" }` | error naming the phase, not "unknown key" |

**Reserved features (must not be silently ignored)**

| # | Given | Expect |
|---|---|---|
| T40 | `mode = "scale"` | error: not implemented, see roadmap phase 8 |
| T41 | `[scale]` present, mode `optimize` | error ✱ |
| T42 | `[ai]` section | error ✱ |
| T43 | `[exec]` section | error ✱ |

**I/O and CLI**

| # | Given | Expect |
|---|---|---|
| T44 | manifest path does not exist | error naming the searched path, exit 2 |
| T45 | path exists but is a directory | error, exit 2 |
| T46 | malformed TOML | parser message surfaced, exit 2 |
| T47 | `resolve --format json` | valid JSON, matches the documented shape |
| T48 | any error case | stdout empty, message on stderr |
| T49 | success | exit 0 |

49 tests. Most are three lines of table data; the validation walker does the work.

### Build order

Deliberately error-first: every later test asserts on real messages instead of placeholder strings.

1. Phase 0 checklist
2. `errors.py` — `ConfigError`, key-path rendering, `difflib` suggestions
3. `model.py` — enums, dataclasses, `__post_init__` invariants
4. `test_duration.py` + duration parser (smallest pure function, sets the testing pattern)
5. `manifest.py` — discovery, read, syntax errors
6. `validate.py` — strict walker: unknown tables, unknown keys, types, required
7. `test_metrics.py` + metric validation (regex compile, group bounds, direction)
8. `resolve.py` — defaults → manifest → CLI, path resolution, `out_dir`
9. `cli.py` — `resolve` command, `--format text|json`, exit codes
10. fixtures + remaining table rows green
11. README usage section, `docs/decisions.md` gets D21 (strict) and D22 (validate-then-merge)
12. commit

### Definition of done

- All 49 rows green, `ruff check` clean, CI green.
- `benchdiff resolve --path ../any-repo --baseline main --optimized HEAD` prints a plan, or fails
  with one message that tells you exactly which key to fix.
- No `subprocess`, no `git`, no network anywhere in `src/benchdiff` yet. Only `pathlib` and `tomllib`.
- A deliberately typo'd manifest fails instead of silently using a default.

### Explicitly out of scope for this phase

Revision existence checks, `git` anything, worktrees, overlay copying, running commands, sampling,
statistics, reports, `[scale]`, `[ai]`, `[exec]`, language presets, `benchdiff init`, TUI.

### Decisions this phase lands in the log

- **D21 — strict manifests, no escape hatch.** Unknown key or type mismatch is fatal.
- **D22 — validate-then-merge.** Defaults are applied only after the manifest is proven well-formed.
- **D23 — errors are key-path addressed, not line-addressed** (until proven annoying).
- **D24 — `command` is manifest-only**; no `--command` flag in v1.
