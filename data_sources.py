"""
Data access layer for the PERSIB Simetris application.

Responsibilities
----------------
- Load and normalize club/player data from the local SQLite database.
- Fetch live fixtures and standings from the AFC public API with a short TTL cache.
- Fall back to a bundled JSON snapshot when the AFC API is unreachable, so the
  UI never crashes with a raw HTTP 502.

This module intentionally keeps secrets/credentials out of the source tree. The
AFC endpoint is public and requires no API key.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import database

logger = logging.getLogger("persib_simetris.data")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "acl2.db")
SNAPSHOT_PATH = os.path.join(BASE_DIR, "data", "snapshot_east.json")

FIXTURES_API = (
    "https://api.the-afc.com/sportdb-connector/api/v1/fixtures"
    "?competitionCodes=afc-champions-league-two&season=20262027&locale=en"
)
STANDINGS_API = (
    "https://api.the-afc.com/sportdb-connector/api/v1/standings"
    "?competitionCode=afc-champions-league-two&season=20262027&locale=en"
)

GROUP_NAMES = ("E", "F", "G", "H")
CACHE_TTL_SECONDS = 300  # Keep API responses for five minutes.

# In-memory cache: endpoint -> (fetched_epoch, payload)
_cache: dict[str, tuple[float, Any]] = {}


def _get_sqlite_rows(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Open a short-lived SQLite connection and return rows as dictionaries."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Local database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_clubs() -> list[dict[str, Any]]:
    """Return all clubs normalized from the local SQLite database."""
    return _get_sqlite_rows(
        """
        SELECT id, name, official_name, abbreviation, group_name,
               country, country_code, country_flag, city, stadium, coach,
               website, logo_url, local_logo, slug
        FROM clubs
        ORDER BY group_name ASC, name ASC
        """
    )


def get_players(club_id: int | None = None) -> list[dict[str, Any]]:
    """Return player rows, optionally filtered by a club id."""
    sql = "SELECT * FROM players"
    params: tuple = ()
    if club_id is not None:
        sql += " WHERE club_id = ?"
        params = (club_id,)
    sql += " ORDER BY club_id, position_code, jersey_number"
    return _get_sqlite_rows(sql, params)


def _fetch_json(url: str) -> Any:
    """Fetch a JSON payload from the AFC API and validate its shape."""
    request = Request(url, headers={"User-Agent": "PERSIB-Simetris/2.0"})
    with urlopen(request, timeout=15) as response:
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        payload = json.loads(body)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Unexpected AFC API response shape")
    return payload["data"]


def _load_snapshot() -> dict[str, Any]:
    """Load the bundled fallback snapshot from disk."""
    if not os.path.exists(SNAPSHOT_PATH):
        return {"fixtures": [], "standings": []}
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not load fallback snapshot: %s", exc)
        return {"fixtures": [], "standings": []}


def _fetch_with_cache(url: str, snapshot_key: str) -> list[dict[str, Any]]:
    """Return API data with TTL caching and a safe snapshot fallback."""
    now = time.monotonic()
    cached = _cache.get(url)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    try:
        data = _fetch_json(url)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("AFC API failed for %s: %s. Using snapshot fallback.", url, exc)
        data = _load_snapshot().get(snapshot_key, [])
    else:
        _cache[url] = (now, data)
    return data


def load_fixtures() -> list[dict[str, Any]]:
    """Return fixtures normalized for the four East-zone groups."""
    records = _fetch_with_cache(FIXTURES_API, "fixtures")
    normalized: dict[str, list[dict[str, Any]]] = {name: [] for name in GROUP_NAMES}

    for record in records:
        group_label = (record.get("group") or {}).get("name", "")
        if not group_label.startswith("Group "):
            continue
        letter = group_label.removeprefix("Group ")
        if letter not in GROUP_NAMES:
            continue
        normalized[letter].append(_normalize_fixture(record))

    for letter in GROUP_NAMES:
        normalized[letter].sort(
            key=lambda item: (item.get("date_venue") or "", item.get("time_venue") or "")
        )
    return [
        {"group": letter, "fixtures": normalized[letter]}
        for letter in GROUP_NAMES
    ]


def load_standings() -> list[dict[str, Any]]:
    """Return standings normalized for the four East-zone groups."""
    records = _fetch_with_cache(STANDINGS_API, "standings")
    normalized: dict[str, list[dict[str, Any]]] = {name: [] for name in GROUP_NAMES}

    for record in records:
        group_label = record.get("groupName") or ""
        if not group_label.startswith("Group "):
            continue
        letter = group_label.removeprefix("Group ")
        if letter not in GROUP_NAMES:
            continue
        for row in record.get("standings", []):
            normalized[letter].append(_normalize_standing(row, letter))
    for letter in GROUP_NAMES:
        normalized[letter].sort(key=lambda row: row.get("rank", 99))
    return [
        {"group": letter, "standings": normalized[letter]}
        for letter in GROUP_NAMES
    ]


def _normalize_fixture(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize one AFC fixture record into the application shape."""
    home = record.get("homeTeam") or {}
    away = record.get("awayTeam") or {}
    result = record.get("result") or {}
    group_label = (record.get("group") or {}).get("name", "")
    letter = group_label.removeprefix("Group ") if group_label.startswith("Group ") else "?"

    return {
        "date_venue": record.get("dateVenue"),
        "time_venue": record.get("timeVenueUTC"),
        "status": "FT" if record.get("status") == "played" else "KO",
        "group": letter,
        "home": home.get("name", "TBD"),
        "away": away.get("name", "TBD"),
        "home_slug": _safe_slug(home.get("slug")),
        "away_slug": _safe_slug(away.get("slug")),
        "home_abbr": home.get("abbreviation") or "",
        "away_abbr": away.get("abbreviation") or "",
        "home_goals": result.get("homeGoals"),
        "away_goals": result.get("awayGoals"),
    }


def _normalize_standing(row: dict[str, Any], group: str) -> dict[str, Any]:
    """Normalize one AFC standings row."""
    return {
        "group": group,
        "rank": row.get("rank"),
        "name": row.get("name", "TBD"),
        "slug": _safe_slug(row.get("name")),
        "played": row.get("played", 0),
        "won": row.get("won", 0),
        "drawn": row.get("drawn", 0),
        "lost": row.get("lost", 0),
        "goals_for": row.get("goalsFor", 0),
        "goals_against": row.get("goalsAgainst", 0),
        "points": row.get("points", 0),
    }


def _safe_slug(value: Any) -> str:
    """Return a string slug or empty string when the value is missing."""
    return str(value).strip() if value else ""


def get_database_stats() -> dict[str, Any]:
    """Expose small cardinality stats for footer/badges."""
    return database.get_database_stats()


def get_season_context() -> dict[str, Any]:
    """Return a small context object used across templates."""
    return {
        "season": "2026/2027",
        "competition": "AFC Champions League Two",
        "zone": "East Zone (Group E–H)",
        "source_label": "AFC Public API with local snapshot fallback",
    }
