"""Tests for the analyst verdict parsing logic."""
import requests
from unittest.mock import patch, MagicMock
from bot.analyst import analyze_release


SAMPLE_SUMMARY = {
    "artists": "ABBA",
    "title": "The Singles",
    "year": 1982,
    "country": "Australia",
    "label": "RCA",
    "catno": "VPK2 6648",
    "formats": "Vinyl - LP, Compilation",
    "genres": "Rock, Pop",
    "styles": "Europop, Disco",
    "have": 4,
    "want": 28,
    "rating_avg": 5.0,
    "rating_count": 1,
    "lowest_price": 25.00,
    "num_for_sale": 3,
}


def _mock_response(content):
    """Create a mock requests response with given LLM content."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }
    return mock_resp


@patch("bot.analyst.requests.post")
def test_parse_buy_verdict(mock_post):
    """Test that BUY verdict is correctly parsed."""
    mock_post.return_value = _mock_response(
        "VERDICT: BUY\nREASONING: High demand.\nCONTEXT: Classic album."
    )
    result = analyze_release(SAMPLE_SUMMARY)
    assert result["verdict"] == "BUY"
    assert result["reasoning"] == "High demand."
    assert result["context"] == "Classic album."


@patch("bot.analyst.requests.post")
def test_parse_skip_verdict(mock_post):
    """Test that SKIP verdict is correctly parsed."""
    mock_post.return_value = _mock_response(
        "VERDICT: SKIP\nREASONING: Very common record.\nCONTEXT: Millions pressed."
    )
    result = analyze_release(SAMPLE_SUMMARY)
    assert result["verdict"] == "SKIP"
    assert result["reasoning"] == "Very common record."


@patch("bot.analyst.requests.post")
def test_parse_mild_verdict(mock_post):
    """Test that MILD verdict is correctly parsed."""
    mock_post.return_value = _mock_response(
        "VERDICT: MILD\nREASONING: Decent demand.\nCONTEXT: Worth it if cheap."
    )
    result = analyze_release(SAMPLE_SUMMARY)
    assert result["verdict"] == "MILD"


@patch("bot.analyst.requests.post")
def test_mild_not_confused_with_buy(mock_post):
    """Test that MILD is not parsed as BUY (both contain 'buy'-like text)."""
    mock_post.return_value = _mock_response(
        "VERDICT: MILD\nREASONING: Not a must-buy but decent."
    )
    result = analyze_release(SAMPLE_SUMMARY)
    assert result["verdict"] == "MILD"


@patch("bot.analyst.requests.post")
def test_api_failure_returns_na(mock_post):
    """Test that API failure returns N/A verdict."""
    mock_post.side_effect = requests.RequestException("Connection error")
    result = analyze_release(SAMPLE_SUMMARY)
    assert result["verdict"] == "N/A"
    assert "unavailable" in result["reasoning"].lower()


@patch("bot.analyst.requests.post")
def test_vinted_data_included(mock_post):
    """Test that Vinted data is passed to the LLM prompt."""
    mock_post.return_value = _mock_response(
        "VERDICT: BUY\nREASONING: Cheap on Vinted.\nCONTEXT: Good flip."
    )
    vinted = {
        "available": True,
        "count": 5,
        "lowest_price": 8.0,
        "highest_price": 20.0,
        "currency": "GBP",
        "listings": [{"title": "ABBA vinyl", "price": 8.0, "currency": "GBP"}],
    }
    result = analyze_release(SAMPLE_SUMMARY, vinted)
    assert result["verdict"] == "BUY"
    # Verify Vinted data was in the prompt
    call_args = mock_post.call_args
    prompt = call_args[1]["json"]["messages"][0]["content"]
    assert "8.0 GBP" in prompt


@patch("bot.analyst.requests.post")
def test_no_context_is_ok(mock_post):
    """Test that missing CONTEXT line doesn't break parsing."""
    mock_post.return_value = _mock_response(
        "VERDICT: SKIP\nREASONING: Not worth it."
    )
    result = analyze_release(SAMPLE_SUMMARY)
    assert result["verdict"] == "SKIP"
    assert result["context"] == ""
