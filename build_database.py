"""
build_database.py
Membangun dan mengisi database SQLite (acl2.db) untuk klub dan pemain
peserta AFC Champions League Two (ACL2) Zona Timur (Grup E–H) musim 2026/2027.
"""

import sqlite3
import os
import json
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "acl2.db")
SCRATCH_JSON = os.path.join(
    r"C:\Users\MY-DESKTOP\.gemini\antigravity\brain\39050d64-cdf2-4af9-923b-90d86f072d13\scratch",
    "squads_extracted.json"
)

CLUBS_DATA = [
    {
        "name": "Persib Bandung",
        "official_name": "Persib Bandung",
        "abbreviation": "PSB",
        "group_name": "E",
        "country": "Indonesia",
        "country_code": "IDN",
        "slug": "persib-bandung",
        "stadium": "Gelora Bandung Lautan Api (GBLA)",
        "city": "Bandung",
        "coach": "Igor Tolic",
        "website": "https://persib.co.id",
        "logo_url": "/static/images/persib.png",
        "local_logo": "/static/images/persib.png"
    },
    {
        "name": "FC Seoul",
        "official_name": "FC Seoul",
        "abbreviation": "SEO",
        "group_name": "E",
        "country": "Korea Republic",
        "country_code": "KOR",
        "slug": "fc-seoul",
        "stadium": "Seoul World Cup Stadium",
        "city": "Seoul",
        "coach": "Kim Gi-dong",
        "website": "http://www.fcseoul.com",
        "logo_url": "https://logo.the-afc.com/u1992_200x200.png",
        "local_logo": "/static/images/fc-seoul.png"
    },
    {
        "name": "Melbourne Victory",
        "official_name": "Melbourne Victory Football Club",
        "abbreviation": "MVC",
        "group_name": "E",
        "country": "Australia",
        "country_code": "AUS",
        "slug": "melbourne-victory",
        "stadium": "AAMI Park (Melbourne Rectangular Stadium)",
        "city": "Melbourne",
        "coach": "Arthur Papas",
        "website": "https://melbournevictory.com.au",
        "logo_url": "https://logo.the-afc.com/u2237_200x200.png",
        "local_logo": "/static/images/melbourne-victory.png"
    },
    {
        "name": "Thể Công – Viettel FC",
        "official_name": "Thể Công – Viettel Football Club",
        "abbreviation": "VTF",
        "group_name": "E",
        "country": "Vietnam",
        "country_code": "VIE",
        "slug": "the-cong-viettel-fc",
        "stadium": "Mỹ Đình National Stadium",
        "city": "Hanoi",
        "coach": "Nguyễn Đức Thắng",
        "website": "https://viettelthecong.vn",
        "logo_url": "https://logo.the-afc.com/u17676_200x200.png",
        "local_logo": "/static/images/viettel.png"
    },
    {
        "name": "Lion City Sailors FC",
        "official_name": "Lion City Sailors Football Club",
        "abbreviation": "LCS",
        "group_name": "F",
        "country": "Singapore",
        "country_code": "SGP",
        "slug": "lion-city-sailors-fc",
        "stadium": "Bishan Stadium",
        "city": "Bishan",
        "coach": "Aleksandar Ranković",
        "website": "https://lioncitysailorsfc.sg",
        "logo_url": "https://logo.the-afc.com/u12460_200x200.png",
        "local_logo": None
    },
    {
        "name": "BG Pathum United",
        "official_name": "BG Pathum United Football Club",
        "abbreviation": "BGP",
        "group_name": "F",
        "country": "Thailand",
        "country_code": "THA",
        "slug": "bg-pathum-united-fc",
        "stadium": "BG Stadium",
        "city": "Pathum Thani",
        "coach": "Surachai Jaturapattarapong",
        "website": "https://bgputd.com",
        "logo_url": "https://logo.the-afc.com/u11628_200x200.png",
        "local_logo": None
    },
    {
        "name": "Adelaide United FC",
        "official_name": "Adelaide United Football Club",
        "abbreviation": "ADL",
        "group_name": "F",
        "country": "Australia",
        "country_code": "AUS",
        "slug": "adelaide-united-fc",
        "stadium": "Coopers Stadium (Hindmarsh Stadium)",
        "city": "Adelaide",
        "coach": "Carl Veart",
        "website": "https://adelaideunited.com.au",
        "logo_url": "https://logo.the-afc.com/u2309_200x200.png",
        "local_logo": None
    },
    {
        "name": "Tai Po FC",
        "official_name": "Tai Po Football Club",
        "abbreviation": "TAI",
        "group_name": "F",
        "country": "Hong Kong, China",
        "country_code": "HKG",
        "slug": "tai-po-fc",
        "stadium": "Tai Po Sports Ground",
        "city": "Tai Po",
        "coach": "Lee Chi-Kin",
        "website": "https://www.taipofc.com",
        "logo_url": "https://logo.the-afc.com/u15589_200x200.png",
        "local_logo": None
    },
    {
        "name": "FC Machida Zelvia",
        "official_name": "FC Machida Zelvia",
        "abbreviation": "MAC",
        "group_name": "G",
        "country": "Japan",
        "country_code": "JPN",
        "slug": "fc-machida-zelvia",
        "stadium": "Machida GION Stadium",
        "city": "Machida, Tokyo",
        "coach": "Go Kuroda",
        "website": "https://www.zelvia.co.jp",
        "logo_url": "https://logo.the-afc.com/u19122_200x200.png",
        "local_logo": None
    },
    {
        "name": "Preah Khan Reach Svay Rieng FC",
        "official_name": "Preah Khan Reach Svay Rieng Football Club",
        "abbreviation": "SVA",
        "group_name": "G",
        "country": "Cambodia",
        "country_code": "CAM",
        "slug": "preah-khan-reach-svay-rieng-fc",
        "stadium": "Svay Rieng Stadium",
        "city": "Svay Rieng",
        "coach": "Pep Muñoz",
        "website": "https://www.svayriengfc.com",
        "logo_url": "https://logo.the-afc.com/u16481_200x200.png",
        "local_logo": None
    },
    {
        "name": "Shanghai Shenhua FC",
        "official_name": "Shanghai Shenhua Football Club",
        "abbreviation": "SHS",
        "group_name": "G",
        "country": "China PR",
        "country_code": "CHN",
        "slug": "shanghai-shenhua-fc",
        "stadium": "Shanghai Stadium",
        "city": "Shanghai",
        "coach": "Leonid Slutsky",
        "website": "http://www.shenhuafc.com.cn",
        "logo_url": "https://logo.the-afc.com/u1377_200x200.png",
        "local_logo": None
    },
    {
        "name": "Tampines Rovers FC",
        "official_name": "BG Tampines Rovers Football Club",
        "abbreviation": "TAM",
        "group_name": "G",
        "country": "Singapore",
        "country_code": "SGP",
        "slug": "tampines-rovers-fc",
        "stadium": "Our Tampines Hub",
        "city": "Tampines",
        "coach": "Gavin Lee",
        "website": "https://tampinesrovers.com",
        "logo_url": "https://logo.the-afc.com/u9641_200x200.png",
        "local_logo": None
    },
    {
        "name": "Phnom Penh Crown FC",
        "official_name": "Phnom Penh Crown Football Club",
        "abbreviation": "CRO",
        "group_name": "H",
        "country": "Cambodia",
        "country_code": "CAM",
        "slug": "phnom-penh-crown-fc",
        "stadium": "Smart RSN Stadium",
        "city": "Phnom Penh",
        "coach": "Oleg Starynskyi",
        "website": "https://ppcfc.com",
        "logo_url": "https://logo.the-afc.com/u19062_200x200.png",
        "local_logo": None
    },
    {
        "name": "Kitchee SC",
        "official_name": "Kitchee Sports Club",
        "abbreviation": "KIT",
        "group_name": "H",
        "country": "Hong Kong, China",
        "country_code": "HKG",
        "slug": "kitchee-sc",
        "stadium": "Mong Kok Stadium",
        "city": "Mong Kok",
        "coach": "Alex Chu",
        "website": "https://www.kitchee.com",
        "logo_url": "https://logo.the-afc.com/u11499_200x200.png",
        "local_logo": None
    },
    {
        "name": "Kuching City FC",
        "official_name": "Kuching City Football Club",
        "abbreviation": "KCI",
        "group_name": "H",
        "country": "Malaysia",
        "country_code": "MAS",
        "slug": "kuching-city-fc",
        "stadium": "Sarawak State Stadium",
        "city": "Kuching, Sarawak",
        "coach": "Aidil Sharin Sahak",
        "website": "https://kuchingcityfc.com",
        "logo_url": "https://logo.the-afc.com/u15095_200x200.png",
        "local_logo": None
    },
    {
        "name": "Gangwon FC",
        "official_name": "Gangwon Football Club",
        "abbreviation": "GAN",
        "group_name": "H",
        "country": "Korea Republic",
        "country_code": "KOR",
        "slug": "gangwon-fc",
        "stadium": "Chuncheon Songam Sports Town",
        "city": "Gangwon-do",
        "coach": "Yoon Jong-hwan",
        "website": "http://www.gangwon-fc.com",
        "logo_url": "https://logo.the-afc.com/u12176_200x200.png",
        "local_logo": None
    }
]

