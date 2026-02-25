"""Progress bars for Pyrogram upload/download callbacks."""
import math
import time
import logging

logger = logging.getLogger(__name__)


def humanbytes(size: int) -> str:
    """Convert bytes to a human-readable string."""
    if not size:
        return "0 B"
    power = 1024
    n = 0
    units = {0: "B", 1: "KB", 2: "MB", 3: "GB", 4: "TB"}
    while size >= power and n < 4:
        size /= power
        n += 1
    return f"{round(size, 2)} {units[n]}"


def time_formatter(ms: int) -> str:
    """Convert milliseconds to a human-readable duration string."""
    seconds, ms   = divmod(int(ms), 1000)
    minutes, secs = divmod(seconds, 60)
    hours, mins   = divmod(minutes, 60)
    days, hrs     = divmod(hours, 24)
    parts = []
    if days:    parts.append(f"{days}d")
    if hrs:     parts.append(f"{hrs}h")
    if mins:    parts.append(f"{mins}m")
    if secs:    parts.append(f"{secs}s")
    return " ".join(parts) if parts else "0s"


def build_progress_bar(percentage: float, width: int = 20) -> str:
    """Return an ASCII progress bar string."""
    filled = math.floor(percentage / 100 * width)
    bar    = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"


async def progress_for_pyrogram(current: int, total: int, ud_type: str, message, start: float):
    """
    Pyrogram upload/download progress callback.
    Edits *message* every PROGRESS_UPDATE_INTERVAL seconds.
    """
    from config import Config

    now  = time.time()
    diff = now - start
    if diff == 0:
        return

    # Only update every N seconds OR when done
    if round(diff % Config.PROGRESS_UPDATE_INTERVAL) != 0 and current != total:
        return

    percentage = current * 100 / total
    speed      = current / diff if diff else 0
    eta_ms     = round((total - current) / speed) * 1000 if speed else 0

    bar  = build_progress_bar(percentage)
    text = (
        f"**{ud_type}**\n\n"
        f"{bar} `{round(percentage, 1)}%`\n\n"
        f"📦 **Done:** `{humanbytes(current)}` / `{humanbytes(total)}`\n"
        f"⚡ **Speed:** `{humanbytes(speed)}/s`\n"
        f"⏱ **ETA:** `{time_formatter(eta_ms)}`"
    )
    try:
        await message.edit(text)
    except Exception:
        pass
