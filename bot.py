"""
╔══════════════════════════════════════════════════════════════╗
║          ULTIMATE URL UPLOADER + UNZIP BOT                   ║
║   Features: URL Upload • HLS • Web Scraping • Unzip • RAR   ║
║   Built with pyrogram | python-telegram-bot compatible       ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import logging
from config import Config
from pyrogram import Client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    # Create required directories
    os.makedirs(Config.DOWNLOAD_LOCATION, exist_ok=True)
    os.makedirs(Config.THUMB_LOCATION, exist_ok=True)

    plugins = dict(root="plugins")

    bot = Client(
        name="UltimateUploaderBot",
        bot_token=Config.BOT_TOKEN,
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        plugins=plugins,
        workers=8
    )

    logger.info("🚀 Ultimate Uploader Bot starting...")
    bot.run()
