"""
Knockout-stage bracket driven strictly by group completion and official draw data.

Design rules (no free manual input anywhere):
- A slot is filled only when its feeding group has finished *and* a draw entry
  assigns that seed to the slot. Otherwise the slot stays TBD with a clear status.
- Winners are never picked by the user: a tie advances only when a recorded
  knockout result names one of its two actual participants.
- The bracket size adapts to the number of cross-group qualifiers, so every
  participant of the knockout phase gets its own slot/matchup (R32/R16/QF/SF/F).

All pairings come from draw data; nothing here invents an AFC pairing.
"""

from __future__ import annotations

from typing import Any

import metrics

# Round identifiers ordered from the earliest possible round to the final.
ROUND_LABELS = {
    "R32": "Round of 32",
    "R16": "Round of 16",
    "QF": "Quarter-finals",
    "SF": "Semi-finals",
    "F": "Final",
}
ROUND_ORDER = ("R32", "R16", "QF", "SF", "F")

# Slot status values used by the template (no 'manual' source exists any more).
SLOT_FILLED = "draw"
SLOT_PENDING_GROUP = "group_incomplete"
SLOT_PENDING_DRAW = "draw_pending"
SLOT_EMPTY = "empty"

STATUS_LABELS = {
    SLOT_FILLED: "Undian",
    SLOT_PENDING_GROUP: "Grup belum selesai",
    SLOT_PENDING_DRAW: "Menunggu undian",
    SLOT_EMPTY: "Kosong",
}

TBD_LABEL = "TBD"

# Structural floor: the East-zone groups feed the knockout phase today, so the
# bracket keeps its full size even before standings/draw data arrives.
DEFAULT_GROUPS = ("E", "F", "G", "H")
# Groups A–H are accepted; A–D stay TBD until their data exists, then join
# automatically and widen the bracket.
SUPPORTED_GROUPS = ("A", "B", "C", "D", "E", "F", "G", "H")


def _round_key_for(slot_count: int) -> str:
    """Return the first round key for a bracket holding ``slot_count`` clubs."""
    return {32: "R32", 16: "R16", 8: "QF", 4: "SF", 2: "F"}.get(slot_count, "R32")


def _bracket_size(qualifier_count: int) -> int:
    """
    Round the qualifier count up to the next power of two (minimum two).

    Extra room keeps every cross-group qualifier visible; surplus slots stay TBD
    instead of being silently dropped.
    """
    size = 2
    while size < max(qualifier_count, 2):
        size *= 2
    return size


