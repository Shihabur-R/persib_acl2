"""
Knockout-stage bracket simulation (pre-draw preparation).

The official ACL2 knockout draw has not been made, so this module builds an
*illustrative* bracket. Nothing here reflects an official AFC pairing: slots are
filled either from projected group standings or from manual club selection, and
the user picks each tie's winner.

Bracket shape follows the East Zone group-stage output: two qualifiers per group
(E-H) give eight clubs, i.e. Quarter-finals -> Semi-finals -> Final.
"""

from __future__ import annotations

from typing import Any

import metrics

# Round identifiers, ordered from the first round to the final.
ROUNDS = ("QF", "SF", "F")
ROUND_LABELS = {
    "QF": "Quarter-finals",
    "SF": "Semi-finals",
    "F": "Final",
}
SLOT_COUNT = 8

# Seed labels describe where a slot's club comes from in the projected table.
# 1E = winner of Group E, 2F = runner-up of Group F, and so on.
DEFAULT_SEEDS = ("1E", "1F", "1G", "1H", "2E", "2F", "2G", "2H")

# Illustrative pairing: group winners meet runners-up from a different group.
# This is a preparation aid, NOT the official draw.
DEFAULT_PAIRINGS = ((0, 5), (1, 4), (2, 7), (3, 6))


def projected_seeds(standings_by_group: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """
    Map seed labels (1E, 2F, ...) to clubs using current/projected standings.

    A group with fewer than two rows simply contributes fewer seeds; callers
    render those slots as undecided instead of failing.
    """
    seeds: dict[str, dict[str, Any]] = {}
    for group, rows in (standings_by_group or {}).items():
        ordered = sorted(rows or [], key=lambda row: metrics._num(row.get("rank"), 99))
        for index, row in enumerate(ordered[:2], start=1):
            seeds[f"{index}{group}"] = row
    return seeds


def build_slots(
    seeds: dict[str, dict[str, Any]],
    manual: dict[str, str] | None = None,
    clubs_by_slug: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Build the eight first-round slots.

    ``manual`` maps a seed label to a club slug and always wins over the seeded
    projection, so the user can explore alternative pre-draw scenarios.
    """
    manual = manual or {}
    clubs_by_slug = clubs_by_slug or {}
    slots = []
    for seed in DEFAULT_SEEDS:
        override = manual.get(seed)
        club = clubs_by_slug.get(override) if override else None
        source = "manual" if club else "projection"
        if club is None:
            row = seeds.get(seed) or {}
            club = {
                "name": row.get("name") or "Belum ditentukan",
                "slug": row.get("slug") or "",
                "group_name": seed[-1],
            }
            source = "projection" if row else "empty"
        slots.append(
            {
                "seed": seed,
                "club": club,
                "source": source,
                "seed_label": f"Peringkat {seed[0]} Grup {seed[-1]}",
            }
        )
    return slots


def _match(match_id: str, round_key: str, home: dict | None, away: dict | None) -> dict[str, Any]:
    """Create one tie, resolving its winner when both sides are known."""
    return {
        "id": match_id,
        "round": round_key,
        "round_label": ROUND_LABELS[round_key],
        "home": home,
        "away": away,
        "winner": None,
        "decided": False,
    }


def build_bracket(
    slots: list[dict[str, Any]], winners: dict[str, str] | None = None
) -> dict[str, Any]:
    """
    Assemble QF/SF/F rounds and propagate the user's chosen winners forward.

    ``winners`` maps a match id to 'home' or 'away'. A tie can only be decided
    once both participants are known, so picking a winner never invents a club.
    """
    winners = winners or {}
    entries = [slot["club"] if slot["source"] != "empty" else None for slot in slots]

    quarter_finals = [
        _match(f"QF{i + 1}", "QF", entries[a], entries[b])
        for i, (a, b) in enumerate(DEFAULT_PAIRINGS)
    ]
    for tie in quarter_finals:
        _apply_winner(tie, winners)

    semi_finals = [
        _match(
            f"SF{i + 1}",
            "SF",
            quarter_finals[i * 2]["winner"],
            quarter_finals[i * 2 + 1]["winner"],
        )
        for i in range(2)
    ]
    for tie in semi_finals:
        _apply_winner(tie, winners)

    final = _match("F1", "F", semi_finals[0]["winner"], semi_finals[1]["winner"])
    _apply_winner(final, winners)

    return {
        "rounds": [
            {"key": key, "label": ROUND_LABELS[key], "matches": matches}
            for key, matches in (
                ("QF", quarter_finals),
                ("SF", semi_finals),
                ("F", [final]),
            )
        ],
        "champion": final["winner"],
        "complete": final["winner"] is not None,
        "is_simulation": True,
    }


def _apply_winner(tie: dict[str, Any], winners: dict[str, str]) -> None:
    """Mark the chosen side as the winner, ignoring stale/invalid selections."""
    choice = winners.get(tie["id"])
    if choice not in ("home", "away"):
        return
    side = tie.get(choice)
    if side:
        tie["winner"] = side
        tie["decided"] = True
        tie["winner_side"] = choice
