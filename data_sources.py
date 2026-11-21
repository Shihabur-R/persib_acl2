"""
Data access layer for the ACL2 Analytics & Simulation application.

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

try:
    from zoneinfo import ZoneInfo

    DEFAULT_TIMEZONE = ZoneInfo("Asia/Jakarta")
except Exception:  # pragma: no cover - system tz database may be absent
    DEFAULT_TIMEZONE = timezone(timedelta(hours=7), name="WIB")

logger = logging.getLogger("persib_simetris.data")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "acl2.db")
SNAPSHOT_PATH = os.path.join(BASE_DIR, "data", "snapshot_east.json")

SOURCE_URL = (
    "https://www.the-afc.com/en/club/afc_champions_league_two/"
    "fixtures__standings.html"
)
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

# Alias map ported from legacy app.py: AFC display names/slugs -> local DB slug.
# Needed because the API returns short names ("Seoul", "Kitchee", "TAMPINES
# ROVERS FC") while club_detail links use the database slugs.
TEAM_SLUG_MAP = {
    "persib": "persib-bandung",
    "persib bandung": "persib-bandung",
    "fc seoul": "fc-seoul",
    "seoul": "fc-seoul",
    "melbourne victory": "melbourne-victory",
    "thể công – viettel fc": "the-cong-viettel-fc",
    "thể công – viettel": "the-cong-viettel-fc",
    "the cong - viettel": "the-cong-viettel-fc",
    "the cong viettel": "the-cong-viettel-fc",
    "the cong-viettel fc": "the-cong-viettel-fc",
    "viettel": "the-cong-viettel-fc",
    "lion city sailors": "lion-city-sailors-fc",
    "lion city sailors fc": "lion-city-sailors-fc",
    "bg pathum united": "bg-pathum-united-fc",
    "adelaide united": "adelaide-united-fc",
    "adelaide united fc": "adelaide-united-fc",
    "tai po": "tai-po-fc",
    "tai po fc": "tai-po-fc",
    "fc machida zelvia": "fc-machida-zelvia",
    "machida zelvia": "fc-machida-zelvia",
    "preah khan reach svay rieng fc": "preah-khan-reach-svay-rieng-fc",
    "svay rieng": "preah-khan-reach-svay-rieng-fc",
    "shanghai shenhua": "shanghai-shenhua-fc",
    "shanghai shenhua fc": "shanghai-shenhua-fc",
    "tampines rovers": "tampines-rovers-fc",
    "tampines rovers fc": "tampines-rovers-fc",
    "bg tampines rovers": "tampines-rovers-fc",
    "phnom penh crown": "phnom-penh-crown-fc",
    "phnom penh crown fc": "phnom-penh-crown-fc",
    "kitchee": "kitchee-sc",
    "kitchee sc": "kitchee-sc",
    "kuching city": "kuching-city-fc",
    "kuching city fc": "kuching-city-fc",
    "gangwon": "gangwon-fc",
    "gangwon fc": "gangwon-fc",
}

# In-memory cache: endpoint -> (fetched_epoch, payload)
_cache: dict[str, tuple[float, Any]] = {}
# Provenance per snapshot key: "live" | "snapshot" | "empty" (for UI notices).
_source_status: dict[str, str] = {}


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
    """
    Return all clubs normalized from the local SQLite database.

    Falls back to database.get_all_clubs() (which can seed the DB) and finally to
    an empty list, so a missing/corrupt database degrades the UI instead of
    raising a 500 on every page.
    """
    try:
        return _get_sqlite_rows(
            """
            SELECT id, name, official_name, abbreviation, group_name,
                   country, country_code, country_flag, city, stadium, coach,
                   website, logo_url, local_logo, slug
            FROM clubs
            ORDER BY group_name ASC, name ASC
            """
        )
    except (sqlite3.Error, FileNotFoundError) as exc:
        logger.warning("Club query failed (%s); trying legacy database helper.", exc)
    try:
        return database.get_all_clubs()
    except Exception as exc:  # pragma: no cover - seeding may be unavailable
        logger.error("Club fallback failed: %s", exc)
        return []


def get_players(club_id: int | None = None) -> list[dict[str, Any]]:
    """Return player rows, optionally filtered by a club id."""
    sql = "SELECT * FROM players"
    params: tuple = ()
    if club_id is not None:
        sql += " WHERE club_id = ?"
        params = (club_id,)
    sql += " ORDER BY club_id, position_code, jersey_number"
    try:
        return _get_sqlite_rows(sql, params)
    except (sqlite3.Error, FileNotFoundError) as exc:
        logger.warning("Player query failed: %s", exc)
        return []


def get_club_by_slug(slug: str) -> dict[str, Any] | None:
    """Return one club by slug, or None when unavailable."""
    return next((club for club in get_clubs() if club["slug"] == slug), None)


def _fetch_json(url: str) -> Any:
    """Fetch a JSON payload from the AFC API and validate its shape."""
    request = Request(url, headers={"User-Agent": "ACL2-Analytics-Simulation/2.0"})
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
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        ValueError,
        EOFError,
        gzip.BadGzipFile,
        json.JSONDecodeError,
    ) as exc:
        logger.warning("AFC API failed for %s: %s. Using snapshot fallback.", url, exc)
        data = _load_snapshot().get(snapshot_key) or []
        _source_status[snapshot_key] = "snapshot" if data else "empty"
    else:
        if not data:
            # A well-formed but empty response is treated like an outage.
            logger.warning("AFC API returned no %s records; using snapshot.", snapshot_key)
            data = _load_snapshot().get(snapshot_key) or []
            _source_status[snapshot_key] = "snapshot" if data else "empty"
        else:
            _source_status[snapshot_key] = "live"
    if not isinstance(data, list):
        data = []
        _source_status[snapshot_key] = "empty"
    # Cache the fallback too, so an outage does not re-trigger a 15s timeout
    # on every single request.
    _cache[url] = (now, data)
    return data


def get_data_status() -> dict[str, str]:
    """Return provenance per dataset: 'live', 'snapshot', or 'empty'."""
    return dict(_source_status)


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

    groups = []
    for letter in GROUP_NAMES:
        matches = normalized[letter]
        matches.sort(
            key=lambda item: (item.get("date_venue") or "", item.get("time_venue") or "")
        )
        # Matchday numbering derived from the distinct venue dates (legacy behaviour).
        match_dates = sorted({m.get("date_venue") for m in matches if m.get("date_venue")})
        matchdays = {date: index + 1 for index, date in enumerate(match_dates)}
        for match in matches:
            day = matchdays.get(match.get("date_venue"))
            match["matchweek"] = f"Matchday {day}" if day else "Jadwal"
        # "name" is the legacy key used by index.html / fixtures.html.
        groups.append({"group": letter, "name": letter, "fixtures": matches})
    return groups


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
    groups = []
    for letter in GROUP_NAMES:
        rows = normalized[letter]
        rows.sort(key=lambda row: row.get("rank", 99))
        groups.append({"group": letter, "name": letter, "standings": rows})
    return groups


def _normalize_fixture(record: dict[str, Any]) -> dict[str, Any]:
    """Normalize one AFC fixture record into the application shape."""
    home = record.get("homeTeam") or {}
    away = record.get("awayTeam") or {}
    result = record.get("result") or {}
    group_label = (record.get("group") or {}).get("name", "")
    letter = group_label.removeprefix("Group ") if group_label.startswith("Group ") else "?"

    home_name = home.get("name") or "TBD"
    away_name = away.get("name") or "TBD"
    row = {
        "date_venue": record.get("dateVenue"),
        "time_venue": record.get("timeVenueUTC"),
        "status": "FT" if record.get("status") == "played" else "KO",
        "group": letter,
        "home": home_name,
        "away": away_name,
        # Resolve to local DB slugs so club_detail links and home/away matching work.
        "home_slug": get_club_slug(home.get("slug"), home_name),
        "away_slug": get_club_slug(away.get("slug"), away_name),
        "home_abbr": home.get("abbreviation") or "",
        "away_abbr": away.get("abbreviation") or "",
        "home_badge": _team_badge(home),
        "away_badge": _team_badge(away),
        "home_logo": _team_logo(home),
        "away_logo": _team_logo(away),
        "home_goals": result.get("homeGoals"),
        "away_goals": result.get("awayGoals"),
        "matchweek": None,  # Filled per group in load_fixtures().
    }
    # Legacy template aliases (fixtures.html / index.html from app.py).
    row.update(_kickoff_fields(record))
    row["skor_home"] = row["home_goals"]
    row["skor_away"] = row["away_goals"]
    return row


def _clubs_index() -> dict[str, dict[str, Any]]:
    """Return a cached slug -> club map used to canonicalize standings names."""
    global _clubs_index_cache
    now = time.monotonic()
    if _clubs_index_cache and now - _clubs_index_cache[0] < CACHE_TTL_SECONDS:
        return _clubs_index_cache[1]
    try:
        index = {club["slug"]: club for club in get_clubs()}
    except (sqlite3.Error, FileNotFoundError) as exc:
        logger.warning("Could not read clubs for standings mapping: %s", exc)
        index = {}
    _clubs_index_cache = (now, index)
    return index


_clubs_index_cache: tuple[float, dict[str, dict[str, Any]]] | None = None


def _int(value: Any, default: int = 0) -> int:
    """Coerce an API number to int, tolerating None/strings/garbage."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_standing(row: dict[str, Any], group: str) -> dict[str, Any]:
    """
    Normalize one AFC standings row.

    The display name is canonicalized to the local club name when the team can
    be resolved, so Scenario Duel / head-to-head lookups by name always match.
    """
    api_name = row.get("name") or "TBD"
    slug = get_club_slug(row.get("slug"), api_name)
    club = _clubs_index().get(slug)
    name = club["name"] if club else api_name

    played = _int(row.get("played"))
    won = _int(row.get("won"))
    drawn = _int(row.get("drawn"))
    lost = _int(row.get("lost"))
    goals_for = _int(row.get("goalsFor"))
    goals_against = _int(row.get("goalsAgainst"))
    points = _int(row.get("points"))
    goal_diff = _int(row.get("scoreDifference"), goals_for - goals_against)

    normalized = {
        "group": group,
        "rank": _int(row.get("rank"), 99),
        "name": name,
        "api_name": api_name,
        "slug": slug,
        "logo": _team_logo(row),
        "badge": _team_badge(row),
        "played": played,
        "won": won,
        "drawn": drawn,
        "lost": lost,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "goal_diff": goal_diff,
        "points": points,
    }
    # Legacy template aliases (index.html standings table from app.py).
    normalized.update(
        {
            "pos": normalized["rank"],
            "tim": name,
            "main": played,
            "menang": won,
            "seri": drawn,
            "kalah": lost,
            "gf": goals_for,
            "ga": goals_against,
            "gd": goal_diff,
            "poin": points,
        }
    )
    return normalized


