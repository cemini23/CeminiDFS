from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from ceminidfs.config import runtime_config

try:
    from ceminidfs.orchestrator.run import run_pipeline
    from ceminidfs.orchestrator.run import _run_fetch, _run_normalize, _run_optimize
except ImportError:  # pragma: no cover - defensive for partial installs
    run_pipeline = None  # type: ignore[assignment]
    _run_fetch = None  # type: ignore[assignment]
    _run_normalize = None  # type: ignore[assignment]
    _run_optimize = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.project import project_week
except ImportError:  # pragma: no cover - defensive for partial installs
    project_week = None  # type: ignore[assignment]

try:
    from ceminidfs.data.salary import write_salary_canonical
except ImportError:  # pragma: no cover - defensive for partial installs
    write_salary_canonical = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.backtest import format_backtest_summary, run_backtest, write_backtest_report
except ImportError:  # pragma: no cover - defensive for partial installs
    run_backtest = None  # type: ignore[assignment]
    write_backtest_report = None  # type: ignore[assignment]
    format_backtest_summary = None  # type: ignore[assignment]

try:
    from ceminidfs.data.benchmark import parse_benchmark_csv, write_benchmark_snapshot
    from ceminidfs.pipeline.benchmark_compare import (
        compare_benchmark_week,
        format_benchmark_compare,
        write_benchmark_compare_report,
    )
except ImportError:  # pragma: no cover - defensive for partial installs
    parse_benchmark_csv = None  # type: ignore[assignment]
    write_benchmark_snapshot = None  # type: ignore[assignment]
    compare_benchmark_week = None  # type: ignore[assignment]
    write_benchmark_compare_report = None  # type: ignore[assignment]
    format_benchmark_compare = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.calibration import (
        build_calibration_report,
        render_calibration_brief,
        write_calibration_brief,
        write_calibration_json,
    )
