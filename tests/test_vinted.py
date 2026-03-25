"""Tests for the Vinted search module."""
from unittest.mock import patch, MagicMock
from bot.vinted import search_vinted


def _mock_vinted_response(items):
    """Create mock cloudscraper responses for Vinted."""
    mock_scraper = MagicMock()

    # Mock the initial page load
    mock_page = MagicMock()
    mock_page.status_code = 200

    # Mock the OAuth token
    mock_oauth = MagicMock()
    mock_oauth.status_code = 200
    mock_oauth.raise_for_status = MagicMock()
    mock_oauth.json.return_value = {"access_token": "fake-token"}

    # Mock the search response
    mock_search = MagicMock()
    mock_search.status_code = 200
    mock_search.json.return_value = {"items": items}

    mock_scraper.get.side_effect = [mock_page, mock_search]
    mock_scraper.post.return_value = mock_oauth
    return mock_scraper


@patch("bot.vinted.cloudscraper.create_scraper")
def test_search_returns_results(mock_cs):
    """Test successful Vinted search with results."""
    items = [
        {"title": "ABBA vinyl", "price": {"amount": "10.0", "currency_code": "GBP"}, "url": "https://vinted.co.uk/1"},
        {"title": "ABBA LP", "price": {"amount": "20.0", "currency_code": "GBP"}, "url": "https://vinted.co.uk/2"},
    ]
    mock_cs.return_value = _mock_vinted_response(items)
    result = search_vinted("ABBA", "The Singles")
    assert result["available"] is True
    assert result["count"] == 2
    assert result["lowest_price"] == 10.0
    assert result["highest_price"] == 20.0
    assert result["currency"] == "GBP"
    assert len(result["listings"]) == 2


@patch("bot.vinted.cloudscraper.create_scraper")
def test_search_no_results(mock_cs):
    """Test Vinted search with no results."""
    mock_cs.return_value = _mock_vinted_response([])
    result = search_vinted("Unknown Artist", "Unknown Album")
    assert result["available"] is True
    assert result["count"] == 0


@patch("bot.vinted.cloudscraper.create_scraper")
def test_search_failure(mock_cs):
    """Test Vinted search when API fails."""
    mock_cs.side_effect = Exception("Connection failed")
    result = search_vinted("ABBA", "The Singles")
    assert result["available"] is False
    assert "error" in result
