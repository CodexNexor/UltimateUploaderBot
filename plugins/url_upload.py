"""
Core URL upload plugin.
Handles any URL message, detects type, downloads, and uploads to Telegram.
"""
import os
import re
import time
import shutil
import asyncio
import logging
import uuid
from urllib.parse import urlparse

from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

from config import Config
from helper_funcs.url_analyzer import analyze_url, classify_url
from helper_funcs.downloader   import smart_download
from helper_funcs.metadata     import get_video_metadata, get_audio_duration, generate_thumbnail, guess_send_type
from helper_funcs.progress     import progress_for_pyrogram, humanbytes

logger = logging.getLogger(__name__)

# Track active tasks per user to allow cancellation
active_uploads: dict = {}   # user_id -> asyncio.Task
pending_uploads: dict = {}  # token -> {user_id, event, choice}

URL_REGEX = re.compile(
    r'https?://[^\s<>"{}|\\^`\[\]]+'
)


def extract_url_and_name(text: str):
    """
    Parse `URL | custom_name.ext` or just `URL`.
    Returns (url, custom_name or None).
    """
    if "|" in text:
        parts = [p.strip() for p in text.split("|", 1)]
        return parts[0], parts[1] if len(parts) == 2 else None
    match = URL_REGEX.search(text)
    return (match.group() if match else text.strip()), None


# ── URL message handler ──────────────────────────────────────────────────────

@Client.on_message(filters.text & filters.private & ~filters.command(
    ["start", "help", "status", "clean", "cancel", "extract", "password"]
))
async def handle_url(client: Client, message: Message):
    text = message.text.strip()
    if not URL_REGEX.search(text):
        return  # Not a URL message — ignore

    url, custom_name = extract_url_and_name(text)
    user_id   = message.from_user.id
    user_dir  = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    status = await message.reply("🔍 **Analyzing URL…** Please wait.")

    # ── Step 1: Analyze URL ──────────────────────────────────────────
    try:
        analysis = await asyncio.wait_for(analyze_url(url), timeout=60)
    except asyncio.TimeoutError:
        await status.edit("❌ URL analysis timed out. Please try again.")
        return
    except Exception as e:
        await status.edit(f"❌ Analysis failed: `{e}`")
        return

    url_type      = analysis["primary_type"]
    direct_info   = analysis["direct_info"]
    scraped_links = analysis["scraped_links"]

    # ── Social / yt-dlp types — just download ───────────────────────
    if url_type in ("youtube", "instagram", "twitter", "facebook", "hls", "dash"):
        await _download_and_upload(client, message, status, url, url_type, user_dir, custom_name)
        return

    # ── Direct file detected ─────────────────────────────────────────
    if direct_info:
        filename  = custom_name or direct_info["filename"]
        file_size = direct_info["size"]
        mime      = direct_info.get("mime", "")

        info_text = (
            f"📎 **File Detected**\n\n"
            f"📄 **Name:** `{filename}`\n"
            f"📦 **Size:** `{humanbytes(file_size)}`\n"
            f"🗂 **Type:** `{mime or 'unknown'}`\n"
            f"🔗 **URL:** `{url[:60]}…`\n\n"
            f"Choose upload format:"
        )
        send_type = guess_send_type(filename, mime)
        buttons = _build_upload_buttons(url, filename, send_type)
        await status.edit(info_text, reply_markup=buttons)
        return

    # ── Webpage with scraped links ───────────────────────────────────
    if scraped_links:
        await _show_scraped_links(client, message, status, url, scraped_links, user_dir)
        return

    # ── Last resort — try yt-dlp ─────────────────────────────────────
    await status.edit("🔄 Trying yt-dlp as fallback…")
    await _download_and_upload(client, message, status, url, "ytdlp", user_dir, custom_name)


def _build_upload_buttons(url: str, filename: str, default_type: str):
    """Build inline keyboard for choosing upload type."""
    # Encode minimal info — actual download triggered by callback
    base = f"ul|{default_type}"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎬 Video",    callback_data=f"ul|video"),
            InlineKeyboardButton("🎵 Audio",    callback_data=f"ul|audio"),
        ],
        [
            InlineKeyboardButton("📄 Document", callback_data=f"ul|document"),
            InlineKeyboardButton("🖼 Photo",    callback_data=f"ul|photo"),
        ],
        [
            InlineKeyboardButton("❌ Cancel",   callback_data="ul|cancel"),
        ]
    ])


@Client.on_callback_query(filters.regex(r"^ul\|"))
async def upload_type_callback(client: Client, cb: CallbackQuery):
    await cb.answer()
    choice = cb.data.split("|")[1]
    if choice == "cancel":
        await cb.message.edit("❌ Upload cancelled.")
        return

    # Recover URL from the original replied-to message
    orig = cb.message.reply_to_message
    if not orig or not orig.text:
        await cb.message.edit("❌ Cannot find original URL. Please resend.")
        return

    url, custom_name = extract_url_and_name(orig.text.strip())
    user_id  = cb.from_user.id
    user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    await cb.message.edit("⬇️ Starting download…")
    await _download_and_upload(client, orig, cb.message, url, "direct", user_dir, custom_name, forced_send_type=choice)


