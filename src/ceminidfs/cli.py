from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from ceminidfs.config import runtime_config

try:
    from ceminidfs.export.pool_guards import DEFAULT_MIN_SKILL_POOL
except ImportError:  # pragma: no cover - defensive for partial installs
    DEFAULT_MIN_SKILL_POOL = 40

try:
    from ceminidfs.bbm.cli import build_bbm_parser, handle_bbm_command
except ImportError:  # pragma: no cover - defensive for partial installs
    build_bbm_parser = None  # type: ignore[assignment]
    handle_bbm_command = None  # type: ignore[assignment]

try:
    from ceminidfs.redraft.cli import build_redraft_parser, handle_redraft_command
except ImportError:  # pragma: no cover - defensive for partial installs
    build_redraft_parser = None  # type: ignore[assignment]
    handle_redraft_command = None  # type: ignore[assignment]

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
    from ceminidfs.data.ownership_labels import load_ownership_labels
    from ceminidfs.data.salary import apply_salary_fppg_placeholder, parse_salary_csv
    from ceminidfs.models.ownership import fit_ownership_calibration, save_ownership_calibration
except ImportError:  # pragma: no cover - defensive for partial installs
    load_ownership_labels = None  # type: ignore[assignment]
    parse_salary_csv = None  # type: ignore[assignment]
    apply_salary_fppg_placeholder = None  # type: ignore[assignment]
    fit_ownership_calibration = None  # type: ignore[assignment]
    save_ownership_calibration = None  # type: ignore[assignment]

try:
    from ceminidfs.data.historical_slate import write_historical_fd_slate
except ImportError:  # pragma: no cover - defensive for partial installs
    write_historical_fd_slate = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.backtest_prepare import format_prepare_summary, prepare_season_cache
except ImportError:  # pragma: no cover - defensive for partial installs
    prepare_season_cache = None  # type: ignore[assignment]
    format_prepare_summary = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.backtest import (
        format_backtest_summary,
        run_backtest,
        write_backtest_report,
    )
except ImportError:  # pragma: no cover - defensive for partial installs
    run_backtest = None  # type: ignore[assignment]
    write_backtest_report = None  # type: ignore[assignment]
    format_backtest_summary = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.coherence_eval import run_coherence_comparison
except ImportError:  # pragma: no cover - defensive for partial installs
    run_coherence_comparison = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.sdv_benchmark import benchmark_pbp_fetch
except ImportError:  # pragma: no cover - defensive for partial installs
    benchmark_pbp_fetch = None  # type: ignore[assignment]

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
    from ceminidfs.pipeline.distributions import (
        build_week_distributions,
        format_distributions_summary,
        parse_season_week,
        write_distributions_csv,
    )
except ImportError:  # pragma: no cover - defensive for partial installs
    build_week_distributions = None  # type: ignore[assignment]
    write_distributions_csv = None  # type: ignore[assignment]
    format_distributions_summary = None  # type: ignore[assignment]
    parse_season_week = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.market_benchmark import (
        format_market_benchmark,
        run_market_benchmark,
        write_market_benchmark_report,
    )
except ImportError:  # pragma: no cover - defensive for partial installs
    run_market_benchmark = None  # type: ignore[assignment]
    write_market_benchmark_report = None  # type: ignore[assignment]
    format_market_benchmark = None  # type: ignore[assignment]

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

try:
    from ceminidfs.pipeline.calibrate_jev import (
        format_calibrate_jev_summary,
        run_calibrate_jev,
        write_calibrate_jev_json,
        write_calibrate_jev_markdown,
    )
except ImportError:  # pragma: no cover - defensive for partial installs
    run_calibrate_jev = None  # type: ignore[assignment]
    write_calibrate_jev_json = None  # type: ignore[assignment]
    write_calibrate_jev_markdown = None  # type: ignore[assignment]
    format_calibrate_jev_summary = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.lineup_backtest import (
        format_lineup_backtest_summary,
        run_lineup_backtest,
        write_lineup_backtest_report,
    )
except ImportError:  # pragma: no cover - defensive for partial installs
    run_lineup_backtest = None  # type: ignore[assignment]
    write_lineup_backtest_report = None  # type: ignore[assignment]
    format_lineup_backtest_summary = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.benchmark_replay import (
        format_benchmark_replay,
        replay_benchmark_directory,
        write_benchmark_replay_report,
    )
except ImportError:  # pragma: no cover - defensive for partial installs
    replay_benchmark_directory = None  # type: ignore[assignment]
    write_benchmark_replay_report = None  # type: ignore[assignment]
    format_benchmark_replay = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.regression import format_regression_result, run_weekly_regression
except ImportError:  # pragma: no cover - defensive for partial installs
    run_weekly_regression = None  # type: ignore[assignment]
    format_regression_result = None  # type: ignore[assignment]

try:
    from ceminidfs.export.late_swap import late_swap_lineups
except ImportError:  # pragma: no cover - defensive for partial installs
    late_swap_lineups = None  # type: ignore[assignment]

try:
    from ceminidfs.export.review_reports import maybe_write_review_reports
except ImportError:  # pragma: no cover - defensive for partial installs
    maybe_write_review_reports = None  # type: ignore[assignment]

try:
    from ceminidfs.export.build_gates import BuildGateError
    from ceminidfs.export.optimize import ExposureCapError, merge_lineup_csvs, write_merged_upload
except ImportError:  # pragma: no cover - defensive for partial installs
    BuildGateError = None  # type: ignore[assignment]
    ExposureCapError = None  # type: ignore[assignment]
    merge_lineup_csvs = None  # type: ignore[assignment]
    write_merged_upload = None  # type: ignore[assignment]

try:
    from ceminidfs.data.sleeper import fetch_trending_players, trending_with_names
except ImportError:  # pragma: no cover - defensive for partial installs
    fetch_trending_players = None  # type: ignore[assignment]
    trending_with_names = None  # type: ignore[assignment]

try:
    from ceminidfs.pipeline.luck_metrics import compute_team_luck_table, summarize_luck_metrics
except ImportError:  # pragma: no cover - defensive for partial installs
    compute_team_luck_table = None  # type: ignore[assignment]
    summarize_luck_metrics = None  # type: ignore[assignment]

try:
    from ceminidfs.data.espn import probe_league
