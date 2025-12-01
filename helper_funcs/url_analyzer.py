"""URL analyzer and web scraper — detects direct links, HLS, DASH, CDN, embedded media."""
import re
import logging
import random
import asyncio
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, urljoin, unquote

import aiohttp
from bs4 import BeautifulSoup

from config import Config

logger = logging.getLogger(__name__)

# ── Pattern sets ────────────────────────────────────────────────────────────

# Extensions that are directly downloadable
DIRECT_EXTS = {
    # Video
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".3gp", ".ts", ".m4v",
    # Audio
    ".mp3", ".flac", ".aac", ".ogg", ".wav", ".m4a", ".opus",
    # Archives
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
    # Documents
    ".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".csv",
    # Images
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    # APK / Executables
    ".apk", ".exe", ".dmg", ".iso",
}

HLS_PATTERN   = re.compile(r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*', re.IGNORECASE)
DASH_PATTERN  = re.compile(r'https?://[^\s\'"<>]+\.mpd[^\s\'"<>]*', re.IGNORECASE)
URL_PATTERN   = re.compile(r'https?://[^\s\'"<>{}\[\]|\\^`\x00-\x1f]+', re.IGNORECASE)

MEDIA_CDN_PATTERNS = [
    re.compile(r'https?://[^\s]+(?:cloudfront\.net|akamaized\.net|fastly\.net)[^\s\'"<>]*', re.I),
    re.compile(r'https?://[^\s]+/(?:video|audio|media|stream|file|download|content|upload)[^\s\'"<>]*', re.I),
]

JS_URL_PATTERNS = [
    re.compile(r'(?:src|href|url|file|source|stream|video|audio|playlist)\s*[=:]\s*["\']([^"\']+)["\']', re.I),
    re.compile(r'(?:file|src|url)\s*:\s*["\']([^"\']+)["\']', re.I),
]


# random_headers
def random_headers() -> Dict[str, str]:
    return {
        "User-Agent": random.choice(Config.USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


def classify_url(url: str) -> str:
    """
    Returns a label: 'hls' | 'dash' | 'direct' | 'youtube' | 'webpage' | 'unknown'
    """
    lower = url.lower()
    if ".m3u8" in lower:            return "hls"
    if ".mpd" in lower:             return "dash"
    if "youtube.com" in lower or "youtu.be" in lower: return "youtube"
    if "instagram.com" in lower:    return "instagram"
    if "twitter.com" in lower or "x.com" in lower: return "twitter"
    if "facebook.com" in lower:     return "facebook"
    parsed = urlparse(url)
    _, ext = __import__("os").path.splitext(parsed.path)
    if ext.lower() in DIRECT_EXTS:  return "direct"
    return "webpage"


async def check_direct_link(url: str, session: aiohttp.ClientSession) -> Optional[Dict]:
    """
    HEAD request to check if URL is a direct file.
    Returns dict with size, mime, filename, or None.
    """
    try:
        async with session.head(
            url,
            headers=random_headers(),
            allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=20)
        ) as resp:
            if resp.status not in (200, 206):
                return None
            content_type        = resp.headers.get("Content-Type", "")
            content_length      = int(resp.headers.get("Content-Length", 0))
            content_disposition = resp.headers.get("Content-Disposition", "")
            final_url           = str(resp.url)

            # Extract filename
            filename = None
            if "filename=" in content_disposition:
                fn_match = re.search(r'filename\*?=["\']?([^"\';\r\n]+)', content_disposition, re.I)
                if fn_match:
                    filename = unquote(fn_match.group(1).strip())
            if not filename:
                filename = urlparse(final_url).path.split("/")[-1] or "file"

            # Ensure correct extension from mime
            if "." not in filename:
                mime_ext_map = {
                    "video/mp4": ".mp4", "video/x-matroska": ".mkv",
                    "audio/mpeg": ".mp3", "audio/flac": ".flac",
                    "application/zip": ".zip", "application/x-rar": ".rar",
                    "application/pdf": ".pdf", "image/jpeg": ".jpg",
                    "image/png": ".png",
                }
                for mime_key, ext in mime_ext_map.items():
                    if mime_key in content_type:
                        filename += ext
                        break

            return {
                "url": final_url,
                "filename": filename,
                "size": content_length,
                "mime": content_type,
                "type": "direct",
            }
    except Exception as e:
        logger.debug(f"HEAD check failed for {url}: {e}")
        return None


async def scrape_webpage(url: str, session: aiohttp.ClientSession) -> List[Dict]:
    """
    Fetch a webpage and extract all downloadable / media links.
    Searches HTML, JavaScript blocks, and inline scripts.
    """
    found: List[Dict] = []
    seen:  set         = set()

    try:
        async with session.get(
            url,
            headers=random_headers(),
            timeout=aiohttp.ClientTimeout(total=30),
            allow_redirects=True
        ) as resp:
            if resp.status != 200:
                return found

            content_type = resp.headers.get("Content-Type", "")
            if "text" not in content_type and "html" not in content_type:
                # It's already a direct file — return it as-is
                return [{
                    "url": str(resp.url),
                    "filename": urlparse(str(resp.url)).path.split("/")[-1] or "file",
                    "size": int(resp.headers.get("Content-Length", 0)),
                    "mime": content_type,
                    "type": "direct",
                    "label": "🗂 Direct File",
                }]

            html = await resp.text(errors="replace")
    except Exception as e:
        logger.error(f"scrape_webpage fetch error: {e}")
        return found

    soup = BeautifulSoup(html, "html.parser")

    def add_link(link_url: str, label: str = "🔗 Link"):
        link_url = link_url.strip()
        if not link_url or link_url in seen:
            return
        # Make relative URLs absolute
        if not link_url.startswith("http"):
            link_url = urljoin(url, link_url)
        seen.add(link_url)
        link_type = classify_url(link_url)
        found.append({
            "url":   link_url,
            "label": label,
            "type":  link_type,
        })

    # 1. HLS / DASH streams
    for m in HLS_PATTERN.finditer(html):
        add_link(m.group(), "📺 HLS Stream")
    for m in DASH_PATTERN.finditer(html):
        add_link(m.group(), "📺 DASH Stream")

    # 2. <source> tags
    for tag in soup.find_all("source"):
        src = tag.get("src", "")
        if src:
            add_link(src, "🎬 Media Source")

    # 3. <a> download links
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        _, ext = __import__("os").path.splitext(urlparse(href).path)
        if ext.lower() in DIRECT_EXTS:
            add_link(href, f"📥 Download ({ext})")

    # 4. <video> / <audio> tags
    for tag in soup.find_all(["video", "audio"]):
        src = tag.get("src", "")
        if src:
            add_link(src, "🎬 Media Tag")

    # 5. <iframe> embed — look for src
    for tag in soup.find_all("iframe"):
        src = tag.get("src", "")
        if src:
            add_link(src, "🖼 iFrame Embed")

    # 6. JavaScript strings — scan all <script> tags
    for script in soup.find_all("script"):
        js_text = script.string or ""
        for pat in JS_URL_PATTERNS:
            for m in pat.finditer(js_text):
                candidate = m.group(1)
                if candidate.startswith("http") or "/" in candidate:
                    add_link(candidate, "🔐 JS Embedded Link")
        # Also raw HLS/DASH inside scripts
        for m in HLS_PATTERN.finditer(js_text):
            add_link(m.group(), "📺 HLS (JS)")
        for m in DASH_PATTERN.finditer(js_text):
            add_link(m.group(), "📺 DASH (JS)")

    # 7. CDN patterns in raw HTML
    for pat in MEDIA_CDN_PATTERNS:
        for m in pat.finditer(html):
            link = m.group()
            _, ext = __import__("os").path.splitext(urlparse(link).path)
            if ext.lower() in DIRECT_EXTS or "stream" in link.lower():
                add_link(link, "☁️ CDN Media")

    return found[:Config.SCRAPER_MAX_LINKS]


async def analyze_url(url: str) -> Dict:
    """
    Full URL analysis. Returns a dict:
    {
      'primary_type': 'direct'|'hls'|'youtube'|'webpage'|...,
      'direct_info':  {...} or None,
      'scraped_links': [...],
      'error': str or None
    }
    """
    result = {
        "primary_type": classify_url(url),
        "direct_info":  None,
        "scraped_links": [],
        "error": None,
    }

    connector = aiohttp.TCPConnector(ssl=False, limit=10)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Always try HEAD first to check for direct file
        direct = await check_direct_link(url, session)
        if direct:
            result["direct_info"] = direct

        url_type = result["primary_type"]

        # For HLS / DASH — just return the URL; yt-dlp will handle it
        if url_type in ("hls", "dash"):
            result["direct_info"] = result["direct_info"] or {
                "url": url, "filename": urlparse(url).path.split("/")[-1],
                "size": 0, "mime": "application/octet-stream", "type": url_type
            }

        # For webpages — also scrape
        if url_type in ("webpage",) or (url_type == "direct" and not direct):
            scraped = await scrape_webpage(url, session)
            result["scraped_links"] = scraped

    return result