COUNTRY_MAP = {
    'IDN': ('Indonesia', '🇮🇩'),
    'KOR': ('Korea Republic', '🇰🇷'),
    'AUS': ('Australia', '🇦🇺'),
    'VIE': ('Vietnam', '🇻🇳'),
    'SGP': ('Singapore', '🇸🇬'),
    'SIN': ('Singapore', '🇸🇬'),
    'THA': ('Thailand', '🇹🇭'),
    'HKG': ('Hong Kong', '🇭🇰'),
    'JPN': ('Japan', '🇯🇵'),
    'CAM': ('Cambodia', '🇰🇭'),
    'CAMBODIA': ('Cambodia', '🇰🇭'),
    'CHN': ('China PR', '🇨🇳'),
    'MAS': ('Malaysia', '🇲🇾'),
    'BRA': ('Brazil', '🇧🇷'),
    'ARG': ('Argentina', '🇦🇷'),
    'FRA': ('France', '🇫🇷'),
    'CRO': ('Croatia', '🇭🇷'),
    'BIH': ('Bosnia and Herzegovina', '🇧🇦'),
    'MNE': ('Montenegro', '🇲🇪'),
    'NED': ('Netherlands', '🇳🇱'),
    'NIR': ('Northern Ireland', '🇬🇧'),
    'TLS': ('Timor-Leste', '🇹🇱'),
    'NAM': ('Namibia', '🇳🇦'),
    'CMR': ('Cameroon', '🇨🇲'),
    'NGR': ('Nigeria', '🇳🇬'),
    'JOR': ('Jordan', '🇯🇴'),
    'SRB': ('Serbia', '🇷🇸'),
    'ESP': ('Spain', '🇪🇸'),
    'POR': ('Portugal', '🇵🇹'),
    'CIV': ('Ivory Coast', '🇨🇮'),
    'COL': ('Colombia', '🇨🇴'),
    'SWE': ('Sweden', '🇸🇪'),
    'NOR': ('Norway', '🇳🇴'),
    'PHI': ('Philippines', '🇵🇭'),
    'UZB': ('Uzbekistan', '🇺🇿'),
    'ENG': ('England', '🏴󠁧󠁢󠁥󠁮󠁧󠁿'),
    'SCO': ('Scotland', '🏴󠁧󠁢󠁳󠁣󠁴󠁿'),
    'IRL': ('Ireland', '🇮🇪'),
    'MLI': ('Mali', '🇲🇱'),
    'GHA': ('Ghana', '🇬🇭'),
    'SEN': ('Senegal', '🇸🇳'),
    'GER': ('Germany', '🇩🇪'),
    'ITA': ('Italy', '🇮🇹'),
    'BEL': ('Belgium', '🇧🇪'),
    'URU': ('Uruguay', '🇺🇾'),
    'PAR': ('Paraguay', '🇵🇾'),
    'CHI': ('Chile', '🇨🇱'),
    'NZL': ('New Zealand', '🇳🇿'),
    'AFG': ('Afghanistan', '🇦🇫'),
    'IRQ': ('Iraq', '🇮🇶'),
    'IRN': ('Iran', '🇮🇷'),
    'LBN': ('Lebanon', '🇱🇧'),
    'SYR': ('Syria', '🇸🇾'),
    'MYA': ('Myanmar', '🇲🇲'),
    'LAO': ('Laos', '🇱🇦'),
}

