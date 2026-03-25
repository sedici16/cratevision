# CrateVision

A Telegram bot that identifies vinyl records from photos and tells you if they're worth buying. Built for crate diggers hitting flea markets and charity shops.

## How It Works

1. Snap a photo of a vinyl record (cover or label)
2. Send it to the bot on Telegram
3. Get back: release info, market data, and a buy recommendation

### Pipeline

```
Photo --> AI Vision --> Discogs --> Vinted --> LLM Analyst --> Verdict
         (Qwen VL)    (search)   (prices)   (72B model)
```

- **Vision** - Qwen2.5-VL reads the image and extracts artist, title, label, catalog number
- **Discogs** - Searches for the release, gets want/have ratio, pricing, tracklist, cover art
- **Vinted** - Checks real second-hand market prices
- **LLM Analyst** - Analyzes all data and gives a verdict based on collector demand and resale value

### Verdicts

| Verdict | Meaning |
|---------|---------|
| BUY     | High demand, good resale value, grab it |
| MILD    | Decent record, some demand, worth it if cheap |
| SKIP    | Common record, low demand, not worth the space |

## Example Response

```
ABBA - The Singles (The First Ten Years)
1982 - RCA - Australia
Vinyl - LP, Compilation
Cat#: VPK2 6648
Rock, Pop - Europop, Disco, Vocal

Discogs:
   4 have - 28 want - 5.0/5
   From: $25.00 - 3 for sale

Vinted:
   10 listings - 8.0-20.0 GBP

BUY: High demand with 7:1 want/have ratio. Few copies
available and strong collector interest for this pressing.

Tracklist:
   A1. Ring Ring
   A2. Waterloo
   B1. Dancing Queen
   ...
```

## Features

- Vinyl record identification from photos
- Discogs integration (want/have, pricing, tracklist, cover art, genres)
- Vinted price lookup for real market value
- 3-tier buy recommendation (BUY / MILD / SKIP)
- LLM-generated context (album history, collectibility tips, notable tracks)
- Correction system - type `correction: it's actually a 7" single` to fix mistakes
- Ad-free listening links via Invidious + YouTube fallback
- Fallback vision models when primary is unavailable

## Setup

### Requirements

- Python 3.11+
- Telegram bot token (from [@BotFather](https://t.me/BotFather))
- Hugging Face API token (free tier works)
- Discogs API credentials

### Install

```bash
git clone https://github.com/sedici16/cratevision.git
cd cratevision
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### Configure

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

```
TELEGRAM_BOT_TOKEN=your-bot-token
hf=your-huggingface-token
DISCOGS_CONSUMER_KEY=your-key
DISCOGS_CONSUMER_SECRET=your-secret
```

### Run

```bash
python -m bot.main
```

### Deploy (systemd)

To run 24/7 on a Linux server:

```bash
# Create a user service
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/cratevision.service << EOF
[Unit]
Description=CrateVision Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/cratevision
ExecStart=/path/to/cratevision/venv/bin/python -m bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable cratevision
systemctl --user start cratevision

# Survive reboots without being logged in
loginctl enable-linger $USER
```

## Project Structure

```
cratevision/
├── bot/
│   ├── main.py        # Entry point, Telegram handler registration
│   ├── config.py      # Environment variables
│   ├── handlers.py    # Telegram message handlers, pipeline orchestration
│   ├── vision.py      # HF Vision API (Qwen2.5-VL / Qwen3-VL / Gemma)
│   ├── discogs.py     # Discogs API search + release details
│   ├── analyst.py     # LLM analysis (Qwen2.5-72B)
│   └── vinted.py      # Vinted marketplace search
├── .env.example
├── requirements.txt
└── SPEC.md
```

## Models Used

| Role | Model | Provider |
|------|-------|----------|
| Vision | Qwen2.5-VL-7B-Instruct | HF Inference API |
| Vision (fallback) | Qwen3-VL-8B-Instruct | HF Inference API |
| Vision (fallback) | Gemma-3-27B-IT | HF Inference API |
| Analysis | Qwen2.5-72B-Instruct | HF Inference API |

All models run via the Hugging Face free inference tier. No GPU required.

## License

MIT
