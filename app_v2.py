"""
PERSIB Simetris — Mana yang Paling...

A modular Flask application built on top of the existing persib_acl2 data.

Routes
------
/          Dashboard with live standings, fixtures, and a compact Balance preview.
/balance   Fitur 1: Balance Meter (squad, home/away, and head-to-head modes).
/duel      Fitur 2: Scenario Duel (two scenarios side by side).
/picks     Fitur 4: Saved Pick (create, list, and delete saved comparisons).

All UI strings use Indonesian labels; code comments and identifiers use English
for international maintainability.
"""

from __future__ import annotations

from flask import Flask, abort, flash, redirect, render_template, request, url_for

import database
import data_sources
import metrics
import picks_store

app = Flask(__name__)
app.secret_key = "change-me-in-production"  # Required for flash messages only.

# Ensure the saved-picks table exists on first import.
picks_store.init_table()


def _clubs_by_slug() -> dict[str, dict]:
    """Return a slug -> club mapping for quick lookups."""
    return {club["slug"]: club for club in data_sources.get_clubs()}


def _group_standings(letter: str) -> list[dict]:
    """Return standings rows for one group letter."""
    for group in data_sources.load_standings():
        if group["group"] == letter:
            return group["standings"]
    return []


def _group_fixtures(letter: str) -> list[dict]:
    """Return fixtures rows for one group letter."""
    for group in data_sources.load_fixtures():
        if group["group"] == letter:
            return group["fixtures"]
    return []


@app.route("/")
def home():
    """Landing dashboard with compact stats and quick navigation."""
    clubs = data_sources.get_clubs()
    db_stats = data_sources.get_database_stats()
    season = data_sources.get_season_context()
    return render_template(
        "index.html",
        clubs=clubs,
        db_stats=db_stats,
        season=season,
    )


@app.route("/balance", methods=["GET"])
def balance():
    """Fitur 1: Balance Meter with three selectable comparison modes."""
    clubs = data_sources.get_clubs()
    mode = request.args.get("mode", "squad")
    club_a_slug = request.args.get("a", "persib-bandung")
    club_b_slug = request.args.get("b", "fc-seoul")

    club_a = next((c for c in clubs if c["slug"] == club_a_slug), clubs[0])
    club_b = next((c for c in clubs if c["slug"] == club_b_slug), clubs[1])

    result: dict = {"mode": mode, "club_a": club_a, "club_b": club_b}

    if mode == "squad":
        players_a = data_sources.get_players(club_a["id"])
        players_b = data_sources.get_players(club_b["id"])
        comp_a = metrics.squad_composition(players_a)
        comp_b = metrics.squad_composition(players_b)
        score = metrics.squad_balance_score(comp_a, comp_b)
        result.update(
            {
                "score": score,
                "label_en": metrics._label_for(score),
                "comp_a": comp_a,
                "comp_b": comp_b,
            }
        )
    elif mode == "home_away":
        fixtures = _group_fixtures(club_a["group_name"])
        split = metrics.home_away_split(fixtures, club_a["slug"])
        result.update({"split": split, "score": split["score"], "label_en": split["label_en"]})
    elif mode == "head_to_head":
        standings = _group_standings(club_a["group_name"])
        h2h = metrics.head_to_head(standings, club_a["name"], club_b["name"])
        result.update(h2h)
    else:
        abort(400, description="Unknown balance mode.")

    return render_template(
        "balance.html",
        clubs=clubs,
        result=result,
        mode=mode,
        selected_a=club_a["slug"],
        selected_b=club_b["slug"],
    )


