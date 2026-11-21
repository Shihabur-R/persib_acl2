"""
Unit tests for the PERSIB Simetris metrics module.

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
