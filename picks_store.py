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
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "acl2.db")

MAX_TITLE_LENGTH = 80
MAX_SIDE_LENGTH = 120
MAX_PAYLOAD_BYTES = 4096
ALLOWED_MODES = ("duel", "squad", "home_away", "head_to_head")
ALLOWED_RESULTS = ("win", "draw", "loss")


class PickValidationError(ValueError):
    """Raised when a pick payload is empty, malformed, or duplicate."""


class PickNotFoundError(KeyError):
    """Raised when a pick id does not exist in the store."""


@contextmanager
def _connection():
    """
    Yield a connection with row factory enabled and always close it.

    sqlite3's own context manager only commits/rolls back; it does not close the
    connection, which leaked a file handle per request in the original code.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
        # Enforce uniqueness at the database level so concurrent requests cannot
        # slip a duplicate past the _is_duplicate() check.
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_picks_identity
            ON saved_picks(title, side_a, side_b)
            """
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


def _validate_payload(payload: dict[str, Any], mode: str) -> str:
    """Serialize and sanity-check the pick payload; returns its JSON text."""
    if mode not in ALLOWED_MODES:
        raise PickValidationError(f"Unknown pick mode '{mode}'.")
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise PickValidationError("Pick payload must be an object.")
    for key in ("result_a", "result_b"):
        if key in payload and payload[key] not in ALLOWED_RESULTS:
            raise PickValidationError(
                f"Invalid scenario result '{payload[key]}'; use win, draw, or loss."
            )
    try:
        encoded = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise PickValidationError(f"Pick payload is not serializable: {exc}") from exc
    if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise PickValidationError("Pick payload is too large.")
    return encoded


def save_pick(
    title: str,
    side_a: str,
    side_b: str,
    payload: dict[str, Any],
    mode: str = "duel",
) -> int:
    """
    Validate and persist a pick. Returns the new row id.

    Raises PickValidationError for empty/long/duplicate/malformed input.
    """
    _validate_pick(title, side_a, side_b)
    payload_json = _validate_payload(payload, mode)
    if _is_duplicate(title, side_a, side_b):
        raise PickValidationError(
            "This pick already exists. Please choose a different title or scenario pair."
        )

    created_at = datetime.now(timezone.utc).isoformat()
    with _connection() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO saved_picks (title, mode, side_a, side_b, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    title.strip(),
                    mode,
                    side_a.strip(),
                    side_b.strip(),
                    payload_json,
                    created_at,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError as exc:
            # Unique index caught a concurrent duplicate that slipped past the check.
            raise PickValidationError(
                "This pick already exists. Please choose a different title or scenario pair."
            ) from exc
        return cursor.lastrowid


def list_picks() -> list[dict[str, Any]]:
    """Return all picks ordered by newest first, with decoded payload."""
    with _connection() as conn:
        rows = conn.execute(
            "SELECT * FROM saved_picks ORDER BY created_at DESC, id DESC"
        ).fetchall()
    picks = []
    for row in rows:
        pick = dict(row)
        try:
            pick["payload"] = json.loads(pick.get("payload_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            pick["payload"] = {}
        pick["created_label"] = _format_created_at(pick.get("created_at"))
        pick["mode_label"] = MODE_LABELS.get(pick.get("mode"), "Perbandingan")
        picks.append(pick)
    return picks


MODE_LABELS = {
    "duel": "Scenario Duel",
    "squad": "Squad Composition",
    "home_away": "Home vs Away",
    "head_to_head": "Head-to-Head",
}


def _format_created_at(value: str | None) -> str:
    """Render an ISO timestamp as a short readable UTC label."""
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value).strftime("%d %b %Y, %H:%M UTC")
    except (TypeError, ValueError):
        return str(value)


def delete_pick(pick_id: int) -> None:
    """Delete one pick by id. Raises PickNotFoundError when absent."""
    with _connection() as conn:
        cursor = conn.execute("DELETE FROM saved_picks WHERE id = ?", (pick_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise PickNotFoundError(f"Pick with id {pick_id} was not found.")
