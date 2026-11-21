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


def _group_rows(letter, teams=4, played=6):
    """Build standings rows for one group; played=6 means a finished 4-team group."""
    return [
        {
            "rank": i + 1,
            "name": f"{letter} Club {i + 1}",
            "slug": f"{letter.lower()}-club-{i + 1}",
            "played": played,
        }
        for i in range(teams)
    ]


def _finished_fixtures(groups, count=12):
    """All group fixtures marked full-time."""
    return {g: [{"status": "FT"}] * count for g in groups}


def test_knockout_slots_stay_tbd_without_draw():
    """Finished groups alone must not fill slots: no draw means every slot is TBD."""
    import knockout

    standings = {g: _group_rows(g) for g in "EFGH"}
    stage = knockout.build_stage(standings, _finished_fixtures("EFGH"))

    assert stage["groups_all_complete"] is True
    assert stage["draw_available"] is False
    assert all(not slot["filled"] for slot in stage["slots"])
    assert {slot["status"] for slot in stage["slots"]} <= {
        knockout.SLOT_PENDING_DRAW,
        knockout.SLOT_EMPTY,
    }
    assert stage["bracket"]["filled_count"] == 0
    assert stage["bracket"]["champion"] is None


def test_knockout_incomplete_group_blocks_seeds():
    """An unfinished group contributes no seeds and its slots stay TBD."""
    import knockout

    standings = {"E": _group_rows("E"), "F": _group_rows("F", played=4)}
    fixtures = {"E": [{"status": "FT"}] * 12, "F": [{"status": "FT"}] * 8 + [{"status": "KO"}] * 4}
    stage = knockout.build_stage(standings, fixtures, draw=[("1E", "2F")])

    assert stage["completion"]["E"]["complete"] is True
    assert stage["completion"]["F"]["complete"] is False
    assert "2F" not in stage["seeds"]
    by_seed = {slot["seed"]: slot for slot in stage["slots"]}
    assert by_seed["1E"]["filled"] is True
    assert by_seed["2F"]["filled"] is False
    assert by_seed["2F"]["status"] == knockout.SLOT_PENDING_GROUP


def test_knockout_bracket_propagation():
    """Recorded results advance round by round; free/premature picks are ignored."""
    import knockout

    standings = {g: _group_rows(g) for g in "EFGH"}
    fixtures = _finished_fixtures("EFGH")
    draw = [("1E", "2F"), ("1F", "2E"), ("1G", "2H"), ("1H", "2G")]
    stage = knockout.build_stage(standings, fixtures, draw=draw)
    bracket = stage["bracket"]

    assert stage["cross_group"] is True
    assert [len(r["matches"]) for r in bracket["rounds"]] == [4, 2, 1]
    assert bracket["filled_count"] == 8
    assert bracket["champion"] is None

    # A premature final result and legacy free 'home'/'away' picks change nothing.
    assert knockout.build_stage(
        standings, fixtures, draw=draw, results={"F1": "e-club-1"}
    )["bracket"]["champion"] is None
    assert knockout.build_stage(
        standings, fixtures, draw=draw, results={"QF1": "home"}
    )["bracket"]["rounds"][0]["matches"][0]["decided"] is False

    results = {
        "QF1": "e-club-1", "QF2": "f-club-1", "QF3": "g-club-1", "QF4": "h-club-1",
        "SF1": "e-club-1", "SF2": "g-club-1", "F1": "e-club-1",
    }
    decided = knockout.build_stage(standings, fixtures, draw=draw, results=results)["bracket"]
    assert decided["complete"] is True
    assert decided["champion"]["slug"] == "e-club-1"


def test_knockout_expands_for_cross_group_field():
    """A larger cross-group field adds slots and rounds instead of dropping clubs."""
    import knockout

    standings = {g: _group_rows(g) for g in "EFGH"}
    fixtures = _finished_fixtures("EFGH")
    draw = [
        (f"{rank}{a}", f"{rank}{b}")
        for rank in range(1, 5)
        for a, b in (("E", "F"), ("G", "H"))
    ]
    stage = knockout.build_stage(standings, fixtures, draw=draw, per_group=4)
    bracket = stage["bracket"]

    assert bracket["slot_count"] == 16
    assert bracket["filled_count"] == 16
    assert [r["key"] for r in bracket["rounds"]] == ["R16", "QF", "SF", "F"]
    assert [len(r["matches"]) for r in bracket["rounds"]] == [8, 4, 2, 1]


