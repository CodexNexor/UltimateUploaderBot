"""
Configuration — set via environment variables or edit defaults below.
Copy .env.example to .env and fill in your values.
"""
import os
import re
from dotenv import load_dotenv

load_dotenv()

id_pattern = re.compile(r'^-?\d+$')


class Config:
    # ─── Bot Credentials ───────────────────────────────────────────
    BOT_TOKEN   = os.environ.get("BOT_TOKEN", "")          # @BotFather token
    API_ID      = int(os.environ.get("API_ID", "0"))        # my.telegram.org
    API_HASH    = os.environ.get("API_HASH", "")            # my.telegram.org

    # ─── Owner / Admin ─────────────────────────────────────────────
    OWNER_ID    = int(os.environ.get("OWNER_ID", "0"))      # Your Telegram user ID
    # Comma-separated extra admin IDs e.g. "123,456"
    ADMIN_IDS   = [
        int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
    ]

    # ─── Channels ──────────────────────────────────────────────────
    LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", "0"))   # Log channel ID (make bot admin)
    # Force subscribe channel — leave blank to disable
    _fs = os.environ.get("FORCE_SUB_CHANNEL", "")
    FORCE_SUB_CHANNEL = int(_fs) if _fs and id_pattern.search(_fs) else None

    # ─── Storage Paths ─────────────────────────────────────────────
    DOWNLOAD_LOCATION = os.environ.get("DOWNLOAD_LOCATION", "./DOWNLOADS")
    THUMB_LOCATION    = os.environ.get("THUMB_LOCATION", "./THUMBNAILS")

    # ─── File Limits ───────────────────────────────────────────────
    MAX_FILE_SIZE        = 4 * 1024 * 1024 * 1024   # 4 GB Telegram premium limit
    FREE_MAX_FILE_SIZE   = 2 * 1024 * 1024 * 1024   # 2 GB for free users
    CHUNK_SIZE           = 512 * 1024                 # 512 KB download chunks

    # ─── Timeouts ──────────────────────────────────────────────────
    PROCESS_TIMEOUT  = 3600   # 1 hour
    REQUEST_TIMEOUT  = 120    # HTTP request timeout seconds
    UPLOAD_CONFIRM_TIMEOUT = int(os.environ.get("UPLOAD_CONFIRM_TIMEOUT", "300"))

    # ─── HLS / yt-dlp ──────────────────────────────────────────────
    FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")

    # ─── Progress Update Interval ──────────────────────────────────
    PROGRESS_UPDATE_INTERVAL = 5   # seconds between progress edits

    # ─── Unzip ─────────────────────────────────────────────────────
    SUPPORTED_ARCHIVE_EXTS = (
        ".zip", ".rar", ".7z",
        ".tar", ".tar.gz", ".tgz",
        ".tar.bz2", ".tar.xz", ".gz"
    )

    # ─── Web Scraper ───────────────────────────────────────────────
    SCRAPER_MAX_DEPTH  = 2
    SCRAPER_MAX_LINKS  = 50
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    ]
