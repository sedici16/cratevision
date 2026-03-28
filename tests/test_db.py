"""Tests for the analytics database module."""
import os
import tempfile
from unittest.mock import patch
from bot.db import init_db, log_search, get_stats, get_verdict_distribution, get_top_artists, get_recent_searches, get_users


def _use_temp_db(tmp_path):
    """Patch DB_PATH to a temp file."""
    return patch("bot.db.DB_PATH", tmp_path / "test.db")


class TestDb:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        from pathlib import Path
        self.db_path = Path(self.tmp) / "test.db"
        self.patcher = patch("bot.db.DB_PATH", self.db_path)
        self.patcher.start()
        init_db()

    def teardown_method(self):
        self.patcher.stop()
        if self.db_path.exists():
            os.remove(self.db_path)

    def test_empty_stats(self):
        stats = get_stats()
        assert stats["total_users"] == 0
        assert stats["total_searches"] == 0
        assert stats["searches_today"] == 0

    def test_log_search_creates_user(self):
        log_search(123, "testuser", "Test", "ABBA", "Waterloo", "BUY", 9999)
        users = get_users()
        assert len(users) == 1
        assert users[0]["username"] == "testuser"
        assert users[0]["search_count"] == 1

    def test_log_search_increments_count(self):
        log_search(123, "testuser", "Test", "ABBA", "Waterloo", "BUY", 9999)
        log_search(123, "testuser", "Test", "Daft Punk", "RAM", "MILD", 1234)
        users = get_users()
        assert users[0]["search_count"] == 2

    def test_stats_after_searches(self):
        log_search(1, "alice", "Alice", "ABBA", "Waterloo", "BUY")
        log_search(2, "bob", "Bob", "Daft Punk", "RAM", "SKIP")
        stats = get_stats()
        assert stats["total_users"] == 2
        assert stats["total_searches"] == 2
        assert stats["searches_today"] == 2

    def test_verdict_distribution(self):
        log_search(1, "a", "A", "X", "Y", "BUY")
        log_search(1, "a", "A", "X", "Y", "BUY")
        log_search(2, "b", "B", "X", "Y", "SKIP")
        dist = get_verdict_distribution()
        verdicts = {d["verdict"]: d["count"] for d in dist}
        assert verdicts["BUY"] == 2
        assert verdicts["SKIP"] == 1

    def test_top_artists(self):
        log_search(1, "a", "A", "ABBA", "Y", "BUY")
        log_search(1, "a", "A", "ABBA", "Z", "BUY")
        log_search(2, "b", "B", "Daft Punk", "RAM", "SKIP")
        top = get_top_artists()
        assert top[0]["artist"] == "ABBA"
        assert top[0]["count"] == 2

    def test_recent_searches(self):
        log_search(1, "alice", "Alice", "ABBA", "Waterloo", "BUY", 9999)
        recent = get_recent_searches()
        assert len(recent) == 1
        assert recent[0]["artist"] == "ABBA"
        assert recent[0]["username"] == "alice"
