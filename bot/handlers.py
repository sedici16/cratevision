import json
import logging
import requests
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from bot.config import HF_TOKEN, HF_API_URL, ANALYST_MODEL, GETSONGBPM_API_KEY
from bot.vision import extract_vinyl_info
from bot.discogs import search_release, get_release_details, build_release_summary
from bot.analyst import analyze_release
from bot.vinted import search_vinted
from bot.bpm import get_bpm
from bot.whosampled import get_album_sample_data
from bot.db import log_search, get_user_stats

logger = logging.getLogger(__name__)

WELCOME_MSG = (
    "Welcome to <b>CrateVision</b>! 📸💿\n\n"
    "Send me a photo of a vinyl record (cover or label) and I'll:\n"
    "1. Identify the record\n"
    "2. Look it up on Discogs\n"
    "3. Tell you if it's worth buying\n\n"
    "Just snap a photo and send it!\n\n"
    "💡 <b>Tip:</b> If I get something wrong, reply with:\n"
    "<code>correction: it's a vinyl LP not a cassette</code>"
)

# Store last vision result per chat: {chat_id: vinyl_info dict}
_last_result: dict[int, dict] = {}


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_MSG, parse_mode=ParseMode.HTML)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME_MSG, parse_mode=ParseMode.HTML)


async def mystats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user their personal stats and dashboard link."""
    user = update.effective_user
    if not user:
        return
    stats = get_user_stats(user.id)
    total = stats["total_searches"]
    if total == 0:
        await update.message.reply_text("You haven't searched anything yet! Send me a photo to get started.")
        return

    verdicts = {v["verdict"]: v["count"] for v in stats["verdicts"]}
    top = stats["top_artists"][:5]

    lines = [
        f"<b>Your CrateVision Stats</b>",
        f"",
        f"Total searches: <b>{total}</b>",
        f"BUY: {verdicts.get('BUY', 0)} | MILD: {verdicts.get('MILD', 0)} | SKIP: {verdicts.get('SKIP', 0)}",
    ]
    if top:
        lines.append("")
        lines.append("<b>Your top artists:</b>")
        for a in top:
            lines.append(f"  {a['artist']} ({a['count']})")

    lines.append("")
    lines.append(f"View full dashboard:\nhttp://83.136.105.116:8090/cratevision/user/{user.id}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def correction_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'correction:' messages — re-run pipeline with corrected info."""
    chat_id = update.message.chat_id
    text = update.message.text

    # Extract the correction text after "correction:"
    correction = text.split(":", 1)[1].strip()
    if not correction:
        await update.message.reply_text("Please provide the correction after 'correction:'")
        return

    prev = _last_result.get(chat_id)
    if not prev:
        await update.message.reply_text("No previous result to correct. Send a photo first!")
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    status_msg = await update.message.reply_text("🔄 Applying correction...")

    # Ask the LLM to fix the previous result based on the correction
    corrected = _apply_correction(prev, correction)
    if not corrected:
        await status_msg.edit_text("❌ Couldn't apply the correction. Please try again.")
        return

    # Store corrected result
    _last_result[chat_id] = corrected

    artist = corrected.get("artist", "Unknown")
    title = corrected.get("title", "Unknown")
    await status_msg.edit_text(
        f"🔄 Corrected: <b>{artist} - {title}</b>\n🔎 Searching Discogs...",
        parse_mode=ParseMode.HTML,
    )

    # Re-run discogs + analysis pipeline
    await _run_discogs_pipeline(update, status_msg, corrected)


