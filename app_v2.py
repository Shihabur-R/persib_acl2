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
import knockout as knockout_stage
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
VENUES = ("home", "away")
VENUE_LABELS = {"home": "Kandang", "away": "Tandang"}
GOAL_SOURCE_LABELS = {
    "manual": "input manual",
    "average": "rata-rata musim",
    "mixed": "sebagian manual, sebagian turunan",
    "contextual": "konteks kandang/tandang, form & head-to-head",
}


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
    return {
        "season": data_sources.get_season_context(),
        "source_url": data_sources.SOURCE_URL,
        "GOAL_SOURCE_LABELS": GOAL_SOURCE_LABELS,
    }


@app.errorhandler(404)
def not_found(error):
    """Friendly 404 page instead of the raw Werkzeug default."""
    return render_template("error.html", code=404, message=getattr(error, "description", "Halaman tidak ditemukan.")), 404


@app.errorhandler(503)
def unavailable(error):
    """Friendly page when the local dataset cannot be read."""
    return render_template("error.html", code=503, message=getattr(error, "description", "Data sementara tidak tersedia.")), 503


def _select_group(
    groups: list[dict], requested: str | None, allow_all: bool = False
) -> tuple[list[str], str, list[dict]]:
    """
    Resolve the group filter shared by Home and Fixtures.

    Returns (available letters, active letter, groups to render). A single group is
    rendered by default so the page stays short. ``allow_all`` (Fixtures only) lets
    ?group=all render every group at once.
    """
    letters = [group["name"] for group in groups]
    if not letters:
        return [], "", []
    active = (requested or "").strip().upper()
    if allow_all and active == "ALL":
        return letters, "ALL", groups
    if active not in letters:
        active = letters[0]
    selected = [group for group in groups if group["name"] == active]
    return letters, active, selected


