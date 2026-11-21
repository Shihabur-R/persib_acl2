"""
ACL2 Analytics & Simulation

A modular Flask application built on top of the existing persib_acl2 data.

Routes
------
/          Dashboard with live standings, fixtures, and a compact Balance preview.
/balance   Fitur 1: Balance Meter (squad, home/away, and head-to-head modes).
/duel      Fitur 2: Scenario Duel (two scenarios side by side).
/picks     Fitur 4: Saved Pick (create, list, and delete saved comparisons).
/insights  Statistical findings and dataset limitations.

All UI strings use Indonesian labels; code comments and identifiers use English
for international maintainability.
"""

from __future__ import annotations

import logging
import os

from flask import Flask, abort, flash, redirect, render_template, request, url_for

import database
import data_sources
import metrics
import picks_store

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
# Read the secret from the environment; the fallback is only for local development.
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")

# Ensure the saved-picks table exists on first import.
picks_store.init_table()

BALANCE_MODES = ("squad", "home_away", "head_to_head")
DUEL_RESULTS = ("win", "draw", "loss")
RESULT_LABELS = {"win": "Menang", "draw": "Seri", "loss": "Kalah"}


def _clubs_by_slug() -> dict[str, dict]:
    """Return a slug -> club mapping for quick lookups."""
    return {club["slug"]: club for club in data_sources.get_clubs()}


def _pick_club(clubs: list[dict], slug: str | None, fallback_index: int = 0) -> dict:
    """
    Resolve a club from a user-supplied slug.

    Falls back to a valid club instead of raising IndexError when the database
    is empty or the slug is unknown, so malformed query strings cannot 500.
    """
    if not clubs:
        abort(503, description="Data klub tidak tersedia.")
    by_slug = {club["slug"]: club for club in clubs}
    if slug and slug in by_slug:
        return by_slug[slug]
    return clubs[min(fallback_index, len(clubs) - 1)]


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


def _base_standing(club: dict) -> dict | None:
    """Find a club's current standing row by slug or canonical name."""
    for row in _group_standings(club["group_name"]):
        if row.get("slug") == club["slug"] or row.get("name") == club["name"]:
            return row
    return None


@app.context_processor
def inject_globals():
    """Expose season/source metadata to every template (legacy footer links)."""
    return {"season": data_sources.get_season_context(), "source_url": data_sources.SOURCE_URL}


@app.errorhandler(404)
def not_found(error):
    """Friendly 404 page instead of the raw Werkzeug default."""
    return render_template("error.html", code=404, message=getattr(error, "description", "Halaman tidak ditemukan.")), 404


@app.errorhandler(503)
def unavailable(error):
    """Friendly page when the local dataset cannot be read."""
    return render_template("error.html", code=503, message=getattr(error, "description", "Data sementara tidak tersedia.")), 503


@app.route("/")
def home():
    """Landing dashboard with compact stats and quick navigation."""
    clubs = data_sources.get_clubs()
    db_stats = data_sources.get_database_stats()
    season = data_sources.get_season_context()
    groups = data_sources.load_dashboard_groups()
    return render_template(
        "index.html",
        clubs=clubs,
        db_stats=db_stats,
        season=season,
        groups=groups,
    )


