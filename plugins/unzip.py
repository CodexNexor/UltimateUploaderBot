"""
Unzip plugin.
Users send any archive file → bot extracts → sends each file back.
Supports: .zip .rar .7z .tar .tar.gz .tgz .tar.bz2 .tar.xz
Password protected archives: user replies `/password <pass>` after sending file.
"""
import os
import time
import shutil
import asyncio
import logging
from typing import Optional

from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

from config import Config
from helper_funcs.extractor import (
    is_archive, extract_archive, list_archive_contents, is_password_protected
)
from helper_funcs.progress import progress_for_pyrogram, humanbytes

logger = logging.getLogger(__name__)

# Store pending password-protected archives: user_id -> file_path
_pending_archives: dict = {}
# Store active extraction tasks: user_id -> asyncio.Task
_active_tasks: dict = {}


@Client.on_message(filters.document & filters.private)
async def handle_archive(client: Client, message: Message):
    doc  = message.document
    if not doc:
        return

    fname = doc.file_name or ""
    if not is_archive(fname):
        return  # Not an archive — let other handlers deal with it

    user_id   = message.from_user.id
    file_size = doc.file_size or 0

    if file_size > Config.MAX_FILE_SIZE:
        await message.reply(f"❌ File too large: `{humanbytes(file_size)}`\nMax: `{humanbytes(Config.MAX_FILE_SIZE)}`")
        return

    status = await message.reply(
        f"📦 **Archive Detected:** `{fname}`\n"
        f"📦 **Size:** `{humanbytes(file_size)}`\n\n"
        f"⏳ Downloading…"
    )

    user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    dl_start = time.time()

    try:
        file_path = await client.download_media(
            message,
            file_name   = os.path.join(user_dir, fname),
            progress    = progress_for_pyrogram,
            progress_args = ("⬇️ Downloading archive", status, dl_start)
        )
    except Exception as e:
        await status.edit(f"❌ Download failed: `{e}`")
        return

    dl_time = round(time.time() - dl_start)
    await status.edit(f"✅ Downloaded in `{dl_time}s`\n\n🔍 Checking archive…")

    # Check if password protected
    if is_password_protected(file_path):
        _pending_archives[user_id] = file_path
        await status.edit(
            f"🔐 **Password Protected Archive**\n\n"
            f"📄 `{fname}`\n\n"
            f"Please reply with:\n`/password <your_password>`\n\n"
            f"Or tap below if you know it's wrong:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔓 Try Without Password", callback_data=f"unzip|nopass|{user_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"unzip|cancel|{user_id}")]
            ])
        )
        return

    # List contents first
    ok, err, names = await list_archive_contents(file_path)
    if ok and names:
        preview = "\n".join(f"• `{n}`" for n in names[:20])
        if len(names) > 20:
            preview += f"\n_…and {len(names)-20} more files_"

        await status.edit(
            f"📂 **Archive Contents ({len(names)} files):**\n\n{preview}\n\n"
            f"Extracting and uploading…"
        )

    # Start extraction
    task = asyncio.create_task(
        _extract_and_send(client, message, status, file_path, user_dir, user_id)
    )
    _active_tasks[user_id] = task
    await task


@Client.on_message(filters.command("password") & filters.private)
async def password_cmd(client: Client, message: Message):
    user_id = message.from_user.id
    args    = message.text.split(None, 1)

    if len(args) < 2:
        await message.reply("❌ Usage: `/password <your_password>`")
        return

    password   = args[1].strip()
    file_path  = _pending_archives.get(user_id)

    if not file_path or not os.path.exists(file_path):
        await message.reply("❌ No pending archive found. Please resend the file.")
        return

    user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))
    status   = await message.reply("🔓 Trying password…")

    task = asyncio.create_task(
        _extract_and_send(client, message, status, file_path, user_dir, user_id, password=password)
    )
    _active_tasks[user_id] = task
    await task
    _pending_archives.pop(user_id, None)


