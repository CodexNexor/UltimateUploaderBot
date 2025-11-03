"""Download engine — aiohttp streaming, yt-dlp, ffmpeg for HLS/DASH, social media."""
import os
import asyncio
import logging
import time
import aiohttp
from typing import Optional, Callable, Awaitable

from config import Config
from helper_funcs.progress import humanbytes, time_formatter, build_progress_bar

logger = logging.getLogger(__name__)

# ── Helpers ─────────────────────────────────────────────────────────────────

# _headers
def _headers():
    import random
    return {
        "User-Agent": random.choice(Config.USER_AGENTS),
        "Accept": "*/*",
        "Connection": "keep-alive",
    }


ProgressCallback = Callable[[int, int], Awaitable[None]]


# ── Direct HTTP Download ─────────────────────────────────────────────────────

# download_http
async def download_http(
    url: str,
    dest_path: str,
    progress_msg,
    status_prefix: str = "⬇️ Downloading"
) -> bool:
    """
    Stream-download *url* to *dest_path*.
    Edits *progress_msg* with a progress bar.
    Returns True on success, False on failure.
    """
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector, headers=_headers()) as session:
        try:
            async with session.get(
                url,
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=Config.PROCESS_TIMEOUT)
            ) as response:
                if response.status not in (200, 206):
                    await progress_msg.edit(f"❌ Server returned HTTP {response.status}")
                    return False

                total = int(response.headers.get("Content-Length", 0))
                downloaded = 0
                start      = time.time()
                last_edit  = 0

                with open(dest_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(Config.CHUNK_SIZE):
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        now = time.time()
                        if now - last_edit >= Config.PROGRESS_UPDATE_INTERVAL:
                            last_edit = now
                            diff      = now - start or 1
                            speed     = downloaded / diff
                            if total:
                                pct = downloaded * 100 / total
                                bar = build_progress_bar(pct)
                                eta = (total - downloaded) / speed if speed else 0
                                text = (
                                    f"**{status_prefix}**\n\n"
                                    f"{bar} `{round(pct, 1)}%`\n\n"
                                    f"📦 `{humanbytes(downloaded)}` / `{humanbytes(total)}`\n"
                                    f"⚡ `{humanbytes(speed)}/s`\n"
                                    f"⏱ ETA: `{time_formatter(int(eta*1000))}`"
                                )
                            else:
                                text = (
                                    f"**{status_prefix}**\n\n"
                                    f"📦 Downloaded: `{humanbytes(downloaded)}`\n"
                                    f"⚡ Speed: `{humanbytes(speed)}/s`"
                                )
                            try:
                                await progress_msg.edit(text)
                            except Exception:
                                pass

                return True

        except asyncio.TimeoutError:
            await progress_msg.edit("❌ Download timed out. URL too slow.")
            return False
        except Exception as e:
            logger.error(f"download_http error: {e}")
            await progress_msg.edit(f"❌ Download failed: `{e}`")
            return False


# ── yt-dlp Download (YouTube, HLS, DASH, social media) ──────────────────────

# download_ytdlp
async def download_ytdlp(
    url: str,
    dest_dir: str,
    progress_msg,
    status_prefix: str = "⬇️ Downloading (yt-dlp)",
    extra_opts: dict = None
) -> Optional[str]:
    """
    Download *url* using yt-dlp into *dest_dir*.
    Returns the downloaded file path, or None on failure.
    """
    import yt_dlp

    os.makedirs(dest_dir, exist_ok=True)
    last_edit  = [0.0]
    final_path = [None]

    # progress_hook
    def progress_hook(d):
        if d["status"] == "downloading":
            now = time.time()
            if now - last_edit[0] < Config.PROGRESS_UPDATE_INTERVAL:
                return
            last_edit[0] = now

            downloaded = d.get("downloaded_bytes", 0)
            total      = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            speed      = d.get("speed", 0) or 0
            eta        = d.get("eta", 0) or 0

            if total:
                pct = downloaded * 100 / total
                bar = build_progress_bar(pct)
                text = (
                    f"**{status_prefix}**\n\n"
                    f"{bar} `{round(pct, 1)}%`\n\n"
                    f"📦 `{humanbytes(downloaded)}` / `{humanbytes(total)}`\n"
                    f"⚡ `{humanbytes(speed)}/s`\n"
                    f"⏱ ETA: `{time_formatter(eta * 1000)}`"
                )
            else:
                text = (
                    f"**{status_prefix}**\n\n"
                    f"📦 Downloaded: `{humanbytes(downloaded)}`\n"
                    f"⚡ Speed: `{humanbytes(speed)}/s`"
                )

            asyncio.get_event_loop().call_soon_threadsafe(
                lambda: asyncio.ensure_future(_safe_edit(progress_msg, text))
            )

        elif d["status"] == "finished":
            final_path[0] = d.get("filename")

    ydl_opts = {
        "outtmpl":         os.path.join(dest_dir, "%(title).50s.%(ext)s"),
        "progress_hooks":  [progress_hook],
        "quiet":           True,
        "no_warnings":     True,
        "merge_output_format": "mp4",
        "ffmpeg_location": Config.FFMPEG_PATH,
        "noplaylist":      True,
    }
    if extra_opts:
        ydl_opts.update(extra_opts)

    try:
        await progress_msg.edit(f"**{status_prefix}**\n\n🔍 Fetching media info…")

        loop = asyncio.get_event_loop()

        def _run():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # find the actual output file
                if info:
                    return ydl.prepare_filename(info)
                return None

        result = await loop.run_in_executor(None, _run)
        # Sometimes yt-dlp changes extension (e.g., webm→mp4 after merge)
        if result and not os.path.exists(result):
            # try .mp4 variant
            base, _ = os.path.splitext(result)
            for ext in (".mp4", ".mkv", ".webm"):
                alt = base + ext
                if os.path.exists(alt):
                    result = alt
                    break

        if result and os.path.exists(result):
            return result

        # Fallback: find newest file in dest_dir
        files = sorted(
            [os.path.join(dest_dir, f) for f in os.listdir(dest_dir)],
            key=os.path.getmtime, reverse=True
        )
        return files[0] if files else None

    except Exception as e:
        logger.error(f"yt-dlp error: {e}")
        await progress_msg.edit(f"❌ yt-dlp failed: `{e}`")
        return None


async def _safe_edit(msg, text):
    try:
        await msg.edit(text)
    except Exception:
        pass


# ── Smart Download Dispatcher ────────────────────────────────────────────────

async def smart_download(
    url: str,
    dest_dir: str,
    filename: str,
    url_type: str,
    progress_msg,
) -> Optional[str]:
    """
    Choose the right download method based on url_type.
    Returns the local file path or None.
    """
    dest_path = os.path.join(dest_dir, filename)

    if url_type in ("youtube", "instagram", "twitter", "facebook", "hls", "dash"):
        return await download_ytdlp(url, dest_dir, progress_msg,
                                     status_prefix=f"⬇️ Downloading ({url_type.upper()})")

    if url_type == "direct":
        success = await download_http(url, dest_path, progress_msg)
        return dest_path if success and os.path.exists(dest_path) else None

    # Fallback — try direct first, then yt-dlp
    success = await download_http(url, dest_path, progress_msg)
    if success and os.path.exists(dest_path):
        return dest_path

    return await download_ytdlp(url, dest_dir, progress_msg,
                                 status_prefix="⬇️ Downloading (yt-dlp fallback)")
