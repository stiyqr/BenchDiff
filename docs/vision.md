# BenchDiff — Vision

> BenchDiff benchmarks a **Git range**, not a command. It materialises two revisions, measures
> both under identical conditions, and turns the difference into a delta you can defend.

**Status:** draft 1 — for discussion. Open forks are tracked in [`decisions.md`](./decisions.md).

---

## 1. The problem

Everyone who optimises code hits the same wall at the end: they *know* it got faster, but they
cannot say by how much, defensibly. So they re-run a benchmark by hand, eyeball two numbers, and
write "~40% faster" in a bullet, hoping nobody asks how it was measured.

The measurement tools that exist are all sharp but narrow:

| Tool | Good at | Missing |
|---|---|---|
| `hyperfine` | Timing any shell command, warmups, markdown/JSON export | No Git awareness, no revision pairing, no stats across runs |
| `go test -bench` + `benchstat` | Rigorous statistical comparison of two Go benchmark sets | Go only, no orchestration, you drive it by hand |
| `cargo bench` / Criterion | Baseline-vs-new change detection with p-values | Rust only, per-project local baselines |
| `pytest-benchmark`, Benchmark.js | Language-native microbenchmarks | No cross-revision comparison |
| k6 / Locust | Load testing a running service | No Git awareness, no revision orchestration, no report |
| Bencher / CodSpeed | CI perf regression tracking with thresholds | Cloud-first, invasive integration, not a local one-shot tool |

The gap is not *measurement*. It is **orchestration and the last mile**: pair two revisions,
enforce the same conditions for both, aggregate honestly, and emit something a human (or a hiring
manager) can trust.

## 2. What BenchDiff is

A local-first CLI that treats the target repo as a **black box**. Given two revisions and a
declared benchmark command, it:

1. materialises both revisions in throwaway checkouts (never touching your working tree),
2. runs the benchmark repeatedly, **interleaved** between the two revisions,
3. extracts declared metrics from the output,
4. computes the delta with its uncertainty and a verdict,
5. writes a JSON record of facts plus a rendered report.

One command, one artifact, zero instrumentation of the target.

```text
benchdiff run --baseline main --optimized HEAD
```

### The mental model — three nouns

- **Target** — a repo plus a manifest that declares *how to measure it*.
- **Comparison** — a revision pair (`optimize` mode) or a workload sweep (`scale` mode).
- **Report** — immutable JSON facts, plus renderers that turn them into prose.

Everything else in this document is plumbing around those three.

## 3. What we are *not* inventing

This matters for scope and for how the project is pitched.

- The statistics are not novel. `benchstat` already solved "are these two benchmark sets actually
  different?" — median, confidence intervals, and an explicit *"they look the same"* answer. We
  should copy that discipline, not invent a new p-value.
- The measurement is not novel. The target's own harness (`go test -bench`, `criterion`, `pytest-benchmark`,
  `hyperfine`, k6) does the measuring. We never reimplement it.
- The novelty is the **integration**: Git-aware pairing + universal manifest + interleaved sampling +
  verdict-first output + auditable report, in one binary that works on any language.

That framing is defensible in an interview. "I wrote a benchmark framework" invites hard questions.
"I wrote the orchestration and statistical reporting layer that turns any harness into a defensible
Git-diff delta" does not.

## 4. Design principles

1. **Black box target.** No source edits, no imports, no instrumentation. If the target can run a
   shell command, BenchDiff can measure it. This is what makes it language-agnostic.
2. **Never touch the user's working tree.** No `git stash`, no `git checkout` in the user's repo.
   Throwaway worktrees only. (See §7 — this is a deliberate reversal of the draft.)
3. **Statistics before prose.** Every number carries `n`, dispersion, and a confidence interval.
   A point estimate alone is not a result.
4. **"Inconclusive" is a first-class answer.** If the delta sits inside the noise, say so and refuse
   to dress it up. A tool that can only ever report wins is a toy.
5. **JSON is the source of truth; prose is a renderer.** Every report format is derived from one
   immutable run record. This makes new outputs (terminal, markdown, HTML, CI) cheap and consistent.
6. **The manifest is the extension point.** Adding a language means writing a TOML block, not a
   release. Adapters are presets/sugar, not the core abstraction.
7. **AI lives after the numbers, never in them.** The measurement path stays deterministic. AI is
   opt-in, local-first, and post-hoc.
8. **Reproducibility is part of the output.** Every report embeds the exact command, both commit
   SHAs, the harness overlay hash, sample count, dispersion, and host fingerprint.

## 5. Determinism, honestly stated

The draft calls this tool "deterministic". It is — but only in one sense, and the distinction
matters for every claim the tool makes.

**Deterministic in orchestration:** same inputs → same plan, same execution order, same extraction,
same math, same verdict logic. Re-running the tool reproduces the *analysis* exactly.