@app.route("/")
def home():
    """Landing dashboard showing one group at a time."""
    clubs = data_sources.get_clubs()
    db_stats = data_sources.get_database_stats()
    season = data_sources.get_season_context()
    letters, active, selected = _select_group(
        data_sources.load_dashboard_groups(), request.args.get("group")
    )
    return render_template(
        "index.html",
        clubs=clubs,
        db_stats=db_stats,
        season=season,
        groups=selected,
        group_letters=letters,
        active_group=active,
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

    # Match context: venue and opponent let the projection use home/away form
    # and head-to-head evidence instead of a plain season average.
    venue = values.get("venue", "home")
    if venue not in VENUES:
        venue = "home"
    opponents = [
        club for club in clubs
        if club["slug"] != selected_club["slug"]
        and club.get("group_name") == selected_club.get("group_name")
    ]
    opponent_slug = values.get("opponent", "")
    if opponent_slug not in {club["slug"] for club in opponents}:
        opponent_slug = opponents[0]["slug"] if opponents else ""

    context = metrics.contextual_goal_baseline(
        base or {},
        fixtures=_group_fixtures(selected_club.get("group_name", "")),
        club_slug=selected_club["slug"],
        venue=venue,
        opponent=opponent_slug,
    )

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
        # Goal inputs are optional; blank values use the contextual baseline.
        goals_a = (values.get("gf_a", ""), values.get("ga_a", ""))
        goals_b = (values.get("gf_b", ""), values.get("ga_b", ""))
        scenario_a = metrics.simulate_scenario(
            baseline, result_a, goals_a[0], goals_a[1], model_goals=True, baseline=context
        )
        scenario_b = metrics.simulate_scenario(
            baseline, result_b, goals_b[0], goals_b[1], model_goals=True, baseline=context
        )
        scenario_result = {
            "scenario_a": scenario_a,
            "scenario_b": scenario_b,
            "verdict": metrics.compare_scenarios(scenario_a, scenario_b),
            "result_a": result_a,
            "result_b": result_b,
            "label_a": RESULT_LABELS[result_a],
            "label_b": RESULT_LABELS[result_b],
            "baseline_used": base is not None,
            "goals_a": goals_a,
            "goals_b": goals_b,
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
        goal_baseline=context,
        goal_inputs={
            "gf_a": values.get("gf_a", ""), "ga_a": values.get("ga_a", ""),
            "gf_b": values.get("gf_b", ""), "ga_b": values.get("ga_b", ""),
        },
        venues=VENUES,
        venue_labels=VENUE_LABELS,
        selected_venue=venue,
        opponents=opponents,
        selected_opponent=opponent_slug,
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


@app.route("/knockout", methods=["GET"])
def knockout():
    """
    Bagan babak gugur yang mengikuti status penyelesaian grup & hasil undian.

    Read-only: tidak ada input manual klub maupun pemenang. Slot hanya terisi
    bila grup terkait selesai dan undian menempatkan seed tersebut; sisanya TBD.
    Jumlah slot/babak menyesuaikan banyaknya kontestan lintas grup.
    """
    standings_by_group = {
        group["group"]: group["standings"] for group in data_sources.load_standings()
    }
    fixtures_by_group = {
        group["group"]: group["fixtures"] for group in data_sources.load_fixtures()
    }
    draw = data_sources.load_knockout_draw()
    results = data_sources.load_knockout_results()
    stage = knockout_stage.build_stage(
        standings_by_group,
        fixtures_by_group,
        draw=draw,
        results=results,
    )
    return render_template(
        "knockout.html",
        stage=stage,
        slots=stage["slots"],
        bracket=stage["bracket"],
        completion=stage["completion"],
    )


@app.route("/insights")
def insights():
    """Temuan statistik: distribusi posisi per klub & perbandingan Grup E."""
    clubs = data_sources.get_clubs()
    composition = metrics.composition_by_club(clubs, data_sources.get_players())
    # Dropdown lists groups that actually have standings (A–H are all accepted).
    available = [
        group["group"] for group in data_sources.load_standings()
        if group["group"] in data_sources.SUPPORTED_GROUPS
    ] or list(data_sources.GROUP_NAMES)
    group_letter = request.args.get("group", available[0]).strip().upper()
    if group_letter not in data_sources.SUPPORTED_GROUPS:
        group_letter = available[0]
    comparison = metrics.group_comparison_table(_group_standings(group_letter))
    return render_template(
        "insights.html",
        composition=composition,
        comparison=comparison,
        group_letter=group_letter,
        groups=available,
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
    """
    Fixtures for one group, or a merged chronological list when 'All' is chosen.

    The status filter (all/played/upcoming) applies to both modes.
    """
    letters, active, selected = _select_group(
        data_sources.load_fixtures(), request.args.get("group"), allow_all=True
    )
    status = (request.args.get("status") or "all").strip().lower()
    if status not in metrics.FIXTURE_FILTERS:
        status = "all"

    merged = active == "ALL"
    if merged:
        matches = metrics.filter_fixtures(metrics.merge_fixtures(selected), status)
        groups_view = []
    else:
        matches = []
        groups_view = [
            dict(group, fixtures=metrics.filter_fixtures(group.get("fixtures") or [], status))
            for group in selected
        ]
    return render_template(
        "fixtures.html",
        groups=groups_view,
        matches=matches,
        merged=merged,
        group_letters=letters,
        active_group=active,
        status_filter=status,
        status_filters=metrics.FIXTURE_FILTERS,
        status_labels=metrics.FIXTURE_FILTER_LABELS,
        total_matches=len(matches) + sum(len(g["fixtures"]) for g in groups_view),
    )


@app.route("/clubs")
def clubs():
    """Club directory for one group, or every populated group when 'All'."""
    grouped_clubs = database.get_clubs_grouped()
    letters = list(grouped_clubs)
    requested = (request.args.get("group") or "all").strip().upper()
    if requested != "ALL" and requested not in letters:
        requested = "ALL"
    visible = (
        grouped_clubs
        if requested == "ALL"
        else {letter: grouped_clubs[letter] for letter in letters if letter == requested}
    )
    db_stats = data_sources.get_database_stats()
    return render_template(
        "clubs.html",
        grouped_clubs=visible,
        group_letters=letters,
        active_group=requested,
        db_stats=db_stats,
    )


@app.route("/players")
def players():
    """Compatibility route: render player directory."""
    q = request.args.get("q", "").strip()
    group_filter = request.args.get("group", "").strip().upper()
    pos_filter = request.args.get("pos", "").strip().upper()
    club_filter = request.args.get("club", type=int)
    player_list = database.search_players(
        query=q if q else None,
        group_name=group_filter if group_filter in database.SUPPORTED_GROUPS else None,
        position=pos_filter if pos_filter in ("GK", "DF", "MF", "FW") else None,
        club_id=club_filter,
    )
    all_clubs = database.get_all_clubs()
    letters = sorted(
        {
            (club.get("group_name") or "").strip().upper()
            for club in all_clubs
        }
        & set(database.SUPPORTED_GROUPS)
    )
    return render_template(
        "players.html",
        players=player_list,
        all_clubs=all_clubs,
        group_letters=letters,
        current_q=q,
        current_group=group_filter,
        current_pos=pos_filter,
        current_club=club_filter,
    )


if __name__ == "__main__":
    app.run(debug=True)
