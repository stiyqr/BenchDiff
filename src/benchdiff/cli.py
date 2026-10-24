"""Command-line entry point for BenchDiff."""

from __future__ import annotations

import argparse
import json
import sys

from benchdiff import __version__
from benchdiff.errors import ConfigError
from benchdiff.model import RunSpec
from benchdiff.resolve import Overrides, resolve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="benchdiff",
        description="Benchmark a Git range.",
    )
    parser.add_argument("--version", action="version", version=f"benchdiff {__version__}")

    commands = parser.add_subparsers(dest="command", metavar="COMMAND")
    resolver = commands.add_parser(
        "resolve",
        help="print the run plan without running anything",
        description="Read a manifest and print the run plan it resolves to. Runs nothing.",
    )
    resolver.add_argument(
        "--path", default=".", metavar="DIR", help="target repository (default: .)"
    )
    resolver.add_argument(
        "--manifest",
        metavar="FILE",
        help=(
            "manifest file (default: <path>/benchdiff.toml); "
            "relative paths use the current directory"
        ),
    )
    resolver.add_argument("--baseline", required=True, metavar="REV", help="baseline revision")
    resolver.add_argument("--optimized", required=True, metavar="REV", help="optimized revision")
    resolver.add_argument("--samples", type=int, metavar="N", help="samples per revision")
    resolver.add_argument("--warmup", type=int, metavar="N", help="discarded runs per revision")
    resolver.add_argument("--timeout", metavar="DUR", help='per-run timeout, e.g. "300s", "5m"')
    resolver.add_argument("--out", metavar="DIR", help="output directory (default: ./.benchdiff)")
    resolver.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="plan format (default: text)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0

    try:
        spec = resolve(
            baseline=args.baseline,
            optimized=args.optimized,
            target=args.path,
            manifest=args.manifest,
            overrides=Overrides(
                samples=args.samples,
                warmup=args.warmup,
                timeout=args.timeout,
                out=args.out,
            ),
        )
        output = render_json(spec) if args.format == "json" else render_text(spec)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(output)
    return 0


def render_text(spec: RunSpec) -> str:
    """The human-facing plan. Every number here comes straight from the spec."""
    project = spec.project
    bench = spec.bench
    overlay = ", ".join(bench.overlay) if bench.overlay else "(none)"
    lines = [
        f"target:    {spec.target}",
        f"manifest:  {spec.manifest}",
        f"baseline:  {spec.baseline}",
        f"optimized: {spec.optimized}",
        f"out:       {spec.out_dir}",
        "",
        f"project:   {project.name} ({project.language or 'unspecified'}, {project.mode.value})",
        f"command:   {bench.command}",
        f"samples:   {bench.samples}",
        f"warmup:    {bench.warmup}",
        f"timeout:   {bench.timeout_seconds:g}s",
        f"overlay:   {overlay}",
        "",
        "metrics:",
    ]
    for metric in bench.metrics:
        lines.append(
            f"  {metric.name} ({metric.label}) [{metric.unit}, {metric.direction.value}] "
            f"group {metric.group}"
        )
        lines.append(f"    pattern: {metric.pattern.pattern}")
    return "\n".join(lines)


def render_json(spec: RunSpec) -> str:
    """The stable machine-facing plan, in the shape documented in docs/phase-1.md."""
    return json.dumps(plan_to_dict(spec), indent=2)


def plan_to_dict(spec: RunSpec) -> dict[str, object]:
    """Facts about the plan, ready for JSON."""
    return {
        "target": spec.target.as_posix(),
        "manifest": spec.manifest.as_posix(),
        "baseline": spec.baseline,
        "optimized": spec.optimized,
        "out_dir": spec.out_dir.as_posix(),
        "project": {
            "name": spec.project.name,
            "language": spec.project.language,
            "mode": spec.project.mode.value,
        },
        "bench": {
            "command": spec.bench.command,
            "samples": spec.bench.samples,
            "warmup": spec.bench.warmup,
            "timeout_seconds": spec.bench.timeout_seconds,
            "overlay": list(spec.bench.overlay),
            "metrics": [
                {
                    "name": metric.name,
                    "label": metric.label,
                    "unit": metric.unit,
                    "direction": metric.direction.value,
                    "group": metric.group,
                    "pattern": metric.pattern.pattern,
                }
                for metric in spec.bench.metrics
            ],
        },
    }


if __name__ == "__main__":
    sys.exit(main())