**Not deterministic in physics:** timings on shared hardware always vary — turbo clocks, thermal
throttling, background processes, page cache. No tool can fix that. What a tool *can* do is make the
variance visible and make the comparison robust to it:

- discard warmup runs (cold page cache / JIT / branch predictor),
- **interleave** A/B/A/B instead of AAAA…BBBB…, so slow drift hits both revisions equally,
- aggregate with median + IQR, not mean,
- report a confidence interval on the *delta*, not just on each side,
- run an optional **A/A control** (same revision, both slots) to measure the tool's own noise floor,
- refuse a verdict when the delta is below that floor.

That last point is the whole ballgame. It is what lets the tool say "verified" without lying.

## 6. Modes

### 6.1 `optimize` — the core (v1)

Two revisions, one benchmark command, repeated samples. Output: delta in time, memory, allocations,
or any declared metric, with a verdict.

Used for: "I made this faster, prove it". This is the mode that earns the CV bullet.

### 6.2 `scale` — new features (v2)

One revision, a workload parameter swept across steps (`100 → 1,000 → 10,000`). Output: growth
factor vs. workload factor, fitted complexity, and whether memory stays flat.

Used for: "I added a feature, prove it won't fall over at 10k". Different question, different math
(no baseline to diff against), so it is a separate mode with its own analyzer.

### 6.3 Later modes (deliberately deferred)

- **`refactor`** — same as `optimize`, but the pass condition is *neutrality*: no regression beyond
  the noise floor. Nearly free once `optimize` exists; the value is in the verdict semantics.
- **`macro`** — replay-style load testing of a whole service (compose stack, DB seed/reset, k6 run,
  p99 / RPS / saturation). This is a genuinely different product (infrastructure orchestration, not
  process execution) and it must not distort the core. Separate command, separate phase.
- **CI gate** — `--fail-if-regression 3%` with exit codes. Turns BenchDiff from a reporting tool
  into a merge gate. High value, low cost, after the report is trustworthy.
- **TUI** — a nice-to-have. Flags first, always. A tool that needs a config edit to change a
  parameter is broken; a tool that *requires* a TUI is worse.

## 7. Architecture

```text
 revA ─┐                                  ┌─ run.json  (facts, immutable)
       ├─▶ [1] Resolve ─▶ [2] Materialise ─┼─▶ [3] Execute ─▶ [4] Extract ─▶ [5] Analyse ─▶ [6] Render
 revB ─┘        │              │          └─▶ report.md / terminal / (later: html, ci)
                │              │
          CLI + manifest   worktree + overlay
                            (temp dir, cleaned up)
                                                    [7] AI  (opt-in, post-hoc, local)
```

Each stage has one job and a hard contract:

| # | Stage | In → Out | Failure mode it must handle |
|---|---|---|---|
| 1 | **Resolve** | CLI args + manifest → `RunSpec` | Missing manifest, unknown mode, bad revision, CLI/manifest conflict |
| 2 | **Materialise** | `RunSpec` → two clean checkouts | Dirty tree, detached HEAD, submodules, LFS, missing harness files |
| 3 | **Execute** | checkout + command → raw stdout/stderr + timing | Non-zero exit, timeout, missing binary |
| 4 | **Extract** | raw output → typed samples per metric | Regex matched nothing, NaN, multiple matches |
| 5 | **Analyse** | samples → stats + verdict | Too few samples, degenerate distribution, noise floor |
| 6 | **Render** | run record → markdown / terminal | Never re-derives numbers; renderer must be pure |
| 7 | **AI** (opt-in) | diff + deltas + language → prose | Model absent, invalid JSON, hallucinated numbers |

### The overlay problem (the thing the draft missed)

Your benchmark harness usually does **not** exist at the baseline commit. It lives on your branch,
or worse, is uncommitted. If BenchDiff simply checks out the parent commit, there is nothing to run.

So Materialise does two things:

1. `git worktree add --detach <tmp> <rev>` — exact commit, zero risk to your workspace.
2. **Overlay** a declared set of paths (the manifest itself, `bench/`, seed scripts) from your
   *working tree* into both checkouts, byte-identical.

The overlay's content hash goes into the report. Otherwise you cannot tell whether a difference came
from the code or from a changed benchmark.

### Executors

Execution is an interface with two backends:

- `local` (v1) — child process, working directory pinned to the checkout, timeout, captured streams,
  host fingerprint recorded.
- `docker` (later) — same interface, pinned CPUs/memory, no network, reproducible image per language.

The sampling and analysis layers never know which one ran. This is why Docker can land later without
a rewrite.

## 8. The manifest (illustrative shape, not final schema)

`benchdiff.toml`, at the target repo root:

