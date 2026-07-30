"""ESPN season-long redraft CLI commands."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from ceminidfs.redraft import config
from ceminidfs.redraft.draft_card import write_draft_card
from ceminidfs.redraft.prerank import prerank_from_paths


def build_redraft_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register ``redraft`` subcommands on the parent CLI."""

    draft_card = subparsers.add_parser(
        "draft-card",
        help="Write ESPN 12-team PPR cheat sheet (BUY/FADE + Auto-Pick Strategy)",
    )
    draft_card.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output markdown path (default: briefs/espn-ppr-draft-card-YYYY-MM-DD.md)",
    )

    prerank = subparsers.add_parser(
        "prerank",
        help="Build ESPN Pre-Draft Rankings CSV from ADP",
    )
    prerank.add_argument(
        "--adp",
        type=Path,
        required=True,
        help="Season-long ADP CSV (name,pos,adp[,team,notes,projection_pts])",
    )
    prerank.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/espn-prerank.csv"),
        help="Output prerank CSV (default: artifacts/espn-prerank.csv)",
    )
    prerank.add_argument(
        "--top",
        type=int,
        default=config.PRERANK_TOP_N,
        help=f"Max players to emit (default: {config.PRERANK_TOP_N})",
    )
    prerank.add_argument(
        "--projections",
        type=Path,
        default=None,
        help="Optional projections CSV with name + projection_pts or counting stats",
    )

    refresh = subparsers.add_parser(
        "refresh",
        help="Weekly: regenerate draft card + prerank from ADP CSV",
    )
    refresh.add_argument(
        "--adp",
        type=Path,
        required=True,
        help="Season-long ADP CSV",
    )
    refresh.add_argument(
        "--card-out",
        type=Path,
        default=None,
        help="Draft card path (default: briefs/espn-ppr-draft-card-YYYY-MM-DD.md)",
    )
    refresh.add_argument(
        "--prerank-out",
        type=Path,
        default=Path("artifacts/espn-prerank.csv"),
        help="Prerank CSV path (default: artifacts/espn-prerank.csv)",
    )
    refresh.add_argument(
        "--top",
        type=int,
        default=config.PRERANK_TOP_N,
        help=f"Max players to emit (default: {config.PRERANK_TOP_N})",
    )
    refresh.add_argument(
        "--projections",
        type=Path,
        default=None,
        help="Optional projections CSV",
    )


def handle_redraft_command(args: argparse.Namespace) -> int:
    """Dispatch redraft subcommands."""

    if not getattr(args, "redraft_command", None):
        print("Error: No redraft subcommand specified", file=sys.stderr)
        print("Available: draft-card, prerank, refresh", file=sys.stderr)
        return 2

    handlers = {
        "draft-card": _cmd_draft_card,
        "prerank": _cmd_prerank,
        "refresh": _cmd_refresh,
    }
    handler = handlers.get(args.redraft_command)
    if handler is None:
        print(f"Error: Unknown redraft command: {args.redraft_command}", file=sys.stderr)
        return 2
    return handler(args)


def _default_card_path() -> Path:
    return Path(f"briefs/espn-ppr-draft-card-{date.today().isoformat()}.md")


def _cmd_draft_card(args: argparse.Namespace) -> int:
    out = args.out or _default_card_path()
    path = write_draft_card(out)
    print(f"Wrote draft card: {path}")
    return 0


def _cmd_prerank(args: argparse.Namespace) -> int:
    try:
        summary = prerank_from_paths(
            args.adp,
            args.out,
            top_n=args.top,
            projections_path=args.projections,
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote prerank: {summary['out']} ({summary['rows']} players)")
    if summary.get("top_name") is not None:
        print(f"  #1: {summary['top_name']} (ADP {summary['top_adp']})")
    return 0


def _cmd_refresh(args: argparse.Namespace) -> int:
    card_out = args.card_out or _default_card_path()
    card_path = write_draft_card(card_out)
    print(f"Wrote draft card: {card_path}")
    try:
        summary = prerank_from_paths(
            args.adp,
            args.prerank_out,
            top_n=args.top,
            projections_path=args.projections,
        )
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote prerank: {summary['out']} ({summary['rows']} players)")
    if summary.get("top_name") is not None:
        print(f"  #1: {summary['top_name']} (ADP {summary['top_adp']})")
    print("Next: load prerank into ESPN Pre-Draft Rankings; save Auto-Pick Strategy ≥1hr before draft.")
    return 0