def _safe_slug(value: Any) -> str:
    """Return a string slug or empty string when the value is missing."""
    return str(value).strip() if value else ""


def get_club_slug(*candidates: Any) -> str:
    """
    Resolve an AFC team name/slug to a local database slug.

    Accepts several candidates (slug first, then display name) and returns the
    first that maps to a known club. Returns "" when nothing matches so the
    templates fall back to plain text instead of a broken club_detail link.
    """
    for candidate in candidates:
        if not candidate:
            continue
        normalized = str(candidate).strip().lower()
        if not normalized:
            continue
        if normalized in _known_slugs():
            return normalized
        if normalized in TEAM_SLUG_MAP:
            return TEAM_SLUG_MAP[normalized]
        for key, slug in TEAM_SLUG_MAP.items():
            if key in normalized or normalized in key:
                return slug
    return ""


_slug_cache: tuple[float, set[str]] | None = None


def _known_slugs() -> set[str]:
    """Return the cached set of database slugs, tolerating a missing database."""
    global _slug_cache
    now = time.monotonic()
    if _slug_cache and now - _slug_cache[0] < CACHE_TTL_SECONDS:
        return _slug_cache[1]
    try:
        slugs = {club["slug"] for club in get_clubs()}
    except (sqlite3.Error, FileNotFoundError) as exc:
        logger.warning("Could not read club slugs: %s", exc)
        slugs = set()
    _slug_cache = (now, slugs)
    return slugs


