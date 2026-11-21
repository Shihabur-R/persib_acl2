"""
seed_west_groups.py
Menambahkan klub Grup A–D ke acl2.db dari data resmi AFC Public API.

Skrip ini tidak mengarang klub, skuad, klasemen, atau fixtures: identitas klub
(nama, singkatan, negara, logo) diambil dari endpoint standings AFC, lalu
klasemen dan fixtures menyusul lewat data_sources yang sudah membaca A–H.

Skuad pemain tidak tersedia pada endpoint publik, jadi klub baru sengaja
dibiarkan tanpa pemain sampai sumber skuad resmi tersedia; UI menampilkan
keadaan itu apa adanya alih-alih mengisi nama pemain rekaan.

Pemakaian:
    venv/bin/python seed_west_groups.py            # tambah grup yang belum ada
    venv/bin/python seed_west_groups.py --dry-run   # pratinjau tanpa menulis
"""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import unicodedata

import data_sources

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("seed_west")

TARGET_GROUPS = ("A", "B", "C", "D")
SEASON = "2026/2027"

# Country name -> flag emoji, derived from the ISO code the API already sends.
def country_flag(code: str) -> str:
    """Build a flag emoji from a two/three-letter country code where possible."""
    iso2 = ISO3_TO_ISO2.get((code or "").strip().upper())
    if not iso2:
        return ""
    return "".join(chr(0x1F1E6 + ord(char) - ord("A")) for char in iso2)


# AFC uses IOC-style three-letter codes; map the ones present in groups A–D.
ISO3_TO_ISO2 = {
    "UAE": "AE", "KUW": "KW", "UZB": "UZ", "BHR": "BH", "TKM": "TM",
    "IRN": "IR", "KSA": "SA", "QAT": "QA", "JOR": "JO", "OMA": "OM",
    "IRQ": "IQ", "LBN": "LB", "SYR": "SY", "IND": "IN", "TJK": "TJ",
    "KGZ": "KG", "AUS": "AU", "JPN": "JP", "KOR": "KR", "CHN": "CN",
    "IDN": "ID", "THA": "TH", "VIE": "VN", "MYA": "MM", "SGP": "SG",
    "HKG": "HK", "CAM": "KH", "MAS": "MY", "PHI": "PH",
}


def slugify(name: str) -> str:
    """Turn a club display name into a stable ASCII slug."""
    text = unicodedata.normalize("NFKD", name or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "club"


def fetch_west_clubs() -> list[dict]:
    """Read groups A–D from the official standings endpoint."""
    records = data_sources._fetch_json(data_sources.STANDINGS_API)
    clubs: list[dict] = []
    for record in records:
        label = (record.get("groupName") or "").strip()
        letter = label.removeprefix("Group ").strip().upper()
        if letter not in TARGET_GROUPS:
            continue
        for team in record.get("standings") or []:
            name = (team.get("name") or "").strip()
            if not name:
                continue
            code = (team.get("teamCountryCode") or "").strip().upper()
            logo = (team.get("logo") or {}).get("bigLogo") or ""
            clubs.append(
                {
                    "name": name,
                    "official_name": name,
                    "abbreviation": (team.get("abbreviation") or name[:3]).strip().upper(),
                    "group_name": letter,
                    "country": (team.get("teamCountryName") or "").strip(),
                    "country_code": code,
                    "country_flag": country_flag(code),
                    "city": None,
                    "stadium": None,
                    "coach": None,
                    "website": None,
                    "logo_url": logo or None,
                    "local_logo": None,
                    "slug": slugify(name),
                }
            )
    return clubs


def insert_clubs(clubs: list[dict], dry_run: bool = False) -> int:
    """Insert only clubs whose slug is not present yet; existing rows untouched."""
    conn = sqlite3.connect(data_sources.DB_PATH)
    conn.row_factory = sqlite3.Row
    added = 0
    try:
        existing = {row["slug"] for row in conn.execute("SELECT slug FROM clubs")}
        for club in clubs:
            if club["slug"] in existing:
                logger.info("Lewati (sudah ada): %s", club["name"])
                continue
            logger.info(
                "Tambah Grup %s: %s (%s)", club["group_name"], club["name"], club["slug"]
            )
            added += 1
            if dry_run:
                continue
            conn.execute(
                """
                INSERT INTO clubs (
                    name, official_name, abbreviation, group_name, country,
                    country_code, country_flag, city, stadium, coach, website,
                    logo_url, local_logo, slug
                ) VALUES (
                    :name, :official_name, :abbreviation, :group_name, :country,
                    :country_code, :country_flag, :city, :stadium, :coach, :website,
                    :logo_url, :local_logo, :slug
                )
                """,
                club,
            )
            existing.add(club["slug"])
        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return added


def refresh_snapshot(dry_run: bool = False) -> tuple[int, int]:
    """
    Add official A–D fixtures/standings to the bundled offline snapshot.

    Existing snapshot entries are kept as-is; only missing groups are appended so
    an outage still shows every group the API had published.
    """
    import json
    import os

    fixtures = data_sources._fetch_json(data_sources.FIXTURES_API)
    standings = data_sources._fetch_json(data_sources.STANDINGS_API)
    path = data_sources.SNAPSHOT_PATH
    current = {"fixtures": [], "standings": []}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as handle:
            current = json.load(handle)

    def group_letter(record: dict, key: str) -> str:
        label = (record.get(key) or {}) if key == "group" else record
        text = label.get("name") if key == "group" else label.get("groupName", "")
        return (text or "").removeprefix("Group ").strip().upper()

    have_fx = {group_letter(row, "group") for row in current.get("fixtures", [])}
    have_st = {group_letter(row, "standings") for row in current.get("standings", [])}
    new_fx = [
        row for row in fixtures
        if group_letter(row, "group") in TARGET_GROUPS and group_letter(row, "group") not in have_fx
    ]
    new_st = [
        row for row in standings
        if group_letter(row, "standings") in TARGET_GROUPS
        and group_letter(row, "standings") not in have_st
    ]
    if not dry_run and (new_fx or new_st):
        current.setdefault("fixtures", []).extend(new_fx)
        current.setdefault("standings", []).extend(new_st)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(current, handle, ensure_ascii=False, indent=2)
    return len(new_fx), len(new_st)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed klub Grup A–D dari API AFC.")
    parser.add_argument("--dry-run", action="store_true", help="Pratinjau tanpa menulis.")
    parser.add_argument(
        "--snapshot", action="store_true", help="Perbarui juga snapshot offline A–D."
    )
    args = parser.parse_args()

    clubs = fetch_west_clubs()
    if not clubs:
        logger.warning("API tidak mengembalikan klub Grup A–D; tidak ada perubahan.")
        return
    added = insert_clubs(clubs, dry_run=args.dry_run)
    logger.info(
        "%s %d klub%s.",
        "Pratinjau" if args.dry_run else "Selesai, menambahkan",
        added,
        "" if args.dry_run else " ke acl2.db",
    )
    if args.snapshot:
        fx_count, st_count = refresh_snapshot(dry_run=args.dry_run)
        logger.info("Snapshot: %d fixtures, %d klasemen grup baru.", fx_count, st_count)


if __name__ == "__main__":
    main()