def group_completion(
    standings_by_group: dict[str, list[dict[str, Any]]],
    fixtures_by_group: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Decide, per group, whether the group stage is finished.

    A group counts as complete only when it has standings rows, every club has
    played the full double round-robin ((teams - 1) * 2 matches), and no fixture
    remains unplayed. Anything unknown is treated as *not* complete.
    """
    fixtures_by_group = fixtures_by_group or {}
    report: dict[str, dict[str, Any]] = {}
    for group, rows in sorted((standings_by_group or {}).items()):
        rows = rows or []
        expected = (len(rows) - 1) * 2 if len(rows) > 1 else 0
        played = [int(metrics._num(row.get("played"), 0)) for row in rows]
        fixtures = fixtures_by_group.get(group) or []
        remaining = sum(1 for f in fixtures if (f.get("status") or "").upper() != "FT")
        complete = (
            bool(rows)
            and expected > 0
            and all(p >= expected for p in played)
            and remaining == 0
        )
        if not rows:
            reason = "Belum ada data"
        elif complete:
            reason = "Selesai"
        elif remaining:
            reason = f"{remaining} laga belum selesai"
        else:
            reason = f"Laga per klub belum {expected}"
        report[group] = {
            "group": group,
            "complete": complete,
            "expected_played": expected,
            "min_played": min(played) if played else 0,
            "remaining_fixtures": remaining,
            "reason": reason,
        }
    return report


def qualified_seeds(
    standings_by_group: dict[str, list[dict[str, Any]]],
    completion: dict[str, dict[str, Any]],
    per_group: int = 2,
) -> dict[str, dict[str, Any]]:
    """
    Map seed labels (1E, 2F, ...) to clubs, but only for completed groups.

    Incomplete groups contribute no seeds at all, so a provisional table is never
    presented as a final qualification.
    """
    seeds: dict[str, dict[str, Any]] = {}
    for group, rows in sorted((standings_by_group or {}).items()):
        if group not in SUPPORTED_GROUPS:
            continue
        if not (completion.get(group) or {}).get("complete"):
            continue
        ordered = sorted(rows or [], key=lambda row: metrics._num(row.get("rank"), 99))
        for index, row in enumerate(ordered[:per_group], start=1):
            seeds[f"{index}{group}"] = dict(row, group_name=group, seed=f"{index}{group}")
    return seeds


def _normalize_draw(draw: Any) -> list[dict[str, str]]:
    """
    Normalize draw data into a list of {home_seed, away_seed} ties.

    Accepts a list of pair dicts/lists or a {"ties": [...]} wrapper. Empty or
    malformed input yields no ties, which keeps the whole bracket TBD.
    """
    if isinstance(draw, dict):
        draw = draw.get("ties") or draw.get("matches") or []
    ties: list[dict[str, str]] = []
    for item in draw or []:
        if isinstance(item, dict):
            home = item.get("home_seed") or item.get("home")
            away = item.get("away_seed") or item.get("away")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            home, away = item
        else:
            continue
        home, away = str(home or "").strip().upper(), str(away or "").strip().upper()
        # Only seeds from a known group can occupy a slot.
        known = home[-1:] in SUPPORTED_GROUPS and away[-1:] in SUPPORTED_GROUPS
        if home and away and home != away and known:
            ties.append({"home_seed": home, "away_seed": away})
    return ties


def _slot_club(row: dict[str, Any], seed: str) -> dict[str, Any]:
    """Build the display club for a resolved seed."""
    group = seed[-1]
    return {
        "name": row.get("name") or TBD_LABEL,
        "slug": row.get("slug") or "",
        "group_name": group,
        "logo": row.get("logo"),
        "badge": row.get("badge") or TBD_LABEL,
        "seed": seed,
    }


def planned_seeds(groups: Any, per_group: int = 2) -> list[str]:
    """
    Return the seed labels the format reserves for ``groups`` (1E, 2E, ...).

    Reserving them up front keeps a labelled TBD slot for every qualifier place,
    including groups that have not finished yet, instead of anonymous padding.
    """
    labels: list[str] = []
    for group in sorted({str(g).strip().upper() for g in groups or () if str(g).strip()}):
        labels.extend(f"{rank}{group}" for rank in range(1, max(per_group, 1) + 1))
    return labels


def planned_slot_count(
    seeds: dict[str, dict[str, Any]],
    ties: list[dict[str, str]],
    groups: Any = None,
    per_group: int = 2,
) -> int:
    """
    Size the bracket from the format, not from how much data happens to exist.

    The count is the largest of: draw participants, resolved seeds, and the places
    reserved for every feeding group. Missing standings therefore cannot shrink
    the bracket down to a lone final, and a wider cross-group field (more groups
    or more qualifiers per group) expands it instead of dropping clubs.
    """
    # The East-zone groups are always part of the format, so they act as a floor.
    known = set(DEFAULT_GROUPS)
    known |= {str(g).strip().upper() for g in groups or () if str(g).strip()}
    known |= {seed[-1] for seed in seeds or ()}
    known |= {tie[side][-1] for tie in ties for side in ("home_seed", "away_seed")}
    return _bracket_size(max(len(ties) * 2, len(seeds or {}), len(known) * max(per_group, 1)))


def build_slots(
    seeds: dict[str, dict[str, Any]],
    completion: dict[str, dict[str, Any]],
    draw: Any = None,
    slot_count: int | None = None,
    reserved: Any = None,
) -> list[dict[str, Any]]:
    """
    Build first-round slots from draw data only.

    Each draw tie contributes two slots. A slot is filled only when its seed's
    group is complete; otherwise it stays TBD with an explicit status. Qualifiers
    without a draw pairing and surplus bracket padding are appended as visible
    TBD slots, so all cross-group participants fit a tidy power-of-two bracket.
    """
    ties = _normalize_draw(draw)
    # A seed is only eligible for a filled slot when the draw actually places it.
    drawn_seeds = {tie["home_seed"] for tie in ties} | {tie["away_seed"] for tie in ties}
    ordered: list[str] = []
    for tie in ties:
        ordered.extend([tie["home_seed"], tie["away_seed"]])
    for seed in sorted(seeds or {}):
        if seed not in ordered:
            ordered.append(seed)
    # Reserved places keep the bracket complete while groups are still running.
    for seed in reserved or ():
        if seed and seed not in ordered:
            ordered.append(seed)

    size = max(slot_count or 0, _bracket_size(len(ordered)))
    ordered += [""] * (size - len(ordered))

    slots: list[dict[str, Any]] = []
    for index, seed in enumerate(ordered[:size], start=1):
        group = seed[-1] if seed else ""
        row = (seeds or {}).get(seed)
        group_done = bool((completion.get(group) or {}).get("complete")) if group else False
        if not seed:
            status, club = SLOT_EMPTY, None
        elif row and group_done and seed in drawn_seeds:
            status, club = SLOT_FILLED, _slot_club(row, seed)
        elif group_done:
            status, club = SLOT_PENDING_DRAW, None
        else:
            status, club = SLOT_PENDING_GROUP, None
        slots.append(
            {
                "index": index,
                "seed": seed,
                "club": club,
                "name": club["name"] if club else TBD_LABEL,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "filled": club is not None,
                "seed_label": (
                    f"Peringkat {seed[0]} Grup {group}" if seed else "Slot tambahan"
                ),
            }
        )
    return slots


def _match(match_id: str, round_key: str, home: dict | None, away: dict | None) -> dict[str, Any]:
    """Create one tie; the winner stays unresolved until a result is recorded."""
    return {
        "id": match_id,
        "round": round_key,
        "round_label": ROUND_LABELS[round_key],
        "home": home,
        "away": away,
        "winner": None,
        "winner_side": None,
        "decided": False,
        "ready": bool(home and away),
    }


def _apply_result(tie: dict[str, Any], results: dict[str, Any]) -> None:
    """
    Advance a tie only from a recorded result naming one of its two clubs.

    Results are matched by slug/name, never by a free 'home'/'away' choice, so a
    stale or invented entry cannot promote a club that is not in the tie.
    """
    entry = results.get(tie["id"])
    if not entry or not tie["ready"]:
        return
    if isinstance(entry, dict):
        key = entry.get("winner_slug") or entry.get("winner")
    else:
        key = entry
    key = str(key or "").strip().lower()
    if not key:
        return
    for side in ("home", "away"):
        club = tie[side]
        identities = {
            str(club.get("slug") or "").lower(),
            str(club.get("name") or "").lower(),
        }
        if key in identities:
            tie["winner"] = club
            tie["winner_side"] = side
            tie["decided"] = True
            return


def build_bracket(
    slots: list[dict[str, Any]],
    results: dict[str, Any] | None = None,
    draw: Any = None,
) -> dict[str, Any]:
    """
    Assemble every round from the first-round slots up to the final.

    The round count follows the slot count, so a larger cross-group field simply
    produces more rounds/matchups. First-round pairings follow the draw/slot
    order; later rounds pair adjacent winners.
    """
    results = results or {}
    entries = [slot["club"] if slot.get("filled") else None for slot in slots]
    size = _bracket_size(len(entries))
    entries += [None] * (size - len(entries))

    first_key = _round_key_for(size)
    start = ROUND_ORDER.index(first_key)
    current = [
        _match(f"{first_key}{i + 1}", first_key, entries[i * 2], entries[i * 2 + 1])
        for i in range(size // 2)
    ]
    for tie in current:
        _apply_result(tie, results)
    rounds = [{"key": first_key, "label": ROUND_LABELS[first_key], "matches": current}]

    for key in ROUND_ORDER[start + 1:]:
        previous = current
        current = [
            _match(
                f"{key}{i + 1}",
                key,
                previous[i * 2]["winner"],
                previous[i * 2 + 1]["winner"],
            )
            for i in range(len(previous) // 2)
        ]
        for tie in current:
            _apply_result(tie, results)
        rounds.append({"key": key, "label": ROUND_LABELS[key], "matches": current})
        if len(current) == 1:
            break

    last = rounds[-1]["matches"]
    final = last[0] if len(last) == 1 else None
    return {
        "rounds": rounds,
        "champion": final["winner"] if final else None,
        "complete": bool(final and final["winner"]),
        "slot_count": size,
        "filled_count": sum(1 for entry in entries if entry),
        "draw_available": bool(_normalize_draw(draw)),
        "is_simulation": False,
    }


def build_stage(
    standings_by_group: dict[str, list[dict[str, Any]]],
    fixtures_by_group: dict[str, list[dict[str, Any]]] | None = None,
    draw: Any = None,
    results: dict[str, Any] | None = None,
    per_group: int = 2,
) -> dict[str, Any]:
    """
    Single entry point for the /knockout page.

    Returns the completion report, resolved seeds, slots, the full bracket and a
    transparent note describing what the bracket depends on. No parameter accepts
    a free manual club selection or a manually chosen winner.
    """
    standings_by_group = standings_by_group or {}
    completion = group_completion(standings_by_group, fixtures_by_group)
    seeds = qualified_seeds(standings_by_group, completion, per_group=per_group)
    ties = _normalize_draw(draw)
    feeding = (
        set(standings_by_group)
        | set(completion)
        | {seed[-1] for seed in seeds}
        | {tie[side][-1] for tie in ties for side in ("home_seed", "away_seed")}
    )
    # Accept A–H, keep the East-zone floor, and ignore unknown group letters.
    groups = sorted((set(DEFAULT_GROUPS) | feeding) & set(SUPPORTED_GROUPS))
    reserved = planned_seeds(groups, per_group=per_group)
    slot_count = planned_slot_count(seeds, ties, groups=groups, per_group=per_group)
    slots = build_slots(
        seeds, completion, draw=ties, slot_count=slot_count, reserved=reserved
    )
    bracket = build_bracket(slots, results=results, draw=ties)

    completed = [g for g, info in completion.items() if info["complete"]]
    pending = [g for g, info in completion.items() if not info["complete"]]
    if not completion:
        note = "Klasemen grup belum tersedia. Seluruh slot TBD."
    elif not ties:
        note = "Undian belum tersedia. Seluruh slot TBD."
    elif pending:
        note = "Grup belum selesai: " + ", ".join(pending) + ". Slot terkait TBD."
    else:
        note = "Grup selesai. Slot mengikuti hasil undian."

    return {
        "completion": completion,
        "completed_groups": completed,
        "pending_groups": pending,
        "seeds": seeds,
        "slots": slots,
        "bracket": bracket,
        "draw_available": bool(ties),
        "draw_ties": ties,
        "note": note,
        "groups_all_complete": bool(completion) and not pending,
        "cross_group": len({slot["club"]["group_name"] for slot in slots if slot["filled"]}) > 1,
        "groups": list(groups or DEFAULT_GROUPS),
        "reserved_seeds": reserved,
        "per_group": per_group,
        "has_standings": bool(completion),
        "slot_count": slot_count,
        "filled_count": bracket["filled_count"],
        "pending_draw_count": sum(1 for s in slots if s["status"] == SLOT_PENDING_DRAW),
        "pending_group_count": sum(1 for s in slots if s["status"] == SLOT_PENDING_GROUP),
        "empty_count": sum(1 for s in slots if s["status"] == SLOT_EMPTY),
    }
