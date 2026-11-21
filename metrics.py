"""
Statistical and balance metrics for the PERSIB Simetris application.

Every function in this module is pure: it receives normalized data and returns
a result without touching the network or the database. This makes the module
trivial to unit test and keeps route handlers thin.
"""

from __future__ import annotations

from typing import Any

POSITIONS = ("GK", "DF", "MF", "FW")
BALANCE_LABELS = (
    (0, 40, "Very Unbalanced", "Sangat Timpang"),
    (40, 70, "Fairly Balanced", "Cukup Seimbang"),
    (70, 101, "Highly Symmetric", "Sangat Simetris"),
)


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp a numeric value into a safe range."""
    return max(low, min(high, value))


def _label_for(score: float, lang: str = "en") -> str:
    """Map a 0-100 balance score to a human-readable label."""
    for low, high, en, id_ in BALANCE_LABELS:
        if low <= score < high:
            return en if lang == "en" else id_
    return BALANCE_LABELS[-1][2] if lang == "en" else BALANCE_LABELS[-1][3]


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
    total_a = sum(team_a.values()) or 1
    total_b = sum(team_b.values()) or 1
    distance = 0.0
    for position in POSITIONS:
        share_a = team_a.get(position, 0) / total_a
        share_b = team_b.get(position, 0) / total_b
        distance += abs(share_a - share_b)
    return round(_clamp((1.0 - distance / 2.0) * 100.0), 1)


def home_away_split(fixtures: list[dict[str, Any]], club_slug: str) -> dict[str, Any]:
    """Split finished fixtures for a club into home and away aggregates."""
    home = {"played": 0, "points": 0, "goals_for": 0, "goals_against": 0}
    away = {"played": 0, "points": 0, "goals_for": 0, "goals_against": 0}

    for match in fixtures:
        if match.get("status") != "FT":
            continue
        if match.get("home_slug") != club_slug and match.get("away_slug") != club_slug:
            continue
        is_home = match.get("home_slug") == club_slug
        bucket = home if is_home else away
        gf = match.get("home_goals" if is_home else "away_goals") or 0
        ga = match.get("away_goals" if is_home else "home_goals") or 0
        bucket["played"] += 1
        bucket["goals_for"] += gf
        bucket["goals_against"] += ga
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
        score = 50.0  # Neutral when one side has no finished matches.

    return {"home": home, "away": away, "score": score, "label_en": _label_for(score)}


def head_to_head(
    standings: list[dict[str, Any]], club_a: str, club_b: str
) -> dict[str, Any]:
    """Compare two clubs by their current standings row."""
    row_a = next((row for row in standings if row.get("name") == club_a), None)
    row_b = next((row for row in standings if row.get("name") == club_b), None)
    if not row_a or not row_b:
        return {"score": 50.0, "label_en": _label_for(50.0)}

    points_gap = abs(row_a["points"] - row_b["points"]) / max(row_a["points"] + row_b["points"], 1)
    goals_gap = abs(row_a["goals_for"] - row_b["goals_for"]) / max(row_a["goals_for"] + row_b["goals_for"], 1)
    score = round(_clamp((1.0 - (0.6 * points_gap + 0.4 * goals_gap)) * 100.0), 1)
    return {
        "score": score,
        "label_en": _label_for(score),
        "team_a": row_a,
        "team_b": row_b,
    }


def simulate_scenario(
    base_standing: dict[str, Any], result: str
) -> dict[str, Any]:
    """
    Project how one match result (win/draw/loss) changes a club's standing row.

    Goals for/against are not modelled; this is an explicit simplification that
    the UI communicates to the user.
    """
    projected = dict(base_standing)
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
    return projected


def compare_scenarios(
    scenario_a: dict[str, Any], scenario_b: dict[str, Any]
) -> dict[str, Any]:
    """
    Decide which of two projected standings is more advantageous/balanced.

    Advantage uses projected points. Balance uses the distance between the two
    projections on points-per-game and won/drawn/lost ratio.
    """
    adv_a = scenario_a["points"] + 0.1 * scenario_a["goals_for"]
    adv_b = scenario_b["points"] + 0.1 * scenario_b["goals_for"]
    more_advantageous = "A" if adv_a > adv_b else "B" if adv_b > adv_a else "Tie"

    games_a = max(scenario_a["played"], 1)
    games_b = max(scenario_b["played"], 1)
    ppg_gap = abs(scenario_a["points"] / games_a - scenario_b["points"] / games_b) / 3.0
    balance_score = round(_clamp((1.0 - ppg_gap) * 100.0), 1)
    more_balanced = "A" if balance_score >= 70 else "B"
    return {
        "advantage": more_advantageous,
        "balance_score": balance_score,
        "balance_label_en": _label_for(balance_score),
    }