async def _show_scraped_links(client, message, status, source_url, links, user_dir):
    """Show extracted links from a webpage as inline buttons."""
    lines = [f"🔍 **Found {len(links)} links on page:**\n"]
    for i, link in enumerate(links[:15], 1):
        label = link.get("label", "🔗 Link")
        url   = link["url"]
        name  = urlparse(url).path.split("/")[-1][:40] or f"link_{i}"
        lines.append(f"`{i}.` {label} — `{name}`")

    lines.append("\n_Reply with the number to download that link._")
    await status.edit("\n".join(lines))

    # Store links in memory keyed by user — simple approach
    user_id = message.from_user.id
    _link_store[user_id] = {"links": links, "source": source_url}

    # Also show as buttons if ≤ 10 links
    if len(links) <= 10:
        rows = []
        for i, link in enumerate(links[:10], 1):
            label = link.get("label", "🔗")[:20]
            rows.append([InlineKeyboardButton(f"{i}. {label}", callback_data=f"scr|{user_id}|{i-1}")])
        rows.append([InlineKeyboardButton("❌ Cancel", callback_data="scr|cancel")])
        await status.edit("\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


_link_store: dict = {}   # user_id -> {links, source}


@Client.on_callback_query(filters.regex(r"^confirm\|"))
async def upload_confirm_callback(client: Client, cb: CallbackQuery):
    parts = cb.data.split("|", 2)
    if len(parts) != 3:
        await cb.answer("Invalid confirmation.", show_alert=True)
        return

    _, token, choice = parts
    pending = pending_uploads.get(token)
    if not pending:
        await cb.answer("This file is no longer available.", show_alert=True)
        return

    if cb.from_user.id != pending["user_id"]:
        await cb.answer("Only the requester can choose this.", show_alert=True)
        return

    pending["choice"] = choice
    pending["event"].set()
    await cb.answer("Selected.")


@Client.on_callback_query(filters.regex(r"^scr\|"))
async def scrape_link_callback(client: Client, cb: CallbackQuery):
    await cb.answer()
    parts = cb.data.split("|")
    if parts[1] == "cancel":
        await cb.message.edit("❌ Cancelled.")
        return

    user_id  = int(parts[1])
    idx      = int(parts[2])
    store    = _link_store.get(user_id)

    if not store or idx >= len(store["links"]):
        await cb.message.edit("❌ Link expired. Please resend the URL.")
        return

    link     = store["links"][idx]
    url      = link["url"]
    url_type = link.get("type", "direct")
    user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    await cb.message.edit(f"⬇️ Starting download for link {idx+1}…")
    await _download_and_upload(client, cb.message.reply_to_message or cb.message,
                               cb.message, url, url_type, user_dir)


# ── /extract command ─────────────────────────────────────────────────────────

@Client.on_message(filters.command("extract"))
async def extract_cmd(client: Client, message: Message):
    args = message.text.split(None, 1)
    if len(args) < 2:
        await message.reply("❌ Usage: `/extract <url>`")
        return

    url    = args[1].strip()
    status = await message.reply("🔍 **Scanning webpage for media links…**")

    try:
        analysis = await asyncio.wait_for(analyze_url(url), timeout=60)
    except Exception as e:
        await status.edit(f"❌ Scan failed: `{e}`")
        return

    scraped = analysis.get("scraped_links", [])
    if not scraped:
        await status.edit("❌ No downloadable links found on this page.")
        return

    user_id  = message.from_user.id
    user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))
    await _show_scraped_links(client, message, status, url, scraped, user_dir)


# ── Number reply to pick scraped link ────────────────────────────────────────

@Client.on_message(filters.private & filters.text & ~filters.command(
    ["start", "help", "status", "clean", "cancel", "extract", "password"]
))
async def handle_number_reply(client: Client, message: Message):
    text = message.text.strip()
    if not text.isdigit():
        return
    idx     = int(text) - 1
    user_id = message.from_user.id
    store   = _link_store.get(user_id)
    if not store or idx < 0 or idx >= len(store["links"]):
        return

    link     = store["links"][idx]
    url      = link["url"]
    url_type = link.get("type", "direct")
    user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))
    os.makedirs(user_dir, exist_ok=True)

    status = await message.reply(f"⬇️ Starting download for link {idx+1}…")
    await _download_and_upload(client, message, status, url, url_type, user_dir)


# ── Core download + upload ────────────────────────────────────────────────────

