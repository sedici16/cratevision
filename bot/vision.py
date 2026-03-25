import base64
import json
import logging
import time
import requests
from bot.config import HF_TOKEN, HF_API_URL, VISION_MODEL

logger = logging.getLogger(__name__)

# Fallback models in case primary is down
VISION_MODELS = [
    VISION_MODEL,
    "Qwen/Qwen3-VL-8B-Instruct",
    "google/gemma-3-27b-it",
]

VISION_PROMPT = """You are a vinyl record expert. Analyze this image of a vinyl record cover or label.
Extract the following information and return it as JSON:
{
  "artist": "...",
  "title": "...",
  "label": "...",
  "catalog_number": "...",
  "year": "...",
  "format": "...",
  "confidence": "high|medium|low",
  "notes": "..."
}
If this is not a vinyl record, set confidence to "none" and explain in notes.
Return ONLY valid JSON, no other text."""


def extract_vinyl_info(image_bytes: bytes, media_type: str = "image/jpeg") -> dict | None:
    """Send image to vision model and extract vinyl record info. Retries with fallback models."""
    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }

    for model in VISION_MODELS:
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media_type};base64,{image_base64}"},
                        },
                        {"type": "text", "text": VISION_PROMPT},
                    ],
                }
            ],
            "max_tokens": 500,
        }

        # Try up to 2 times per model
        for attempt in range(2):
            try:
                logger.info("Vision attempt %d with model %s", attempt + 1, model)
                response = requests.post(HF_API_URL, headers=headers, json=payload, timeout=90)
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"]

                # Strip markdown code fences if present
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1]
                    content = content.rsplit("```", 1)[0]

                return json.loads(content)
            except requests.RequestException as e:
                logger.warning("Vision API request failed (model=%s, attempt=%d): %s", model, attempt + 1, e)
                if attempt == 0:
                    time.sleep(2)
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.error("Failed to parse vision response (model=%s): %s", model, e)
                break  # Don't retry parse errors, try next model

    logger.error("All vision models failed")
    return None