@Client.on_callback_query(filters.regex(r"^unzip\|"))
async def unzip_callback(client: Client, cb: CallbackQuery):
    await cb.answer()
    parts   = cb.data.split("|")
    action  = parts[1]
    user_id = int(parts[2])

    if action == "cancel":
        _pending_archives.pop(user_id, None)
        await cb.message.edit("❌ Extraction cancelled.")
        return

    if action == "nopass":
        file_path = _pending_archives.pop(user_id, None)
        if not file_path:
            await cb.message.edit("❌ Archive expired. Please resend.")
            return
        user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))
        task = asyncio.create_task(
            _extract_and_send(client, cb.message.reply_to_message or cb.message,
                              cb.message, file_path, user_dir, user_id)
        )
        _active_tasks[user_id] = task
        await task

    if action == "cancel_active":
        task = _active_tasks.get(user_id)
        if task and not task.done():
            task.cancel()
            await cb.message.edit("⛔ Extraction cancelled.")
        else:
            await cb.message.edit("⚠️ No active extraction found.")


async def _extract_and_send(
    client: Client,
    orig_msg: Message,
    status_msg: Message,
    file_path: str,
    user_dir: str,
    user_id: int,
    password: Optional[str] = None
):
    extract_dir = os.path.join(user_dir, f"extracted_{user_id}")
    try:
        # Extract
        ok, err, extracted_files = await extract_archive(
            file_path   = file_path,
            extract_dir = extract_dir,
            password    = password,
            status_msg  = status_msg
        )

        if not ok:
            await status_msg.edit(
                f"❌ **Extraction Failed**\n\n`{err}`\n\n"
                + ("Wrong password? Use `/password <correct_password>`" if "password" in err.lower() else "")
            )
            return

        if not extracted_files:
            await status_msg.edit("❌ No files found after extraction.")
            return

        total    = len(extracted_files)
        uploaded = 0
        failed   = 0

        await status_msg.edit(
            f"📤 **Uploading {total} file(s)…**\n\n"
            f"[{'░' * 20}] 0%\n\n"
            f"This may take a while.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⛔ Cancel Upload", callback_data=f"unzip|cancel_active|{user_id}")]
            ])
        )

        upload_start = time.time()

        for i, fpath in enumerate(extracted_files):
            rel_name = os.path.relpath(fpath, extract_dir)
            fname    = os.path.basename(fpath)
            fsize    = os.path.getsize(fpath)

            if fsize > Config.MAX_FILE_SIZE:
                await orig_msg.reply(f"⚠️ Skipped `{fname}` — too large (`{humanbytes(fsize)}`)")
                failed += 1
                continue

            try:
                file_status = await orig_msg.reply(f"⬆️ Uploading `{rel_name}`…")
                ul_start    = time.time()

                await client.send_document(
                    chat_id             = orig_msg.chat.id,
                    document            = fpath,
                    file_name           = fname,
                    caption             = f"📄 `{rel_name}`\n📦 `{humanbytes(fsize)}`",
                    reply_to_message_id = orig_msg.id,
                    progress            = progress_for_pyrogram,
                    progress_args       = (f"⬆️ Uploading {fname}", file_status, ul_start)
                )
                await file_status.delete()
                uploaded += 1

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Failed to upload {fname}: {e}")
                await orig_msg.reply(f"❌ Failed to upload `{fname}`: `{e}`")
                failed += 1

            # Update overall progress bar
            pct  = int((i + 1) * 100 / total)
            bar  = "█" * (pct // 5) + "░" * (20 - pct // 5)
            elapsed = round(time.time() - upload_start)
            try:
                await status_msg.edit(
                    f"📤 **Uploading {total} file(s)…**\n\n"
                    f"[{bar}] {pct}%\n\n"
                    f"✅ Uploaded: {uploaded} | ❌ Failed: {failed}\n"
                    f"⏱ Elapsed: `{elapsed}s`",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("⛔ Cancel Upload", callback_data=f"unzip|cancel_active|{user_id}")]
                    ])
                )
            except Exception:
                pass

        total_time = round(time.time() - upload_start)
        await status_msg.edit(
            f"✅ **Extraction Complete!**\n\n"
            f"📂 Total Files: `{total}`\n"
            f"⬆️ Uploaded: `{uploaded}`\n"
            f"❌ Failed: `{failed}`\n"
            f"⏱ Time: `{total_time}s`"
        )

    except asyncio.CancelledError:
        await status_msg.edit("⛔ **Extraction cancelled by user.**")
    except Exception as e:
        logger.error(f"_extract_and_send error: {e}")
        await status_msg.edit(f"❌ Error during extraction: `{e}`")
    finally:
        # Cleanup extracted dir
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)
        # Cleanup downloaded archive
        if os.path.exists(file_path):
            os.remove(file_path)
        _active_tasks.pop(user_id, None)
