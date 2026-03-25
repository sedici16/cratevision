import logging
import cloudscraper

logger = logging.getLogger(__name__)

VINTED_DOMAIN = "https://www.vinted.co.uk"


def _get_token() -> tuple:
    """Get a cloudscraper session with a valid Vinted access token."""
    scraper = cloudscraper.create_scraper()
    scraper.get(VINTED_DOMAIN, timeout=10)

    r = scraper.post(f"{VINTED_DOMAIN}/oauth/token", json={
        "grant_type": "client_credentials",
        "client_id": "web",
        "scope": "public",
    }, timeout=10)
    r.raise_for_status()
    token = r.json()["access_token"]
    return scraper, token


def search_vinted(artist: str, title: str, fmt: str = "vinyl") -> dict:
    """Search Vinted for listings. Returns summary dict or error info."""
    query = f"{artist} {title} {fmt}".strip()

    try:
        scraper, token = _get_token()

        r = scraper.get(
            f"{VINTED_DOMAIN}/api/v2/catalog/items",
            params={
                "search_text": query,
                "per_page": 10,
                "order": "relevance",
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )

        if r.status_code != 200:
            logger.warning("Vinted search returned status %d", r.status_code)
            return {"available": False, "error": f"Vinted status {r.status_code}"}

        data = r.json()
        items = data.get("items", [])

        if not items:
            return {"available": True, "count": 0, "listings": []}

        listings = []
        prices = []
        for item in items[:5]:
            price_data = item.get("price", {})
            price = float(price_data.get("amount", 0))
            currency = price_data.get("currency_code", "GBP")
            prices.append(price)
            listings.append({
                "title": item.get("title", ""),
                "price": price,
                "currency": currency,
                "url": item.get("url", ""),
            })

        return {
            "available": True,
            "count": len(items),
            "lowest_price": min(prices),
            "highest_price": max(prices),
            "currency": listings[0]["currency"],
            "listings": listings,
        }

    except Exception as e:
        logger.warning("Vinted search failed: %s", e)
        return {"available": False, "error": str(e)}