except ImportError:  # pragma: no cover - defensive for partial installs
    probe_league = None  # type: ignore[assignment]


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
    fetch.add_argument(
        "--force",
        action="store_true",
        help="Ignore parquet cache TTL and refetch",
    )
    fetch.set_defaults(handler=_cmd_fetch)

    project = subparsers.add_parser("project", help="Create canonical placeholder projections")
    project.add_argument("--season", type=int, required=True)
    project.add_argument("--week", type=int, required=True)
    project.add_argument("--salary", type=Path, required=True)
    _add_profile_argument(project)
    _add_premium_mode_arguments(project)
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
    optimize.add_argument(
        "--sim-rerank",
        action="store_true",
        default=None,
        help="Rerank pydfs candidates by simulation",
    )
    optimize.add_argument(
        "--candidates",
        type=int,
        default=None,
        help="Candidate lineups before rerank (GPP profile default 500)",
    )
    optimize.add_argument("--final-count", type=int, default=150, help="Final lineups after rerank")
    _add_rerank_mode_argument(optimize)
    _add_optimizer_build_arguments(optimize)
    _add_fade_guard_arguments(optimize)
    _add_review_report_arguments(optimize, default_on=True)
    _add_environment_argument(optimize)
    _add_profile_argument(optimize)
    optimize.set_defaults(handler=_cmd_optimize)

    ownership = subparsers.add_parser("ownership", help="Ownership projection tools")
    ownership_sub = ownership.add_subparsers(dest="ownership_command")

    ownership_calibrate = ownership_sub.add_parser(
        "calibrate",
        help="Fit ownership calibration from paid labels and salary rows",
    )
    ownership_calibrate.add_argument("--labels", type=Path, required=True)
    ownership_calibrate.add_argument("--salary", type=Path, required=True)
    ownership_calibrate.add_argument("--season", type=int, required=True)
    ownership_calibrate.add_argument("--week", type=int, required=True)
    ownership_calibrate.add_argument("--out", dest="output_path", type=Path, required=True)
    ownership_calibrate.add_argument("--site")
    ownership_calibrate.set_defaults(handler=_cmd_ownership_calibrate)

    late_swap = subparsers.add_parser(
        "late-swap", help="Late-swap existing lineups after teams lock"
    )
    late_swap.add_argument("--lineups", dest="lineups_path", type=Path, required=True)
    late_swap.add_argument("--players", dest="players_path", type=Path, required=True)
    late_swap.add_argument(
        "--lock-team",
        action="append",
        default=[],
        help="Locked team abbreviation; repeatable",
    )
    late_swap.add_argument("--out", dest="output_path", type=Path)
    late_swap.add_argument("--site", default="fanduel")
    late_swap.add_argument("--count", type=int, default=None)
    late_swap.add_argument(
        "--prelock",
        action="store_true",
        default=False,
        help=(
            "Run the pre-lock Q/D gate only. Refuse a Q or D player over "
            "--q-exposure-cap. Writes late_swap_alert_report.csv. No swap"
        ),
    )
    late_swap.add_argument(
        "--q-exposure-cap",
        type=float,
        default=None,
        help="Pre-lock Q/D exposure share (0-1; GPP profile default 0.08)",
    )
    _add_optimizer_build_arguments(late_swap)
    _add_review_report_arguments(late_swap)
    _add_profile_argument(late_swap)
    late_swap.set_defaults(handler=_cmd_late_swap)

    review = subparsers.add_parser(
        "review",
        help="Write human-gate review CSVs from existing lineups (no re-solve)",
    )
    review.add_argument("--lineups", dest="lineups_path", type=Path, required=True)
    review.add_argument("--players", dest="players_path", type=Path, required=True)
    review.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        default=None,
        help="Directory for report CSVs (default: lineup parent dir)",
    )
    review.add_argument("--site", default="fanduel")
    _add_review_report_arguments(review)
    _add_environment_argument(review)
    _add_jev_arguments(review)
    review.set_defaults(handler=_cmd_review)

    merge = subparsers.add_parser(
        "merge-lineups",
        help="Merge lineup CSVs and refuse when a player would exceed the exposure cap",
    )
    merge.add_argument("--base", dest="base_path", type=Path, required=True)
    merge.add_argument("--extra", dest="extra_path", type=Path, required=True)
    merge.add_argument("--out", dest="output_path", type=Path, required=True)
    merge.add_argument(
        "--max-exposure",
        dest="max_exposure",
        type=float,
        required=True,
        help="Max player exposure 0-1. Cap is floor(max-exposure * count)",
    )
    merge.add_argument(
        "--count",
        type=int,
        required=True,
        help="Final book size used for the exposure cap",
    )
    merge.add_argument(
        "--core-cap",
        type=int,
        default=None,
        help="Refuse a repeated 5-player core over this count (default off)",
    )
    merge.add_argument("--site", default="fanduel")
    merge.add_argument(
        "--players",
        dest="players_path",
        type=Path,
        default=None,
        help="Players CSV with FanDuel ids. Default: normalized_players.csv next to --out",
    )
    merge.set_defaults(handler=_cmd_merge_lineups)

    buckets = subparsers.add_parser(
        "buckets",
        help="Report the cash-line bucket distribution from a totals CSV",
    )
    buckets.add_argument(
        "--totals",
        dest="totals_path",
        type=Path,
        required=True,
        help="Totals CSV with a rank column and a score column",
    )
    buckets.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        default=None,
        help="Output CSV (default: cash_bucket_report.csv next to --totals)",
    )
    buckets.set_defaults(handler=_cmd_buckets)

    research = subparsers.add_parser(
        "research-export",
        help="Write environment and injury-status CSVs for CeminiParlays",
    )
    research_sub = research.add_subparsers(dest="research_command")
    research_env = research_sub.add_parser("env", help="Write environment.csv for one slate")
    research_env.add_argument("--salary", type=Path, required=True)
    research_env.add_argument("--season", type=int, required=True)
    research_env.add_argument("--week", type=int, required=True)
    research_env.add_argument("--out", dest="output_path", type=Path, required=True)
    research_env.add_argument("--slate-id", default=None)
    research_env.set_defaults(handler=_cmd_research_env)
    research_status = research_sub.add_parser(
        "status",
        help="Write injury status CSVs from the nflverse injuries cache",
    )
    research_status.add_argument("--season", type=int, required=True)
    research_status.add_argument("--week", type=int, required=True)
    research_status.add_argument("--out", dest="output_path", type=Path, required=True)
    research_status.add_argument("--injuries", dest="injuries_path", type=Path, default=None)
    research_status.set_defaults(handler=_cmd_research_status)
    research_validate = research_sub.add_parser(
        "validate",
        help="Check an environment CSV",
    )
    research_validate.add_argument("--slate", dest="slate_path", type=Path, required=True)
    research_validate.add_argument("--salary", type=Path, default=None)
    research_validate.add_argument("--season", type=int, default=0)
    research_validate.add_argument("--week", type=int, default=0)
    research_validate.set_defaults(handler=_cmd_research_validate)

    run = subparsers.add_parser("run", help="Run one or more pipeline stages")
    run.add_argument("--season", type=int, required=True)
    run.add_argument("--week", type=int, required=True)
    run.add_argument("--salary", type=Path, required=True)
    run.add_argument("--site", default="fanduel")
    run.add_argument("--count", type=int, default=150)
    run.add_argument(
        "--sim-rerank",
        action="store_true",
        default=None,
        help="Rerank optimizer candidates by simulation",
    )
    run.add_argument(
        "--candidates",
        type=int,
        default=None,
        help="Candidate lineups before rerank (GPP profile default 500)",
    )
    run.add_argument("--final-count", type=int, default=150, help="Final lineups after rerank")
    _add_rerank_mode_argument(run)
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
    run.add_argument(
        "--force",
        action="store_true",
        help="Ignore parquet cache TTL and refetch",
    )
    _add_premium_mode_arguments(run)
    _add_optimizer_build_arguments(run)
    _add_fade_guard_arguments(run)
    _add_review_report_arguments(run, default_on=True)
    _add_environment_argument(run)
    _add_profile_argument(run)
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

    coherence_eval = subparsers.add_parser(
        "coherence-eval",
        help="Compare baseline backtest vs coherence-risk enabled",
    )
    coherence_eval.add_argument("--season", type=int, required=True)
    coherence_eval.add_argument("--start-week", type=int, required=True)
    coherence_eval.add_argument("--end-week", type=int, required=True)
    coherence_eval.set_defaults(handler=_cmd_coherence_eval)

    sdv_benchmark = subparsers.add_parser(
        "sdv-benchmark",
        help="Compare nflreadpy vs sportsdataverse PBP fetch coverage and latency",
    )
    sdv_benchmark.add_argument("--season", type=int, required=True)
    sdv_benchmark.add_argument("--week", type=int)
    sdv_benchmark.add_argument("--start-week", type=int)
    sdv_benchmark.add_argument("--end-week", type=int)
    sdv_benchmark.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        required=True,
        help="JSON report path",
    )
    sdv_benchmark.set_defaults(handler=_cmd_sdv_benchmark)

    backtest_prepare = subparsers.add_parser(
        "backtest-prepare",
        help="Fetch nflverse caches for a season range (offseason backtest setup)",
    )
    backtest_prepare.add_argument("--season", type=int, required=True)
    backtest_prepare.add_argument("--start-week", type=int, default=1)
    backtest_prepare.add_argument("--end-week", type=int, default=18)
    backtest_prepare.add_argument(
        "--allow-stub",
        action="store_true",
        help="Allow stub artifacts when nflreadpy is unavailable",
    )
    backtest_prepare.set_defaults(handler=_cmd_backtest_prepare)

    historical_slate = subparsers.add_parser(
        "historical-slate",
        help="Write a synthetic FanDuel salary CSV from nflverse (no live slate export)",
    )
    historical_slate.add_argument("--season", type=int, required=True)
    historical_slate.add_argument("--week", type=int, required=True)
    historical_slate.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        help="Output CSV path (default: artifacts/slates/{season}_w{week}_fd.csv)",
    )
    historical_slate.set_defaults(handler=_cmd_historical_slate)

    benchmark = subparsers.add_parser("benchmark", help="Paid projection benchmark tools")
    benchmark_sub = benchmark.add_subparsers(dest="benchmark_command")

    benchmark_load = benchmark_sub.add_parser(
        "load", help="Parse a Stokastic/Labs CSV into a snapshot JSON"
    )
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

    benchmark_replay = benchmark_sub.add_parser(
        "replay",
        help="Compare every discoverable paid CSV in a folder across weeks",
    )
    benchmark_replay.add_argument("--season", type=int, required=True)
    benchmark_replay.add_argument("--start-week", type=int, required=True)
    benchmark_replay.add_argument("--end-week", type=int, required=True)
    benchmark_replay.add_argument("--dir", dest="benchmark_dir", type=Path, required=True)
    benchmark_replay.add_argument("--site", default="fanduel")
    benchmark_replay.add_argument("--source")
    benchmark_replay.add_argument("--no-diy", action="store_true", help="Skip DIY side-by-side")
    benchmark_replay.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        default=Path("reports/benchmark_replay.json"),
    )
    benchmark_replay.set_defaults(handler=_cmd_benchmark_replay)

    export_distributions = subparsers.add_parser(
        "export-distributions",
        help="Write per-player per-stat lognormal distributions for one week",
    )
    export_distributions.add_argument(
        "--week",
        dest="season_week",
        required=True,
        help="Season_week token, e.g. 2026_5",
    )
    export_distributions.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        required=True,
        help="Output CSV path for the distributions handoff",
    )
    export_distributions.set_defaults(handler=_cmd_export_distributions)

    market_benchmark_cmd = subparsers.add_parser(
        "market-benchmark",
        help="Compare model medians vs closing prop lines against realized stats",
    )
    market_benchmark_cmd.add_argument("--season", type=int, required=True)
    market_benchmark_cmd.add_argument("--week", type=int, required=True)
    market_benchmark_cmd.add_argument(
        "--closing-props",
        dest="closing_props",
        type=Path,
        required=True,
        help="Closing prop lines CSV with player_key,stat_type,line columns",
    )
    market_benchmark_cmd.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        default=None,
        help="Optional JSON report path",
    )
    market_benchmark_cmd.set_defaults(handler=_cmd_market_benchmark)

    lineup_backtest = subparsers.add_parser(
        "lineup-backtest",
        help="Walk-forward synthetic slate → optimize → score vs actuals",
    )
    lineup_backtest.add_argument("--season", type=int, required=True)
    lineup_backtest.add_argument("--start-week", type=int, required=True)
    lineup_backtest.add_argument("--end-week", type=int, required=True)
    lineup_backtest.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        default=Path("reports/lineup_backtest.json"),
    )
    lineup_backtest.set_defaults(handler=_cmd_lineup_backtest)

    regression = subparsers.add_parser(
        "regression",
        help="Prepare (optional) + backtest + calibrate + lineup backtest in one run",
    )
    regression.add_argument("--season", type=int, required=True)
    regression.add_argument("--start-week", type=int, required=True)
    regression.add_argument("--end-week", type=int, required=True)
    regression.add_argument("--prepare", action="store_true", help="Fetch nflverse caches first")
    regression.add_argument("--skip-lineup", action="store_true", help="Skip lineup-level backtest")
    regression.add_argument("--output-dir", type=Path, default=Path("reports"))
    regression.add_argument(
        "--benchmark-dir", type=Path, help="Folder of paid CSV exports to replay"
    )
    regression.add_argument("--benchmark-csv", type=Path, help="Single paid export for calibration")
    regression.add_argument("--benchmark-week", type=int)
    regression.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero when regression gate thresholds are exceeded",
    )
    regression.add_argument("--max-mae", type=float, help="Override regression.max_overall_mae gate")
    regression.add_argument("--max-qb-mae", type=float, help="Override regression.max_qb_mae gate")
    regression.set_defaults(handler=_cmd_regression)

    calibrate = subparsers.add_parser(
        "calibrate", help="Generate calibration wiki brief from backtest results"
    )
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
    calibrate.add_argument(
        "--benchmark-csv",
        dest="benchmark_csv",
        type=Path,
        help="Optional paid export for one week",
    )
    calibrate.add_argument(
        "--benchmark-week",
        type=int,
        help="Week for benchmark CSV (default: end-week)",
    )
    calibrate.set_defaults(handler=_cmd_calibrate)

    calibrate_jev = subparsers.add_parser(
        "calibrate-jev",
        help="Walk-forward GMM + Jev calibration against the v6 report",
    )
    calibrate_jev.add_argument(
        "--weeks",
        required=True,
        help="Season-week window token, e.g. 2025_w5-17",
    )
    calibrate_jev.add_argument(
        "--out",
        dest="output_path",
        type=Path,
        default=None,
        help="Markdown report path (default: reports/calibration_<weeks>_v8_jev.md)",
    )
    calibrate_jev.add_argument(
        "--json-out",
        dest="json_output_path",
        type=Path,
        default=None,
        help="JSON report path (default: reports/calibration_<weeks>_v8_jev.json)",
    )
    calibrate_jev.add_argument("--v6-report", type=Path, default=None, help="Baseline v6 JSON")
    calibrate_jev.add_argument("--n-iterations", type=int, default=10000)
    calibrate_jev.add_argument(
        "--dispersion-scale",
        type=float,
        default=None,
        help="Fix the sigma multiplier instead of fitting it on the window",
    )
    _add_jev_decision_arguments(calibrate_jev)
    calibrate_jev.set_defaults(handler=_cmd_calibrate_jev)

    sleeper = subparsers.add_parser("sleeper", help="Sleeper public API tools (K129 buzz)")
    sleeper_sub = sleeper.add_subparsers(dest="sleeper_command")

    sleeper_trending = sleeper_sub.add_parser(
        "trending",
        help="Fetch trending add/drop players from Sleeper",
    )
    sleeper_trending.add_argument(
        "--direction",
        choices=("add", "drop", "both"),
        default="both",
        help="Trending direction (default: both)",
    )
    sleeper_trending.add_argument("--lookback-hours", type=int, default=24)
    sleeper_trending.add_argument("--limit", type=int, default=25)
    sleeper_trending.add_argument("--json-out", type=Path, help="Write JSON output to path")
    sleeper_trending.set_defaults(handler=_cmd_sleeper_trending)

    luck_metrics = subparsers.add_parser(
        "luck-metrics",
        help="Team Pythagorean expected wins and luck table",
    )
    luck_metrics.add_argument("--season", type=int, required=True)
    luck_metrics.add_argument("--through-week", type=int, required=True)
    luck_metrics.add_argument("--json-out", type=Path, help="Write JSON summary to path")
    _add_profile_argument(luck_metrics)
    luck_metrics.set_defaults(handler=_cmd_luck_metrics)

    espn = subparsers.add_parser("espn", help="ESPN fantasy adjunct tools (K138)")
    espn_sub = espn.add_subparsers(dest="espn_command")

    espn_probe = espn_sub.add_parser("probe", help="Test ESPN league connectivity and injury map")
    espn_probe.add_argument("--league-id", type=int, required=True)
    espn_probe.add_argument("--year", type=int, required=True)
    espn_probe.add_argument("--json-out", type=Path, help="Write JSON output to path")
    espn_probe.set_defaults(handler=_cmd_espn_probe)

    # BBM (Best Ball Mania) draft copilot
    bbm_parser = subparsers.add_parser("bbm", help="Best Ball Mania draft copilot")
    bbm_sub = bbm_parser.add_subparsers(dest="bbm_command")
    if build_bbm_parser is not None:
        build_bbm_parser(bbm_sub)
    bbm_parser.set_defaults(handler=_cmd_bbm)

    # ESPN season-long redraft (12-team snake full PPR)
    redraft_parser = subparsers.add_parser(
        "redraft",
        help="ESPN 12-team PPR snake draft prep (cheat sheet + prerank)",
    )
    redraft_sub = redraft_parser.add_subparsers(dest="redraft_command")
    if build_redraft_parser is not None:
        build_redraft_parser(redraft_sub)
    redraft_parser.set_defaults(handler=_cmd_redraft)

    return parser


