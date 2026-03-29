import logging
import re
import requests
from bot.config import DISCOGS_CONSUMER_KEY, DISCOGS_CONSUMER_SECRET, DISCOGS_BASE_URL, DISCOGS_USER_AGENT

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": DISCOGS_USER_AGENT}
AUTH_PARAMS = {"key": DISCOGS_CONSUMER_KEY, "secret": DISCOGS_CONSUMER_SECRET}


def search_release(vinyl_info: dict) -> list[dict]:
    """Search Discogs for matching releases. Tries multiple strategies."""
    artist = vinyl_info.get("artist", "")
    title = vinyl_info.get("title", "")
    catno = vinyl_info.get("catalog_number", "")

    # Use format from vision/correction if provided, default to Vinyl
    fmt = vinyl_info.get("format", "Vinyl") or "Vinyl"
    # Map common names to Discogs format values
    fmt_map = {"lp": "Vinyl", "vinyl": "Vinyl", "record": "Vinyl", "vinyl record": "Vinyl",
               "12\"": "Vinyl", "7\"": "Vinyl", "10\"": "Vinyl", "cassette": "Cassette",
               "tape": "Cassette", "cd": "CD", "compact disc": "CD"}
    # Normalize: strip size prefixes like '12" vinyl' → 'vinyl', then map
    fmt_lower = fmt.lower().strip()
    fmt_stripped = re.sub(r'^\d+"\s*', '', fmt_lower).strip() or fmt_lower
    discogs_format = fmt_map.get(fmt_stripped, fmt_map.get(fmt_lower, "Vinyl"))

    logger.info("Discogs search input — artist=%r, title=%r, catno=%r, format=%r (mapped=%r)",
                artist, title, catno, fmt, discogs_format)

    strategies = []
    # Strategy 1: artist + title
    if artist and title:
        strategies.append({"artist": artist, "release_title": title, "type": "release", "format": discogs_format})
    # Strategy 2: catalog number + artist (avoid blind catno matches)
    if catno and artist:
        strategies.append({"catno": catno, "artist": artist, "type": "release", "format": discogs_format})
    # Strategy 2b: catalog number + title
    if catno and title:
        strategies.append({"catno": catno, "release_title": title, "type": "release", "format": discogs_format})
    # Strategy 3: title only
    if title:
        strategies.append({"release_title": title, "type": "release", "format": discogs_format})
    # Strategy 4: loose query (artist + title as free text) — catches vision typos
    if artist and title:
        strategies.append({"q": f"{artist} {title}", "type": "release", "format": discogs_format})
    # Strategy 5: loose query without format filter
    if artist and title:
        strategies.append({"q": f"{artist} {title}", "type": "release"})
    # Strategy 6: keyword-stripped query — remove filler/noise words from vision output
    if artist and title:
        filler = {"a", "an", "the", "that", "thats", "that's", "this", "its", "it's", "is", "of", "and", "or", "in", "on", "to"}
        words = re.sub(r"[^a-zA-Z0-9\s]", " ", title).split()
        keywords = [w for w in words if w.lower() not in filler and len(w) > 1]
        stripped_q = f"{artist} {' '.join(keywords)}".strip()
        if stripped_q != f"{artist} {title}":
            strategies.append({"q": stripped_q, "type": "release"})

    for i, params in enumerate(strategies, 1):
        params.update(AUTH_PARAMS)
        params["per_page"] = 5
        try:
            r = requests.get(
                f"{DISCOGS_BASE_URL}/database/search",
                params=params,
                headers=HEADERS,
                timeout=15,
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            logger.info("Discogs strategy %d returned %d results", i, len(results))
            if results:
                return results
        except requests.RequestException as e:
            logger.error("Discogs search failed (strategy %d): %s", i, e)

    logger.warning("Discogs: all strategies exhausted, no results found")
    return []


def get_release_details(release_id: int) -> dict | None:
    """Fetch full release details from Discogs."""
    try:
        r = requests.get(
            f"{DISCOGS_BASE_URL}/releases/{release_id}",
            params=AUTH_PARAMS,
            headers=HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.error("Discogs release fetch failed: %s", e)
        return None


def build_release_summary(release: dict) -> dict:
    """Extract the key fields we need from a full release response."""
    # Tracklist
    tracklist = []
    for t in release.get("tracklist", []):
        if t.get("type_") == "track":
            pos = t.get("position", "")
            title = t.get("title", "")
            dur = t.get("duration", "")
            line = f"{pos}. {title}" if pos else title
            if dur:
                line += f" ({dur})"
            tracklist.append(line)

    # Listening links (Invidious for ad-free, YouTube as fallback)
    videos = release.get("videos", [])
    listen_url = None
    youtube_url = None
    if videos:
        youtube_url = videos[0]["uri"]
        listen_url = youtube_url.replace("www.youtube.com", "yewtu.be").replace("youtube.com", "yewtu.be")

    # Cover image
    images = release.get("images", [])
    cover_url = None
    for img in images:
        if img.get("type") == "primary":
            cover_url = img["uri"]
            break
    if not cover_url and images:
        cover_url = images[0]["uri"]

    # Labels
    labels = release.get("labels", [])
    label_name = labels[0]["name"] if labels else "Unknown"
    catno = labels[0].get("catno", "") if labels else ""

    community = release.get("community", {})
    rating = community.get("rating", {})

    return {
        "id": release.get("id"),
        "title": release.get("title", ""),
        "artists": ", ".join(a["name"] for a in release.get("artists", [])),
        "year": release.get("year"),
        "country": release.get("country", ""),
        "label": label_name,
        "catno": catno,
        "formats": ", ".join(
            f.get("name", "") + (" - " + ", ".join(f.get("descriptions", [])) if f.get("descriptions") else "")
            for f in release.get("formats", [])
        ),
        "genres": ", ".join(release.get("genres", [])),
        "styles": ", ".join(release.get("styles", [])),
        "have": community.get("have", 0),
        "want": community.get("want", 0),
        "rating_avg": rating.get("average", 0),
        "rating_count": rating.get("count", 0),
        "lowest_price": release.get("lowest_price"),
        "num_for_sale": release.get("num_for_sale", 0),
        "tracklist": tracklist,
        "listen_url": listen_url,
        "youtube_url": youtube_url,
        "cover_url": cover_url,
        "discogs_url": release.get("uri", ""),
        "notes": release.get("notes", ""),
    }