def test_knockout_empty_source_keeps_full_bracket():
    """Missing standings/draw must not collapse the bracket into a lone final."""
    import knockout

    stage = knockout.build_stage({}, {})
    bracket = stage["bracket"]

    assert stage["has_standings"] is False
    assert stage["draw_available"] is False
    assert bracket["slot_count"] == 8
    assert bracket["filled_count"] == 0
    assert [r["key"] for r in bracket["rounds"]] == ["QF", "SF", "F"]
    assert [len(r["matches"]) for r in bracket["rounds"]] == [4, 2, 1]
    # Every reserved place stays a labelled TBD slot, never a projected club.
    assert [slot["seed"] for slot in stage["slots"]] == [
        "1E", "2E", "1F", "2F", "1G", "2G", "1H", "2H"
    ]
    assert all(slot["name"] == knockout.TBD_LABEL for slot in stage["slots"])
    assert all(not slot["filled"] for slot in stage["slots"])


def test_knockout_partial_data_never_shrinks_below_format():
    """A partial draw/group set still reserves the full East-zone field."""
    import knockout

    standings = {"E": _group_rows("E")}
    fixtures = {"E": [{"status": "FT"}] * 12}
    stage = knockout.build_stage(standings, fixtures, draw=[("1E", "2F"), ("1F", "2E")])
    bracket = stage["bracket"]

    assert bracket["slot_count"] >= 8
    assert [r["key"] for r in bracket["rounds"]] == ["QF", "SF", "F"]
    # Both drawn seeds from the finished group E are filled; group F stays TBD.
    assert bracket["filled_count"] == 2
    by_seed = {slot["seed"]: slot for slot in stage["slots"]}
    assert by_seed["1E"]["filled"] is True
    assert by_seed["2E"]["filled"] is True
    assert by_seed["1F"]["status"] == knockout.SLOT_PENDING_GROUP
    assert by_seed["2F"]["status"] == knockout.SLOT_PENDING_GROUP
    assert stage["cross_group"] is False


def test_knockout_wider_cross_group_field_expands_to_r32():
    """More feeding groups expand slots/rounds rather than dropping contestants."""
    import knockout

    letters = "ABCDEFGH"
    standings = {g: _group_rows(g) for g in letters}
    fixtures = _finished_fixtures(letters)
    stage = knockout.build_stage(standings, fixtures, per_group=4)
    bracket = stage["bracket"]

    assert bracket["slot_count"] == 32
    assert [r["key"] for r in bracket["rounds"]] == ["R32", "R16", "QF", "SF", "F"]
    assert [len(r["matches"]) for r in bracket["rounds"]] == [16, 8, 4, 2, 1]
    # No draw published yet: the larger bracket is still entirely TBD.
    assert bracket["filled_count"] == 0
    assert stage["pending_draw_count"] == 32


def test_knockout_accepts_groups_a_to_h():
    """Groups A–D stay TBD until data exists, then join and widen the bracket."""
    import knockout

    east_only = knockout.build_stage({g: _group_rows(g) for g in "EFGH"}, _finished_fixtures("EFGH"))
    assert east_only["groups"] == ["E", "F", "G", "H"]
    assert east_only["bracket"]["slot_count"] == 8

    full = knockout.build_stage(
        {g: _group_rows(g) for g in "ABCDEFGH"}, _finished_fixtures("ABCDEFGH")
    )
    assert full["groups"] == list("ABCDEFGH")
    assert full["bracket"]["slot_count"] == 16
    assert [r["key"] for r in full["bracket"]["rounds"]] == ["R16", "QF", "SF", "F"]
    # Draw pairing a west-group seed with an east-group seed fills both slots.
    paired = knockout.build_stage(
        {g: _group_rows(g) for g in "ABCDEFGH"},
        _finished_fixtures("ABCDEFGH"),
        draw=[("1A", "2E"), ("1E", "2A")],
    )
    assert paired["cross_group"] is True
    by_seed = {slot["seed"]: slot for slot in paired["slots"]}
    assert by_seed["1A"]["filled"] is True
    assert by_seed["2E"]["filled"] is True

    # Unknown group letters are ignored instead of creating stray slots.
    odd = knockout.build_stage({"E": _group_rows("E"), "Z": _group_rows("Z")})
    assert "Z" not in odd["groups"]
    assert all(slot["seed"][-1] in "ABCDEFGH" for slot in odd["slots"] if slot["seed"])