def _apply_correction(prev_result: dict, correction: str) -> dict | None:
    """Send previous result + user correction to LLM to get fixed info."""
    prompt = f"""You previously analyzed a vinyl record image and returned this result:
{json.dumps(prev_result, indent=2)}

The user says this is wrong and provides this correction:
"{correction}"

Apply the correction to the result and return the updated JSON. Keep all fields that weren't corrected.
Return ONLY valid JSON, no other text."""

    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": ANALYST_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 500,
    }

    try:
        response = requests.post(HF_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            content = content.rsplit("```", 1)[0]

        return json.loads(content)
    except Exception as e:
        logger.error("Correction LLM call failed: %s", e)
        return None


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photos sent as compressed images."""
    await update.message.chat.send_action(ChatAction.TYPING)
    photo = update.message.photo[-1]  # largest size
    file = await photo.get_file()
    image_bytes = await file.download_as_bytearray()
    await _process_image(update, bytes(image_bytes), "image/jpeg")


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle images sent as uncompressed documents."""
    doc = update.message.document
    if not doc.mime_type or not doc.mime_type.startswith("image/"):
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    file = await doc.get_file()
    image_bytes = await file.download_as_bytearray()
    media_type = doc.mime_type or "image/jpeg"
    await _process_image(update, bytes(image_bytes), media_type)


async def _process_image(update: Update, image_bytes: bytes, media_type: str):
    """Core pipeline: vision → discogs → analysis → response."""
    chat_id = update.message.chat_id

    # Step 1: Vision
    status_msg = await update.message.reply_text("🔍 Analyzing image...")
    vinyl_info = extract_vinyl_info(image_bytes, media_type)

    if not vinyl_info:
        await status_msg.edit_text("❌ Sorry, I couldn't analyze this image. Please try again.")
        return

    if vinyl_info.get("confidence") == "none":
        await status_msg.edit_text(
            "❌ This doesn't look like a vinyl record.\n"
            f"📝 {vinyl_info.get('notes', 'Please send a photo of a record cover or label.')}"
        )
        return

    # Store result for corrections
    _last_result[chat_id] = vinyl_info
    logger.info("Vision extracted: %s", vinyl_info)

    artist = vinyl_info.get("artist", "Unknown")
    title = vinyl_info.get("title", "Unknown")
    await status_msg.edit_text(f"🔍 Found: <b>{artist} - {title}</b>\n🔎 Searching Discogs...", parse_mode=ParseMode.HTML)

    # Steps 2-4: Discogs + Analysis
    await _run_discogs_pipeline(update, status_msg, vinyl_info)


async def _run_discogs_pipeline(update: Update, status_msg, vinyl_info: dict):
    """Run discogs search → full details → LLM analysis → send response."""
    artist = vinyl_info.get("artist", "Unknown")
    title = vinyl_info.get("title", "Unknown")

    # Step 2: Discogs search
    search_results = search_release(vinyl_info)

    if not search_results:
        text = _format_vision_only(vinyl_info)
        await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
        return

    # Get full details — try multiple results if top one 404s
    await status_msg.edit_text(
        f"🔍 Found: <b>{artist} - {title}</b>\n📊 Fetching details & analyzing...",
        parse_mode=ParseMode.HTML,
    )

    release_details = None
    for result in search_results[:5]:
        release_details = get_release_details(result.get("id"))
        if release_details:
            break

    if not release_details:
        text = _format_vision_only(vinyl_info)
        await status_msg.edit_text(text, parse_mode=ParseMode.HTML)
        return

    summary = build_release_summary(release_details)

    # Step 2.5: Vinted search
    await status_msg.edit_text(
        f"🔍 Found: <b>{artist} - {title}</b>\n🛒 Checking Vinted...",
        parse_mode=ParseMode.HTML,
    )
    fmt = vinyl_info.get("format", "vinyl")
    vinted_data = search_vinted(artist, title, fmt)
    logger.info("Vinted result: %s", {k: v for k, v in vinted_data.items() if k != "listings"})

    bpm_data = get_bpm(artist, title, GETSONGBPM_API_KEY)
    logger.info("BPM result: %s", bpm_data)

    sample_data = get_album_sample_data(artist, summary.get("tracklist", []))
    logger.info("WhoSampled result: %d tracks with connections", len(sample_data))

    # Step 3: LLM Analysis (with Vinted data)
    await status_msg.edit_text(
        f"🔍 Found: <b>{artist} - {title}</b>\n🤖 Analyzing...",
        parse_mode=ParseMode.HTML,
    )
    analysis = analyze_release(summary, vinted_data)

    # Log to analytics
    user = update.effective_user
    if user:
        log_search(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            artist=summary["artists"],
            title=summary["title"],
            verdict=analysis["verdict"],
            discogs_id=summary.get("id"),
            youtube_url=summary.get("youtube_url"),
            bpm=bpm_data.get("bpm") if bpm_data else None,
            key_of=bpm_data.get("key") if bpm_data else None,
        )

    # Step 4: Send response
    await status_msg.delete()
    await _send_response(update, summary, analysis, vinted_data, bpm_data, sample_data)


async def _send_response(update: Update, summary: dict, analysis: dict, vinted_data: dict = None, bpm_data: dict = None, sample_data: list = None):
    """Send the final response with cover image and analysis."""
    verdict_map = {"BUY": "🟢", "MILD": "🟡", "SKIP": "🔴"}
    verdict_emoji = verdict_map.get(analysis["verdict"], "⚪")

    # Build caption
    lines = [
        f"🎵 <b>{summary['artists']} - {summary['title']}</b>",
        f"📅 {summary['year'] or '?'} · 🏷️ {summary['label']} · 🌍 {summary['country']}",
        f"💿 {summary['formats']}",
    ]
    if summary["catno"]:
        lines.append(f"📋 Cat#: {summary['catno']}")
    if summary.get("genres") or summary.get("styles"):
        genre_parts = []
        if summary.get("genres"):
            genre_parts.append(summary["genres"])
        if summary.get("styles"):
            genre_parts.append(summary["styles"])
        lines.append(f"🎸 {' · '.join(genre_parts)}")
    if summary.get("notes"):
        notes = summary["notes"].replace("\n", " ").strip()
        if len(notes) > 150:
            notes = notes[:147] + "..."
        lines.append(f"📝 {notes}")

    lines.append("")
    lines.append("📊 <b>Discogs:</b>")
    price_str = f"${summary['lowest_price']:.2f}" if summary['lowest_price'] else "N/A"
    lines.append(f"   👥 {summary['have']} have · {summary['want']} want · ⭐ {summary['rating_avg']}/5")
    lines.append(f"   💰 From: {price_str} · {summary['num_for_sale']} for sale")

    # Vinted data
    lines.append("")
    if vinted_data and vinted_data.get("available") and vinted_data.get("count", 0) > 0:
        cur = vinted_data["currency"]
        lines.append("🛒 <b>Vinted:</b>")
        lines.append(f"   {vinted_data['count']} listings · {vinted_data['lowest_price']}-{vinted_data['highest_price']} {cur}")
    elif vinted_data and vinted_data.get("available") and vinted_data.get("count", 0) == 0:
        lines.append("🛒 <b>Vinted:</b> no listings found")
    elif vinted_data and not vinted_data.get("available"):
        lines.append("🛒 <b>Vinted:</b> ⚠️ unavailable")
    else:
        lines.append("🛒 <b>Vinted:</b> not checked")

    lines.append("")
    lines.append(f"{verdict_emoji} <b>{analysis['verdict']}</b>: {analysis['reasoning']}")
    if analysis.get("context"):
        lines.append(f"💡 {analysis['context']}")

    # Tracklist (truncated)
    if summary["tracklist"]:
        lines.append("")
        lines.append("🎶 <b>Tracklist:</b>")
        for track in summary["tracklist"][:10]:
            lines.append(f"   {track}")
        if len(summary["tracklist"]) > 10:
            lines.append(f"   ... +{len(summary['tracklist']) - 10} more")

    # BPM / Key
    if bpm_data and bpm_data.get("bpm"):
        bpm_line = f"🎵 <b>BPM:</b> {bpm_data['bpm']}"
        if bpm_data.get("key"):
            bpm_line += f"  🎹 <b>Key:</b> {bpm_data['key']}"
        if bpm_data.get("danceability") is not None:
            bpm_line += f"  💃 <b>Dance:</b> {bpm_data['danceability']}/100"
        lines.append(bpm_line)

    # WhoSampled (per track)
    if sample_data:
        lines.append("")
        lines.append("🔁 <b>Sample connections:</b>")
        for td in sample_data:
            tname = td["track"]
            parts = []
            if td.get("contains"):
                s = td["contains"][0]
                parts.append("samples %s - %s" % (s["artist"], s["track"]))
            if td.get("sampled_in"):
                count = len(td["sampled_in"])
                names = ", ".join(s["artist"] for s in td["sampled_in"][:2])
                if count > 2:
                    names += " +%d more" % (count - 2)
                parts.append("sampled by %s" % names)
            if parts:
                url = td["url"]
                lines.append('   <a href="%s">%s</a>: ' % (url, tname) + " · ".join(parts))
    # Links
    lines.append("")
    if summary["listen_url"]:
        lines.append(f'🎧 <a href="{summary["listen_url"]}">Listen (ad-free)</a>')
    if summary.get("youtube_url"):
        lines.append(f'▶️ <a href="{summary["youtube_url"]}">YouTube</a>')
    if summary["discogs_url"]:
        lines.append(f'🔗 <a href="{summary["discogs_url"]}">View on Discogs</a>')

    user = update.effective_user
    if user:
        lines.append(f'\n📊 <a href="http://83.136.105.116:8090/cratevision/user/{user.id}">Your search history</a>')

    text = "\n".join(lines)

    # Always send photo + text separately to avoid caption truncation
    if summary["cover_url"]:
        try:
            await update.message.reply_photo(
                photo=summary["cover_url"],
                caption=f"🎵 <b>{summary['artists']} - {summary['title']}</b>",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning("Failed to send cover image: %s", e)

    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


def _format_vision_only(vinyl_info: dict) -> str:
    """Format a response when Discogs search found nothing."""
    lines = [
        f"🎵 <b>{vinyl_info.get('artist', '?')} - {vinyl_info.get('title', '?')}</b>",
    ]
    if vinyl_info.get("year"):
        lines.append(f"📅 Year: {vinyl_info['year']}")
    if vinyl_info.get("label"):
        lines.append(f"🏷️ Label: {vinyl_info['label']}")
    if vinyl_info.get("catalog_number"):
        lines.append(f"📋 Cat#: {vinyl_info['catalog_number']}")
    if vinyl_info.get("notes"):
        lines.append(f"📝 {vinyl_info['notes']}")
    lines.append("")
    lines.append("⚠️ No matching release found on Discogs.")
    return "\n".join(lines)