except ImportError:  # pragma: no cover - defensive for partial installs
    build_calibration_report = None  # type: ignore[assignment]
    write_calibration_brief = None  # type: ignore[assignment]
    write_calibration_json = None  # type: ignore[assignment]
    render_calibration_brief = None  # type: ignore[assignment]


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

    fetch = subparsers.add_parser("fetch", help="Fetch week-scoped source data")
    fetch.add_argument("--season", type=int, required=True)
    fetch.add_argument("--week", type=int, required=True)
    fetch.add_argument(
        "--allow-stub",
        action="store_true",
        help="Write a stub artifact when nflreadpy is unavailable",
    )
    fetch.set_defaults(handler=_cmd_fetch)

    project = subparsers.add_parser("project", help="Create canonical placeholder projections")
    project.add_argument("--season", type=int, required=True)
    project.add_argument("--week", type=int, required=True)
    project.add_argument("--salary", type=Path, required=True)
    project.set_defaults(handler=_cmd_project)

    salary = subparsers.add_parser("salary", help="Ingest a salary CSV into canonical schema")
    salary.add_argument("--season", type=int, required=True)
    salary.add_argument("--week", type=int, required=True)
    salary.add_argument("--salary", type=Path, required=True)
    salary.add_argument("--out", dest="output_path", type=Path, required=True)
    salary.add_argument("--site")
    salary.set_defaults(handler=_cmd_salary)

    normalize = subparsers.add_parser("normalize", help="Normalize a projection CSV for a DFS site")
    normalize.add_argument("--in", dest="input_path", type=Path, required=True)
    normalize.add_argument("--out", dest="output_path", type=Path, required=True)
    normalize.add_argument("--site", required=True)
    normalize.set_defaults(handler=_cmd_normalize)

    optimize = subparsers.add_parser("optimize", help="Generate lineups from a normalized CSV")
    optimize.add_argument("--csv", dest="csv_path", type=Path, required=True)
    optimize.add_argument("--out", dest="output_path", type=Path, required=True)
    optimize.add_argument("--count", type=int, default=150)
    optimize.add_argument("--site", default="fanduel")
    optimize.set_defaults(handler=_cmd_optimize)

    run = subparsers.add_parser("run", help="Run one or more pipeline stages")
    run.add_argument("--season", type=int, required=True)
    run.add_argument("--week", type=int, required=True)
    run.add_argument("--salary", type=Path, required=True)
    run.add_argument("--site", default="fanduel")
    run.add_argument("--count", type=int, default=150)
    run.add_argument(
        "--stages",
        default="all",
        help="all or comma-separated: fetch,project,normalize,optimize",
    )
    run.add_argument(
        "--allow-stub",
        action="store_true",
        help="Allow fetch stage to write stub artifacts when data deps are missing",
    )
    run.set_defaults(handler=_cmd_run)

    backtest = subparsers.add_parser("backtest", help="Walk-forward projection accuracy backtest")
    backtest.add_argument("--season", type=int, required=True)
    backtest.add_argument("--start-week", type=int, required=True)
    backtest.add_argument("--end-week", type=int, required=True)
    backtest.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        default=Path("reports/backtest.json"),
        help="JSON report path (default: reports/backtest.json)",
    )
    backtest.set_defaults(handler=_cmd_backtest)

    benchmark = subparsers.add_parser("benchmark", help="Paid projection benchmark tools")
    benchmark_sub = benchmark.add_subparsers(dest="benchmark_command")

    benchmark_load = benchmark_sub.add_parser("load", help="Parse a Stokastic/Labs CSV into a snapshot JSON")
    benchmark_load.add_argument("--csv", dest="csv_path", type=Path, required=True)
    benchmark_load.add_argument("--out", dest="output_path", type=Path, required=True)
    benchmark_load.add_argument("--season", type=int)
    benchmark_load.add_argument("--week", type=int)
    benchmark_load.add_argument("--site", default="fanduel")
    benchmark_load.add_argument("--source", help="stokastic, fantasylabs, etr, or generic")
    benchmark_load.set_defaults(handler=_cmd_benchmark_load)

    benchmark_compare = benchmark_sub.add_parser(
        "compare",
        help="Compare paid projections vs actuals (and optional DIY model)",
    )
    benchmark_compare.add_argument("--season", type=int, required=True)
    benchmark_compare.add_argument("--week", type=int, required=True)
    benchmark_compare.add_argument("--csv", dest="csv_path", type=Path, required=True)
    benchmark_compare.add_argument("--site", default="fanduel")
    benchmark_compare.add_argument("--source")
    benchmark_compare.add_argument(
        "--no-diy",
        action="store_true",
        help="Skip DIY model comparison (benchmark vs actuals only)",
    )
    benchmark_compare.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        default=Path("reports/benchmark_compare.json"),
    )
    benchmark_compare.set_defaults(handler=_cmd_benchmark_compare)

    calibrate = subparsers.add_parser("calibrate", help="Generate calibration wiki brief from backtest results")
    calibrate.add_argument("--season", type=int, required=True)
    calibrate.add_argument("--start-week", type=int, required=True)
    calibrate.add_argument("--end-week", type=int, required=True)
    calibrate.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        default=Path("reports/calibration_brief.md"),
        help="Markdown wiki brief path (default: reports/calibration_brief.md)",
    )
    calibrate.add_argument(
        "--json-out",
        dest="json_output_path",
        type=Path,
        default=Path("reports/calibration.json"),
        help="Structured JSON report path (default: reports/calibration.json)",
    )
    calibrate.add_argument("--benchmark-csv", dest="benchmark_csv", type=Path, help="Optional paid export for one week")
    calibrate.add_argument(
        "--benchmark-week",
        type=int,
        help="Week for benchmark CSV (default: end-week)",
    )
    calibrate.set_defaults(handler=_cmd_calibrate)

    return parser


def _cmd_fetch(args: argparse.Namespace) -> int:
    if _run_fetch is None:
        raise RuntimeError("Fetch stage unavailable: orchestrator import failed")
    config = runtime_config(
        work_dir=Path("runs") / f"{args.season}_week_{args.week}",
        allow_stub=args.allow_stub,
    )
    artifact = _run_fetch(args.season, args.week, config)
    print(artifact)
    return 0