POSITION_ORDER = {
    'GK': 1,
    'DF': 2,
    'MF': 3,
    'FW': 4
}


def clean_name(val):
    val = re.sub(r'<ref[^>]*>.*?</ref>', '', val, flags=re.DOTALL | re.IGNORECASE)
    val = re.sub(r'<ref[^>]*/>', '', val, flags=re.IGNORECASE)
    val = re.sub(r'<ref[^>]*', '', val, flags=re.IGNORECASE)
    val = re.sub(r'\{\{[^}]*\}\}', '', val)
    val = re.sub(r'\{\{[^}]*', '', val)
    val = re.sub(r'<[^>]+>', '', val)
    val = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', val)
    val = re.sub(r'\[\[([^\]]+)', r'\1', val)
    val = val.replace(']]', '').replace('[[', '')
    val = re.sub(r'\s*\([^)]*footballer[^)]*\)', '', val, flags=re.IGNORECASE)
    val = re.sub(r'\s*\([^)]*born[^)]*\)', '', val, flags=re.IGNORECASE)
    val = val.replace("''", "").replace("'''", "")
    val = re.sub(r'\s*\(captain\)', '', val, flags=re.IGNORECASE)
    val = re.sub(r'\s*\(c\)', '', val, flags=re.IGNORECASE)
    val = re.sub(r'\s*\(vice-captain\)', '', val, flags=re.IGNORECASE)
    val = re.sub(r'\s*\(on loan[^)]*\)', '', val, flags=re.IGNORECASE)
    val = re.sub(r'\s+', ' ', val).strip(' ,;|/-')
    return val


