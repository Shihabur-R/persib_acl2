"""
Unit tests for the ACL2 Analytics & Simulation metrics module.

Maps to SRS test cases:
  TC-01  Balance Meter with valid squad data returns score + label.
  TC-02  Balance Meter with empty/incomplete data falls back safely.
  TC-03  Scenario Duel simulation projects standings correctly.
  TC-04  Saved Pick validation rejects empty and duplicate input.
  TC-05  Saved Pick deletion removes the item from the store.
"""

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import metrics
import picks_store


def _make_players(gk=3, df=6, mf=12, fw=6):
    """Build a synthetic player list for tests."""
    players = []
    for _ in range(gk):
        players.append({"position_code": "GK"})
    for _ in range(df):
        players.append({"position_code": "DF"})
    for _ in range(mf):
        players.append({"position_code": "MF"})
    for _ in range(fw):
        players.append({"position_code": "FW"})
    return players


def test_tc01_squad_balance_valid():
    """TC-01: identical distributions yield a high symmetric score."""
    team_a = metrics.squad_composition(_make_players(3, 6, 12, 6))
    team_b = metrics.squad_composition(_make_players(3, 6, 12, 6))
    score = metrics.squad_balance_score(team_a, team_b)
    assert score == 100.0
    assert metrics._label_for(score) == "Highly Symmetric"


def test_tc02_squad_balance_empty():
    """TC-02: empty composition should not raise and returns neutral score."""
    empty = metrics.squad_composition([])
    other = metrics.squad_composition(_make_players())
    score = metrics.squad_balance_score(empty, other)
    assert 0.0 <= score <= 100.0


def test_tc03_simulate_scenario():
    """TC-03: a win adds three points and one played match."""
    base = {"played": 4, "won": 4, "drawn": 0, "lost": 0, "points": 12, "goals_for": 6, "goals_against": 1}
    projected = metrics.simulate_scenario(base, "win")
    assert projected["played"] == 5
    assert projected["points"] == 15
    assert projected["won"] == 5


def test_tc04_pick_validation(tmp_path, monkeypatch):
    """TC-04: empty title is rejected; duplicate pick is rejected."""
    # Use a temporary database for this test.
    temp_db = tmp_path / "test_picks.db"
    monkeypatch.setattr(picks_store, "DB_PATH", str(temp_db))
    picks_store.init_table()

    # Empty title.
    try:
        picks_store.save_pick("", "A", "B", {})
        assert False, "Expected PickValidationError"
    except picks_store.PickValidationError:
        pass

    # Valid save then duplicate save.
    picks_store.save_pick("My Pick", "Win home", "Draw away", {})
    try:
        picks_store.save_pick("My Pick", "Win home", "Draw away", {})
        assert False, "Expected PickValidationError"
    except picks_store.PickValidationError:
        pass


def test_tc05_pick_delete(tmp_path, monkeypatch):
    """TC-05: deleting a saved pick removes it from the store."""
    temp_db = tmp_path / "test_picks.db"
    monkeypatch.setattr(picks_store, "DB_PATH", str(temp_db))
    picks_store.init_table()

    pick_id = picks_store.save_pick("Delete Me", "A", "B", {})
    assert any(p["id"] == pick_id for p in picks_store.list_picks())

    picks_store.delete_pick(pick_id)
    assert not any(p["id"] == pick_id for p in picks_store.list_picks())


def test_scenario_goals_manual_and_fallback():
    """Goal inputs change GF/GA/GD; blank inputs fall back to season averages."""
    base = {"played": 4, "won": 4, "drawn": 0, "lost": 0, "points": 12,
            "goals_for": 8, "goals_against": 4}
    manual = metrics.simulate_scenario(base, "win", 3, 0, model_goals=True)
    assert manual["goals_for"] == 11
    assert manual["goals_against"] == 4
    assert manual["goal_diff"] == 7
    assert manual["scenario_goals"]["source"] == "manual"

    auto = metrics.simulate_scenario(base, "win", model_goals=True)
    assert auto["scenario_goals"]["source"] == "average"
    assert auto["goals_for"] > base["goals_for"]

    # Legacy points-only behaviour is preserved when model_goals is off.
    legacy = metrics.simulate_scenario(base, "win")
    assert legacy["goals_for"] == base["goals_for"]


def test_scenario_goals_invalid_and_contradictory():
    """Garbage input falls back; contradictory scorelines are reconciled."""
    base = {"played": 2, "won": 1, "drawn": 0, "lost": 1, "points": 3,
            "goals_for": 2, "goals_against": 2}
    garbage = metrics.simulate_scenario(base, "draw", "abc", "", model_goals=True)
    assert garbage["scenario_goals"]["source"] == "average"
    assert garbage["goals_for"] - base["goals_for"] == garbage["goals_against"] - base["goals_against"]

    odd = metrics.simulate_scenario(base, "win", 0, 5, model_goals=True)
    scored = odd["scenario_goals"]
    assert scored["for"] > scored["against"]


def test_knockout_bracket_propagation():
    """Winners advance round by round; premature picks are ignored."""
    import knockout

    clubs = {
        f"club{i}": {"name": f"Club {i}", "slug": f"club{i}", "group_name": "E"}
        for i in range(8)
    }
    slots = knockout.build_slots({}, {f"{i+1}E": f"club{i}" for i in range(8)}, clubs)
    empty = knockout.build_bracket(slots)
    assert empty["champion"] is None
    # Picking a final winner before the semis are decided must not invent a club.
    assert knockout.build_bracket(slots, {"F1": "home"})["champion"] is None

    winners = {"QF1": "home", "QF2": "away", "QF3": "home", "QF4": "away",
               "SF1": "home", "SF2": "away", "F1": "home"}
    bracket = knockout.build_bracket(slots, winners)
    assert bracket["complete"] is True
    assert bracket["champion"] is not None
    assert [len(r["matches"]) for r in bracket["rounds"]] == [4, 2, 1]
