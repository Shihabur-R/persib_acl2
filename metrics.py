"""
Statistical and balance metrics for the ACL2 Analytics & Simulation application.

Every function in this module is pure: it receives normalized data and returns
a result without touching the network or the database. This makes the module
trivial to unit test and keeps route handlers thin.
"""

from __future__ import annotations

from typing import Any

POSITIONS = ("GK", "DF", "MF", "FW")
ADVANTAGE_LABELS = {"A": "Skenario A", "B": "Skenario B", "Tie": "Seimbang"}
BALANCE_LABELS = (
    (0, 40, "Very Unbalanced", "Sangat Timpang"),
    (40, 70, "Fairly Balanced", "Cukup Seimbang"),
    (70, 101, "Highly Symmetric", "Sangat Simetris"),
)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp a numeric value into a safe range."""
    return max(low, min(high, value))


NEUTRAL_SCORE = 50.0  # Used whenever a comparison lacks usable data.


def _label_for(score: float, lang: str = "en") -> str:
    """Map a 0-100 balance score to a human-readable label."""
    for low, high, en, id_ in BALANCE_LABELS:
        if low <= score < high:
            return en if lang == "en" else id_
    return BALANCE_LABELS[-1][2] if lang == "en" else BALANCE_LABELS[-1][3]


def label_id(score: float) -> str:
    """Indonesian label for a balance score (UI language)."""
    return _label_for(score, lang="id")


def _num(value: Any, default: float = 0.0) -> float:
    """Coerce a possibly-missing numeric field into a safe number."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _same_team(row: dict[str, Any], identifier: str) -> bool:
    """Match a standings row against a club slug or name (case-insensitive)."""
    if not identifier:
        return False
    target = str(identifier).strip().lower()
    for key in ("slug", "name", "api_name", "tim"):
        value = row.get(key)
        if value and str(value).strip().lower() == target:
            return True
    return False


def squad_composition(players: list[dict[str, Any]]) -> dict[str, int]:
    """Return a position-code -> player-count dictionary."""
    counts = {position: 0 for position in POSITIONS}
    for player in players:
        code = (player.get("position_code") or "").upper()
        if code in counts:
            counts[code] += 1
    return counts


def squad_balance_score(team_a: dict[str, int], team_b: dict[str, int]) -> float:
    """
    Compare two position distributions using Total Variation Distance.

    A score of 100 means identical proportions; a score of 0 means completely
disjoint distributions. The function is symmetric: squad_balance_score(A, B) ==
squad_balance_score(B, A).
    """
    total_a = sum(_num(value) for value in (team_a or {}).values())
    total_b = sum(_num(value) for value in (team_b or {}).values())
    # No squad data on one/both sides: report a neutral score instead of 0.
    if not total_a or not total_b:
        return NEUTRAL_SCORE
    distance = 0.0
    for position in POSITIONS:
        share_a = _num((team_a or {}).get(position)) / total_a
        share_b = _num((team_b or {}).get(position)) / total_b
        distance += abs(share_a - share_b)
    return round(_clamp((1.0 - distance / 2.0) * 100.0), 1)