def create_schema(conn):
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS players")
    cursor.execute("DROP TABLE IF EXISTS clubs")

    cursor.execute("""
    CREATE TABLE clubs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        official_name TEXT NOT NULL,
        abbreviation TEXT NOT NULL,
        group_name TEXT NOT NULL,
        country TEXT NOT NULL,
        country_code TEXT NOT NULL,
        country_flag TEXT NOT NULL,
        city TEXT,
        stadium TEXT,
        coach TEXT,
        website TEXT,
        logo_url TEXT,
        local_logo TEXT,
        slug TEXT UNIQUE NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        club_id INTEGER NOT NULL,
        jersey_number INTEGER,
        name TEXT NOT NULL,
        position TEXT NOT NULL,
        position_code TEXT NOT NULL,
        nationality TEXT NOT NULL,
        nationality_code TEXT NOT NULL,
        nationality_flag TEXT NOT NULL,
        is_captain INTEGER DEFAULT 0,
        season TEXT DEFAULT '2026/2027',
        FOREIGN KEY (club_id) REFERENCES clubs (id) ON DELETE CASCADE
    )
    """)

    cursor.execute("CREATE INDEX idx_clubs_group ON clubs(group_name)")
    cursor.execute("CREATE INDEX idx_clubs_slug ON clubs(slug)")
    cursor.execute("CREATE INDEX idx_players_club ON players(club_id)")
    cursor.execute("CREATE INDEX idx_players_pos ON players(position_code)")
    cursor.execute("CREATE INDEX idx_players_num ON players(jersey_number)")
    conn.commit()


