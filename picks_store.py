"""
Persistence and validation for user-saved picks.

The Saved Pick feature keeps its own lightweight storage in the existing SQLite
database. All validation errors are returned as Python exceptions that route
handlers convert into user-friendly flash messages.
"""

from __future__ import annotations

import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "acl2.db")

MAX_TITLE_LENGTH = 80
MAX_SIDE_LENGTH = 120


class PickValidationError(ValueError):
    """Raised when a pick payload is empty, malformed, or duplicate."""


class PickNotFoundError(KeyError):
    """Raised when a pick id does not exist in the store."""


def _connection() -> sqlite3.Connection:
    """Return a connection with row factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_table() -> None:
    """Create the saved_picks table if it does not exist yet."""
    with _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS saved_picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'duel',
                side_a TEXT NOT NULL,
                side_b TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_picks_created ON saved_picks(created_at)"
        )
        conn.commit()


def _validate_pick(title: str, side_a: str, side_b: str) -> None:
    """Reject empty, overly long, or malformed pick fields."""
    if not title or not title.strip():
        raise PickValidationError("Title is required and cannot be empty.")
    if len(title.strip()) > MAX_TITLE_LENGTH:
        raise PickValidationError(f"Title cannot exceed {MAX_TITLE_LENGTH} characters.")
    if not side_a or not side_a.strip():
        raise PickValidationError("Scenario A is required and cannot be empty.")
    if not side_b or not side_b.strip():
        raise PickValidationError("Scenario B is required and cannot be empty.")
    if len(side_a.strip()) > MAX_SIDE_LENGTH or len(side_b.strip()) > MAX_SIDE_LENGTH:
        raise PickValidationError(
            f"Scenario labels cannot exceed {MAX_SIDE_LENGTH} characters."
        )


def _is_duplicate(title: str, side_a: str, side_b: str) -> bool:
    """Return True when a pick with the same normalized identity exists."""
    with _connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM saved_picks WHERE title = ? AND side_a = ? AND side_b = ?",
            (title.strip(), side_a.strip(), side_b.strip()),
        ).fetchone()
        return row[0] > 0


def save_pick(title: str, side_a: str, side_b: str, payload: dict[str, Any]) -> int:
    """
    Validate and persist a pick. Returns the new row id.

    Raises PickValidationError for empty/long/duplicate input.
    """
    _validate_pick(title, side_a, side_b)
    if _is_duplicate(title, side_a, side_b):
        raise PickValidationError(
            "This pick already exists. Please choose a different title or scenario pair."
        )

    created_at = datetime.now(timezone.utc).isoformat()
    with _connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO saved_picks (title, mode, side_a, side_b, payload_json, created_at)
            VALUES (?, 'duel', ?, ?, ?, ?)
            """,
            (
                title.strip(),
                side_a.strip(),
                side_b.strip(),
                json.dumps(payload, ensure_ascii=False),
                created_at,
            ),
        )
        conn.commit()
        return cursor.lastrowid


def list_picks() -> list[dict[str, Any]]:
    """Return all picks ordered by newest first."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM saved_picks ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_pick(pick_id: int) -> None:
    """Delete one pick by id. Raises PickNotFoundError when absent."""
    with _connection() as conn:
        cursor = conn.execute("DELETE FROM saved_picks WHERE id = ?", (pick_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise PickNotFoundError(f"Pick with id {pick_id} was not found.")