```toml
[project]
name = "banking-core"
language = "go"        # advisory: used for AI prompts and adapter presets
mode = "optimize"      # optimize | scale

[bench]
command = "go test -bench=. -benchmem -count=1 ./internal/billing/..."
samples = 10           # process-level runs per revision
warmup  = 1            # discarded runs, applied to both revisions
timeout = "300s"
overlay = ["bench/", "scripts/seed_test_db.sql"]

[[bench.metrics]]
name      = "latency"
unit      = "ns/op"
direction = "lower_is_better"
extract   = { regex = '^\S+\s+\d+\s+([\d.]+) ns/op' }

[[bench.metrics]]
name      = "allocs"
unit      = "B/op"
direction = "lower_is_better"
extract   = { regex = '^\S+\s+\d+\s+[\d.]+ ns/op\s+(\d+) B/op' }
```

Rules:

- **Precedence:** CLI flag > manifest > built-in default. A flag never requires a file edit.
- **Metrics are declared, never inferred.** If a declared metric fails to extract, that is a hard
  error — not a silent zero. Silent zeros are how benchmark tools lie.
- **Direction is required.** "23% fewer bytes" and "23% more requests/sec" are both improvements.
- **Language is advisory only.** Nothing in the pipeline branches on it except AI prompts and
  preset generation. This is what keeps the core from becoming a parser zoo.

Language presets (`benchdiff init --language=go`) can generate a starting manifest later. Presets
are a convenience; the regex contract is the abstraction.

## 9. The integrity contract

The tool's only real asset is that its numbers are believable. Non-negotiable rules:

1. **No point estimates without dispersion.** Median, IQR, n, min/max. Always.
2. **No verdict inside the noise floor.** Below the measured floor → `inconclusive`.
3. **No silent failures.** Unmatched metric, non-zero exit, timeout → fail loudly with the raw output.
4. **No unmeasured claims.** The renderer may only state numbers present in the run record.
5. **No hidden conditions.** The report carries command, SHAs, overlay hash, host, and sample count.
6. **The renderer refuses.** If the verdict is `inconclusive`, the CV renderer emits the honest
   version ("no measurable difference at n=10") rather than the aspirational one.
7. **"Measured", not "verified".** Nothing here is independently verified; say what was done.

Rule 6 is the feature. It is what separates this from a bullet-point generator.

## 10. AI layer (opt-in, post-hoc)

Off by default. `--ai` or `[ai] enabled = true`. Runs only after `Analyse` has frozen the numbers.

**Inputs:** the diff between the two revisions, the frozen metrics, the language.
**Outputs (three separate commands, so users can take one without the others):**

| Feature | Question it answers |
|---|---|
| `explain` | *Why* did this work, mechanically? (allocations removed, lock contention, cache lines) |
| `bullet` | Turn the facts into a resume/PR sentence, without inflating them |
| `next` | What is still slow in the new code, and what should I try next? |

**Constraints:**

- Local-first via Ollama; no cloud key required. Cloud providers are an optional plug.
- Strict JSON schema out, validated, retried once, then fail cleanly.
- The model may **not** invent numbers. Bullets are generated from a template populated with the
  frozen metrics; the model only writes the clause around them.
- If the model is unavailable, BenchDiff still works — just without the prose.

Note that the `bullet` feature is the one users will care about most, and the one most likely to
inflate claims. Hence the template constraint: the model gets to write English, not statistics.

The **intent classifier** (AI picks `optimize` vs `scale` from the diff) is a cute idea and a bad
default. It adds a non-deterministic step at the very front of a deterministic pipeline, and it can
silently pick the wrong mode. Explicit `--mode` always wins; classification can be a suggestion
printed in the output, never an automatic branch.

## 11. What v1 is / is not

**v1 (the thing we build first):**

- `optimize` mode, `local` executor, local repo path (remote URLs optional).
- Manifest with command, samples, warmup, overlay, N declared metrics via regex.
- Interleaved sampling, warmup discard, median/IQR, delta + confidence interval, verdict.
- Non-destructive via worktree + overlay, with guaranteed cleanup.
- Terminal report + `run.json` + markdown renderer.
- Verified end-to-end against a generated dummy repo with a known ~10× improvement.

**Not v1 (explicitly out of scope):**

- Docker execution, remote Git URLs, `scale` mode, `macro` mode, AI, TUI, CI exit codes, HTML,
  per-language adapters, Windows-specific performance tuning.

Every item on the second list has a phase in the roadmap. None of them are allowed to shape v1.

## 12. Risks

