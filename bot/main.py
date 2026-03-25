import logging
import ssl
import httpx
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from bot.config import TELEGRAM_BOT_TOKEN, validate
from bot.handlers import start_handler, help_handler, photo_handler, document_handler, correction_handler


def main():
    validate()

    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    # Work around Windows SSL certificate revocation check issue
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = True
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    ssl_context.options |= 0x4  # ssl.OP_LEGACY_SERVER_CONNECT

    request = HTTPXRequest(
        connection_pool_size=8,
        connect_timeout=20.0,
        read_timeout=40.0,
        write_timeout=40.0,
        pool_timeout=10.0,
        httpx_kwargs={"verify": ssl_context},
    )

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .request(request)
        .get_updates_request(HTTPXRequest(httpx_kwargs={"verify": ssl_context}))
        .build()
    )

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.IMAGE, document_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)^correction:"), correction_handler))

    logging.info("CrateVision bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