def home_away_split(fixtures: list[dict[str, Any]], club_slug: str) -> dict[str, Any]:
    """Split finished fixtures for a club into home and away aggregates."""
    home = {"played": 0, "points": 0, "goals_for": 0, "goals_against": 0}
    away = {"played": 0, "points": 0, "goals_for": 0, "goals_against": 0}

    for match in fixtures or []:
        if match.get("status") != "FT":
            continue
        home_id = match.get("home_slug") or match.get("home")
        away_id = match.get("away_slug") or match.get("away")
        is_home = _same_team({"slug": home_id, "name": match.get("home")}, club_slug)
        is_away = _same_team({"slug": away_id, "name": match.get("away")}, club_slug)
        if not is_home and not is_away:
            continue
        bucket = home if is_home else away
        gf = _num(match.get("home_goals" if is_home else "away_goals"))
        ga = _num(match.get("away_goals" if is_home else "home_goals"))
        bucket["played"] += 1
        bucket["goals_for"] += int(gf)
        bucket["goals_against"] += int(ga)
        if gf > ga:
            bucket["points"] += 3
        elif gf == ga:
            bucket["points"] += 1

    # Weighted balance: points 50%, goals 30%, conceded 20%.
    if home["played"] and away["played"]:
        home_pts_per_game = home["points"] / home["played"]
        away_pts_per_game = away["points"] / away["played"]
        pts_gap = abs(home_pts_per_game - away_pts_per_game) / 3.0

        home_gf_per_game = home["goals_for"] / home["played"]
        away_gf_per_game = away["goals_for"] / away["played"]
        gf_gap = abs(home_gf_per_game - away_gf_per_game) / max(home_gf_per_game + away_gf_per_game, 1)

        home_ga_per_game = home["goals_against"] / home["played"]
        away_ga_per_game = away["goals_against"] / away["played"]
        ga_gap = abs(home_ga_per_game - away_ga_per_game) / max(home_ga_per_game + away_ga_per_game, 1)

        score = round(_clamp((1.0 - (0.5 * pts_gap + 0.3 * gf_gap + 0.2 * ga_gap)) * 100.0), 1)
    else:
        score = NEUTRAL_SCORE  # Neutral when one side has no finished matches.

    return {
        "home": home,
        "away": away,
        "score": score,
        "label_en": _label_for(score),
        "label_id": label_id(score),
        "has_data": bool(home["played"] and away["played"]),
    }


def head_to_head(
    standings: list[dict[str, Any]], club_a: str, club_b: str
) -> dict[str, Any]:
    """Compare two clubs by their current standings row."""
    rows = standings or []
    row_a = next((row for row in rows if _same_team(row, club_a)), None)
    row_b = next((row for row in rows if _same_team(row, club_b)), None)
    if not row_a or not row_b:
        return {
            "score": NEUTRAL_SCORE,
            "label_en": _label_for(NEUTRAL_SCORE),
            "label_id": label_id(NEUTRAL_SCORE),
            "team_a": row_a,
            "team_b": row_b,
            "has_data": False,
            "note": "Kedua klub harus berada di grup yang sama untuk perbandingan klasemen.",
        }

    pts_a, pts_b = _num(row_a.get("points")), _num(row_b.get("points"))
    gf_a, gf_b = _num(row_a.get("goals_for")), _num(row_b.get("goals_for"))
    points_gap = abs(pts_a - pts_b) / max(pts_a + pts_b, 1)
    goals_gap = abs(gf_a - gf_b) / max(gf_a + gf_b, 1)
    score = round(_clamp((1.0 - (0.6 * points_gap + 0.4 * goals_gap)) * 100.0), 1)
    return {
        "score": score,
        "label_en": _label_for(score),
        "label_id": label_id(score),
        "team_a": row_a,
        "team_b": row_b,
        "has_data": True,
    }


def goal_baseline(base_standing: dict[str, Any]) -> dict[str, int]:
    """
    Return per-match goal averages from a standing row.

    Used as the automatic fallback when the user leaves the goal inputs blank.
    With no matches played yet a neutral 1-1 scoreline is assumed.
    """
    played = _num(base_standing.get("played"))
    if played <= 0:
        return {"goals_for": 1, "goals_against": 1}
    return {
        "goals_for": int(round(_num(base_standing.get("goals_for")) / played)),
        "goals_against": int(round(_num(base_standing.get("goals_against")) / played)),
    }