def seed_database():
    if not os.path.exists(SCRATCH_JSON):
        raise FileNotFoundError(f"Extracted json file not found at: {SCRATCH_JSON}")

    with open(SCRATCH_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)
    cursor = conn.cursor()

    total_clubs = 0
    total_players = 0

    # Specific missing number fills from verified roster data
    special_numbers = {
        ("Thể Công – Viettel FC", "Trần Đức Duy"): 54,
        ("Thể Công – Viettel FC", "Đỗ Văn Chí"): 16,
        ("Thể Công – Viettel FC", "Nguyễn Đình Đức"): 27,
        ("Thể Công – Viettel FC", "Nguyễn Hữu Tiệp"): 29,
        ("Thể Công – Viettel FC", "Vũ Bá Hải Dương"): 32,
        ("Kuching City FC", "Christian Bassogog"): 9,
        ("Kuching City FC", "Jacob Mahler"): 6,
    }

    for club_data in CLUBS_DATA:
        country_meta = COUNTRY_MAP.get(club_data["country_code"].upper(), (club_data["country"], "🌐"))
        cursor.execute("""
            INSERT INTO clubs (
                name, official_name, abbreviation, group_name, country,
                country_code, country_flag, city, stadium, coach,
                website, logo_url, local_logo, slug
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            club_data["name"],
            club_data["official_name"],
            club_data["abbreviation"],
            club_data["group_name"],
            club_data["country"],
            club_data["country_code"],
            country_meta[1],
            club_data["city"],
            club_data["stadium"],
            club_data["coach"],
            club_data["website"],
            club_data["logo_url"],
            club_data["local_logo"],
            club_data["slug"]
        ))
        club_id = cursor.lastrowid
        total_clubs += 1

        players_list = data["squads"].get(club_data["name"], [])
        
        # Sort players by position then jersey number
        cleaned_players = []
        seen = set()

        for p in players_list:
            cname = clean_name(p["name"])
            if not cname or cname.lower() in seen:
                continue
            seen.add(cname.lower())

            j_num = p["jersey_number"]
            if j_num is None and (club_data["name"], cname) in special_numbers:
                j_num = special_numbers[(club_data["name"], cname)]

            nat_code = p.get("nationality", "").strip().upper()
            country_info = COUNTRY_MAP.get(nat_code, (nat_code.title() if nat_code else "Unknown", "🏳️"))

            pos_code = p.get("position_code", "").strip().upper()
            pos_name = p.get("position", "Player")

            cleaned_players.append({
                "jersey_number": j_num,
                "name": cname,
                "position": pos_name,
                "position_code": pos_code,
                "nationality": country_info[0],
                "nationality_code": nat_code,
                "nationality_flag": country_info[1],
                "is_captain": p.get("is_captain", 0)
            })

        # Sort: Pos code (GK -> DF -> MF -> FW) then jersey_number
        cleaned_players.sort(key=lambda x: (
            POSITION_ORDER.get(x["position_code"], 99),
            x["jersey_number"] if x["jersey_number"] is not None else 999
        ))

        for cp in cleaned_players:
            cursor.execute("""
                INSERT INTO players (
                    club_id, jersey_number, name, position, position_code,
                    nationality, nationality_code, nationality_flag, is_captain, season
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '2026/2027')
            """, (
                club_id,
                cp["jersey_number"],
                cp["name"],
                cp["position"],
                cp["position_code"],
                cp["nationality"],
                cp["nationality_code"],
                cp["nationality_flag"],
                cp["is_captain"]
            ))
            total_players += 1

    conn.commit()
    conn.close()
    print(f"Database successfully built at: {DB_PATH}")
    print(f"Summary: {total_clubs} clubs and {total_players} players inserted.")


if __name__ == "__main__":
    seed_database()