@app.route("/duel", methods=["GET", "POST"])
def duel():
    """Fitur 2: Scenario Duel comparing two projected match outcomes."""
    clubs = data_sources.get_clubs()
    selected_club_slug = request.form.get("club", "persib-bandung")
    selected_club = next((c for c in clubs if c["slug"] == selected_club_slug), clubs[0])
    standings = _group_standings(selected_club["group_name"])
    base = next((r for r in standings if r["name"] == selected_club["name"]), None)

    scenario_result = None
    if request.method == "POST" and base:
        result_a = request.form.get("result_a", "win")
        result_b = request.form.get("result_b", "draw")
        scenario_a = metrics.simulate_scenario(base, result_a)
        scenario_b = metrics.simulate_scenario(base, result_b)
        verdict = metrics.compare_scenarios(scenario_a, scenario_b)
        scenario_result = {
            "scenario_a": scenario_a,
            "scenario_b": scenario_b,
            "verdict": verdict,
            "result_a": result_a,
            "result_b": result_b,
        }

    return render_template(
        "duel.html",
        clubs=clubs,
        selected_club=selected_club,
        base=base,
        scenario_result=scenario_result,
    )


@app.route("/picks", methods=["GET", "POST"])
def picks():
    """Fitur 4: Saved Pick — create, list, and delete user-saved scenarios."""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        side_a = request.form.get("side_a", "").strip()
        side_b = request.form.get("side_b", "").strip()
        payload = {
            "club": request.form.get("club", ""),
            "result_a": request.form.get("result_a", "win"),
            "result_b": request.form.get("result_b", "draw"),
        }
        try:
            picks_store.save_pick(title, side_a, side_b, payload)
            flash("Pick saved successfully.", "success")
        except picks_store.PickValidationError as exc:
            flash(str(exc), "error")
        return redirect(url_for("picks"))

    saved = picks_store.list_picks()
    clubs = data_sources.get_clubs()
    return render_template("picks.html", saved=saved, clubs=clubs)


@app.route("/picks/<int:pick_id>/delete", methods=["POST"])
def delete_pick(pick_id: int):
    """Delete a saved pick by id."""
    try:
        picks_store.delete_pick(pick_id)
        flash("Pick deleted successfully.", "success")
    except picks_store.PickNotFoundError as exc:
        flash(str(exc), "error")
    return redirect(url_for("picks"))


@app.route("/club/<slug>")
def club_detail(slug):
    """Compatibility route: render one club's squad profile."""
    club = database.get_club_by_slug(slug)
    if not club:
        abort(404, description=f"Club with slug '{slug}' was not found.")
    players = database.get_club_players(club["id"])
    by_position = {
        "GK": [p for p in players if p["position_code"] == "GK"],
        "DF": [p for p in players if p["position_code"] == "DF"],
        "MF": [p for p in players if p["position_code"] == "MF"],
        "FW": [p for p in players if p["position_code"] == "FW"],
    }
    sibling_clubs = [
        c for c in database.get_all_clubs()
        if c["group_name"] == club["group_name"] and c["slug"] != club["slug"]
    ]
    return render_template(
        "club_detail.html",
        club=club,
        players=players,
        by_position=by_position,
        sibling_clubs=sibling_clubs,
    )


@app.route("/fixtures")
def fixtures():
    """Compatibility route: render fixtures from the new data source."""
    groups = data_sources.load_fixtures()
    return render_template("fixtures.html", groups=groups)


@app.route("/clubs")
def clubs():
    """Compatibility route: render clubs from the new data source."""
    grouped_clubs = database.get_clubs_grouped()
    db_stats = data_sources.get_database_stats()
    return render_template("clubs.html", grouped_clubs=grouped_clubs, db_stats=db_stats)


@app.route("/players")
def players():
    """Compatibility route: render player directory."""
    q = request.args.get("q", "").strip()
    group_filter = request.args.get("group", "").strip().upper()
    pos_filter = request.args.get("pos", "").strip().upper()
    club_filter = request.args.get("club", type=int)
    player_list = database.search_players(
        query=q if q else None,
        group_name=group_filter if group_filter in ("E", "F", "G", "H") else None,
        position=pos_filter if pos_filter in ("GK", "DF", "MF", "FW") else None,
        club_id=club_filter,
    )
    all_clubs = database.get_all_clubs()
    return render_template(
        "players.html",
        players=player_list,
        all_clubs=all_clubs,
        current_q=q,
        current_group=group_filter,
        current_pos=pos_filter,
        current_club=club_filter,
    )


if __name__ == "__main__":
    app.run(debug=True)