def _is_persib(team: dict[str, Any]) -> bool:
    """Detect Persib so the bundled local crest can be preferred."""
    name = (team.get("name") or "").lower()
    abbr = (team.get("abbreviation") or "").lower()
    slug = (team.get("slug") or "").lower()
    return "persib" in name or abbr == "psb" or "persib" in slug


def _team_logo(team: dict[str, Any]) -> str | None:
    """Return a usable crest URL, preferring bundled local images."""
    if not isinstance(team, dict):
        return None
    if _is_persib(team):
        return "/static/images/persib.png"
    template = (team.get("logo") or {}).get("urlTemplate")
    if template:
        return template.replace("{{Resolution}}", "30x30")
    return None


def _team_badge(team: dict[str, Any]) -> str:
    """Return an abbreviation or initials fallback when no crest exists."""
    if not isinstance(team, dict):
        return "TBD"
    abbr = team.get("abbreviation")
    if abbr:
        return abbr
    initials = "".join(part[0] for part in (team.get("name") or "").split()[:3])
    return initials.upper() or "TBD"


def _formatted_date(value: Any) -> str:
    """Format an AFC date as 'DD Mon YYYY'; return 'TBD' when unusable."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except (TypeError, ValueError):
        return "TBD"


def _kickoff_fields(record: dict[str, Any]) -> dict[str, Any]:
    """
    Build the legacy tanggal/waktu/iso_utc fields from an AFC fixture record.

    Unlike the legacy version this never aborts the request: malformed dates
    degrade to a 'TBD' label so one bad record cannot break a whole page.
    """
    date_venue = record.get("dateVenue")
    venue_time = record.get("timeVenueUTC")
    tanggal = _formatted_date(date_venue)
    kickoff = None
    iso_utc = None

    if venue_time and date_venue and not record.get("noTime"):
        try:
            utc_dt = datetime.strptime(
                f"{date_venue} {str(venue_time)[:8]}", "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
            iso_utc = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            local_dt = utc_dt.astimezone(DEFAULT_TIMEZONE)
            kickoff = f"{local_dt.strftime('%H:%M')} WIB"
            tanggal = local_dt.strftime("%d %b %Y")
        except (ValueError, TypeError):
            kickoff = f"{str(venue_time)[:5]} WIB"
    return {"tanggal": tanggal, "waktu": kickoff, "iso_utc": iso_utc}


def load_dashboard_groups() -> list[dict[str, Any]]:
    """
    Return per-group fixtures + standings for the dashboard.

    This restores the legacy app.py home page payload (groups[].name/.fixtures/
    .standings) on top of the new data source, so index.html keeps working.
    """
    fixtures = {group["group"]: group["fixtures"] for group in load_fixtures()}
    standings = {group["group"]: group["standings"] for group in load_standings()}
    return [
        {
            "name": letter,
            "group": letter,
            "fixtures": fixtures.get(letter, []),
            "standings": standings.get(letter, []),
        }
        for letter in GROUP_NAMES
    ]


def get_database_stats() -> dict[str, Any]:
    """Expose small cardinality stats for footer/badges, with a safe fallback."""
    try:
        return database.get_database_stats()
    except Exception as exc:
        logger.warning("Database stats unavailable: %s", exc)
        clubs = get_clubs()
        return {
            "total_clubs": len(clubs),
            "total_players": len(get_players()),
            "season": "2026/2027",
            "zones": "East Zone (Grup E, F, G, H)",
        }


def get_season_context() -> dict[str, Any]:
    """Return a small context object used across templates."""
    status = get_data_status()
    used_snapshot = "snapshot" in status.values() or not status
    return {
        "season": "2026/2027",
        "competition": "AFC Champions League Two",
        "zone": "East Zone (Group E–H)",
        "source_url": SOURCE_URL,
        "source_label": (
            "Snapshot lokal (API AFC tidak terjangkau)"
            if used_snapshot
            else "AFC Public API (live)"
        ),
        "data_status": status,
    }
