import logging
import re
import time
import cloudscraper
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE = "https://www.whosampled.com"
_STRIP_POS = re.compile(r"^[A-Za-z]?\d+[\.\s]+")
_STRIP_DUR = re.compile(r"\s*\(\d+:\d+\)\s*$")


def get_sample_data(artist: str, title: str) -> dict | None:
    """
    Single track lookup. Returns dict with url, contains, sampled_in. None on failure.
    """
    track_url = _find_track_url(artist, title)
    if not track_url:
        return None
    return _scrape_track(track_url)


def get_album_sample_data(artist: str, tracklist: list[str]) -> list[dict]:
    """
    Look up every track in tracklist and return only tracks that have
    sample connections. Each entry: {track, url, contains, sampled_in}.
    Skips tracks with no connections. Limits to first 8 tracks to avoid
    rate-limiting.
    """
    results = []
    for raw_track in tracklist[:8]:
        clean = _STRIP_DUR.sub("", _STRIP_POS.sub("", raw_track)).strip()
        if not clean:
            continue
        try:
            data = get_sample_data(artist, clean)
        except Exception as e:
            logger.warning("WhoSampled error for %s: %s", clean, e)
            data = None
        if data:
            data["track"] = clean
            results.append(data)
        time.sleep(0.6)  # polite rate limiting
    return results


def _find_track_url(artist: str, title: str) -> str | None:
    scraper = cloudscraper.create_scraper()
    q = f"{artist} {title}"
    try:
        r = scraper.get(f"{BASE}/search/tracks/", params={"q": q}, timeout=10)
        r.raise_for_status()
    except Exception as e:
        logger.warning("WhoSampled search failed: %s", e)
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/") and href.count("/") == 3 and not any(
            skip in href for skip in ["/search/", "/user/", "/buy/", "/browse/", "/sample/", "/static/", "/contact/", "/sitemap/", "/about/", "/advertise/", "/privacy/", "/terms/"]
        ):
            return BASE + href
    return None


def _scrape_track(url: str) -> dict | None:
    scraper = cloudscraper.create_scraper()
    try:
        r = scraper.get(url, timeout=10)
        r.raise_for_status()
    except Exception as e:
        logger.warning("WhoSampled track fetch failed: %s", e)
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    contains = []
    sampled_in = []

    for section in soup.find_all("section", class_="subsection"):
        h = section.find(["h2", "h3"])
        if not h:
            continue
        heading = h.get_text(strip=True).lower()

        if "contains sample" in heading:
            contains = _parse_table(section)
        elif "sampled in" in heading:
            sampled_in = _parse_table(section)

    if not contains and not sampled_in:
        return None

    return {"url": url, "contains": contains, "sampled_in": sampled_in}


def _parse_table(section) -> list:
    entries = []
    for row in section.select("table.tdata tr"):
        tds = row.find_all("td")
        if len(tds) < 3:
            continue
        track_a = tds[1].find("a")
        artist_a = tds[2].find("a")
        year_td = tds[3] if len(tds) > 3 else None
        badge = row.find("span", class_="tdata__badge")

        entries.append({
            "track": track_a.get_text(strip=True) if track_a else "",
            "artist": artist_a.get_text(strip=True) if artist_a else "",
            "year": year_td.get_text(strip=True) if year_td else "",
            "type": badge.get_text(strip=True) if badge else "",
        })
    return entries