def _cmd_fetch(args: argparse.Namespace) -> int:
    if _run_fetch is None:
        raise RuntimeError("Fetch stage unavailable: orchestrator import failed")
    config = runtime_config(
        work_dir=Path("runs") / f"{args.season}_week_{args.week}",
        allow_stub=args.allow_stub,
        fetch={"force": True} if args.force else None,
    )
    artifact = _run_fetch(args.season, args.week, config)
    print(artifact)
    return 0


def _add_premium_mode_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--premium-mode",
        choices=("off", "baseline", "market"),
        default="off",
        help="Premium band mode. off leaves the projections unchanged. The default is off.",
    )
    parser.add_argument(
        "--premium-guard",
        action="store_true",
        help=argparse.SUPPRESS,
    )


def _premium_mode_override(args: argparse.Namespace) -> dict[str, Any]:
    mode = str(getattr(args, "premium_mode", None) or "off").strip().lower()
    if mode == "off" and getattr(args, "premium_guard", False):
        mode = "baseline"
    return {"premium_mode": mode}


def _cmd_project(args: argparse.Namespace) -> int:
    if project_week is None:
        raise RuntimeError("Projection stage unavailable: ceminidfs.pipeline.project import failed")
    config = runtime_config(
        profile=args.profile,
        work_dir=Path("runs") / f"{args.season}_week_{args.week}",
        **_premium_mode_override(args),
    )
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
    rerank_override = _sim_rerank_cli_override(args)
    config = runtime_config(
        profile=args.profile,
        site=args.site,
        sim_rerank=rerank_override,
        **_optimizer_build_overrides(args),
        **_review_report_overrides(args),
    )
    count = args.final_count if _sim_rerank_enabled(config) else args.count
    config["count"] = count
    output = _run_optimize(args.csv_path, args.output_path, count, config)
    print(output)
    return 0


