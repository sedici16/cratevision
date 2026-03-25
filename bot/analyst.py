import json
import logging
import requests
from bot.config import HF_TOKEN, HF_API_URL, ANALYST_MODEL

logger = logging.getLogger(__name__)

ANALYST_PROMPT = """You are a vinyl record market analyst helping a crate digger at a flea market or charity shop.
They found a record and need to know: is it worth picking up?

Your job is to assess the record based on collector demand and resale value.

Decision criteria (in order of importance):
1. WANT/HAVE RATIO on Discogs — this is the #1 signal. High want + low have = desirable & rare.
2. DISCOGS PRICE — what collectors actually pay
3. VINTED PRICES — what it sells for on the second-hand market (this is what they could flip it for)
4. NUMBER FOR SALE — fewer for sale = harder to find
5. FORMAT — original pressings worth more than reissues
6. YEAR & COUNTRY — early pressings, Japanese, UK first press etc. are more collectible

Discogs data:
{discogs_data}

Vinted market data:
{vinted_data}

Give one of three verdicts:
- SKIP — common record, low demand, not worth the space
- MILD — decent record, some demand, worth picking up if cheap
- BUY — high demand, good resale value, grab it

Respond in this exact format:
VERDICT: BUY, MILD, or SKIP
REASONING: your market analysis (2-3 sentences max)
CONTEXT: brief interesting info about this record from your knowledge — why it matters, notable tracks, samples used by other artists, collectibility tips, fun facts (2-3 sentences max, skip if you don't know enough)"""


def analyze_release(release_summary: dict, vinted_data: dict = None) -> dict:
    """Send release + Vinted data to 70B LLM for buy/skip analysis."""
    # Prepare Discogs data for the LLM
    discogs_data = {
        "artist": release_summary["artists"],
        "title": release_summary["title"],
        "year": release_summary["year"],
        "country": release_summary["country"],
        "label": release_summary["label"],
        "catalog_number": release_summary["catno"],
        "format": release_summary["formats"],
        "genres": release_summary["genres"],
        "styles": release_summary["styles"],
        "have": release_summary["have"],
        "want": release_summary["want"],
        "rating": f"{release_summary['rating_avg']}/5 ({release_summary['rating_count']} votes)",
        "lowest_price": release_summary["lowest_price"],
        "num_for_sale": release_summary["num_for_sale"],
    }

    # Prepare Vinted data
    if vinted_data and vinted_data.get("available") and vinted_data.get("count", 0) > 0:
        vinted_str = json.dumps({
            "listings_found": vinted_data["count"],
            "lowest_price": f"{vinted_data['lowest_price']} {vinted_data['currency']}",
            "highest_price": f"{vinted_data['highest_price']} {vinted_data['currency']}",
            "sample_listings": [
                f"{l['title']} - {l['price']} {l['currency']}"
                for l in vinted_data.get("listings", [])[:3]
            ],
        }, indent=2)
    elif vinted_data and not vinted_data.get("available"):
        vinted_str = "Vinted data unavailable"
    else:
        vinted_str = "No Vinted listings found for this release"

    prompt = ANALYST_PROMPT.format(
        discogs_data=json.dumps(discogs_data, indent=2),
        vinted_data=vinted_str,
    )

    payload = {
        "model": ANALYST_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
    }

    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(HF_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()

        # Parse verdict and reasoning
        first_line = content.upper().split("\n")[0]
        if "BUY" in first_line and "MILD" not in first_line:
            verdict = "BUY"
        elif "MILD" in first_line:
            verdict = "MILD"
        else:
            verdict = "SKIP"
        reasoning = content
        context = ""
        # Extract reasoning and context parts
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.upper().startswith("REASONING:"):
                reasoning = stripped.split(":", 1)[1].strip()
            elif stripped.upper().startswith("CONTEXT:"):
                context = stripped.split(":", 1)[1].strip()

        return {"verdict": verdict, "reasoning": reasoning, "context": context}
    except requests.RequestException as e:
        logger.error("Analyst API request failed: %s", e)
        return {"verdict": "N/A", "reasoning": "Analysis unavailable.", "context": ""}
    except (KeyError, IndexError) as e:
        logger.error("Failed to parse analyst response: %s", e)
        return {"verdict": "N/A", "reasoning": "Analysis unavailable.", "context": ""}