# --- Contextual scenario modelling -----------------------------------------


def _context_fixtures():
    """Two strong home wins and two weak away defeats for 'persib'."""
    return [
        {"status": "FT", "home_slug": "persib", "away_slug": "seoul",
         "home_goals": 3, "away_goals": 0, "iso_utc": "2026-09-01T10:00:00Z"},
        {"status": "FT", "home_slug": "persib", "away_slug": "kitchee",
         "home_goals": 2, "away_goals": 0, "iso_utc": "2026-09-08T10:00:00Z"},
        {"status": "FT", "home_slug": "seoul", "away_slug": "persib",
         "home_goals": 2, "away_goals": 1, "iso_utc": "2026-09-15T10:00:00Z"},
        {"status": "FT", "home_slug": "kitchee", "away_slug": "persib",
         "home_goals": 3, "away_goals": 0, "iso_utc": "2026-09-22T10:00:00Z"},
        {"status": "NS", "home_slug": "persib", "away_slug": "seoul",
         "home_goals": None, "away_goals": None, "iso_utc": "2026-10-01T10:00:00Z"},
    ]


def test_venue_and_h2h_aggregates_use_finished_matches_only():
    fixtures = _context_fixtures()

    home = metrics.venue_record(fixtures, "persib", "home")
    away = metrics.venue_record(fixtures, "persib", "away")
    assert home["played"] == 2 and home["points"] == 6
    assert away["played"] == 2 and away["points"] == 0
    assert home["rate_for"] == 2.5 and away["rate_for"] == 0.5

    h2h = metrics.head_to_head_record(fixtures, "persib", "seoul")
    assert h2h["played"] == 2 and h2h["points"] == 3
    # Unplayed fixture excluded, unknown opponent yields an empty sample.
    assert metrics.club_form(fixtures, "persib")["played"] == 4
    assert metrics.head_to_head_record(fixtures, "persib", "unknown")["played"] == 0
    assert metrics.head_to_head_record(fixtures, "persib", None)["played"] == 0


def test_contextual_baseline_differs_by_venue_and_falls_back():
    fixtures = _context_fixtures()
    base = {"played": 4, "goals_for": 6, "goals_against": 5}

    home = metrics.contextual_goal_baseline(base, fixtures, "persib", "home", "seoul")
    away = metrics.contextual_goal_baseline(base, fixtures, "persib", "away", "seoul")
    assert home["source"] == "contextual"
    assert home["components"] == ["venue", "form", "h2h"]
    assert home["samples"] == {"venue": 2, "form": 4, "h2h": 2}
    # Strong home form must not be flattened into the away projection.
    assert home["rate_for"] > away["rate_for"]
    assert home["rate_against"] < away["rate_against"]

    # No fixtures at all degrades to the plain season average.
    plain = metrics.contextual_goal_baseline(base, [], "persib", "home", "seoul")
    assert plain["source"] == "average" and plain["components"] == []
    assert (plain["goals_for"], plain["goals_against"]) == (
        metrics.goal_baseline(base)["goals_for"],
        metrics.goal_baseline(base)["goals_against"],
    )
    # Missing standings and malformed fixture rows never raise.
    assert metrics.contextual_goal_baseline({}, fixtures, "persib", "home", None)["goals_for"] >= 0
    assert metrics.contextual_goal_baseline(base, [{"status": "FT"}], "persib", "home", None)