def _cmd_ownership_calibrate(args: argparse.Namespace) -> int:
    if (
        load_ownership_labels is None
        or parse_salary_csv is None
        or apply_salary_fppg_placeholder is None
        or fit_ownership_calibration is None
        or save_ownership_calibration is None
    ):
        raise RuntimeError("Ownership calibration unavailable: ownership imports failed")
    rows = parse_salary_csv(args.salary, args.season, args.week, site=args.site)
    site = args.site or _site_from_salary_rows(rows)
    rows = apply_salary_fppg_placeholder(rows, site)
    labels = load_ownership_labels(args.labels)
    calibration = fit_ownership_calibration(labels, rows, site=site, target_week=args.week)
    output = save_ownership_calibration(calibration, args.output_path)
    print(f"Fitted {calibration.sample_size} ownership labels → {output}")
    return 0


def _cmd_late_swap(args: argparse.Namespace) -> int:
    if late_swap_lineups is None:
        raise RuntimeError("Late swap unavailable: ceminidfs.export.late_swap import failed")
    if bool(getattr(args, "prelock", False)):
        return _cmd_prelock(args)
    output_path = args.output_path or args.lineups_path.with_name(
        f"{args.lineups_path.stem}_late_swap.csv"
    )
    overrides = _optimizer_build_overrides(args)
    review = _review_report_overrides(args)
    late_swap_lineups(
        args.lineups_path,
        args.players_path,
        set(args.lock_team),
        output_path,
        site=args.site,
        count=args.count,
        stacks=overrides.get("stacks"),
        locks=overrides.get("locks"),
        excludes=overrides.get("excludes"),
        max_exposure=overrides.get("max_exposure"),
        max_team_exposure=overrides.get("max_team_exposure"),
        no_offense_vs_dst=bool(overrides.get("no_offense_vs_dst")),
        one_rb_per_team=bool(overrides.get("one_rb_per_team")),
        projection_floor=overrides.get("projection_floor"),
        uniques=overrides.get("uniques"),
        max_repeating_players=overrides.get("max_repeating_players"),
        flag_wr_triples=bool(review.get("flag_wr_triples")),
        late_swap_audit=bool(review.get("late_swap_audit")),
        ownership_fade_report=bool(review.get("ownership_fade_report")),
        ownership_calibration=review.get("ownership_calibration"),
        flag_duplicate_cores=bool(review.get("flag_duplicate_cores")),
        dart_ceiling_report=bool(review.get("dart_ceiling_report")),
        flag_qb_starter=bool(review.get("flag_qb_starter")),
        flag_stack_concentration=bool(review.get("flag_stack_concentration")),
        flag_correlated_pairs=bool(review.get("flag_correlated_pairs")),
        defense_context_report=bool(review.get("defense_context_report")),
        projection_bands=bool(review.get("projection_bands")),
        season=review.get("season"),
        week=review.get("week"),
    )
    print(output_path)
    return 0


def _cmd_buckets(args: argparse.Namespace) -> int:
    from ceminidfs.export.review_reports import (
        CASH_BUCKET_NAME,
        read_lineup_totals,
        write_cash_bucket_report,
    )

    totals_path = Path(args.totals_path)
    if not totals_path.is_file():
        print(f"Error: totals CSV not found: {totals_path}", file=sys.stderr)
        return 1
    out_path = args.output_path or totals_path.with_name(CASH_BUCKET_NAME)
    rows = read_lineup_totals(totals_path)
    if not rows:
        print(f"Error: no ranked rows in {totals_path}", file=sys.stderr)
        return 1
    write_cash_bucket_report(out_path, rows)
    print(out_path)
    return 0


