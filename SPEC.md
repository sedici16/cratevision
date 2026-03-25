# CrateVision - App Specification

## Overview
CrateVision is a Telegram bot that identifies vinyl records from photos and tells you if they're worth buying. It combines AI vision, Discogs data, and LLM analysis to give you a quick buy/skip verdict.

## Pipeline
1. User sends a photo of a vinyl record to the Telegram bot
2. **Qwen2.5-VL-7B** (vision) reads the image → extracts artist, title, label, catalog number, year
3. **Discogs API** searches for matching releases → gets want/have counts, price, tracklist, cover art, YouTube links
4. **70B LLM** (Qwen2.5-72B or Llama 3.3-70B) analyzes the Discogs data → buy/skip recommendation based on rarity (want vs have ratio), price, desirability
5. Bot returns: cover image, LLM analysis, tracklist, listening link, Discogs link

## Tech Stack
- **Language:** Python 3.11+
- **Telegram:** python-telegram-bot v21 (async)
- **Vision Model:** Qwen2.5-VL-7B-Instruct via HF Inference API
- **Analysis LLM:** 70B model (Qwen2.5-72B-Instruct or Llama 3.3-70B-Instruct) via HF Inference API
- **Database:** Discogs API (key/secret auth)
- **Config:** python-dotenv

## Features

### MVP
- `/start` - Welcome message with usage instructions
- `/help` - How to use the bot
- **Photo handler** - Accepts photos (compressed) and image files (uncompressed)
- Vision analysis: extracts artist, title, label, catalog number, year, format
- Discogs search: finds matching releases with full release details
- LLM analysis: buy/skip recommendation with reasoning
- Displays: cover art, analysis, listening link (YouTube), Discogs link
- Typing indicator while processing

### Future (optional)
- Barcode reading for precise identification
- Collection tracking / history
- Multiple photo support in one message
- Price trend analysis

## Project Structure
```
cratevision/
├── .env                  # API keys (gitignored)
├── .env.example          # Template
├── .gitignore
├── requirements.txt
├── SPEC.md               # This file
├── bot/
│   ├── __init__.py
│   ├── main.py           # Entry point, handler registration
│   ├── config.py         # Environment variable loading
│   ├── handlers.py       # Telegram command & message handlers
│   ├── vision.py         # HF Vision API / Qwen2.5-VL integration
│   ├── discogs.py        # Discogs API search + full release fetch
│   └── analyst.py        # 70B LLM analysis - buy/skip recommendation
```

## Environment Variables
| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `hf` | Yes | Hugging Face API token |
| `DISCOGS_CONSUMER_KEY` | Yes | Discogs API consumer key |
| `DISCOGS_CONSUMER_SECRET` | Yes | Discogs API consumer secret |

## API Details

### HF Inference API - Vision (Step 2)
- **Endpoint:** `https://router.huggingface.co/v1/chat/completions`
- **Model:** `Qwen/Qwen2.5-VL-7B-Instruct`
- **Input:** Base64-encoded image + structured prompt
- **Output:** JSON with artist, title, label, catalog_number, year, confidence, notes

### Discogs API (Step 3)
- **Search endpoint:** `https://api.discogs.com/database/search`
- **Release endpoint:** `https://api.discogs.com/releases/{id}`
- **Auth:** key/secret query parameters
- **Search strategy:** artist + title → catno → title only
- **Rate limit:** 60 requests/minute
- **Data used for analysis:**
  - `community.want` / `community.have` — rarity signal
  - `community.rating` — quality signal
  - `lowest_price` / `num_for_sale` — market value
  - `tracklist` — track listing
  - `videos` — YouTube listening links
  - `images` — cover art to display in Telegram
  - `country`, `year`, `format`, `labels`, `genres`, `styles`

### HF Inference API - Analysis LLM (Step 4)
- **Endpoint:** `https://router.huggingface.co/v1/chat/completions`
- **Model:** `Qwen/Qwen2.5-72B-Instruct` (or `meta-llama/Llama-3.3-70B-Instruct`)
- **Input:** Structured Discogs data (want/have, price, format, year, genre, etc.)
- **Output:** Buy/skip verdict with reasoning
- **Prompt considerations:**
  - High want / low have = rare & desirable → BUY signal
  - Low price + high want = undervalued → STRONG BUY
  - High have / low want = common → SKIP unless cheap
  - Original pressing vs reissue matters
  - Genre/style context for collectibility

### Telegram Bot API
- Receives photos via `filters.PHOTO` and `filters.Document.IMAGE`
- Uses largest available photo size (`photo[-1]`)
- Sends cover art as photo with caption
- Message length limit: 4096 characters (caption limit: 1024)
- Uses HTML parse mode for formatting

## Error Handling
| Scenario | Response |
|----------|----------|
| Not a vinyl record | "I couldn't identify a vinyl record. Please send a clear photo of a record cover or label." |
| Low confidence from vision | Show what was found with a disclaimer |
| HF API error/timeout | "Sorry, I'm having trouble right now. Please try again." |
| Discogs returns no results | Show vision results only, skip analysis |
| Discogs API error | Show vision results only, skip analysis |
| LLM analysis fails | Show Discogs data without recommendation |

## Response Format Example
The bot sends the Discogs cover image as a photo, with a caption containing:

```
🎵 ABBA - The Singles (The First Ten Years)
📅 1982 · 🏷️ RCA · 🇦🇺 Australia
💿 2×LP, Compilation
📋 Cat#: VPK2 6648

📊 Market:
   👥 4 have · 28 want · ⭐ 5.0/5
   💰 Lowest price: N/A · 0 for sale

🤖 Analysis:
   🟢 BUY — High demand (28 want) with very few
   copies available (4 have). This Australian RCA
   pressing is scarce. The 7:1 want/have ratio
   signals strong collector interest. Worth picking
   up if priced reasonably.

🎧 Listen: https://youtube.com/watch?v=VYpHzPvhQT0
🔗 Discogs: https://www.discogs.com/release/9452364
```

If the caption exceeds 1024 chars, send cover as photo + analysis as a separate text message.
