import os
import sys
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_TOKEN = os.getenv("hf")
DISCOGS_CONSUMER_KEY = os.getenv("DISCOGS_CONSUMER_KEY")
DISCOGS_CONSUMER_SECRET = os.getenv("DISCOGS_CONSUMER_SECRET")

HF_API_URL = "https://router.huggingface.co/v1/chat/completions"
VISION_MODEL = "Qwen/Qwen2.5-VL-7B-Instruct"
ANALYST_MODEL = "Qwen/Qwen2.5-72B-Instruct"

DISCOGS_BASE_URL = "https://api.discogs.com"
DISCOGS_USER_AGENT = "CrateVision/1.0"

_REQUIRED = {
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "hf": HF_TOKEN,
    "DISCOGS_CONSUMER_KEY": DISCOGS_CONSUMER_KEY,
    "DISCOGS_CONSUMER_SECRET": DISCOGS_CONSUMER_SECRET,
}


def validate():
    missing = [name for name, val in _REQUIRED.items() if not val]
    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your keys.")
        sys.exit(1)
