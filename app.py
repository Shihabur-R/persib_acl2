import gzip
import json
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from zoneinfo import ZoneInfo
    DEFAULT_TIMEZONE = ZoneInfo("Asia/Jakarta")
except Exception:
    DEFAULT_TIMEZONE = timezone(timedelta(hours=7), name="WIB")

from flask import Flask, abort, render_template

app = Flask(__name__)

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


def fetch_afc_json(url):
    request = Request(url, headers={"User-Agent": "ACL2-Dashboard/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            payload = json.loads(body)
    except (gzip.BadGzipFile, EOFError):
        abort(502, description="The AFC data service returned invalid compressed data.")
    except HTTPError as error:
        abort(502, description=f"AFC data service returned HTTP {error.code}.")
    except URLError as error:
        abort(502, description=f"Unable to reach the AFC data service: {error.reason}")
    except TimeoutError:
        abort(502, description="The AFC data service timed out.")
    except json.JSONDecodeError:
        abort(502, description="The AFC data service returned invalid JSON.")

    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        abort(502, description="The AFC data service returned an unexpected response.")
    return payload["data"]


def team_logo(team):
    logo = team.get("logo") or {}
    template = logo.get("urlTemplate")
    if template:
        return template.replace("{{Resolution}}", "30x30")
    return None


def team_badge(team):
    return team.get("abbreviation") or "".join(
        part[0] for part in team.get("name", "").split()[:3]
    ).upper()


def group_name(value):
    if not isinstance(value, str) or not value.startswith("Group "):
        return None
    name = value.removeprefix("Group ")
    return name if name in GROUP_NAMES else None


def formatted_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except (TypeError, ValueError):
        abort(502, description="The AFC data service returned an invalid fixture date.")


def load_fixtures():
    records = fetch_afc_json(FIXTURES_API)
    grouped = {name: [] for name in GROUP_NAMES}
    for record in records:
        group = group_name((record.get("group") or {}).get("name"))
        if group is not None:
            grouped[group].append(record)

    groups = []
    for name in GROUP_NAMES:
        matches = grouped[name]
        if not matches:
            abort(502, description=f"The AFC data service returned no fixtures for Group {name}.")

        match_dates = sorted({match.get("dateVenue") for match in matches})
        matchdays = {date: index + 1 for index, date in enumerate(match_dates)}
        fixtures = []
        for record in sorted(
            matches,
            key=lambda match: (match.get("dateVenue") or "", match.get("timeVenueUTC") or ""),
        ):
            home = record.get("homeTeam") or {}
            away = record.get("awayTeam") or {}
            result = record.get("result") or {}
            venue_time = record.get("timeVenueUTC")
            date_venue = record.get("dateVenue")
            kickoff = None
            iso_utc = None
            tanggal = formatted_date(date_venue)

            if venue_time and not record.get("noTime"):
                try:
                    utc_dt = datetime.strptime(
                        f"{date_venue} {venue_time[:8]}", "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=timezone.utc)
                    iso_utc = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    local_dt = utc_dt.astimezone(DEFAULT_TIMEZONE)
                    kickoff = f"{local_dt.strftime('%H:%M')} WIB"
                    tanggal = local_dt.strftime("%d %b %Y")
                except (ValueError, TypeError):
                    kickoff = f"{venue_time[:5]} WIB"

            status = "FT" if record.get("status") == "played" else "KO"
            fixtures.append(
                {
                    "matchweek": f"Matchday {matchdays[record.get('dateVenue')]}",
                    "tanggal": tanggal,
                    "waktu": kickoff,
                    "iso_utc": iso_utc,
                    "home": home.get("name", "TBD"),
                    "away": away.get("name", "TBD"),
                    "home_logo": team_logo(home),
                    "away_logo": team_logo(away),
                    "home_badge": team_badge(home),
                    "away_badge": team_badge(away),
                    "status": status,
                    "skor_home": result.get("homeGoals"),
                    "skor_away": result.get("awayGoals"),
                }
            )
        groups.append({"name": name, "fixtures": fixtures})
    return groups


def load_standings():
    records = fetch_afc_json(STANDINGS_API)
    grouped = {}
    for record in records:
        name = group_name(record.get("groupName"))
        if name is not None:
            grouped[name] = record.get("standings", [])

    groups = []
    for name in GROUP_NAMES:
        rows = grouped.get(name)
        if not rows:
            abort(502, description=f"The AFC data service returned no standings for Group {name}.")
        standings = []
        for record in sorted(rows, key=lambda row: row.get("rank", 0)):
            team = record
            standings.append(
                {
                    "pos": record.get("rank"),
                    "tim": team.get("name", "TBD"),
                    "logo": team_logo(team),
                    "badge": team_badge(team),
                    "main": record.get("played", 0),
                    "menang": record.get("won", 0),
                    "seri": record.get("drawn", 0),
                    "kalah": record.get("lost", 0),
                    "gf": record.get("goalsFor", 0),
                    "ga": record.get("goalsAgainst", 0),
                    "gd": record.get("scoreDifference", 0),
                    "poin": record.get("points", 0),
                }
            )
        groups.append({"name": name, "standings": standings})
    return groups


@app.route("/")
def home():
    fixture_groups = {group["name"]: group["fixtures"] for group in load_fixtures()}
    standings_groups = {group["name"]: group["standings"] for group in load_standings()}
    groups = [
        {
            "name": name,
            "fixtures": fixture_groups[name],
            "standings": standings_groups[name],
        }
        for name in GROUP_NAMES
    ]
    return render_template("index.html", groups=groups, source_url=SOURCE_URL)


@app.route("/fixtures")
def fixtures():
    return render_template(
        "fixtures.html", groups=load_fixtures(), source_url=SOURCE_URL
    )


if __name__ == "__main__":
    app.run(debug=True)
