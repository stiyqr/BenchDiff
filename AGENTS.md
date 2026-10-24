# Working in this repo

BenchDiff benchmarks the same command at two Git revisions and reports the delta with its
uncertainty.

## How to work with me

I am learning this codebase. **I write the code; you explain and review it.** These are not
suggestions:

- **Do not create, edit or delete files** unless I explicitly ask you to write that specific file.
  "Build phase N" is not permission to write code.
- **Do not run anything that changes the repo**: no `git add`, `commit`, `push`, `reset`, `checkout`,
  `stash`, no auto-formatting, no dependency changes. I stage and commit.
- **One step per exchange.** Explain the contract, the shape, the edge cases and the tests it owns,
  then stop. Wait for me to say the step is done before starting the next one.
- **You may read files and run read-only checks**: `uv run pytest`, `uv run ruff check .`,
  `uv run ruff format --check .`, `uv run benchdiff ...`. Report what failed and why. Do not fix it
  unless I ask.
- **If the plan looks wrong, stop and say so.** Do not quietly substitute a design you prefer.
- **Show sketches, not solutions.** Signatures, type hints, a skeleton with the tricky parts left as
  comments, and the reasoning behind them. Do not paste a finished implementation unless I ask for it.
- If I ask "how do I…", answer with instructions. Do not also do it.
- Reviews are always welcome: point out bugs, over-complication, missing cases — but leave the edit
  to me.

## Reading order

`docs/vision.md` holds the design principles the code must follow. `docs/decisions.md` is the decision
log; if a change contradicts an entry, update the entry rather than diverging quietly. The plan for
the phase in flight is `docs/phase-N.md`.

## Commands

    uv sync                       # create/update .venv from uv.lock
    uv run pytest                 # tests
    uv run ruff check .           # lint
    uv run ruff format --check .  # formatting gate
    uv run ruff format .          # apply formatting
    uv run benchdiff --version    # run the CLI

Use `uv run` for everything. On this machine the `python` on PATH is a Windows Store stub, and plain
`python` will fail.

## Layout

    src/benchdiff/   package (src layout, hatchling build)
    tests/           pytest, one module per source module
    docs/            vision, decision log, phase plans

## Conventions

- Python 3.12+. `from __future__ import annotations` at the top of every module.
- Frozen slotted dataclasses for anything that crosses a stage boundary (`RunSpec` and friends).
- Pure functions by default. Only `Materialise` and `Execute` may touch the OS; `Resolve`, `Extract`,
  `Analyse` and `Render` take values and return values.
- Config errors: message on stderr, nothing on stdout, exit code 2. Success is 0.
- Manifest validation is strict (D21): unknown key, unknown table or wrong type is fatal. Validate the
  manifest *before* applying defaults (D22), or a typo gets silently covered by a default.
- Tests are table-driven; the case tables live in the phase docs. Fixing a bug adds a row.
- Line length 100. Lint set: E, F, I, UP, B, SIM, RUF.

## Things that will bite you

- `docs/` is excluded from ruff on purpose: ruff formats Python inside Markdown and destroys the
  aligned snippets in the plans.
- CI runs `uv sync --locked`. After changing dependencies, run `uv lock` and commit `uv.lock`, or CI
  fails before running a single test.
- The repo lives on `D:`, the uv cache on `C:`, so hardlinks fail and uv copies. Harmless; `link-mode`
  is set to `copy` in uv's own config.
