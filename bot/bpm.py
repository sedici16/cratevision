"""BPM and key lookup via GetSongBPM API."""
import logging
import requests

logger = logging.getLogger(__name__)

API_BASE = "https://api.getsong.co"


def get_bpm(artist: str, title: str, api_key: str) -> dict | None:
    if not api_key:
        return None

    # Use only first artist if multiple are listed
    first_artist = artist.split(",")[0].split("&")[0].split("/")[0].strip()

    result = _search(f"song:{title} artist:{first_artist}", "both", api_key)
    if not result:
        result = _search(title, "song", api_key)
    if not result or not result.get("bpm"):
        return None
    return result


def _search(lookup: str, search_type: str, api_key: str) -> dict | None:
    try:
        resp = requests.get(
            f"{API_BASE}/search/",
            params={"api_key": api_key, "type": search_type, "lookup": lookup, "limit": 1},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json().get("search", [])
        if not data or isinstance(data, dict):
            return None
        song = data[0]
        bpm = song.get("tempo")
        if not bpm:
            return None
        return {
            "bpm":          int(bpm),
            "key":          song.get("key_of"),
            "danceability": song.get("danceability"),
        }
    except Exception as e:
        logger.warning(f"BPM lookup failed for {lookup}: {e}")
        return None