def test_contextual_baseline_is_shrunk_and_bounded():
    base = {"played": 10, "goals_for": 20, "goals_against": 10}
    # One extreme home match must not fully replace a ten-match season average.
    single = [{"status": "FT", "home_slug": "persib", "away_slug": "seoul",
               "home_goals": 9, "away_goals": 0}]
    blended = metrics.contextual_goal_baseline(base, single, "persib", "home", "seoul")
    assert blended["rate_for"] < 4.0
    assert 0 <= blended["goals_for"] <= 6 and 0 <= blended["goals_against"] <= 6

    scenario = metrics.simulate_scenario(base, "win", model_goals=True, baseline=blended)
    assert scenario["scenario_goals"]["source"] == "contextual"
    assert scenario["scenario_goals"]["components"] == ["venue", "form", "h2h"]
    # Manual goals still win over the contextual projection.
    manual = metrics.simulate_scenario(base, "win", 5, 0, model_goals=True, baseline=blended)
    assert manual["scenario_goals"]["source"] == "manual"
    assert manual["scenario_goals"]["for"] == 5


# --- Merged fixture listing ------------------------------------------------


def _listing_groups():
    """Out-of-order fixtures across groups, including missing/broken dates."""
    rows = [
        {"group": "F", "status": "KO", "home": "B", "away": "C",
         "iso_utc": "2026-09-20T10:00:00Z"},
        {"group": "E", "status": "FT", "home": "A", "away": "D",
         "iso_utc": "2026-09-01T10:00:00Z"},
        {"group": "G", "status": "KO", "home": "X", "away": "Y",
         "date_venue": "2026-09-05", "time_venue": "12:00:00"},
        {"group": "H", "status": "KO", "home": "N", "away": "M"},
        {"group": "E", "status": "KO", "home": "Q", "away": "R",
         "date_venue": "tanggal-rusak"},
    ]
    return [
        {"group": letter, "name": letter,
         "fixtures": [row for row in rows if row["group"] == letter]}
        for letter in "EFGH"
    ]


def test_merge_fixtures_is_chronological_with_safe_fallback():
    merged = metrics.merge_fixtures(_listing_groups())

    # Dated matches come first in kickoff order, across group boundaries.
    assert [row["home"] for row in merged[:3]] == ["A", "X", "B"]
    # Missing/unparseable dates sink to the end instead of jumping to the top.
    assert all(metrics.fixture_sort_key(row)[0] == 1 for row in merged[3:])
    assert {row["home"] for row in merged[3:]} == {"N", "Q"}
    # Group letter is preserved so the combined list can label each match.
    assert [row["group"] for row in merged[:3]] == ["E", "G", "F"]
    # Empty input and malformed rows never raise.
    assert metrics.merge_fixtures([]) == []
    assert metrics.merge_fixtures([{"group": "E", "fixtures": [{}]}])[0]["group"] == "E"


def test_fixture_status_filter_covers_both_modes():
    merged = metrics.merge_fixtures(_listing_groups())
    single = _listing_groups()[0]["fixtures"]  # group E only

    assert len(metrics.filter_fixtures(merged, "played")) == 1
    assert len(metrics.filter_fixtures(merged, "upcoming")) == 4
    assert len(metrics.filter_fixtures(merged, "all")) == 5
    # Unknown filter and empty input degrade safely.
    assert len(metrics.filter_fixtures(merged, "bogus")) == 5
    assert metrics.filter_fixtures(None, "played") == []

    assert [row["home"] for row in metrics.filter_fixtures(single, "played")] == ["A"]
    assert [row["home"] for row in metrics.filter_fixtures(single, "upcoming")] == ["Q"]
    assert metrics.is_played({"status": "ft"}) is True
    assert metrics.is_played({"status": "KO"}) is False
    assert metrics.is_played({}) is False


# --- Club directory group support ------------------------------------------


def test_clubs_grouped_supports_a_to_h_and_skips_empty(monkeypatch):
    import database

    rows = [
        {"id": 1, "name": "Alpha", "group_name": "a"},
        {"id": 2, "name": "Bravo", "group_name": "D"},
        {"id": 3, "name": "Echo", "group_name": "E"},
        {"id": 4, "name": "Stray", "group_name": "Z"},
        {"id": 5, "name": "NoGroup", "group_name": None},
    ]
    monkeypatch.setattr(database, "get_all_clubs", lambda: rows)

    grouped = database.get_clubs_grouped()
    # Groups A–D are supported, letters normalized, empty groups omitted.
    assert list(grouped) == ["A", "D", "E"]
    assert [club["name"] for club in grouped["A"]] == ["Alpha"]
    assert "Z" not in grouped and "" not in grouped
    assert all(grouped.values())

    monkeypatch.setattr(database, "get_all_clubs", lambda: [])
    assert database.get_clubs_grouped() == {}