| Risk | Why it matters | Mitigation |
|---|---|---|
| Laptop noise makes small deltas meaningless | Undermines every claim | Interleaving, warmup, A/A calibration, noise floor, honest verdicts |
| Scope creep (3 modes + AI + Docker + macro) | Nothing ships | Phase fence in §11; each mode is its own analyzer |
| Manifest regex is tedious to write | Adoption friction | `init` presets per language; regex is still the contract |
| "Verified" wording invites scrutiny | Credibility | Say "measured"; embed reproduction footer |
| Macro mode is a different product | Derails core | Separate command and phase, shared only at the report layer |
| 8B local models produce bad prose/JSON | Feature looks broken | Strict schema, retry, template-constrained bullets, graceful absence |
| Cross-machine numbers differ | Confusion when sharing | Report is scoped to "this machine, this run"; no cross-machine comparison claims |

## 13. Phase sketch

One-liners only — detailed plans get written per phase, right before building it.

| Phase | Deliverable | Ships when |
|---|---|---|
| 0 | Repo skeleton, docs, `git init`, `uv` + `ruff` + `pytest`, CI | `pytest` and `ruff check` pass on an empty project |
| 1 | Manifest parsing + config resolution + precedence | Table-driven tests cover every precedence and error case |
| 2 | Materialise: worktree, overlay, cleanup | Fixture repo runs a command at both revisions; workspace provably untouched |
| 3 | Execute + extract, single revision, one metric | First end-to-end run prints a raw number from the dummy repo |
| 4 | Sampling + analysis + verdict + `run.json` | Dummy repo reports a 10× speedup with an `improved` verdict, reproducibly |
| 5 | Report renderers (terminal + markdown + trust footer) | `report.md` is auditable and refuses to overclaim |
| 6 | Hardening: A/A calibration, edge cases, docs, demo | v1.0 tagged, demo recorded |
| 7 | `docker` executor | Same v1 report, produced inside a pinned container |
| 8 | `scale` mode | Growth curve + complexity estimate on the dummy repo |
| 9 | AI layer (`explain`, `bullet`, `next`) via Ollama | Works offline; degrades cleanly with no model |
| 10 | `macro` replay mode | Baseline vs optimized p99/RPS on a compose stack |

## 14. Open questions

1. ~~Language for the CLI itself.~~ **Answered: Python 3.12+.** Go would buy a single binary and a
   better systems signal, but you would be learning it while designing the pipeline. The core stays
   pure so a port remains cheap. See `decisions.md` D20.
2. **Who is the actual first user?** If this is primarily a CV/demo artifact, `optimize` + reports is
   enough. If you intend to run it on the real legacy monolith, `macro` matters much earlier and the
   whole roadmap reorders.
3. **Is the target repo always dirty?** If yes, overlay handling is critical-path and needs to land in
   phase 2, not "later".
4. **How many samples can we afford by default?** 10 × 2 revisions × warmup is fine for microbenches;
   for a 2-minute load test it is not. Per-mode defaults, not one global number.
5. **Do we support remote URLs in v1?** Cheap (`git clone --filter=blob:none`) but adds auth, LFS, and
   network failure paths. Probably yes, but as a thin wrapper around the local path.
6. **Distribution:** Homebrew/Scoop/`go install`/curl? Affects binary size and release engineering,
   not architecture — decide at phase 6.

## 15. Deliberate departures from the draft

| Draft said | We do instead | Why |
|---|---|---|
| `git stash` + `git checkout` in the user's repo, restore in `finally` | Throwaway `git worktree`, never touch the workspace | `stash pop` can conflict or silently fail; a detached HEAD breaks "checkout original branch"; a crash leaves the user stranded mid-history |
| "Isolated workspace in `/tmp`" **and** "stash your workspace" | Worktree in a temp dir — one mechanism, not two | The two ideas contradict each other; worktree is the safer one |
| Docker sandbox required from day one | `local` executor first behind an interface, `docker` in phase 7 | Docker would block the first end-to-end run on image plumbing |
| Language-specific parsers (Go/Rust/Python/Node) as core | Declared metrics + regex in the manifest; adapters become presets | Four parsers = four maintenance burdens before anything ships |
| `N` runs, median + IQR | Same, plus **interleaved** ordering, warmup discard, and a CI on the delta | Batch-running A then B lets thermal drift masquerade as a result |
| "Deterministic benchmarking" | Deterministic orchestration; variance made visible, never hidden | The first claim is unachievable and an interviewer will know it |
| "Verified Performance Impact Report" | "Measured Performance Impact" + reproduction footer | Nothing is verified by a tool that runs your own harness |
| AI intent classifier as step 1 | Explicit `--mode`; classification is at most a suggestion | Do not put a non-deterministic branch at the front of a deterministic pipeline |
| CV bullet as the primary output | `run.json` is primary; the bullet is one renderer | Without the record, the bullet is unfalsifiable marketing |
| Macro-benchmarking as a mode of the same tool | Deferred to phase 10, separate command | It orchestrates infrastructure, not processes — a different product |