def _cmd_prelock(args: argparse.Namespace) -> int:
    """Run the pre-lock Q/D gate. Write the alert report. Refuse on a breach."""

    from ceminidfs.export.late_swap import (
        PrelockQError,
        assert_prelock_q,
        prelock_q_violations,
        write_prelock_alert,
    )

    out_dir = args.output_path.parent if args.output_path else None
    write_prelock_alert(
        args.lineups_path,
        args.players_path,
        site=args.site,
        out_dir=out_dir,
    )
    profile = runtime_config(profile=getattr(args, "profile", None))
    cap = args.q_exposure_cap
    if cap is None:
        cap = profile.get("prelock", {}).get("q_exposure_cap", 0.08)
    cap = float(cap)
    try:
        assert_prelock_q(
            args.lineups_path,
            args.players_path,
            cap=cap,
            site=args.site,
        )
    except PrelockQError as exc:
        over = prelock_q_violations(
            args.lineups_path,
            args.players_path,
            cap=cap,
            site=args.site,
        )
        for name, injury, count, limit in over:
            print(f"prelock: {name} ({injury}) is in {count} lineups; cap is {limit}", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 1
    print(f"prelock: no Q or D player over {cap:.0%}")
    return 0


def _cmd_merge_lineups(args: argparse.Namespace) -> int:
    if merge_lineup_csvs is None or ExposureCapError is None or write_merged_upload is None:
        print("Error: lineup merge unavailable", file=sys.stderr)
        return 1
    try:
        players_path = args.players_path
        if players_path is None:
            players_path = Path(args.output_path).parent / "normalized_players.csv"
        if not Path(players_path).is_file():
            raise FileNotFoundError(
                f"players CSV not found: {players_path}. "
                "Pass --players or place normalized_players.csv next to --out."
            )
        merge_lineup_csvs(
            args.base_path,
            args.extra_path,
            args.output_path,
            max_exposure=args.max_exposure,
            final_count=args.count,
            site=args.site,
            core_cap=getattr(args, "core_cap", None),
        )
        write_merged_upload(args.output_path, players_path, site=args.site)
    except ExposureCapError as exc:
        print(exc, file=sys.stderr)
        return 1
    except BuildGateError as exc:
        print(exc, file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(args.output_path)
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    if maybe_write_review_reports is None:
        raise RuntimeError("Review reports unavailable: review_reports import failed")

    out_dir = args.output_path
    if out_dir is None:
        out_dir = args.lineups_path.parent
    maybe_write_review_reports(
        args.lineups_path,
        args.players_path,
        site=args.site,
        out_dir=out_dir,
        flag_wr_triples=bool(getattr(args, "flag_wr_triples", False))
        and not bool(getattr(args, "no_review_reports", False)),
        late_swap_audit=bool(getattr(args, "late_swap_audit", False)),
        ownership_fade_report=bool(getattr(args, "ownership_fade_report", False)),
        ownership_calibration=getattr(args, "ownership_calibration", None),
        flag_duplicate_cores=bool(getattr(args, "flag_duplicate_cores", False))
        and not bool(getattr(args, "no_review_reports", False)),
        dart_ceiling_report=bool(getattr(args, "dart_ceiling_report", False))
        and not bool(getattr(args, "no_review_reports", False)),
        flag_qb_starter=bool(getattr(args, "flag_qb_starter", False)),
        flag_stack_concentration=bool(getattr(args, "flag_stack_concentration", False)),
        flag_correlated_pairs=bool(getattr(args, "flag_correlated_pairs", False)),
        defense_context_report=bool(getattr(args, "defense_context_report", False)),
        projection_bands=bool(getattr(args, "projection_bands", False)),
        environment=getattr(args, "environment", None),
        season=getattr(args, "season", None),
        week=getattr(args, "week", None),
    )
    print(out_dir)
    if bool(getattr(args, "jev", False)):
        return _run_jev_gate(args, out_dir)
    return 0


def _run_jev_gate(args: argparse.Namespace, out_dir: Path) -> int:
    """Run the Jev pre-lock gate. The gate marks. The operator decides."""

    from ceminidfs.export.jev_gate import run_jev_gate, write_blocked_report
    from ceminidfs.integrations.jev import JevError, build_jev_client

    fixture = getattr(args, "jev_fixture", None)
    try:
        client = build_jev_client(fixture=fixture)
    except JevError as exc:
        path = write_blocked_report(out_dir, args.lineups_path, str(exc))
        print(path)
        print(f"jev gate BLOCKED: {exc}", file=sys.stderr)
        print("jev gate: pass=0 flag=0 review=0 block=1 low_confidence=0", file=sys.stderr)
        return 1

    status_doc = None
    status_path = getattr(args, "jev_status", None)
    if status_path is not None:
        status_doc = Path(status_path).read_text(encoding="utf-8")
    standings = None
    standings_path = getattr(args, "jev_standings", None)
    if standings_path is not None:
        standings = Path(standings_path).read_text(encoding="utf-8")

    cap = getattr(args, "jev_exposure_cap", None)
    if cap is None:
        profile = runtime_config(profile=getattr(args, "profile", None))
        cap = profile.get("max_exposure", 0.20)

    close = getattr(client, "close", None)
    try:
        result = run_jev_gate(
            args.lineups_path,
            args.players_path,
            client=client,
            site=args.site,
            out_dir=out_dir,
            date=getattr(args, "jev_date", None),
            exposure_cap=cap,
            status_doc=status_doc,
            standings=standings,
            cash_claim=getattr(args, "jev_cash_claim", None),
            enable_late_swap=not bool(getattr(args, "no_jev_late_swap", False)),
            enable_cash=bool(getattr(args, "jev_cash_claim", None)),
        )
    except JevError as exc:
        print(f"jev gate BLOCKED: {exc}", file=sys.stderr)
        print("jev gate: pass=0 flag=0 review=0 block=1 low_confidence=0", file=sys.stderr)
        return 1
    finally:
        if callable(close):
            close()

    print(result.path)
    print(result.summary())
    for row in result.rows:
        if row.action in {"flag", "block"}:
            print(f"jev {row.action}: {row.player} — {row.question} [{row.result}]")
    if result.blocked:
        print(f"jev gate BLOCKED: {result.blocked_reason}", file=sys.stderr)
        return 1
    return 0


def _cmd_research_env(args: argparse.Namespace) -> int:
    from ceminidfs.export.research_export import write_environment_csv

    path = write_environment_csv(
        args.salary,
        args.output_path,
        season=args.season,
        week=args.week,
        slate_id=args.slate_id,
    )
    print(path)
    return 0


def _cmd_research_status(args: argparse.Namespace) -> int:
    from ceminidfs.data.fetch import week_cache_dir
    from ceminidfs.export.research_export import write_status_csvs

    injuries_path = args.injuries_path
    if injuries_path is None:
        injuries_path = week_cache_dir(args.season, args.week) / "injuries.parquet"
    try:
        dfs_path, parlay_path = write_status_csvs(
            injuries_path,
            args.output_path,
            week=args.week,
        )
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(dfs_path)
    print(parlay_path)
    return 0


def _cmd_research_validate(args: argparse.Namespace) -> int:
    from ceminidfs.export.research_export import validate_environment

    errors = validate_environment(
        args.slate_path,
        salary_path=args.salary,
        season=args.season or 0,
        week=args.week or 0,
    )
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


def _cmd_run(args: argparse.Namespace) -> int:
    if run_pipeline is None:
        raise RuntimeError("Run pipeline unavailable: orchestrator import failed")
    rerank_override = _sim_rerank_cli_override(args)
    config = runtime_config(
        profile=args.profile,
        site=args.site,
        allow_stub=args.allow_stub,
        sim_rerank=rerank_override,
        fetch={"force": True} if args.force else None,
        **_premium_mode_override(args),
        **_optimizer_build_overrides(args),
        **_review_report_overrides(args),
    )
    count = args.final_count if _sim_rerank_enabled(config) else args.count
    config["count"] = count
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


def _cmd_coherence_eval(args: argparse.Namespace) -> int:
    if run_coherence_comparison is None:
        raise RuntimeError("Coherence eval unavailable: ceminidfs.pipeline.coherence_eval import failed")
    config = runtime_config()
    summary = run_coherence_comparison(args.season, args.start_week, args.end_week, config=config)
    print(json.dumps(summary, indent=2))
    return 0


def _cmd_sdv_benchmark(args: argparse.Namespace) -> int:
    if benchmark_pbp_fetch is None:
        raise RuntimeError("SDV benchmark unavailable: ceminidfs.pipeline.sdv_benchmark import failed")

    if args.week is not None and (args.start_week is not None or args.end_week is not None):
        raise ValueError("Use either --week or --start-week/--end-week, not both")
    if args.week is None and (args.start_week is None or args.end_week is None):
        raise ValueError("Provide either --week or both --start-week and --end-week")
    if args.start_week is not None and args.end_week is not None and args.start_week > args.end_week:
        raise ValueError("start-week must be <= end-week")

    if args.week is not None:
        summary = benchmark_pbp_fetch(args.season, week=args.week)
    else:
        summary = {
            "season": args.season,
            "start_week": args.start_week,
            "end_week": args.end_week,
            "weeks": [
                benchmark_pbp_fetch(args.season, week=week)
                for week in range(args.start_week, args.end_week + 1)
            ],
        }

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nReport: {args.output_path}")
    return 0


def _cmd_backtest_prepare(args: argparse.Namespace) -> int:
    if prepare_season_cache is None or format_prepare_summary is None:
        raise RuntimeError(
            "Backtest prepare unavailable: ceminidfs.pipeline.backtest_prepare import failed"
        )
    config = runtime_config()
    if args.allow_stub:
        config = {**config, "allow_stub": True}
    result = prepare_season_cache(args.season, args.start_week, args.end_week, config=config)
    print(format_prepare_summary(result))
    print(
        "\nNext: ceminidfs backtest --season {season} --start-week {start} --end-week {end}".format(
            season=args.season,
            start=args.start_week,
            end=args.end_week,
        )
    )
    return 0


def _cmd_historical_slate(args: argparse.Namespace) -> int:
    if write_historical_fd_slate is None:
        raise RuntimeError(
            "Historical slate unavailable: ceminidfs.data.historical_slate import failed"
        )
    config = runtime_config()
    output = args.output_path or Path("artifacts/slates") / f"{args.season}_w{args.week}_fd.csv"
    path = write_historical_fd_slate(args.season, args.week, output, config=config)
    print(f"Wrote synthetic FanDuel slate → {path}")
    print(
        "Run full pipeline:\n"
        f"  ceminidfs run --season {args.season} --week {args.week} --salary {path} --stages all"
    )
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
    if (
        compare_benchmark_week is None
        or write_benchmark_compare_report is None
        or format_benchmark_compare is None
    ):
        raise RuntimeError(
            "Benchmark compare unavailable: ceminidfs.pipeline.benchmark_compare import failed"
        )
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


def _cmd_export_distributions(args: argparse.Namespace) -> int:
    if (
        build_week_distributions is None
        or write_distributions_csv is None
        or format_distributions_summary is None
        or parse_season_week is None
    ):
        raise RuntimeError(
            "Distributions export unavailable: ceminidfs.pipeline.distributions import failed"
        )
    config = runtime_config()
    try:
        season, week = parse_season_week(args.season_week)
        distributions = build_week_distributions(season, week, config=config)
        path = write_distributions_csv(distributions, args.output_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(format_distributions_summary(distributions, season, week))
    print(f"\nDistributions: {path}")
    return 0


def _cmd_market_benchmark(args: argparse.Namespace) -> int:
    if (
        run_market_benchmark is None
        or format_market_benchmark is None
        or write_market_benchmark_report is None
    ):
        raise RuntimeError(
            "Market benchmark unavailable: ceminidfs.pipeline.market_benchmark import failed"
        )
    config = runtime_config()
    try:
        result = run_market_benchmark(
            args.season,
            args.week,
            args.closing_props,
            config=config,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(format_market_benchmark(result))
    if args.output_path is not None:
        path = write_market_benchmark_report(result, args.output_path)
        print(f"\nReport: {path}")
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


def _cmd_calibrate_jev(args: argparse.Namespace) -> int:
    if (
        run_calibrate_jev is None
        or write_calibrate_jev_json is None
        or write_calibrate_jev_markdown is None
        or format_calibrate_jev_summary is None
    ):
        raise RuntimeError("Calibrate-jev unavailable: ceminidfs.pipeline.calibrate_jev import failed")

    config = runtime_config()
    provider = "prior" if bool(getattr(args, "no_jev", False)) else args.jev_provider
    report = run_calibrate_jev(
        args.weeks,
        config=config,
        provider=provider,
        fallback=args.jev_fallback,
        n_iterations=int(args.n_iterations),
        cache_dir=args.jev_cache_dir,
        v6_report=args.v6_report or Path("reports/calibration_2025_w5-17_v6.json"),
        dispersion_scale=args.dispersion_scale,
    )
    default_stem = Path("reports") / f"calibration_{args.weeks}_v8_jev"
    json_path = write_calibrate_jev_json(report, args.json_output_path or default_stem.with_suffix(".json"))
    md_path = write_calibrate_jev_markdown(report, args.output_path or default_stem.with_suffix(".md"))
    print(format_calibrate_jev_summary(report))
    print(f"\nJSON: {json_path}")
    print(f"Brief: {md_path}")
    return 0


def _cmd_lineup_backtest(args: argparse.Namespace) -> int:
    if (
        run_lineup_backtest is None
        or write_lineup_backtest_report is None
        or format_lineup_backtest_summary is None
    ):
        raise RuntimeError(
            "Lineup backtest unavailable: ceminidfs.pipeline.lineup_backtest import failed"
        )
    config = runtime_config()
    summary = run_lineup_backtest(args.season, args.start_week, args.end_week, config=config)
    report_path = write_lineup_backtest_report(summary, args.output_path)
    print(format_lineup_backtest_summary(summary))
    print(f"\nReport: {report_path}")
    return 0


def _cmd_benchmark_replay(args: argparse.Namespace) -> int:
    if (
        replay_benchmark_directory is None
        or write_benchmark_replay_report is None
        or format_benchmark_replay is None
    ):
        raise RuntimeError(
            "Benchmark replay unavailable: ceminidfs.pipeline.benchmark_replay import failed"
        )
    config = runtime_config()
    summary = replay_benchmark_directory(
        args.season,
        args.start_week,
        args.end_week,
        args.benchmark_dir,
        site=args.site,
        source=args.source,
        include_diy=not args.no_diy,
        config=config,
    )
    report_path = write_benchmark_replay_report(summary, args.output_path)
    print(format_benchmark_replay(summary))
    print(f"\nReport: {report_path}")
    return 0


def _cmd_regression(args: argparse.Namespace) -> int:
    if run_weekly_regression is None or format_regression_result is None:
        raise RuntimeError("Regression unavailable: ceminidfs.pipeline.regression import failed")
    config = runtime_config()
    gates = None
    if args.max_mae is not None or args.max_qb_mae is not None:
        from ceminidfs.pipeline.regression_gates import RegressionGates

        base = RegressionGates.from_config(config)
        gates = RegressionGates(
            max_overall_mae=args.max_mae if args.max_mae is not None else base.max_overall_mae,
            max_qb_mae=args.max_qb_mae if args.max_qb_mae is not None else base.max_qb_mae,
            max_rb_mae=base.max_rb_mae,
            max_wr_mae=base.max_wr_mae,
            max_te_mae=base.max_te_mae,
            max_dst_mae=base.max_dst_mae,
            min_overall_spearman=base.min_overall_spearman,
        )
    result = run_weekly_regression(
        args.season,
        args.start_week,
        args.end_week,
        config=config,
        output_dir=args.output_dir,
        prepare=args.prepare,
        skip_lineup=args.skip_lineup,
        benchmark_dir=args.benchmark_dir,
        benchmark_csv=args.benchmark_csv,
        benchmark_week=args.benchmark_week,
        fail_on_regression=args.fail_on_regression,
        gates=gates,
    )
    print("\n" + format_regression_result(result))
    return 0


def _cmd_sleeper_trending(args: argparse.Namespace) -> int:
    if trending_with_names is None or fetch_trending_players is None:
        raise RuntimeError("Sleeper tools unavailable: ceminidfs.data.sleeper import failed")

    if args.direction == "both":
        frame = trending_with_names(
            lookback_hours=args.lookback_hours,
            limit=args.limit,
        )
        payload = frame.to_dict(orient="records") if not frame.empty else []
    else:
        trending = fetch_trending_players(
            direction=args.direction,
            lookback_hours=args.lookback_hours,
            limit=args.limit,
        )
        payload = [
            {
                "player_id": item.player_id,
                "count": item.count,
                "direction": item.direction,
            }
            for item in trending
        ]

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(args.json_out)
        return 0

    if not payload:
        print("No trending players returned.")
        return 0

    if isinstance(payload[0], dict) and "name" in payload[0]:
        for row in payload:
            print(
                f"{row.get('direction', ''):>4}  {int(row.get('count', 0)):>6}  "
                f"{row.get('name', '')} ({row.get('team', '')}, {row.get('position', '')})"
            )
    else:
        for row in payload:
            print(
                f"{row['direction']:>4}  {row['count']:>6}  player_id={row['player_id']}"
            )
    return 0


def _cmd_luck_metrics(args: argparse.Namespace) -> int:
    if summarize_luck_metrics is None or compute_team_luck_table is None:
        raise RuntimeError("Luck metrics unavailable: ceminidfs.pipeline.luck_metrics import failed")

    config = runtime_config(profile=args.profile)
    summary = summarize_luck_metrics(
        args.season,
        args.through_week,
        config=config,
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(args.json_out)
        return 0

    table = compute_team_luck_table(args.season, args.through_week)
    if table.empty:
        print(
            f"No completed games through week {args.through_week} for season {args.season}. "
            "Run fetch first."
        )
        return 1

    print(f"Luck metrics — season {args.season}, through week {args.through_week}")
    print(f"{'team':<5} {'g':>3} {'w':>3} {'pf':>5} {'pa':>5} {'xW':>5} {'luck':>6}")
    for _, row in table.iterrows():
        print(
            f"{row['team']:<5} {int(row['games']):>3} {int(row['wins']):>3} "
            f"{int(row['points_for']):>5} {int(row['points_against']):>5} "
            f"{row['expected_wins']:>5.1f} {row['luck']:>+6.2f}"
        )
    return 0


def _cmd_espn_probe(args: argparse.Namespace) -> int:
    if probe_league is None:
        raise RuntimeError("ESPN tools unavailable: ceminidfs.data.espn import failed")

    summary = probe_league(args.league_id, args.year)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(args.json_out)
        return 0

    print(f"ESPN league {summary['league_id']} ({summary['year']})")
    print(f"  roster players: {summary['roster_players']}")
    print(f"  injured/flagged: {summary['injured_or_flagged']}")
    if summary.get("sample"):
        print("  sample:")
        for name, status in summary["sample"]:
            print(f"    {name}: {status}")
    return 0


def _cmd_bbm(args: argparse.Namespace) -> int:
    """Dispatch to BBM subcommand handler."""
    if handle_bbm_command is None:
        print("Error: BBM module not available", file=sys.stderr)
        return 1
    return handle_bbm_command(args)


def _cmd_redraft(args: argparse.Namespace) -> int:
    """Dispatch to ESPN redraft subcommand handler."""
    if handle_redraft_command is None:
        print("Error: redraft module not available", file=sys.stderr)
        return 1
    return handle_redraft_command(args)


def _site_from_salary_rows(rows: list[dict[str, object]]) -> str:
    if rows and rows[0].get("dk_id") and not rows[0].get("fd_id"):
        return "draftkings"
    return "fanduel"


def _add_review_report_arguments(
    parser: argparse.ArgumentParser,
    *,
    default_on: bool = False,
) -> None:
    parser.add_argument(
        "--flag-wr-triples",
        action="store_true",
        default=default_on,
        help="Write stack_fragility_report.csv (same-game WR triples / CHALK-QB-WR-WR)",
    )
    parser.add_argument(
        "--late-swap-audit",
        action="store_true",
        default=False,
        help="Write late_swap_alert_report.csv (rostered Q/D). Does not auto-swap",
    )
    parser.add_argument(
        "--ownership-fade-report",
        action="store_true",
        default=False,
        help="Write leverage_fade_matrix.csv (exposure vs projected own%%)",
    )
    parser.add_argument(
        "--ownership-calibration",
        type=Path,
        default=None,
        help="Optional calibration JSON; scales report own%% only, never FPPG",
    )
    parser.add_argument(
        "--flag-duplicate-cores",
        action="store_true",
        default=default_on,
        help=(
            "Write duplicate_core_report.csv when one QB and two RB slots "
            "repeat, or two lineups share four or more names"
        ),
    )
    parser.add_argument(
        "--dart-ceiling-report",
        action="store_true",
        default=default_on,
        help="Write dart_ceiling_rank.csv for salary at or below 5500. Does not invent a ceiling",
    )
    parser.add_argument(
        "--flag-qb-starter",
        action="store_true",
        default=False,
        help="Write qb_starter_report.csv for a rostered QB who is not a confirmed starter",
    )
    parser.add_argument(
        "--flag-stack-concentration",
        action="store_true",
        default=False,
        help="Write stack_concentration_report.csv with prior-3-week target share. Does not drop a stack",
    )
    parser.add_argument(
        "--flag-correlated-pairs",
        action="store_true",
        default=False,
        help="Write correlated_pair_report.csv when one TE and DST pair is on more than one lineup",
    )
    parser.add_argument(
        "--defense-context-report",
        action="store_true",
        default=False,
        help="Write defense_context_report.csv beside the pass multiplier. Does not down-weight a DST",
    )
    parser.add_argument(
        "--projection-bands",
        action="store_true",
        default=False,
        help="Write projection_bands.csv with P85 and P15. Does not change the projection",
    )
    parser.add_argument(
        "--no-review-reports",
        action="store_true",
        default=False,
        help="Turn off flag-wr-triples, flag-duplicate-cores, and dart-ceiling-report",
    )


def _review_report_overrides(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if not bool(getattr(args, "no_review_reports", False)):
        if getattr(args, "flag_wr_triples", False):
            overrides["flag_wr_triples"] = True
        if getattr(args, "flag_duplicate_cores", False):
            overrides["flag_duplicate_cores"] = True
        if getattr(args, "dart_ceiling_report", False):
            overrides["dart_ceiling_report"] = True
    if getattr(args, "late_swap_audit", False):
        overrides["late_swap_audit"] = True
    if getattr(args, "ownership_fade_report", False):
        overrides["ownership_fade_report"] = True
    if getattr(args, "flag_qb_starter", False):
        overrides["flag_qb_starter"] = True
    if getattr(args, "flag_stack_concentration", False):
        overrides["flag_stack_concentration"] = True
    if getattr(args, "flag_correlated_pairs", False):
        overrides["flag_correlated_pairs"] = True
    if getattr(args, "defense_context_report", False):
        overrides["defense_context_report"] = True
    if getattr(args, "projection_bands", False):
        overrides["projection_bands"] = True
    if getattr(args, "season", None) is not None:
        overrides["season"] = args.season
    if getattr(args, "week", None) is not None:
        overrides["week"] = args.week
    calibration = getattr(args, "ownership_calibration", None)
    if calibration is not None:
        overrides["ownership_calibration"] = calibration
    environment = getattr(args, "environment", None)
    if environment is not None:
        overrides["environment"] = str(environment)
    return overrides


def _add_environment_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--environment",
        type=Path,
        default=None,
        help="Environment CSV. Fills implied_total on the parlays handoff",
    )


def _add_jev_decision_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the tiered Jev decision-client flags (Choice and Score routing)."""

    parser.add_argument(
        "--jev-provider",
        choices=("auto", "typesafe", "mcp", "openrouter", "prior"),
        default="auto",
        help="Tiered Jev provider routing (default: auto)",
    )
    parser.add_argument(
        "--jev-fallback",
        choices=("prior", "raise"),
        default="prior",
        help="Fallback when every network provider fails (default: prior)",
    )
    parser.add_argument(
        "--jev-model-version",
        default="jev-1.13",
        help="Pinned Jev model version (default: jev-1.13)",
    )
    parser.add_argument(
        "--jev-cache-dir",
        type=Path,
        default=None,
        help="Jev answer cache directory (default: data/cache/jev)",
    )
    parser.add_argument(
        "--no-jev",
        action="store_true",
        default=False,
        help="Disable network providers and use the deterministic prior only",
    )


def _add_jev_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the Jev pre-lock gate flags. The gate marks. It does not swap."""

    parser.add_argument(
        "--jev",
        action="store_true",
        default=False,
        help=(
            "Run the Jev pre-lock gate. Writes jev_gate_report.csv. "
            "Missing key or network error blocks the gate and exits non-zero"
        ),
    )
    parser.add_argument(
        "--jev-fixture",
        type=Path,
        default=None,
        help="Recorded Jev responses. Runs the gate with no key and no network",
    )
    parser.add_argument("--jev-date", default=None, help="Slate date for the status question")
    parser.add_argument(
        "--jev-exposure-cap",
        type=float,
        default=None,
        help="Exposure share at or above which a player gets a status question (0-1)",
    )
    parser.add_argument(
        "--jev-status",
        type=Path,
        default=None,
        help="Optional status or inactive-report text to add to the evidence",
    )
    parser.add_argument(
        "--jev-standings",
        type=Path,
        default=None,
        help="Standings screenshot text. Without it the cash claim stays UNKNOWN",
    )
    parser.add_argument(
        "--jev-cash-claim",
        default=None,
        help="Recap cash-count claim to verify against the standings text",
    )
    parser.add_argument(
        "--no-jev-late-swap",
        action="store_true",
        default=False,
        help="Skip the Choice step over late_swap_alert_report.csv rows",
    )


def _add_optimizer_build_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stack",
        action="append",
        default=[],
        help="Stack rule: qb:3, CIN:3, CIN3-TB2, 3-2, game:5, wr:2, rb+dst",
    )
    parser.add_argument("--lock", action="append", default=[], help="Force a player into every lineup")
    parser.add_argument("--exclude", action="append", default=[], help="Remove a player from the pool")
    parser.add_argument("--max-exposure", type=float, default=None, help="Max player exposure 0-1")
    parser.add_argument(
        "--max-team-exposure",
        type=float,
        default=None,
        help="Max share of lineups that may include any one team (0-1; default off)",
    )
    parser.add_argument(
        "--max-repeating-players",
        type=int,
        default=None,
        help="Max players that may repeat across lineups",
    )
    parser.add_argument(
        "--uniques",
        type=int,
        default=None,
        help="Alias for max_repeating_players = slate_size - N (wins over --max-repeating-players)",
    )
    parser.add_argument(
        "--no-offense-vs-dst",
        action="store_true",
        default=None,
        help="Block DST plus an offensive player from the opposing team",
    )
    parser.add_argument(
        "--one-rb-per-team",
        action="store_true",
        default=None,
        help="At most one RB from any single team",
    )
    parser.add_argument(
        "--projection-floor",
        type=float,
        default=None,
        help="Remove unlocked pool players with FPPG below N",
    )
    parser.add_argument(
        "--min-salary",
        type=int,
        default=None,
        help="Min salary cap used (FanDuel default 59400; 0=disable)",
    )
    parser.add_argument(
        "--research-csv",
        type=Path,
        default=None,
        help="Optional research CSV with name plus lock/exclude/fade columns",
    )
    parser.add_argument(
        "--min-skill-pool",
        type=int,
        default=DEFAULT_MIN_SKILL_POOL,
        help=(
            "Refuse the solve when fewer eligible skill players remain on a classic "
            "slate. 0 disables the floor. Showdown and tiny slates skip it"
        ),
    )


def _add_fade_guard_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--keep-team-dart",
        dest="keep_team_dart",
        type=float,
        default=0.0,
        help=(
            "Keep the cheapest eligible player at or below this salary on every "
            "slate team. Candidate pool only; the optimizer still chooses. Default 0 = off"
        ),
    )
    parser.add_argument(
        "--soft-fade",
        action="append",
        default=[],
        metavar="TEAM[=WEIGHT]",
        help=(
            "Lower a team weight instead of deleting its players. Repeatable. "
            "A hard fade (--exclude or the research scratch file) removes players"
        ),
    )


def _parse_soft_fade(values: list[str] | None) -> dict[str, float]:
    """Parse ``--soft-fade TEAM[=WEIGHT]`` values into a team -> weight mapping."""

    weights: dict[str, float] = {}
    for raw in values or []:
        token = str(raw or "").strip()
        if not token:
            continue
        team, _, weight_text = token.partition("=")
        team = team.strip().upper()
        if not team:
            continue
        weights[team] = float(weight_text) if weight_text.strip() else 0.65
    return weights


def _add_rerank_mode_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--rerank-mode",
        choices=("fpts", "ceiling", "leverage"),
        default=None,
        help=(
            "Simulation rerank objective: fpts (median), ceiling (tail), or "
            "leverage (P(score >= top 1%%) / geom_mean_own ** 0.5)"
        ),
    )


def _sim_rerank_cli_override(args: argparse.Namespace) -> dict[str, Any]:
    override: dict[str, Any] = {
        "final_count": args.final_count,
    }
    if getattr(args, "candidates", None) is not None:
        override["candidates"] = args.candidates
    if getattr(args, "sim_rerank", None) is not None:
        override["enabled"] = args.sim_rerank
    if getattr(args, "rerank_mode", None) is not None:
        override["mode"] = args.rerank_mode
    return override


def _optimizer_build_overrides(args: argparse.Namespace) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    if getattr(args, "stack", None):
        overrides["stacks"] = list(args.stack)
    if getattr(args, "lock", None):
        overrides["locks"] = list(args.lock)
    if getattr(args, "exclude", None):
        overrides["excludes"] = list(args.exclude)
    if getattr(args, "max_exposure", None) is not None:
        overrides["max_exposure"] = args.max_exposure
    if getattr(args, "max_team_exposure", None) is not None:
        overrides["max_team_exposure"] = args.max_team_exposure
    if getattr(args, "max_repeating_players", None) is not None:
        overrides["max_repeating_players"] = args.max_repeating_players
    if getattr(args, "uniques", None) is not None:
        overrides["uniques"] = args.uniques
    if getattr(args, "no_offense_vs_dst", None) is not None:
        overrides["no_offense_vs_dst"] = bool(args.no_offense_vs_dst)
    if getattr(args, "one_rb_per_team", None) is not None:
        overrides["one_rb_per_team"] = bool(args.one_rb_per_team)
    if getattr(args, "projection_floor", None) is not None:
        overrides["projection_floor"] = args.projection_floor
    if getattr(args, "min_salary", None) is not None:
        overrides["min_salary"] = args.min_salary
    if getattr(args, "min_skill_pool", None) is not None:
        overrides["min_skill_pool"] = int(args.min_skill_pool)
    keep_team_dart = getattr(args, "keep_team_dart", 0.0)
    if keep_team_dart:
        overrides["keep_team_dart"] = float(keep_team_dart)
    soft_fade = _parse_soft_fade(getattr(args, "soft_fade", None))
    if soft_fade:
        overrides["soft_fade"] = soft_fade
    research_csv = getattr(args, "research_csv", None)
    if research_csv is not None:
        from ceminidfs.data.research_locks import parse_research_locks, parse_research_qb_cells

        extra_locks, extra_excludes, extra_fades = parse_research_locks(research_csv)
        if extra_locks:
            overrides["locks"] = list(overrides.get("locks", [])) + extra_locks
        if extra_excludes:
            overrides["excludes"] = list(overrides.get("excludes", [])) + extra_excludes
        if extra_fades:
            overrides["player_soft_fade"] = list(overrides.get("player_soft_fade", [])) + extra_fades
        open_qb_teams = parse_research_qb_cells(research_csv)
        if open_qb_teams:
            overrides["open_qb_teams"] = sorted(open_qb_teams)
    return overrides


def _add_profile_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        choices=("gpp",),
        help="Apply a named contest profile over the base config",
    )


def _sim_rerank_enabled(config: Mapping[str, Any]) -> bool:
    rerank_cfg = config.get("sim_rerank", {})
    if isinstance(rerank_cfg, Mapping):
        return bool(rerank_cfg.get("enabled"))
    return bool(rerank_cfg)