def test_newly_seeded_clubs_resolve_by_database_name(monkeypatch):
    import data_sources as ds

    clubs = [
        {"name": "Al Wahda FC", "slug": "al-wahda-fc"},
        {"name": "East Bengal FC", "slug": "east-bengal-fc"},
    ]
    monkeypatch.setattr(ds, "get_clubs", lambda: clubs)
    monkeypatch.setattr(ds, "_slug_cache", None)
    monkeypatch.setattr(ds, "_name_slug_cache", None)
    monkeypatch.setattr(ds, "TEAM_SLUG_MAP", {})

    # Clubs seeded later resolve without a hand-written alias entry.
    assert ds.get_club_slug(None, "Al Wahda FC") == "al-wahda-fc"
    assert ds.get_club_slug(None, "east bengal fc") == "east-bengal-fc"
    assert ds.get_club_slug("al-wahda-fc", None) == "al-wahda-fc"
    # Unknown teams still degrade to an empty slug (plain text in templates).
    assert ds.get_club_slug(None, "Tim Tidak Dikenal") == ""
    assert ds.get_club_slug(None, None) == ""


def test_fixture_filter_labels_are_consistent_english():
    assert metrics.FIXTURE_FILTERS == ("all", "played", "upcoming")
    assert [metrics.FIXTURE_FILTER_LABELS[key] for key in metrics.FIXTURE_FILTERS] == [
        "All",
        "Played",
        "Upcoming",
    ]


# --- Data source resilience ------------------------------------------------


def test_data_source_retry_stale_and_snapshot_layers(monkeypatch):
    import data_sources as ds

    monkeypatch.setattr(ds, "RETRY_BACKOFF_SECONDS", 0)
    monkeypatch.setattr(ds, "_cache", {})
    monkeypatch.setattr(ds, "_last_good", {})
    monkeypatch.setattr(ds, "_source_status", {})

    calls = {"n": 0}

    def live(url):
        calls["n"] += 1
        return [{"id": calls["n"]}]

    monkeypatch.setattr(ds, "_fetch_json", live)
    assert ds._fetch_with_cache("u", "fixtures") == [{"id": 1}]
    assert ds.get_data_status()["fixtures"] == "live"
    # Fresh cache hit does not touch the network.
    ds._fetch_with_cache("u", "fixtures")
    assert calls["n"] == 1

    # Transient failure is retried and recovers within the same request.
    attempts = {"n": 0}

    def flaky(url):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise OSError("timeout")
        return [{"id": 99}]

    monkeypatch.setattr(ds, "_cache", {})
    monkeypatch.setattr(ds, "_fetch_json", flaky)
    assert ds._fetch_with_cache("u", "fixtures") == [{"id": 99}]
    assert attempts["n"] == 2
    assert ds.get_data_status()["fixtures"] == "live"

    # Outage after a good fetch serves the last known payload as 'stale'.
    monkeypatch.setattr(ds, "_fetch_json", lambda url: (_ for _ in ()).throw(OSError("down")))
    monkeypatch.setattr(ds, "_cache", {})
    assert ds._fetch_with_cache("u", "fixtures") == [{"id": 99}]
    assert ds.get_data_status()["fixtures"] == "stale"

    # Without a last-good payload the bundled snapshot is used.
    monkeypatch.setattr(ds, "_last_good", {})
    monkeypatch.setattr(ds, "_cache", {})
    snapshot_rows = ds._fetch_with_cache(ds.FIXTURES_API, "fixtures")
    assert ds.get_data_status()["fixtures"] in ("snapshot", "empty")
    assert isinstance(snapshot_rows, list)

    # A well-formed but empty response counts as an outage, not as live data.
    monkeypatch.setattr(ds, "_fetch_json", lambda url: [])
    monkeypatch.setattr(ds, "_cache", {})
    ds._fetch_with_cache(ds.FIXTURES_API, "fixtures")
    assert ds.get_data_status()["fixtures"] != "live"
