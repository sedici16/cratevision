"""SQLite analytics database for tracking users and searches."""
import os
import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cratevision.db"


def _connect():
    """Get a database connection."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    os.makedirs(DB_PATH.parent, exist_ok=True)

    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            search_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            artist TEXT,
            title TEXT,
            verdict TEXT,
            discogs_id INTEGER,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_searches_user ON searches(user_id);
        CREATE INDEX IF NOT EXISTS idx_searches_timestamp ON searches(timestamp);
    """)
    conn.close()
    logger.info("Database initialized at %s", DB_PATH)


def log_search(user_id: int, username: str | None, first_name: str | None,
               artist: str, title: str, verdict: str, discogs_id: int | None = None, youtube_url: str | None = None, bpm: int | None = None, key_of: str | None = None):
    """Log a search and upsert the user record."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    conn = _connect()
    try:
        # Upsert user
        conn.execute("""
            INSERT INTO users (user_id, username, first_name, first_seen, last_seen, search_count)
            VALUES (?, ?, ?, ?, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen = excluded.last_seen,
                search_count = search_count + 1
        """, (user_id, username, first_name, now, now))

        # Insert search
        conn.execute("""
            INSERT INTO searches (user_id, artist, title, verdict, discogs_id, youtube_url, bpm, key_of, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, artist, title, verdict, discogs_id, youtube_url, bpm, key_of, now))

        conn.commit()
    except Exception as e:
        logger.error("Failed to log search: %s", e)
        conn.rollback()
    finally:
        conn.close()


# ── Query helpers for dashboard ──────────────────────────────────────

def get_stats() -> dict:
    """Overview stats: total users, total searches, searches today."""
    conn = _connect()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    total_searches = conn.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    searches_today = conn.execute(
        "SELECT COUNT(*) FROM searches WHERE timestamp LIKE ?", (f"{today}%",)
    ).fetchone()[0]

    conn.close()
    return {
        "total_users": total_users,
        "total_searches": total_searches,
        "searches_today": searches_today,
    }


def get_searches_over_time(days: int = 30) -> list[dict]:
    """Daily search counts for the last N days."""
    conn = _connect()
    rows = conn.execute("""
        SELECT DATE(timestamp) as date, COUNT(*) as count
        FROM searches
        WHERE timestamp >= DATE('now', ?)
        GROUP BY DATE(timestamp)
        ORDER BY date
    """, (f"-{days} days",)).fetchall()
    conn.close()
    return [{"date": r["date"], "count": r["count"]} for r in rows]


def get_verdict_distribution() -> list[dict]:
    """Count of each verdict type."""
    conn = _connect()
    rows = conn.execute("""
        SELECT verdict, COUNT(*) as count
        FROM searches
        WHERE verdict IS NOT NULL
        GROUP BY verdict
        ORDER BY count DESC
    """).fetchall()
    conn.close()
    return [{"verdict": r["verdict"], "count": r["count"]} for r in rows]


def get_top_artists(limit: int = 10) -> list[dict]:
    """Most searched artists."""
    conn = _connect()
    rows = conn.execute("""
        SELECT artist, COUNT(*) as count
        FROM searches
        WHERE artist IS NOT NULL AND artist != ''
        GROUP BY artist
        ORDER BY count DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [{"artist": r["artist"], "count": r["count"]} for r in rows]


def get_recent_searches(limit: int = 50) -> list[dict]:
    """Most recent searches with user info."""
    conn = _connect()
    rows = conn.execute("""
        SELECT s.artist, s.title, s.verdict, s.discogs_id, s.bpm, s.key_of, s.timestamp,
               u.username, u.first_name
        FROM searches s
        JOIN users u ON s.user_id = u.user_id
        ORDER BY s.timestamp DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_users() -> list[dict]:
    """All users ordered by search count."""
    conn = _connect()
    rows = conn.execute("""
        SELECT user_id, username, first_name, first_seen, last_seen, search_count
        FROM users
        ORDER BY search_count DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Per-user queries ─────────────────────────────────────────────────

def get_user(user_id: int) -> dict | None:
    """Get a single user by ID."""
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_searches(user_id: int, limit: int = 100) -> list[dict]:
    """All searches for a specific user."""
    conn = _connect()
    rows = conn.execute("""
        SELECT artist, title, verdict, discogs_id, youtube_url, bpm, key_of, timestamp
        FROM searches WHERE user_id = ?
        ORDER BY timestamp DESC LIMIT ?
    """, (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_stats(user_id: int) -> dict:
    """Stats for a specific user."""
    conn = _connect()
    total = conn.execute(
        "SELECT COUNT(*) FROM searches WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    verdicts = conn.execute("""
        SELECT verdict, COUNT(*) as count FROM searches
        WHERE user_id = ? AND verdict IS NOT NULL
        GROUP BY verdict ORDER BY count DESC
    """, (user_id,)).fetchall()
    top_artists = conn.execute("""
        SELECT artist, COUNT(*) as count FROM searches
        WHERE user_id = ? AND artist IS NOT NULL AND artist != ''
        GROUP BY artist ORDER BY count DESC LIMIT 10
    """, (user_id,)).fetchall()
    conn.close()
    return {
        "total_searches": total,
        "verdicts": [dict(r) for r in verdicts],
        "top_artists": [dict(r) for r in top_artists],
    }
