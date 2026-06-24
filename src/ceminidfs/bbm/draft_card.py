"""Generate the BBM draft cheat sheet."""

from __future__ import annotations

from pathlib import Path

from ceminidfs.bbm import config


def _format_tuple(values: tuple[str, ...]) -> str:
    return ", ".join(values)


def _matrix_table() -> str:
    header = "| Archetype | May-Jun | Jul-Aug | Late Aug | Total |"
    separator = "|---|---:|---:|---:|---:|"
    rows = [
        f"| {archetype} | {cells['may_jun']} | {cells['jul_mid_aug']} | {cells['late_aug_sep']} | {config.ARCHETYPE_SPLIT[archetype]} |"
        for archetype, cells in config.TIMING_ARCHETYPE_MATRIX.items()
    ]
    total_row = (
        f"| TOTAL | {config.TIMING_SPLIT['may_jun']} | {config.TIMING_SPLIT['jul_mid_aug']} | "
        f"{config.TIMING_SPLIT['late_aug_sep']} | {config.TOTAL_ENTRIES} |"
    )
    return "\n".join([header, separator, *rows, total_row])


def build_draft_card() -> str:
    """Return the BBM draft cheat sheet as markdown."""

    lines = [
        "# CeminiBBM Draft Copilot",
        "",
        "## Portfolio targets",
        f"- Total entries: `{config.TOTAL_ENTRIES}`",
        f"- Draft rounds: `{config.DRAFT_ROUNDS}`",
        f"- Teams: `{config.TEAMS}`",
        f"- Timing split: May-Jun {config.TIMING_SPLIT['may_jun']}, Jul-mid Aug {config.TIMING_SPLIT['jul_mid_aug']}, Late Aug-Sep {config.TIMING_SPLIT['late_aug_sep']}",
        "",
        "## Archetype split",
        f"- A RB-forward: {config.ARCHETYPE_SPLIT['A']}",
        f"- B Hero RB + WR: {config.ARCHETYPE_SPLIT['B']}",
        f"- C Stack-heavy: {config.ARCHETYPE_SPLIT['C']}",
        f"- D Zero RB: {config.ARCHETYPE_SPLIT['D']}",
        f"- E Contrarian / CLV-only: {config.ARCHETYPE_SPLIT['E']}",
        "",
        "## Timing × archetype matrix",
        _matrix_table(),
        "",
        "## Exposure caps",
        f"- elite: {config.EXPOSURE_CAPS['elite']}%",
        f"- stack_core: {config.EXPOSURE_CAPS['stack_core']}%",
        f"- mid_target: {config.EXPOSURE_CAPS['mid_target']}%",
        f"- late_lottery: {config.EXPOSURE_CAPS['late_lottery']}%",
        f"- single_dart: {config.EXPOSURE_CAPS['single_dart']}%",
        "",
        f"- Combo pair cap: 25% for stack pairs such as {_format_tuple(config.STACK_PAIRS[:3][0])}",
        "",
        "## BUY / FADE",
        f"- BUY TE: {_format_tuple(config.BUY_TE_CLUSTER)}",
        f"- BUY QB: {_format_tuple(config.BUY_QB)}",
        f"- BUY RB: {_format_tuple(config.BUY_RB_EARLY)}",
        f"- BUY WR: {_format_tuple(config.BUY_WR)}",
        f"- BUY rookie WR: {_format_tuple(config.BUY_ROOKIE_WR)}",
        f"- FADE: {_format_tuple(config.FADE_PLAYERS)}",
        "",
        "## Round bands",
    ]

    for band in config.ROUND_BAND_RULES:
        lines.extend(
            [
                f"- {band['rounds']}: {band['target']}",
                f"  - BUY: {_format_tuple(tuple(band['buy']))}",
                f"  - FADE: {_format_tuple(tuple(band['fade']))}",
            ]
        )

    lines.extend(
        [
            "",
            "## CLV weights",
            f"- May: {config.CLV_WEIGHTS_BY_MONTH['may']}",
            f"- Jul: {config.CLV_WEIGHTS_BY_MONTH['jul']}",
            f"- Aug: {config.CLV_WEIGHTS_BY_MONTH['aug']}",
            "",
            "## Roster shell",
            f"- QB: {config.DEFAULT_ROSTER_SHELL['qb']}",
            f"- RB: {config.DEFAULT_ROSTER_SHELL['rb']}",
            f"- WR: {config.DEFAULT_ROSTER_SHELL['wr']}",
            f"- TE: {config.DEFAULT_ROSTER_SHELL['te']}",
        ]
    )
    return "\n".join(lines) + "\n"


def write_draft_card(path: Path | str) -> Path:
    """Write the cheat sheet to disk and return the file path."""

    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_draft_card(), encoding="utf-8")
    return out_path

