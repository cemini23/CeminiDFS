"""Practice draft simulator — 12-team snake with auto-pick opponents."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ceminidfs.bbm.ledger import (
    count_room_taken,
    complete_draft,
    create_draft,
    get_draft_state,
    list_available_players,
    record_pick,
    record_taken,
    resolve_player_query,
    undo_last_action,
    get_last_ambiguous_matches,
    ensure_player_stub,
)
from ceminidfs.bbm.session import archetype_header, get_recommendations
from ceminidfs.bbm.audit import audit_draft, PickAnalysis
from ceminidfs.bbm.models import Draft, DraftStatus, Roster
from ceminidfs.bbm.session import get_taken_player_ids, player_from_row


def _whose_pick(pick_num: int, total_teams: int = 12) -> int:
    """Determine which team slot has a given pick number in snake draft.

    Round 1 (picks 1-12): pick_num maps directly to slot (1-12)
    Round 2 (picks 13-24): reverse order (pick 13 = slot 12, pick 24 = slot 1)
    Round 3 (picks 25-36): normal order, etc.
    """
    round_num = (pick_num - 1) // total_teams + 1
    offset_in_round = (pick_num - 1) % total_teams

    if round_num % 2 == 1:
        # Odd rounds: ascending (1 -> pick 1, 12 -> pick 12)
        return offset_in_round + 1
    else:
        # Even rounds: descending (12 -> pick 13, 1 -> pick 24)
        return total_teams - offset_in_round


def _pick_num_for(slot: int, round_num: int, total_teams: int = 12) -> int:
    """Calculate pick number for a given slot and round."""
    if round_num % 2 == 1:
        # Odd round: ascending
        return (round_num - 1) * total_teams + slot
    else:
        # Even round: descending
        return round_num * total_teams - slot + 1


def _get_highest_adp_available(draft_id: str, taken_ids: set[str]) -> dict[str, Any] | None:
    """Get the highest ADP (lowest ADP number) available player."""
    players = list_available_players(limit=240, draft_id=draft_id)
    available = [p for p in players if p["player_id"] not in taken_ids]
    if not available:
        return None
    # Sort by ADP ascending, return first
    available.sort(key=lambda p: p.get("adp", 999))
    return available[0]


def _resume_state(draft_id: str) -> tuple[int, set[str]]:
    """Return (next overall pick number, taken player ids) for a resumed draft.

    Picks consumed = my/recorded picks rows + room_taken rows (disjoint in practice flow).
    """
    state = get_draft_state(draft_id)
    if state is None:
        raise ValueError(f"Draft '{draft_id}' not found")
    taken_ids = {pick["player_id"] for pick in state.all_picks} | get_taken_player_ids(draft_id)
    picks_consumed = len(state.all_picks) + count_room_taken(draft_id)
    return picks_consumed + 1, taken_ids


def run_practice_draft(
    slot: int,
    archetype: str,
    rounds: int = 18,
    draft_id: str | None = None,
) -> str:
    """Run an interactive practice draft with auto-pick opponents.

    Args:
        slot: User's draft slot (1-12)
        archetype: Archetype A-E for recommendations
        rounds: Number of rounds to simulate (default 18)
        draft_id: Optional existing draft ID to resume

    Returns:
        The draft_id of the completed or in-progress draft
    """
    if slot < 1 or slot > 12:
        raise ValueError(f"Slot must be 1-12, got {slot}")

    # Create or resume draft
    if draft_id:
        current_pick_num, taken_ids = _resume_state(draft_id)
        print(f"Resumed practice draft: {draft_id}")
    else:
        draft_id = f"practice-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        create_draft(draft_id, slot, archetype, total_rounds=rounds, is_practice=True)
        print(f"Created practice draft: {draft_id}")
        current_pick_num = 1
        taken_ids = set()

    print(f"\n{archetype_header(archetype)}")
    print("Practice mode: 12-team snake, you pick, opponents auto-pick")
    print("Commands: p <name> | t/taken <name> | undo | quit")
    print("=" * 60)

    total_picks_needed = rounds * 12

    while current_pick_num <= total_picks_needed:
        whose_turn = _whose_pick(current_pick_num, 12)
        round_num = (current_pick_num - 1) // 12 + 1

        if whose_turn == slot:
            # User's turn - show recommendations and prompt
            print(f"\nRound {round_num}, Pick {current_pick_num} — YOUR PICK — top 3:")
            recs = get_recommendations(round_num, current_pick_num, archetype, draft_id, limit=3)

            if not recs:
                print("  (no recommendations — check registry sync)")
            else:
                # Display pivot warning if present
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

            # Get user input
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

            if cmd == "undo":
                result = undo_last_action(draft_id)
                if result:
                    print(f"  -> Undid {result['undone']} (round {result['round']})")
                    if result["undone"] == "pick":
                        # Need to recalculate current position
                        state = get_draft_state(draft_id)
                        if state:
                            current_pick_num, taken_ids = _resume_state(draft_id)
                        continue
                else:
                    print("  -> Nothing to undo")
                continue

            if cmd in ("t", "taken"):
                if not arg:
                    print("Usage: t <player_name>")
                    continue
                player = resolve_player_query(arg)
                if player is None:
                    ambiguous = get_last_ambiguous_matches()
                    if len(ambiguous) > 1:
                        print("Ambiguous — pick number:")
                        for idx, m in enumerate(ambiguous, 1):
                            print(f"  {idx}. {m['name']} {m['position']} {m.get('team', '')}")
                        continue
                    stub = ensure_player_stub(arg)
                    record_taken(draft_id, round_num, current_pick_num, stub["player_id"])
                    taken_ids.add(stub["player_id"])
                    print(f"  -> WARNING: unknown player — created stub for: {arg} (verify spelling)")
                else:
                    record_taken(draft_id, round_num, current_pick_num, player["player_id"])
                    taken_ids.add(player["player_id"])
                    print(f"  -> Marked taken: {player['name']}")
                current_pick_num += 1
                continue

            if cmd == "p":
                if not arg:
                    print("Usage: p <player_name>")
                    continue
                player = resolve_player_query(arg)
                if player is None:
                    ambiguous = get_last_ambiguous_matches()
                    if len(ambiguous) > 1:
                        print("Ambiguous — pick number:")
                        for idx, m in enumerate(ambiguous, 1):
                            print(f"  {idx}. {m['name']} {m['position']} {m.get('team', '')}")
                        continue
                    print(f"Player not found: {arg}")
                    continue
                record_pick(draft_id, round_num, current_pick_num, player["player_id"], is_mine=True)
                taken_ids.add(player["player_id"])
                print(f"  -> Picked: {player['name']} ({player['position']} {player.get('team', '')})")
                current_pick_num += 1
                continue

            print(f"Unknown command: {cmd}")

        else:
            # Opponent's turn - auto-pick highest ADP available
            player = _get_highest_adp_available(draft_id, taken_ids)
            if player is None:
                print(f"\nRound {round_num}, Pick {current_pick_num} — Slot {whose_turn}: No players available!")
                break

            record_taken(draft_id, round_num, current_pick_num, player["player_id"])
            taken_ids.add(player["player_id"])
            print(f"\nRound {round_num}, Pick {current_pick_num} — Slot {whose_turn}: {player['name']} ({player['position']})")
            current_pick_num += 1

    # Draft complete or exited
    if current_pick_num > total_picks_needed:
        complete_draft(draft_id)
        print("\nPractice draft complete!")

        # Generate audit summary one-liner
        state = get_draft_state(draft_id)
        if state and state.my_picks:
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
                    PickAnalysis(
                        round=pick["round"],
                        pick_num=pick.get("pick_num") or 0,
                        player=player_from_row(row),
                        adp=row["adp"],
                        clv_delta=(pick.get("pick_num") or 0) - row["adp"],
                        position=pick["position"],
                        was_recommended=False,
                        warnings=[],
                    )
                )

            draft = Draft(
                draft_id=draft_id,
                draft_date=datetime.now(),
                slot=slot,
                archetype=archetype,
                status=DraftStatus.COMPLETE,
            )
            roster = Roster(players=roster_players, draft_position=slot)
            from ceminidfs.bbm.models import Archetype
            from ceminidfs.bbm.ledger import exposure_pct

            try:
                arch = Archetype(archetype)
            except ValueError:
                arch = Archetype.B

            exposure_counts = {
                p["player_id"]: int(exposure_pct(p["player_id"])["current"] * 150)
                for p in state.my_picks
            }

            result = audit_draft(draft, roster, pick_analyses, exposure_counts, arch)

            # One-liner summary
            pos_str = "/".join(f"{p}:{c}" for p, c in result.position_counts.items())
            print(f"Audit: {pos_str} | avg CLV {result.estimated_clv:+.1f} | {'PASS' if result.passes_audit else 'FAIL'}")

    return draft_id
