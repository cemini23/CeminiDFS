from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

try:
    from ceminidfs.orchestrator.run import run_pipeline
    from ceminidfs.orchestrator.run import _run_fetch, _run_normalize, _run_optimize
except Exception:  # pragma: no cover - defensive for partial installs
    run_pipeline = None  # type: ignore[assignment]
    _run_fetch = None  # type: ignore[assignment]
    _run_normalize = None  # type: ignore[assignment]
    _run_optimize = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.project import project_week
except Exception:  # pragma: no cover - defensive for partial installs
    project_week = None  # type: ignore[assignment]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2
    return args.handler(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ceminidfs", description="CeminiDFS command line tools")
    subparsers = parser.add_subparsers(dest="command")

    fetch = subparsers.add_parser("fetch", help="Fetch source data for a season or week")
    fetch.add_argument("--season", type=int, required=True)
    fetch.add_argument("--week", type=int)
    fetch.set_defaults(handler=_cmd_fetch)

    project = subparsers.add_parser("project", help="Create canonical placeholder projections")
    project.add_argument("--season", type=int, required=True)
    project.add_argument("--week", type=int, required=True)
    project.add_argument("--salary", type=Path, required=True)
    project.set_defaults(handler=_cmd_project)

    normalize = subparsers.add_parser("normalize", help="Normalize a projection CSV for a DFS site")
    normalize.add_argument("--in", dest="input_path", type=Path, required=True)
    normalize.add_argument("--out", dest="output_path", type=Path, required=True)
    normalize.add_argument("--site", required=True)
    normalize.set_defaults(handler=_cmd_normalize)

    optimize = subparsers.add_parser("optimize", help="Generate lineups from a normalized CSV")
    optimize.add_argument("--csv", dest="csv_path", type=Path, required=True)
    optimize.add_argument("--out", dest="output_path", type=Path, required=True)
    optimize.add_argument("--count", type=int, default=150)
    optimize.set_defaults(handler=_cmd_optimize)

    run = subparsers.add_parser("run", help="Run one or more pipeline stages")
    run.add_argument("--season", type=int, required=True)
    run.add_argument("--week", type=int, required=True)
    run.add_argument("--salary", type=Path, required=True)
    run.add_argument("--stages", default="all", help="all or comma-separated: fetch,project,normalize,optimize")
    run.set_defaults(handler=_cmd_run)

    return parser


def _cmd_fetch(args: argparse.Namespace) -> int:
    if _run_fetch is None:
        raise RuntimeError("Fetch stage unavailable: orchestrator import failed")
    week = args.week if args.week is not None else 0
    artifact = _run_fetch(args.season, week, {"work_dir": Path("runs") / f"{args.season}_fetch"})
    print(artifact)
    return 0


def _cmd_project(args: argparse.Namespace) -> int:
    if project_week is None:
        raise RuntimeError("Projection stage unavailable: ceminidfs.pipeline.project import failed")
    output = project_week(args.season, args.week, args.salary, {})
    print(output)
    return 0


def _cmd_normalize(args: argparse.Namespace) -> int:
    if _run_normalize is None:
        raise RuntimeError("Normalize stage unavailable: orchestrator import failed")
    output = _run_normalize(args.input_path, args.output_path, site=args.site, config={})
    print(output)
    return 0


def _cmd_optimize(args: argparse.Namespace) -> int:
    if _run_optimize is None:
        raise RuntimeError("Optimize stage unavailable: orchestrator import failed")
    output = _run_optimize(args.csv_path, args.output_path, args.count, {})
    print(output)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    if run_pipeline is None:
        raise RuntimeError("Run pipeline unavailable: orchestrator import failed")
    manifest = run_pipeline(
        season=args.season,
        week=args.week,
        salary_path=args.salary,
        stages=args.stages,
        config={"count": 150},
    )
    print(manifest)
    return 0
