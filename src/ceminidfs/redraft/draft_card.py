"""Generate the ESPN 12-team PPR redraft cheat sheet."""

from __future__ import annotations

from pathlib import Path

from ceminidfs.redraft import config


def _format_tuple(values: tuple[str, ...] | list[str]) -> str:
    return ", ".join(values)


def _position_limits_table() -> str:
    header = "| Position | Min | Max |"
    separator = "|---|---:|---:|"
    rows = [
        f"| {pos} | {lo} | {hi} |"
        for pos, (lo, hi) in config.POSITION_LIMITS.items()
    ]
    return "\n".join([header, separator, *rows])


def _autopick_rounds_table() -> str:
    header = "| Round | Auto-Pick choice |"
    separator = "|---:|---|"
    rows = [
        f"| {row['round']} | {row['choice']} |" for row in config.AUTOPICK_ROUND_STRATEGY
    ]
    return "\n".join([header, separator, *rows])


def build_draft_card() -> str:
    """Return the ESPN PPR redraft cheat sheet as markdown."""

    lines = [
        f"# {config.LEAGUE_LABEL} — Draft Card",
        "",
        "## Format",
        f"- Teams: `{config.TEAMS}`",
        f"- Draft rounds: `{config.DRAFT_ROUNDS}`",
        "- Scoring: ESPN default full PPR (1.0/rec, 4pt pass TD, −2 INT, −2 fumble)",
        "",
        "## Roster shell",
    ]
    for pos, target in config.ROSTER_SHELL.items():
        lines.append(f"- {pos}: {target}")

    lines.extend(
        [
            "",
            "## BUY / FADE",
            f"- BUY TE: {_format_tuple(config.BUY_TE)}",
            f"- BUY QB: {_format_tuple(config.BUY_QB)}",
            f"- BUY RB: {_format_tuple(config.BUY_RB)}",
            f"- BUY WR: {_format_tuple(config.BUY_WR)}",
            f"- BUY rookie WR: {_format_tuple(config.BUY_ROOKIE_WR)}",
            f"- FADE: {_format_tuple(config.FADE_PLAYERS)}",
            "",
            "## Round bands",
        ]
    )

    for band in config.ROUND_BAND_RULES:
        lines.extend(
            [
                f"- {band['rounds']}: {band['target']}",
                f"  - BUY: {_format_tuple(tuple(band['buy']))}",  # type: ignore[arg-type]
                f"  - FADE: {_format_tuple(tuple(band['fade']))}",  # type: ignore[arg-type]
            ]
        )

    lines.extend(
        [
            "",
            "## ESPN Auto-Pick Strategy",
            "",
            "Load these into **Edit Auto-Pick Strategy** (My Team) and save **≥1 hour** before draft.",
            "",
            "### Position limits",
            _position_limits_table(),
            "",
            "### Per-round choices",
            _autopick_rounds_table(),
            "",
            "## Draft-night checklist",
            "1. Open this card + prerank CSV side-by-side with ESPN.",
            "2. Confirm Pre-Draft Rankings match your prerank order (at least top 60).",
            "3. Confirm Auto-Pick Strategy + position limits saved.",
            "4. Live: click picks; keep Player Queue topped with next 5–8 targets.",
            "5. Backup: if disconnected, ESPN uses your Pre-Draft Rankings + strategy.",
            "",
            "## Explicit non-goals",
            "- No browser click-bot / extension autopick.",
            "- Autopick = ESPN native Pre-Draft Rankings + Auto-Pick Strategy only.",
            "",
        ]
    )
    return "\n".join(lines)


def write_draft_card(path: Path | str) -> Path:
    """Write the draft card markdown to ``path`` and return the path."""

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_draft_card(), encoding="utf-8")
    return out_path
