"""Tests for Discogs search and release summary building."""
from bot.discogs import build_release_summary


# Sample Discogs API response for testing
SAMPLE_RELEASE = {
    "id": 9452364,
    "title": "The Singles (The First Ten Years)",
    "year": 1982,
    "country": "Australia",
    "uri": "https://www.discogs.com/release/9452364",
    "notes": "Recorded at Polar Studios 1973-1982.",
    "artists": [{"name": "ABBA", "id": 69866}],
    "labels": [{"name": "RCA", "catno": "VPK2 6648", "id": 895}],
    "formats": [{"name": "Vinyl", "qty": "2", "descriptions": ["LP", "Compilation"]}],
    "genres": ["Rock", "Pop"],
    "styles": ["Europop", "Disco"],
    "community": {
        "have": 4,
        "want": 28,
        "rating": {"count": 1, "average": 5.0},
    },
    "lowest_price": 25.00,
    "num_for_sale": 3,
    "tracklist": [
        {"position": "A1", "type_": "track", "title": "Ring Ring", "duration": "3:05"},
        {"position": "A2", "type_": "track", "title": "Waterloo", "duration": "2:45"},
        {"position": "", "type_": "heading", "title": "Side B"},
        {"position": "B1", "type_": "track", "title": "Dancing Queen", "duration": "3:51"},
    ],
    "videos": [
        {"uri": "https://www.youtube.com/watch?v=VYpHzPvhQT0", "title": "ABBA"},
    ],
    "images": [
        {"type": "primary", "uri": "https://i.discogs.com/cover.jpg"},
        {"type": "secondary", "uri": "https://i.discogs.com/back.jpg"},
    ],
}


def test_build_release_summary_basic_fields():
    """Test that basic release fields are correctly extracted."""
    summary = build_release_summary(SAMPLE_RELEASE)
    assert summary["id"] == 9452364
    assert summary["title"] == "The Singles (The First Ten Years)"
    assert summary["artists"] == "ABBA"
    assert summary["year"] == 1982
    assert summary["country"] == "Australia"
    assert summary["label"] == "RCA"
    assert summary["catno"] == "VPK2 6648"


def test_build_release_summary_community():
    """Test that community data (want/have/rating) is extracted."""
    summary = build_release_summary(SAMPLE_RELEASE)
    assert summary["have"] == 4
    assert summary["want"] == 28
    assert summary["rating_avg"] == 5.0
    assert summary["rating_count"] == 1
    assert summary["lowest_price"] == 25.00
    assert summary["num_for_sale"] == 3


def test_build_release_summary_tracklist():
    """Test that tracklist only includes tracks, not headings."""
    summary = build_release_summary(SAMPLE_RELEASE)
    assert len(summary["tracklist"]) == 3  # 3 tracks, heading excluded
    assert "A1. Ring Ring (3:05)" == summary["tracklist"][0]
    assert "B1. Dancing Queen (3:51)" == summary["tracklist"][2]


def test_build_release_summary_listen_urls():
    """Test that YouTube URL is converted to Invidious."""
    summary = build_release_summary(SAMPLE_RELEASE)
    assert "yewtu.be" in summary["listen_url"]
    assert "youtube.com" in summary["youtube_url"]


def test_build_release_summary_cover_image():
    """Test that primary cover image is selected."""
    summary = build_release_summary(SAMPLE_RELEASE)
    assert summary["cover_url"] == "https://i.discogs.com/cover.jpg"


def test_build_release_summary_formats():
    """Test that format string is correctly built."""
    summary = build_release_summary(SAMPLE_RELEASE)
    assert "Vinyl" in summary["formats"]
    assert "LP" in summary["formats"]
    assert "Compilation" in summary["formats"]


def test_build_release_summary_genres():
    """Test that genres and styles are joined."""
    summary = build_release_summary(SAMPLE_RELEASE)
    assert summary["genres"] == "Rock, Pop"
    assert summary["styles"] == "Europop, Disco"


def test_build_release_summary_empty_release():
    """Test that empty/minimal release data doesn't crash."""
    summary = build_release_summary({})
    assert summary["title"] == ""
    assert summary["artists"] == ""
    assert summary["tracklist"] == []
    assert summary["listen_url"] is None
    assert summary["cover_url"] is None
    assert summary["label"] == "Unknown"


def test_build_release_summary_no_primary_image():
    """Test fallback to first image when no primary exists."""
    release = {**SAMPLE_RELEASE, "images": [
        {"type": "secondary", "uri": "https://i.discogs.com/back.jpg"},
    ]}
    summary = build_release_summary(release)
    assert summary["cover_url"] == "https://i.discogs.com/back.jpg"
