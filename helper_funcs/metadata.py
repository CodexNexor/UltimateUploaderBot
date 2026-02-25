"""Media metadata — hachoir for metadata, ffmpeg for thumbnails."""
import os
import asyncio
import logging
import subprocess
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


async def get_video_metadata(file_path: str) -> Tuple[int, int, int]:
    """Return (width, height, duration_seconds) for a video file."""
    try:
        from hachoir.parser   import createParser
        from hachoir.metadata import extractMetadata

        parser   = createParser(file_path)
        metadata = extractMetadata(parser)
        if metadata:
            duration = int(metadata.get("duration").total_seconds()) if metadata.get("duration") else 0
            width    = metadata.get("width")  or 0
            height   = metadata.get("height") or 0
            return int(width), int(height), duration
    except Exception as e:
        logger.warning(f"hachoir metadata failed: {e}")
    return 0, 0, 0


async def get_audio_duration(file_path: str) -> int:
    """Return duration in seconds for an audio file."""
    try:
        from hachoir.parser   import createParser
        from hachoir.metadata import extractMetadata

        parser   = createParser(file_path)
        metadata = extractMetadata(parser)
        if metadata and metadata.get("duration"):
            return int(metadata.get("duration").total_seconds())
    except Exception as e:
        logger.warning(f"audio duration fetch failed: {e}")
    return 0


async def generate_thumbnail(file_path: str, output_path: str, seek_time: int = 5) -> Optional[str]:
    """
    Extract a thumbnail from a video at *seek_time* seconds using ffmpeg.
    Returns output_path on success, None on failure.
    """
    from config import Config

    cmd = [
        Config.FFMPEG_PATH,
        "-ss", str(seek_time),
        "-i", file_path,
        "-vframes", "1",
        "-vf", "scale=320:-1",
        "-y", output_path
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        await asyncio.wait_for(proc.communicate(), timeout=30)
        if os.path.exists(output_path):
            return output_path
    except Exception as e:
        logger.warning(f"Thumbnail generation failed: {e}")
    return None


def get_file_extension(filename: str) -> str:
    """Return the file extension (lowercase), e.g. '.mp4'."""
    _, ext = os.path.splitext(filename)
    return ext.lower()


def guess_send_type(filename: str, mime_type: str = "") -> str:
    """
    Guess the Telegram send type from filename / mime type.
    Returns: 'video' | 'audio' | 'photo' | 'document'
    """
    ext  = get_file_extension(filename)
    mime = mime_type.lower()

    VIDEO_EXTS  = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".3gp", ".ts", ".m4v"}
    AUDIO_EXTS  = {".mp3", ".flac", ".aac", ".ogg", ".wav", ".m4a", ".opus", ".wma"}
    PHOTO_EXTS  = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

    if ext in VIDEO_EXTS or "video" in mime:
        return "video"
    if ext in AUDIO_EXTS or "audio" in mime:
        return "audio"
    if ext in PHOTO_EXTS or "image" in mime:
        return "photo"
    return "document"