def _cmd_project(args: argparse.Namespace) -> int:
    if project_week is None:
        raise RuntimeError("Projection stage unavailable: ceminidfs.pipeline.project import failed")
    config = runtime_config(work_dir=Path("runs") / f"{args.season}_week_{args.week}")
    output = project_week(args.season, args.week, args.salary, config)
    print(output)
    return 0


def _cmd_salary(args: argparse.Namespace) -> int:
    if write_salary_canonical is None:
        raise RuntimeError("Salary ingest unavailable: ceminidfs.data.salary import failed")
    output = write_salary_canonical(
        args.salary,
        args.output_path,
        args.season,
        args.week,
        site=args.site,
    )
    print(output)
    return 0


def _cmd_normalize(args: argparse.Namespace) -> int:
    if _run_normalize is None:
        raise RuntimeError("Normalize stage unavailable: orchestrator import failed")
    config = runtime_config(site=args.site)
    output = _run_normalize(args.input_path, args.output_path, site=args.site, config=config)
    print(output)
    return 0


def _cmd_optimize(args: argparse.Namespace) -> int:
    if _run_optimize is None:
        raise RuntimeError("Optimize stage unavailable: orchestrator import failed")
    config = runtime_config(site=args.site, count=args.count)
    output = _run_optimize(args.csv_path, args.output_path, args.count, config)
    print(output)
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    if run_pipeline is None:
        raise RuntimeError("Run pipeline unavailable: orchestrator import failed")
    config = runtime_config(
        count=args.count,
        site=args.site,
        allow_stub=args.allow_stub,
    )
    manifest = run_pipeline(
        season=args.season,
        week=args.week,
        salary_path=args.salary,
        stages=args.stages,
        config=config,
    )
    print(manifest)
    return 0


def _cmd_backtest(args: argparse.Namespace) -> int:
    if run_backtest is None or write_backtest_report is None or format_backtest_summary is None:
        raise RuntimeError("Backtest unavailable: ceminidfs.pipeline.backtest import failed")
    config = runtime_config()
    summary = run_backtest(args.season, args.start_week, args.end_week, config=config)
    report_path = write_backtest_report(summary, args.output_path)
    print(format_backtest_summary(summary))
    print(f"\nReport: {report_path}")
    return 0


def _cmd_benchmark_load(args: argparse.Namespace) -> int:
    if parse_benchmark_csv is None or write_benchmark_snapshot is None:
        raise RuntimeError("Benchmark load unavailable: ceminidfs.data.benchmark import failed")
    rows = parse_benchmark_csv(
        args.csv_path,
        site=args.site,
        source=args.source,
        season=args.season,
        week=args.week,
    )
    output = write_benchmark_snapshot(rows, args.output_path)
    print(f"Loaded {len(rows)} benchmark rows → {output}")
    return 0


def _cmd_benchmark_compare(args: argparse.Namespace) -> int:
    if compare_benchmark_week is None or write_benchmark_compare_report is None or format_benchmark_compare is None:
        raise RuntimeError("Benchmark compare unavailable: ceminidfs.pipeline.benchmark_compare import failed")
    config = runtime_config()
    result = compare_benchmark_week(
        args.season,
        args.week,
        args.csv_path,
        site=args.site,
        source=args.source,
        include_diy=not args.no_diy,
        config=config,
    )
    report_path = write_benchmark_compare_report(result, args.output_path)
    print(format_benchmark_compare(result))
    print(f"\nReport: {report_path}")
    return 0


def _cmd_calibrate(args: argparse.Namespace) -> int:
    if (
        build_calibration_report is None
        or write_calibration_brief is None
        or write_calibration_json is None
        or render_calibration_brief is None
    ):
        raise RuntimeError("Calibrate unavailable: ceminidfs.pipeline.calibration import failed")
    config = runtime_config()
    report = build_calibration_report(
        args.season,
        args.start_week,
        args.end_week,
        benchmark_csv=args.benchmark_csv,
        benchmark_week=args.benchmark_week,
        config=config,
    )
    brief_path = write_calibration_brief(report, args.output_path)
    json_path = write_calibration_json(report, args.json_output_path)
    print(render_calibration_brief(report))
    print(f"\nBrief: {brief_path}")
    print(f"JSON:  {json_path}")
    return 0