def resolve_goals(
    base_standing: dict[str, Any],
    result: str,
    goals_for: Any = None,
    goals_against: Any = None,
) -> dict[str, Any]:
    """
    Resolve scenario goals from user input, falling back to season averages.

    A single supplied value is enough: the other side is derived from the result
    (win => scored more, draw => level, loss => conceded more). Values are
    clamped to 0..20 and coerced so malformed input can never break the page.
    """
    baseline = goal_baseline(base_standing)
    gf = _parse_goals(goals_for)
    ga = _parse_goals(goals_against)
    source = "manual"

    if gf is None and ga is None:
        gf, ga = _scoreline_for_result(result, baseline)
        source = "average"
    elif gf is None:
        gf = _infer_opponent(ga, result, invert=True)
        source = "mixed"
    elif ga is None:
        ga = _infer_opponent(gf, result, invert=False)
        source = "mixed"

    gf, ga = _reconcile_with_result(gf, ga, result)
    return {"goals_for": gf, "goals_against": ga, "source": source}


def _parse_goals(value: Any) -> int | None:
    """Parse a goal input into 0..20, or None when blank/invalid."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(_clamp(int(float(value)), 0, 20))
    except (TypeError, ValueError):
        return None


def _scoreline_for_result(result: str, baseline: dict[str, int]) -> tuple[int, int]:
    """Build a plausible scoreline from averages that respects the result."""
    gf, ga = baseline["goals_for"], baseline["goals_against"]
    if result == "win":
        return max(gf, ga + 1), min(ga, max(gf, ga + 1) - 1)
    if result == "loss":
        return min(gf, max(ga, gf + 1) - 1), max(ga, gf + 1)
    level = int(round((gf + ga) / 2))
    return level, level


def _infer_opponent(known: int, result: str, invert: bool) -> int:
    """Derive the missing side of a scoreline from the known side and result."""
    if result == "draw":
        return known
    if (result == "win") != invert:
        return max(known - 1, 0)
    return known + 1


def _reconcile_with_result(gf: int, ga: int, result: str) -> tuple[int, int]:
    """Nudge a contradictory scoreline so it matches the declared result."""
    if result == "win" and gf <= ga:
        return ga + 1, ga
    if result == "loss" and gf >= ga:
        return gf, gf + 1
    if result == "draw" and gf != ga:
        level = int(round((gf + ga) / 2))
        return level, level
    return gf, ga


def simulate_scenario(
    base_standing: dict[str, Any],
    result: str,
    goals_for: Any = None,
    goals_against: Any = None,
    model_goals: bool = False,
) -> dict[str, Any]:
    """
    Project how one match result (win/draw/loss) changes a club's standing row.

    Goals are only modelled when ``model_goals`` is true; user-supplied goals
    fall back to season averages via :func:`resolve_goals`. Keeping the default
    off preserves the original points-only behaviour for existing callers.
    """
    projected = dict(base_standing)
    for key in ("played", "won", "drawn", "lost", "points", "goals_for", "goals_against"):
        projected[key] = int(_num(projected.get(key)))
    projected["played"] += 1
    if result == "win":
        projected["won"] += 1
        projected["points"] += 3
    elif result == "draw":
        projected["drawn"] += 1
        projected["points"] += 1
    elif result == "loss":
        projected["lost"] += 1
    else:
        raise ValueError(f"Unknown result '{result}'; expected win, draw, or loss")

    projected["goal_diff"] = projected["goals_for"] - projected["goals_against"]
    if model_goals:
        goals = resolve_goals(base_standing, result, goals_for, goals_against)
        projected["goals_for"] += goals["goals_for"]
        projected["goals_against"] += goals["goals_against"]
        projected["goal_diff"] = projected["goals_for"] - projected["goals_against"]
        projected["goals_modelled"] = True
        projected["scenario_goals"] = {
            "for": goals["goals_for"],
            "against": goals["goals_against"],
            "source": goals["source"],
        }
    else:
        projected["goals_modelled"] = False
    return projected


def compare_scenarios(
    scenario_a: dict[str, Any], scenario_b: dict[str, Any]
) -> dict[str, Any]:
    """
    Decide which of two projected standings is more advantageous/balanced.

    Advantage uses projected points. Balance uses the distance between the two
    projections on points-per-game and won/drawn/lost ratio.
    """
    pts_a = _num(scenario_a.get("points"))
    pts_b = _num(scenario_b.get("points"))
    adv_a = pts_a + 0.1 * _num(scenario_a.get("goals_for"))
    adv_b = pts_b + 0.1 * _num(scenario_b.get("goals_for"))
    more_advantageous = "A" if adv_a > adv_b else "B" if adv_b > adv_a else "Tie"

    symmetry_a = scenario_symmetry(scenario_a)
    symmetry_b = scenario_symmetry(scenario_b)
    if symmetry_a == symmetry_b:
        more_balanced = "Tie"
    else:
        more_balanced = "A" if symmetry_a > symmetry_b else "B"

    games_a = max(_num(scenario_a.get("played")), 1)
    games_b = max(_num(scenario_b.get("played")), 1)
    ppg_gap = abs(pts_a / games_a - pts_b / games_b) / 3.0
    gap_score = round(_clamp((1.0 - ppg_gap) * 100.0), 1)
    return {
        "advantage": more_advantageous,
        "advantage_label": ADVANTAGE_LABELS.get(more_advantageous, "Seri"),
        "symmetry_a": symmetry_a,
        "symmetry_b": symmetry_b,
        "more_balanced": more_balanced,
        "balance_score": symmetry_a if more_balanced == "A" else symmetry_b,
        "balance_label_en": _label_for(max(symmetry_a, symmetry_b)),
        "balance_label_id": label_id(max(symmetry_a, symmetry_b)),
        "gap_score": gap_score,
    }


def scenario_symmetry(scenario: dict[str, Any]) -> float:
    """
    Score how evenly a projected record spreads across win/draw/loss.

    Uses normalized Total Variation Distance against a perfectly even 1/3-1/3-1/3
    record: 100 = perfectly even, 0 = every match had the same outcome.
    """
    outcomes = [_num(scenario.get(key)) for key in ("won", "drawn", "lost")]
    total = sum(outcomes)
    if not total:
        return NEUTRAL_SCORE
    distance = sum(abs(value / total - 1.0 / 3.0) for value in outcomes)
    # Maximum possible TV distance for 3 categories against uniform is 4/3.
    return round(_clamp((1.0 - distance / (4.0 / 3.0)) * 100.0), 1)


def composition_by_club(
    clubs: list[dict[str, Any]], players: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Statistical finding 1: squad position distribution per club.

    Returns one row per club with counts, shares, total and the dominant line,
    ready to render as a grouped/stacked bar chart without extra JS libraries.
    """
    buckets: dict[Any, list[dict[str, Any]]] = {club["id"]: [] for club in clubs}
    for player in players or []:
        buckets.setdefault(player.get("club_id"), []).append(player)

    rows = []
    for club in clubs:
        counts = squad_composition(buckets.get(club["id"], []))
        total = sum(counts.values())
        shares = {
            position: round(count / total * 100.0, 1) if total else 0.0
            for position, count in counts.items()
        }
        dominant = max(POSITIONS, key=lambda p: counts[p]) if total else None
        rows.append(
            {
                "club": club,
                "counts": counts,
                "shares": shares,
                "total": total,
                "dominant": dominant,
                "defensive_share": round(shares["GK"] + shares["DF"], 1),
                "attacking_share": round(shares["MF"] + shares["FW"], 1),
            }
        )
    return rows


def group_comparison_table(standings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Statistical finding 2: head-to-head style comparison inside one group.

    Adds goal difference, points-per-game and the gap to the group leader.
    """
    rows = sorted(standings or [], key=lambda row: _num(row.get("rank"), 99))
    leader_points = _num(rows[0].get("points")) if rows else 0.0
    table = []
    for row in rows:
        played = _num(row.get("played"))
        points = _num(row.get("points"))
        table.append(
            {
                "row": row,
                "goal_diff": int(_num(row.get("goals_for")) - _num(row.get("goals_against"))),
                "ppg": round(points / played, 2) if played else 0.0,
                "gap_to_leader": int(leader_points - points),
            }
        )
    return table
