"""CeminiBBM CLI — Best Ball Mania draft copilot commands."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ceminidfs.bbm.archetype import assign_archetype
from ceminidfs.bbm.audit import audit_draft, format_audit_report
from ceminidfs.bbm.backtest import (
    BBM3_DOWNLOAD_URL,
    BBM3_EXPECTED_PATH,
    run_backtest,
    validate_backtest_readiness,
    write_backtest_report,
)
from ceminidfs.bbm.draft_card import write_draft_card
from ceminidfs.bbm.ledger import (
    abandon_draft,
    complete_draft,
    count_room_taken,
    create_draft,
    ensure_player_stub,
    exposure_pct,
    get_draft_state,
    get_last_ambiguous_matches,
    list_in_progress_drafts,
    list_room_taken_names,
    record_pick,
    record_taken,
    resolve_player_query,
    update_draft_archetype,
    undo_last_action,
)
from ceminidfs.bbm.models import Draft, DraftStatus, LedgerCounts, Roster
from ceminidfs.bbm.normalize_adp import merge_adp_csv, merge_projections_csv
from ceminidfs.bbm.reconcile import format_reconcile_report, reconcile_from_csv
from ceminidfs.bbm.registry import check_registry_coverage, load_registry, save_registry
from ceminidfs.bbm.session import (
    archetype_header,
    ensure_initialized,
    get_pivot_message,
    get_recommendations,
    player_from_row,
)
from ceminidfs.bbm.ledger import sync_players_from_registry
from ceminidfs.bbm.api_server import run_server
from ceminidfs.bbm import practice


def handle_bbm_command(args: argparse.Namespace) -> int:
    """Dispatch to the appropriate BBM subcommand handler."""

    if not hasattr(args, "bbm_command") or args.bbm_command is None:
        print("Error: No BBM subcommand specified", file=sys.stderr)
        print(
            "Available: draft, serve, practice, abandon, refresh-adp, refresh-weekly, refresh-schedule, fetch-bbm3, draft-card, audit, reconcile, backtest"
        )
        return 2

    handler_map = {
        "draft": _cmd_draft,
        "serve": _cmd_serve,
        "practice": _cmd_practice,
        "abandon": _cmd_abandon,
        "refresh-adp": _cmd_refresh_adp,
        "refresh-weekly": _cmd_refresh_weekly,
        "refresh-schedule": _cmd_refresh_schedule,
        "fetch-bbm3": _cmd_fetch_bbm3,
        "draft-card": _cmd_draft_card,
        "audit": _cmd_audit,
        "reconcile": _cmd_reconcile,
        "backtest": _cmd_backtest,
    }
    handler = handler_map.get(args.bbm_command)
    if handler is None:
        print(f"Error: Unknown BBM subcommand: {args.bbm_command}", file=sys.stderr)
        return 2
    return handler(args)


def build_bbm_parser(subparsers: Any) -> None:
    """Add BBM subcommands."""

    draft_parser = subparsers.add_parser("draft", help="Interactive draft REPL")
    draft_parser.add_argument("--slot", type=int, required=True, help="Draft slot (1-12)")
    draft_parser.add_argument("--archetype", type=str, default=None, help="Archetype override A-E")
    draft_parser.add_argument("--draft-id", type=str, default=None, help="Resume existing draft")

    serve_parser = subparsers.add_parser("serve", help="Run local API server for Chrome extension")
    serve_parser.add_argument("--slot", type=int, default=None, help="Draft slot (1-12)")
    serve_parser.add_argument("--draft-id", type=str, default=None, help="Existing draft ID")
    serve_parser.add_argument("--archetype", type=str, default=None, help="Archetype A-E")
    serve_parser.add_argument("--port", type=int, default=8765, help="Server port (default: 8765)")
    serve_parser.add_argument("--host", type=str, default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    serve_parser.add_argument("--token", type=str, default=None, help="Optional static token required on POST endpoints (X-BBM-Token header)")

    refresh_parser = subparsers.add_parser("refresh-adp", help="Refresh ADP from CSV")
    refresh_parser.add_argument("--csv", type=Path, required=True, help="Path to BBTB ADP CSV")
    refresh_parser.add_argument(
        "--add-unmatched",
        action="store_true",
        help="Insert unmatched CSV names as new team=FA registry rows (off by default)",
    )

    weekly_parser = subparsers.add_parser(
        "refresh-weekly",
        help="Refresh ADP and optional projections, then sync the registry",
    )
    weekly_parser.add_argument("--adp", type=Path, required=True, help="Path to ADP CSV")
    weekly_parser.add_argument(
        "--projections",
        type=Path,
        default=None,
        help="Optional path to projections CSV",
    )
    weekly_parser.add_argument(
        "--add-unmatched",
        action="store_true",
        help="Insert unmatched CSV names as new team=FA registry rows (off by default)",
    )

    schedule_parser = subparsers.add_parser(
        "refresh-schedule", help="Fetch season byes + W17 matchups via nflreadpy"
    )
    schedule_parser.add_argument("--season", type=int, default=2026, help="Season year (default: 2026)")

    subparsers.add_parser(
        "fetch-bbm3",
        help="Print BBM III download details and readiness",
    )

    card_parser = subparsers.add_parser("draft-card", help="Generate markdown draft card")
    card_parser.add_argument("--out", type=Path, required=True)
    audit = subparsers.add_parser("audit", help="Audit a completed draft")
    audit.add_argument("--draft-id", type=str, required=True)
    recon = subparsers.add_parser("reconcile", help="Reconcile Underdog exposure CSV")
    recon.add_argument("--csv", type=Path, required=True)
    bt = subparsers.add_parser("backtest", help="BBM III replay backtest")
    bt.add_argument("--sample", type=int, default=100)
    bt.add_argument("--csv", type=Path, default=None, help="Path to custom pick data CSV")
    bt.add_argument("--fixture", type=Path, default=None, help="Path to fixture CSV for testing")
    bt.add_argument("--out", type=Path, default=Path("reports/bbm_backtest.json"), help="Output path for JSON report")

    practice = subparsers.add_parser("practice", help="Practice draft with auto-pick opponents")
    practice.add_argument("--slot", type=int, required=True, help="Draft slot (1-12)")
    practice.add_argument("--archetype", type=str, default=None, help="Archetype A-E")
    practice.add_argument("--rounds", type=int, default=18, help="Number of rounds (default: 18)")
    practice.add_argument("--draft-id", type=str, default=None, help="Resume existing practice draft")

    abandon_parser = subparsers.add_parser("abandon", help="Delete a stale in-progress draft")
    abandon_parser.add_argument("--draft-id", type=str, default=None, help="Draft to delete (omit to list)")
    abandon_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    abandon_parser.add_argument("--force", action="store_true", help="Allow deleting a complete draft")


def _cmd_draft(args: argparse.Namespace) -> int:
    ensure_initialized()

    # Print coverage summary
    registry = load_registry()
    coverage = check_registry_coverage(registry)
    print(f"Registry: {coverage['player_count']} players, {coverage['team_count']} teams")

    if args.draft_id:
        draft_id = args.draft_id
        state = get_draft_state(draft_id)
        if state is None:
            print(f"Error: Draft '{draft_id}' not found", file=sys.stderr)
            return 1
        slot = state.slot
        archetype = args.archetype or state.archetype
        current_round = state.current_round
        print(f"Resumed draft: {draft_id}")

        # Show pivot warning on resume (P4-4)
        pivot_msg = get_pivot_message(draft_id)
        if pivot_msg:
            print(f"[!] {pivot_msg}")

        # Show room taken info on resume (P1-4)
        taken_count = count_room_taken(draft_id)
        if taken_count > 0:
            print(f"Room: {taken_count} players marked taken")
            taken_names = list_room_taken_names(draft_id, limit=5)
            for name in taken_names:
                print(f"  - {name}")
    else:
        slot = args.slot
        if slot < 1 or slot > 12:
            print("Error: --slot must be 1-12", file=sys.stderr)
            return 1
        archetype = args.archetype or _suggest_archetype()
        draft_id = f"draft-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        create_draft(draft_id, slot, archetype)
        current_round = 1
        print(f"Created draft: {draft_id}")

    return _run_repl(draft_id, slot, archetype, current_round)


def _run_repl(draft_id: str, slot: int, archetype: str, start_round: int) -> int:
    current_round = start_round
    total_rounds = 18

    def pick_num_for(round_num: int) -> int:
        if round_num % 2 == 1:
            return (round_num - 1) * 12 + slot
        return round_num * 12 - slot + 1

    print(f"\n{archetype_header(archetype)}")
    print("Commands: p <name> | t/taken <name> | undo | sync | exp | archetype X | quit")
    print("=" * 60)

    while current_round <= total_rounds:
        pick_num = pick_num_for(current_round)
        _show_recommendations(current_round, pick_num, archetype, draft_id)

        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSaving draft state...")
            break

        if not user_input:
            continue

        parts = user_input.split(None, 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("quit", "q"):
            print("Saving draft state...")
            break

        if cmd == "p":
            if not arg:
                print("Usage: p <player_name>")
                continue
            player = resolve_player_query(arg)
            if player is None:
                # Check if there were ambiguous matches
                ambiguous = get_last_ambiguous_matches()
                if len(ambiguous) > 1:
                    print("Ambiguous — pick number:")
                    for idx, m in enumerate(ambiguous, 1):
                        print(f"  {idx}. {m['name']} {m['position']} {m.get('team', '')}")
                else:
                    print(f"Player not found: {arg}")
                continue
            record_pick(draft_id, current_round, pick_num, player["player_id"], is_mine=True)
            print(f"  -> Picked: {player['name']} ({player['position']} {player.get('team', '')})")
            current_round += 1
            continue

        if cmd in ("t", "taken"):
            if not arg:
                print("Usage: t <player_name>")
                continue
            player = resolve_player_query(arg)
            if player is None:
                # Check if there were ambiguous matches
                ambiguous = get_last_ambiguous_matches()
                if len(ambiguous) > 1:
                    print("Ambiguous — pick number:")
                    for idx, m in enumerate(ambiguous, 1):
                        print(f"  {idx}. {m['name']} {m['position']} {m.get('team', '')}")
                    continue
                # Not found and not ambiguous — create stub
                stub = ensure_player_stub(arg)
                record_taken(draft_id, current_round, pick_num, stub["player_id"])
                print(f"  -> WARNING: unknown player — created stub for: {arg} (verify spelling)")
                continue
            record_taken(draft_id, current_round, pick_num, player["player_id"])
            print(f"  -> Marked taken: {player['name']}")
            continue

        if cmd == "undo":
            result = undo_last_action(draft_id)
            if result:
                print(f"  -> Undid {result['undone']} (round {result['round']})")
                if result["undone"] == "pick":
                    current_round = result["round"]
            else:
                print("  -> Nothing to undo")
            continue

        if cmd == "sync":
            print("  -> Paste board snapshot (blank line to finish):")
            count = 0
            unmatched_lines: list[str] = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if not line.strip():
                    break
                player = resolve_player_query(line.strip())
                if player:
                    record_taken(draft_id, current_round, pick_num, player["player_id"])
                    count += 1
                else:
                    # Check if ambiguous
                    ambiguous = get_last_ambiguous_matches()
                    if len(ambiguous) > 1:
                        print(f"    Ambiguous '{line.strip()}' — skipping (use 't' command to pick)")
                    unmatched_lines.append(line.rstrip())
            print(f"  -> Synced {count} players")
            if unmatched_lines:
                print("  Unmatched lines:")
                for unmatched in unmatched_lines:
                    print(f"    {unmatched}")
            continue

        if cmd == "exp":
            _show_exposure_warnings()
            continue

        if cmd == "archetype":
            if arg:
                archetype = arg.upper()
                update_draft_archetype(draft_id, archetype)
                print(f"  -> Switched to archetype: {archetype}")
            else:
                print(archetype_header(archetype))
            continue

        print(f"Unknown command: {cmd}")

    if current_round > total_rounds:
        complete_draft(draft_id)
        print("Draft complete! Run: ceminidfs bbm audit --draft-id", draft_id)

    return 0


def _show_recommendations(round_num: int, pick_num: int, archetype: str, draft_id: str) -> None:
    print(f"\nRound {round_num}, Pick {pick_num} — top 3:")
    recs = get_recommendations(round_num, pick_num, archetype, draft_id, limit=3)
    if not recs:
        print("  (no recommendations — check registry sync)")
        return

    # Display pivot warning if present (attached to first recommendation)
    if recs and recs[0].get("pivot_warning"):
        print(f"  [!] {recs[0]['pivot_warning']}")

    for index, player in enumerate(recs, 1):
        signal_str = f"  {player['signal']}" if player.get("signal") else ""
        exp = int(player.get("exp_current", 0) * 100)
        exp_str = f"  exp {exp}%"
        if player.get("exp_current", 0) >= player.get("exp_cap", 1) * 0.95:
            exp_str += "  WARN near cap"
        stack_str = "  stack —" if player.get("is_stack_candidate") else ""
        warn = player.get("warnings") or []
        warn_str = f"  WARN {'; '.join(warn)}" if warn else ""
        print(
            f"  {index}. {player['name']} {player['position']} {player.get('team', '')}"
            f"{signal_str}{exp_str}{stack_str}{warn_str}"
        )


def _show_exposure_warnings() -> None:
    from ceminidfs.bbm.ledger import list_available_players

    print("\nTop exposure warnings:")
    rows = list_available_players(limit=30)
    warnings: list[tuple[float, str]] = []
    for row in rows:
        exp = exposure_pct(row["player_id"])
        if exp["current"] >= exp["cap"] * 0.85:
            warnings.append((exp["current"], f"  {row['name']}: {exp['current']:.0%} (cap {exp['cap']:.0%})"))
    warnings.sort(reverse=True)
    for _, line in warnings[:10]:
        print(line)
    if not warnings:
        print("  (none near cap)")


def _suggest_archetype() -> str:
    from ceminidfs.bbm.ledger import get_db_path
    import sqlite3

    db = get_db_path()
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT archetype, COUNT(*) FROM drafts WHERE status = 'complete' AND is_practice = 0 GROUP BY archetype"
    )
    counts = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return assign_archetype(LedgerCounts(archetype_counts=counts)).value


def _cmd_refresh_adp(args: argparse.Namespace) -> int:
    refresh_summary = _refresh_registry(args.csv, add_unmatched=args.add_unmatched)
    if refresh_summary is None:
        return 1
    adp_result, projection_result, synced_count = refresh_summary
    _print_refresh_summary(adp_result, projection_result, synced_count)
    return 0


def _cmd_refresh_weekly(args: argparse.Namespace) -> int:
    refresh_summary = _refresh_registry(
        args.adp, args.projections, add_unmatched=args.add_unmatched
    )
    if refresh_summary is None:
        return 1
    adp_result, projection_result, synced_count = refresh_summary
    _print_refresh_summary(adp_result, projection_result, synced_count)
    return 0


def _cmd_refresh_schedule(args: argparse.Namespace) -> int:
    from ceminidfs.bbm.schedule import (
        clear_schedule_memo,
        fetch_season_schedule,
        save_schedule_cache,
    )

    try:
        data = fetch_season_schedule(args.season)
    except Exception as exc:  # ImportError, ValueError, network errors from nflreadpy
        print(f"Error: {exc}", file=sys.stderr)
        print("Hardcoded 2026 schedule fallback remains active.", file=sys.stderr)
        return 1
    path = save_schedule_cache(data)
    clear_schedule_memo()
    print(
        f"Schedule cache written: {path} "
        f"({len(data['bye_weeks'])} team byes, {len(data['week17_matchups'])} W17 games)"
    )
    return 0


def _refresh_registry(
    adp_csv: Path,
    projections_csv: Path | None = None,
    add_unmatched: bool = False,
) -> tuple[Any, Any | None, int] | None:
    ensure_initialized()
    if not adp_csv.exists():
        print(f"Error: File not found: {adp_csv}", file=sys.stderr)
        return None
    if projections_csv is not None and not projections_csv.exists():
        print(f"Error: File not found: {projections_csv}", file=sys.stderr)
        return None

    registry = load_registry()
    adp_result = merge_adp_csv(adp_csv, registry, add_unmatched=add_unmatched)
    projection_result = (
        merge_projections_csv(projections_csv, registry) if projections_csv is not None else None
    )
    save_registry(registry)
    synced_count = sync_players_from_registry(registry)
    return adp_result, projection_result, synced_count


def _print_refresh_summary(adp_result: Any, projection_result: Any | None, synced_count: int) -> None:
    print(
        f"ADP updated {adp_result.matched} (exact {adp_result.exact_matched}, "
        f"fuzzy {adp_result.fuzzy_matched}, added {adp_result.added}, unmatched {len(adp_result.unmatched)})"
    )
    if adp_result.unmatched:
        print(f"  ADP unmatched ({len(adp_result.unmatched)}): {', '.join(adp_result.unmatched[:10])}")
        if len(adp_result.unmatched) > 10:
            print(f"    ... and {len(adp_result.unmatched) - 10} more")

    if projection_result is None:
        print("Projections: skipped")
    else:
        print(
            f"Projections updated {projection_result.matched} (exact {projection_result.exact_matched}, "
            f"fuzzy {projection_result.fuzzy_matched}, unmatched {len(projection_result.unmatched)})"
        )
        if projection_result.unmatched:
            print(
                f"  Projection unmatched ({len(projection_result.unmatched)}): "
                f"{', '.join(projection_result.unmatched[:10])}"
            )
            if len(projection_result.unmatched) > 10:
                print(f"    ... and {len(projection_result.unmatched) - 10} more")

    print(f"Registry synced: {synced_count} players")


def _cmd_fetch_bbm3(args: argparse.Namespace) -> int:
    del args
    print(f"Download URL: {BBM3_DOWNLOAD_URL}")
    print(f"Expected path: {BBM3_EXPECTED_PATH}")
    ready, message = validate_backtest_readiness()
    print(f"Readiness: {message}")
    return 0 if ready else 1


def _cmd_draft_card(args: argparse.Namespace) -> int:
    path = write_draft_card(args.out)
    print(f"Draft card written to {path}")
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    ensure_initialized()
    state = get_draft_state(args.draft_id)
    if state is None:
        print(f"Error: Draft '{args.draft_id}' not found", file=sys.stderr)
        return 1

    roster_players = []
    pick_analyses = []
    for pick in state.my_picks:
        row = {
            "player_id": pick["player_id"],
            "name": pick["name"],
            "position": pick["position"],
            "team": pick.get("team") or "",
            "bye_week": pick.get("bye_week") or 0,
            "adp": pick.get("adp") or 999,
        }
        roster_players.append(player_from_row(row))
        pick_analyses.append(
            {
                "round": pick["round"],
                "pick_num": pick.get("pick_num") or 0,
                "player": player_from_row(row),
                "adp": row["adp"],
                "clv_delta": (pick.get("pick_num") or 0) - row["adp"],
            }
        )

    from ceminidfs.bbm.models import Archetype

    draft = Draft(
        draft_id=state.draft_id,
        draft_date=datetime.now(),
        slot=state.slot,
        archetype=state.archetype,
        status=DraftStatus.COMPLETE if state.status == "complete" else DraftStatus.IN_PROGRESS,
    )
    roster = Roster(players=roster_players, draft_position=state.slot)
    exposure_counts = {
        p["player_id"]: int(exposure_pct(p["player_id"])["current"] * 150)
        for p in state.my_picks
    }

    try:
        arch = Archetype(state.archetype)
    except ValueError:
        arch = Archetype.B

    from ceminidfs.bbm.audit import PickAnalysis

    analyses = [
        PickAnalysis(
            round=p["round"],
            pick_num=p["pick_num"],
            player=p["player"],
            adp=p["adp"],
            clv_delta=p["clv_delta"],
            position=p["player"].position,
            was_recommended=False,
            warnings=[],
        )
        for p in pick_analyses
    ]

    result = audit_draft(draft, roster, analyses, exposure_counts, arch)
    print(format_audit_report(result))
    return 0 if result.passes_audit else 1


def _cmd_reconcile(args: argparse.Namespace) -> int:
    ensure_initialized()
    if not args.csv.exists():
        print(f"Error: File not found: {args.csv}", file=sys.stderr)
        return 1
    result = reconcile_from_csv(args.csv)
    print(format_reconcile_report(result))
    drift = len(result.drifts_flagged)
    return 0 if drift == 0 else 1


def _cmd_backtest(args: argparse.Namespace) -> int:
    result = run_backtest(
        sample=args.sample,
        csv_path=args.csv,
        fixture_path=args.fixture,
    )
    print(result.message)
    if result.metrics:
        m = result.metrics
        print(
            f"  structural pass: {m.structural_pass_rate:.0%} | "
            f"median CLV: {m.median_clv_delta:+.1f} | p99: {m.latency_p99_ms:.0f}ms | "
            f"picks evaluated: {m.picks_evaluated}"
        )
        # Write report
        report_path = write_backtest_report(result, args.out)
        print(f"  report written to: {report_path}")
        return 0
    else:
        print("  (no data available - provide --csv or --fixture)")
        return 1


def _cmd_practice(args: argparse.Namespace) -> int:
    """Run practice draft with auto-pick opponents."""
    ensure_initialized()

    slot = args.slot
    if slot < 1 or slot > 12:
        print("Error: --slot must be 1-12", file=sys.stderr)
        return 1

    archetype = args.archetype or _suggest_archetype()
    rounds = args.rounds
    draft_id = args.draft_id

    try:
        practice.run_practice_draft(
            slot=slot,
            archetype=archetype,
            rounds=rounds,
            draft_id=draft_id,
        )
        return 0
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_serve(args: argparse.Namespace) -> int:
    """Run the local API server for Chrome extension integration."""
    print("CeminiBBM serve — starting…", flush=True)

    try:
        ensure_initialized()
    except Exception as exc:
        print(f"Error: initialization failed: {exc}", file=sys.stderr, flush=True)
        return 1

    # Determine draft_id
    draft_id = args.draft_id
    slot = args.slot
    archetype = args.archetype

    if draft_id:
        # Resume existing draft
        state = get_draft_state(draft_id)
        if state is None:
            print(f"Error: Draft '{draft_id}' not found", file=sys.stderr, flush=True)
            return 1
        slot = slot or state.slot
        archetype = archetype or state.archetype
        print(f"Resuming draft: {draft_id}", flush=True)

        # Show pivot warning on resume (P4-4)
        pivot_msg = get_pivot_message(draft_id)
        if pivot_msg:
            print(f"[!] {pivot_msg}", flush=True)
    else:
        # Create new draft if slot provided
        if slot is None:
            print("Error: --slot required when creating new draft", file=sys.stderr, flush=True)
            print("Usage: ceminidfs bbm serve --slot <1-12> [--archetype A-E]", file=sys.stderr, flush=True)
            return 1
        if slot < 1 or slot > 12:
            print("Error: --slot must be 1-12", file=sys.stderr, flush=True)
            return 1

        archetype = archetype or _suggest_archetype()
        draft_id = f"draft-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}"
        create_draft(draft_id, slot, archetype)
        print(f"Created draft: {draft_id}", flush=True)

    print(f"Slot: {slot}, Archetype: {archetype}", flush=True)
    print("\nExtension setup: paste draft ID into extension/bbm-copilot popup", flush=True)
    print(f"  draft_id = {draft_id}", flush=True)
    print(f"  api_base = http://{args.host}:{args.port}\n", flush=True)
    if args.token:
        print(f"  token   = {args.token}  (set in extension popup)", flush=True)

    # Run server until Ctrl+C
    try:
        run_server(
            host=args.host,
            port=args.port,
            draft_id=draft_id,
            slot=slot,
            archetype=archetype,
            token=args.token,
        )
    except OSError as exc:
        if exc.errno in (48, 98) or "Address already in use" in str(exc):
            print(
                f"Error: port {args.port} already in use. "
                f"Stop the other serve process or use --port {args.port + 1}",
                file=sys.stderr,
                flush=True,
            )
            return 1
        raise

    return 0


def _cmd_abandon(args: argparse.Namespace) -> int:
    ensure_initialized()
    if not args.draft_id:
        drafts = list_in_progress_drafts()
        if not drafts:
            print("No in-progress drafts.")
            return 0
        for draft in drafts:
            tag = " [practice]" if draft.get("is_practice") else ""
            print(
                f"  {draft['draft_id']}  slot {draft['slot']}  "
                f"R{draft['current_round']}/{draft['total_rounds']}{tag}"
            )
        print("Re-run with --draft-id <id> to delete one.")
        return 0

    if not args.yes:
        confirm = input(f"Delete draft {args.draft_id} and all its picks? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return 1

    try:
        result = abandon_draft(args.draft_id, force=args.force)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Deleted {args.draft_id} ({result['picks_removed']} picks, {result['taken_removed']} taken)")
    return 0
