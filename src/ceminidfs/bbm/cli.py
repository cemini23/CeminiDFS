"""CeminiBBM CLI — Best Ball Mania draft copilot commands."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ceminidfs.bbm.archetype import assign_archetype
from ceminidfs.bbm.audit import audit_draft, format_audit_report
from ceminidfs.bbm.draft_card import write_draft_card
from ceminidfs.bbm.ledger import (
    complete_draft,
    create_draft,
    exposure_pct,
    get_draft_state,
    get_players_by_name,
    get_player_by_name,
    record_pick,
    record_taken,
    update_draft_archetype,
    undo_last_action,
)
from ceminidfs.bbm.models import Draft, DraftStatus, LedgerCounts, Roster
from ceminidfs.bbm.normalize_adp import merge_adp_csv
from ceminidfs.bbm.reconcile import format_reconcile_report, reconcile_from_csv
from ceminidfs.bbm.registry import load_registry, save_registry
from ceminidfs.bbm.session import (
    archetype_header,
    ensure_initialized,
    get_recommendations,
    player_from_row,
)


def handle_bbm_command(args: argparse.Namespace) -> int:
    """Dispatch to the appropriate BBM subcommand handler."""

    if not hasattr(args, "bbm_command") or args.bbm_command is None:
        print("Error: No BBM subcommand specified", file=sys.stderr)
        print("Available: draft, refresh-adp, draft-card, audit, reconcile, backtest")
        return 2

    handler_map = {
        "draft": _cmd_draft,
        "refresh-adp": _cmd_refresh_adp,
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

    refresh_parser = subparsers.add_parser("refresh-adp", help="Refresh ADP from CSV")
    refresh_parser.add_argument("--csv", type=Path, required=True, help="Path to BBTB ADP CSV")

    card_parser = subparsers.add_parser("draft-card", help="Generate markdown draft card")
    card_parser.add_argument("--out", type=Path, required=True)
    audit = subparsers.add_parser("audit", help="Audit a completed draft")
    audit.add_argument("--draft-id", type=str, required=True)
    recon = subparsers.add_parser("reconcile", help="Reconcile Underdog exposure CSV")
    recon.add_argument("--csv", type=Path, required=True)
    bt = subparsers.add_parser("backtest", help="BBM III replay backtest (stub)")
    bt.add_argument("--sample", type=int, default=100)


def _cmd_draft(args: argparse.Namespace) -> int:
    ensure_initialized()

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
            player = get_player_by_name(arg)
            if player is None:
                matches = get_players_by_name(arg)
                if len(matches) > 1:
                    print("Ambiguous: use full name")
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
            player = get_player_by_name(arg)
            if player is None:
                matches = get_players_by_name(arg)
                if len(matches) > 1:
                    print("Ambiguous: use full name")
                else:
                    print(f"Player not found: {arg}")
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
                player = get_player_by_name(line.strip())
                if player:
                    record_taken(draft_id, current_round, pick_num, player["player_id"])
                    count += 1
                else:
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
        "SELECT archetype, COUNT(*) FROM drafts WHERE status = 'complete' GROUP BY archetype"
    )
    counts = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return assign_archetype(LedgerCounts(archetype_counts=counts)).value


def _cmd_refresh_adp(args: argparse.Namespace) -> int:
    ensure_initialized()
    if not args.csv.exists():
        print(f"Error: File not found: {args.csv}", file=sys.stderr)
        return 1

    registry = load_registry()
    result = merge_adp_csv(args.csv, registry)
    save_registry(registry)
    from ceminidfs.bbm.ledger import sync_players_from_registry

    sync_players_from_registry(registry)
    print(f"Updated {result.matched} players from {args.csv}")
    if result.unmatched:
        print(f"Unmatched ({len(result.unmatched)}): {', '.join(result.unmatched[:10])}")
        if len(result.unmatched) > 10:
            print(f"  ... and {len(result.unmatched) - 10} more")
    return 0


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
    from ceminidfs.bbm.backtest import run_backtest

    result = run_backtest(args.sample)
    print(result.message)
    if result.metrics:
        m = result.metrics
        print(
            f"  structural pass: {m.structural_pass_rate:.0%} | "
            f"median CLV: {m.median_clv_delta:+.1f} | p99: {m.latency_p99_ms:.0f}ms"
        )
    return 0
