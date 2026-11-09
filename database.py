"""
database.py
Modul helper untuk mengakses database SQLite (acl2.db).
Menyediakan fungsi-fungsi query untuk klub dan pemain ACL2 Zona Timur (Grup E–H).
"""

import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "acl2.db")


def get_db_connection():
    """Membuka koneksi ke database SQLite dan mengembalikan objek connection dengan Row factory."""
    if not os.path.exists(DB_PATH):
        # Jalankan inisialisasi jika file database belum dibuat
        from build_database import seed_database
        seed_database()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_clubs():
    """Mengambil seluruh 16 klub peserta ACL2 Grup E-H."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT c.*,
                   (SELECT COUNT(*) FROM players WHERE club_id = c.id) AS squad_count
            FROM clubs c
            ORDER BY c.group_name ASC, c.name ASC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_clubs_grouped():
    """Mengambil klub yang dikelompokkan berdasarkan grup (E, F, G, H)."""
    clubs = get_all_clubs()
    grouped = {"E": [], "F": [], "G": [], "H": []}
    for club in clubs:
        grp = club.get("group_name")
        if grp in grouped:
            grouped[grp].append(club)
    return grouped


def get_club_by_slug(slug):
    """Mengambil data profil satu klub berdasarkan slug."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM clubs WHERE slug = ?", (slug,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_club_players(club_id):
    """Mengambil seluruh pemain dari klub tertentu berdasarkan club_id."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM players
            WHERE club_id = ?
            ORDER BY 
                CASE position_code
                    WHEN 'GK' THEN 1
                    WHEN 'DF' THEN 2
                    WHEN 'MF' THEN 3
                    WHEN 'FW' THEN 4
                    ELSE 5
                END,
                CASE WHEN jersey_number IS NULL THEN 1 ELSE 0 END,
                jersey_number ASC
        """, (club_id,))
        return [dict(row) for row in cursor.fetchall()]


def search_players(query=None, group_name=None, position=None, club_id=None):
    """Mencari pemain berdasarkan nama/kebangsaan, grup, klub, dan posisi."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        sql = """
            SELECT p.*, c.name AS club_name, c.group_name, c.slug AS club_slug, c.logo_url AS club_logo
            FROM players p
            JOIN clubs c ON p.club_id = c.id
            WHERE 1=1
        """
        params = []

        if query:
            sql += " AND (p.name LIKE ? OR p.nationality LIKE ? OR p.jersey_number LIKE ?)"
            q_like = f"%{query.strip()}%"
            params.extend([q_like, q_like, q_like])

        if group_name and group_name in ("E", "F", "G", "H"):
            sql += " AND c.group_name = ?"
            params.append(group_name)

        if club_id:
            sql += " AND p.club_id = ?"
            params.append(club_id)

        if position and position.upper() in ("GK", "DF", "MF", "FW"):
            sql += " AND p.position_code = ?"
            params.append(position.upper())

        sql += """
            ORDER BY c.group_name ASC, c.name ASC,
            CASE p.position_code
                WHEN 'GK' THEN 1
                WHEN 'DF' THEN 2
                WHEN 'MF' THEN 3
                WHEN 'FW' THEN 4
                ELSE 5
            END,
            p.jersey_number ASC
        """
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]


def get_database_stats():
    """Mengambil ringkasan statistik database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM clubs")
        total_clubs = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM players")
        total_players = cursor.fetchone()[0]
        return {
            "total_clubs": total_clubs,
            "total_players": total_players,
            "season": "2026/2027",
            "zones": "East Zone (Grup E, F, G, H)"
        }