@app.route("/balance", methods=["GET"])
def balance():
    """Fitur 1: Balance Meter with three selectable comparison modes."""
    clubs = data_sources.get_clubs()
    mode = request.args.get("mode", "squad")
    if mode not in BALANCE_MODES:
        # Unknown modes fall back to the default instead of a hard 400.
        mode = "squad"

    club_a = _pick_club(clubs, request.args.get("a", "persib-bandung"), 0)
    club_b = _pick_club(clubs, request.args.get("b", "fc-seoul"), 1)

    result: dict = {
        "mode": mode,
        "club_a": club_a,
        "club_b": club_b,
        "has_data": True,
        "note": None,
    }

    if mode == "squad":
        comp_a = metrics.squad_composition(data_sources.get_players(club_a["id"]))
        comp_b = metrics.squad_composition(data_sources.get_players(club_b["id"]))
        score = metrics.squad_balance_score(comp_a, comp_b)
        has_data = bool(sum(comp_a.values()) and sum(comp_b.values()))
        result.update(
            {
                "score": score,
                "label_en": metrics._label_for(score),
                "label_id": metrics.label_id(score),
                "comp_a": comp_a,
                "comp_b": comp_b,
                "has_data": has_data,
                "note": None if has_data else "Salah satu klub belum memiliki data skuad; skor netral 50 ditampilkan.",
            }
        )
    elif mode == "home_away":
        split = metrics.home_away_split(_group_fixtures(club_a["group_name"]), club_a["slug"])
        result.update(
            {
                "split": split,
                "score": split["score"],
                "label_en": split["label_en"],
                "label_id": split["label_id"],
                "has_data": split["has_data"],
                "note": None if split["has_data"] else "Belum ada laga kandang & tandang yang selesai untuk klub ini; skor netral 50 ditampilkan.",
            }
        )
    else:  # head_to_head
        standings = _group_standings(club_a["group_name"])
        h2h = metrics.head_to_head(standings, club_a["slug"], club_b["slug"])
        result.update(h2h)
        if club_a["group_name"] != club_b["group_name"]:
            result["note"] = "Kedua klub berbeda grup; pilih klub dalam grup yang sama untuk membandingkan klasemen."

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
    values = request.form if request.method == "POST" else request.args
    selected_club = _pick_club(clubs, values.get("club", "persib-bandung"), 0)
    base = _base_standing(selected_club)

    result_a = values.get("result_a", "win")
    result_b = values.get("result_b", "draw")
    if result_a not in DUEL_RESULTS:
        result_a = "win"
    if result_b not in DUEL_RESULTS:
        result_b = "draw"

    scenario_result = None
    note = None
    if base is None:
        note = "Klasemen klub ini belum tersedia; proyeksi dimulai dari rekor 0 laga."
    if request.method == "POST":
        # Project from an empty record when standings are unavailable so the
        # feature still demonstrates the points/ratio maths.
        baseline = base or {
            "played": 0, "won": 0, "drawn": 0, "lost": 0,
            "points": 0, "goals_for": 0, "goals_against": 0,
        }
        scenario_a = metrics.simulate_scenario(baseline, result_a)
        scenario_b = metrics.simulate_scenario(baseline, result_b)
        scenario_result = {
            "scenario_a": scenario_a,
            "scenario_b": scenario_b,
            "verdict": metrics.compare_scenarios(scenario_a, scenario_b),
            "result_a": result_a,
            "result_b": result_b,
            "label_a": RESULT_LABELS[result_a],
            "label_b": RESULT_LABELS[result_b],
            "baseline_used": base is not None,
        }

    return render_template(
        "duel.html",
        clubs=clubs,
        selected_club=selected_club,
        base=base,
        scenario_result=scenario_result,
        result_a=result_a,
        result_b=result_b,
        results=DUEL_RESULTS,
        result_labels=RESULT_LABELS,
        note=note,
    )


@app.route("/picks", methods=["GET", "POST"])
def picks():
    """Fitur 4: Saved Pick — create, list, and delete user-saved scenarios."""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        side_a = request.form.get("side_a", "").strip()
        side_b = request.form.get("side_b", "").strip()
        mode = request.form.get("mode", "duel")
        payload = {
            "club": request.form.get("club", ""),
            "result_a": request.form.get("result_a", "win"),
            "result_b": request.form.get("result_b", "draw"),
        }
        try:
            picks_store.save_pick(title, side_a, side_b, payload, mode=mode)
            flash("Pick berhasil disimpan.", "success")
        except picks_store.PickValidationError as exc:
            flash(str(exc), "error")
        return redirect(url_for("picks"))

    saved = picks_store.list_picks()
    clubs = data_sources.get_clubs()
    # Prefill support: /picks?club=...&result_a=...&result_b=... from a duel.
    prefill = {
        "club": request.args.get("club", ""),
        "result_a": request.args.get("result_a", ""),
        "result_b": request.args.get("result_b", ""),
    }
    return render_template(
        "picks.html",
        saved=saved,
        clubs=clubs,
        prefill=prefill,
        results=DUEL_RESULTS,
        result_labels=RESULT_LABELS,
    )


@app.route("/picks/<int:pick_id>/delete", methods=["POST"])
def delete_pick(pick_id: int):
    """Delete a saved pick by id."""
    try:
        picks_store.delete_pick(pick_id)
        flash("Pick berhasil dihapus.", "success")
    except picks_store.PickNotFoundError:
        flash("Pick tidak ditemukan atau sudah dihapus.", "error")
    return redirect(url_for("picks"))


@app.route("/insights")
def insights():
    """Temuan statistik: distribusi posisi per klub & perbandingan Grup E."""
    clubs = data_sources.get_clubs()
    composition = metrics.composition_by_club(clubs, data_sources.get_players())
    group_letter = request.args.get("group", "E").strip().upper()
    if group_letter not in data_sources.GROUP_NAMES:
        group_letter = "E"
    comparison = metrics.group_comparison_table(_group_standings(group_letter))
    return render_template(
        "insights.html",
        composition=composition,
        comparison=comparison,
        group_letter=group_letter,
        groups=data_sources.GROUP_NAMES,
        positions=metrics.POSITIONS,
        db_stats=data_sources.get_database_stats(),
    )


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