async def _download_and_upload(
    client: Client,
    orig_message: Message,
    status_message: Message,
    url: str,
    url_type: str,
    user_dir: str,
    custom_name: str = None,
    forced_send_type: str = None
):
    user_id = orig_message.from_user.id if orig_message.from_user else 0
    start   = time.time()

    # ── Download ─────────────────────────────────────────────────────
    filename = custom_name or urlparse(url).path.split("/")[-1] or "file"
    if not filename or filename == "/":
        filename = "file"

    downloaded_path = await smart_download(
        url      = url,
        dest_dir = user_dir,
        filename = filename,
        url_type = url_type,
        progress_msg = status_message
    )

    if not downloaded_path or not os.path.exists(downloaded_path):
        await status_message.edit("❌ Download failed. The link may be invalid or expired.")
        return

    dl_time   = round(time.time() - start)
    file_size = os.path.getsize(downloaded_path)

    if file_size > Config.MAX_FILE_SIZE:
        await status_message.edit(
            f"❌ File too large: `{humanbytes(file_size)}` — Telegram limit is 4 GB."
        )
        _cleanup_files(downloaded_path)
        _cleanup_empty_dir(user_dir)
        return

    # ── Determine send type ──────────────────────────────────────────
    actual_filename = os.path.basename(downloaded_path)
    send_type = forced_send_type or guess_send_type(actual_filename)

    if not await _confirm_before_upload(status_message, user_id, actual_filename, file_size):
        _cleanup_files(downloaded_path)
        _cleanup_empty_dir(user_dir)
        return

    # ── Extract metadata ─────────────────────────────────────────────
    thumb_path = None
    width = height = duration = 0

    if send_type == "video":
        width, height, duration = await get_video_metadata(downloaded_path)
        thumb_path = os.path.join(user_dir, f"thumb_{user_id}.jpg")
        thumb_path = await generate_thumbnail(downloaded_path, thumb_path, seek_time=min(5, duration//2 or 1))

    elif send_type == "audio":
        duration = await get_audio_duration(downloaded_path)

    # ── Upload ───────────────────────────────────────────────────────
    await status_message.edit("⬆️ **Uploading to Telegram…**")
    upload_start = time.time()

    caption = (
        f"📄 **{actual_filename}**\n"
        f"📦 Size: `{humanbytes(file_size)}`\n"
        f"⬇️ Downloaded in: `{dl_time}s`"
    )

    try:
        common_kwargs = dict(
            chat_id              = orig_message.chat.id,
            caption              = caption,
            reply_to_message_id  = orig_message.id,
            progress             = progress_for_pyrogram,
            progress_args        = ("⬆️ Uploading", status_message, upload_start)
        )

        if send_type == "video":
            await client.send_video(
                video              = downloaded_path,
                duration           = duration,
                width              = width,
                height             = height,
                thumb              = thumb_path,
                supports_streaming = True,
                **common_kwargs
            )
        elif send_type == "audio":
            await client.send_audio(
                audio    = downloaded_path,
                duration = duration,
                thumb    = thumb_path,
                **common_kwargs
            )
        elif send_type == "photo":
            await client.send_photo(
                photo   = downloaded_path,
                caption = caption,
                chat_id = orig_message.chat.id,
                reply_to_message_id = orig_message.id
            )
        else:
            await client.send_document(
                document  = downloaded_path,
                file_name = actual_filename,
                thumb     = thumb_path,
                **common_kwargs
            )

        ul_time = round(time.time() - upload_start)
        await status_message.edit(
            f"✅ **Done!**\n\n"
            f"📄 `{actual_filename}`\n"
            f"📦 `{humanbytes(file_size)}`\n"
            f"⬇️ Download: `{dl_time}s` | ⬆️ Upload: `{ul_time}s`"
        )

    except Exception as e:
        logger.error(f"Upload error: {e}")
        await status_message.edit(f"❌ Upload failed: `{e}`")

    finally:
        # Cleanup
        _cleanup_files(downloaded_path, thumb_path)
        _cleanup_empty_dir(user_dir)


async def _confirm_before_upload(
    status_message: Message,
    user_id: int,
    filename: str,
    file_size: int
) -> bool:
    token = uuid.uuid4().hex[:16]
    event = asyncio.Event()
    pending_uploads[token] = {
        "user_id": user_id,
        "event": event,
        "choice": None,
    }

    timeout = Config.UPLOAD_CONFIRM_TIMEOUT
    await status_message.edit(
        "✅ **Download complete.**\n\n"
        f"📄 `{filename}`\n"
        f"📦 `{humanbytes(file_size)}`\n\n"
        f"Send this file to Telegram? If you do not reply in {timeout // 60} minutes, "
        "the file will be deleted from the VPS.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Send", callback_data=f"confirm|{token}|send"),
                InlineKeyboardButton("🗑 Delete", callback_data=f"confirm|{token}|delete"),
            ]
        ])
    )

    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        await status_message.edit(
            "⌛ **No reply received.**\n\n"
            "The downloaded file was deleted from the VPS."
        )
        return False
    finally:
        pending = pending_uploads.pop(token, None)

    if not pending or pending.get("choice") != "send":
        await status_message.edit("🗑 **Deleted.** The file was removed from the VPS.")
        return False

    await status_message.edit("⬆️ **Uploading to Telegram…**")
    return True


def _cleanup_files(*paths):
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.warning(f"Cleanup failed for {path}: {e}")


def _cleanup_empty_dir(path: str):
    try:
        if path and os.path.isdir(path) and not os.listdir(path):
            os.rmdir(path)
    except Exception:
        pass
