"""
Admin commands: /status, /clean, /cancel, /broadcast
"""
import os
import shutil
import asyncio
import logging
import platform
import time

from pyrogram import Client, filters
from pyrogram.types import Message

from config import Config

logger = logging.getLogger(__name__)


# get_dir_size
def get_dir_size(path: str) -> int:
    total = 0
    try:
        for root, _, files in os.walk(path):
            for fname in files:
                fp = os.path.join(root, fname)
                try:
                    total += os.path.getsize(fp)
                except Exception:
                    pass
    except Exception:
        pass
    return total


def humanbytes(size: int) -> str:
    if not size:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    power = 1024
    n = 0
    while size >= power and n < 4:
        size /= power
        n += 1
    return f"{round(size, 2)} {units[n]}"


def get_disk_usage():
    try:
        total, used, free = shutil.disk_usage("/")
        return total, used, free
    except Exception:
        return 0, 0, 0


# ── /status ──────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("status"))
async def status_cmd(client: Client, message: Message):
    user_id  = message.from_user.id
    user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))

    # User's files
    user_size  = get_dir_size(user_dir)
    user_files = sum(len(files) for _, _, files in os.walk(user_dir)) if os.path.exists(user_dir) else 0

    # Total downloads folder
    total_dl_size  = get_dir_size(Config.DOWNLOAD_LOCATION)

    # Disk
    disk_total, disk_used, disk_free = get_disk_usage()

    # CPU / Memory
    try:
        import psutil
        cpu_pct = psutil.cpu_percent(interval=0.5)
        mem     = psutil.virtual_memory()
        mem_text = f"`{humanbytes(mem.used)}` / `{humanbytes(mem.total)}` ({mem.percent}%)"
        cpu_text = f"`{cpu_pct}%`"
    except ImportError:
        cpu_text = "_psutil not installed_"
        mem_text = "_psutil not installed_"

    disk_bar_pct = round(disk_used * 100 / disk_total) if disk_total else 0
    disk_bar     = "█" * (disk_bar_pct // 5) + "░" * (20 - disk_bar_pct // 5)

    text = (
        f"📊 **Server Status**\n\n"
        f"**💾 Disk:**\n"
        f"`[{disk_bar}]` {disk_bar_pct}%\n"
        f"Total: `{humanbytes(disk_total)}` | "
        f"Used: `{humanbytes(disk_used)}` | "
        f"Free: `{humanbytes(disk_free)}`\n\n"
        f"**🖥 CPU:** {cpu_text}\n"
        f"**🧠 RAM:** {mem_text}\n\n"
        f"**📁 Downloads Folder:**\n"
        f"Total: `{humanbytes(total_dl_size)}`\n\n"
        f"**👤 Your Files:**\n"
        f"Files: `{user_files}` | Size: `{humanbytes(user_size)}`\n\n"
        f"**🤖 Bot:**\n"
        f"Python: `{platform.python_version()}`\n"
        f"OS: `{platform.system()} {platform.release()}`"
    )
    await message.reply(text)


@Client.on_callback_query(filters.regex("^status$"))
async def status_cb(client, cb):
    await cb.answer()
    # Reuse status logic
    user_id  = cb.from_user.id
    user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))

    user_size  = get_dir_size(user_dir)
    user_files = sum(len(files) for _, _, files in os.walk(user_dir)) if os.path.exists(user_dir) else 0
    total_dl   = get_dir_size(Config.DOWNLOAD_LOCATION)
    disk_total, disk_used, disk_free = get_disk_usage()
    disk_bar_pct = round(disk_used * 100 / disk_total) if disk_total else 0
    disk_bar     = "█" * (disk_bar_pct // 5) + "░" * (20 - disk_bar_pct // 5)

    text = (
        f"📊 **Server Status**\n\n"
        f"`[{disk_bar}]` {disk_bar_pct}%\n"
        f"Free: `{humanbytes(disk_free)}` / `{humanbytes(disk_total)}`\n\n"
        f"📁 Downloads: `{humanbytes(total_dl)}`\n"
        f"👤 Your files: `{user_files}` (`{humanbytes(user_size)}`)"
    )
    await cb.message.edit(text)


# ── /clean ────────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("clean"))
async def clean_cmd(client: Client, message: Message):
    user_id  = message.from_user.id
    user_dir = os.path.join(Config.DOWNLOAD_LOCATION, str(user_id))

    if not os.path.exists(user_dir):
        await message.reply("✅ Nothing to clean — your folder is already empty.")
        return

    size_before = get_dir_size(user_dir)
    try:
        shutil.rmtree(user_dir, ignore_errors=True)
        os.makedirs(user_dir, exist_ok=True)
        await message.reply(
            f"🧹 **Cleaned!**\n\n"
            f"Freed: `{humanbytes(size_before)}`"
        )
    except Exception as e:
        await message.reply(f"❌ Clean failed: `{e}`")


# ── /cancel ───────────────────────────────────────────────────────────────────

@Client.on_message(filters.command("cancel"))
async def cancel_cmd(client: Client, message: Message):
    from plugins.url_upload import active_uploads
    from plugins.unzip import _active_tasks

    user_id = message.from_user.id
    cancelled = False

    task = active_uploads.get(user_id)
    if task and not task.done():
        task.cancel()
        cancelled = True

    task2 = _active_tasks.get(user_id)
    if task2 and not task2.done():
        task2.cancel()
        cancelled = True

    if cancelled:
        await message.reply("⛔ **Task cancelled.**")
    else:
        await message.reply("⚠️ No active task to cancel.")


# ── /broadcast (owner only) ───────────────────────────────────────────────────

@Client.on_message(filters.command("broadcast") & filters.user(Config.OWNER_ID))
async def broadcast_cmd(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply("❌ Reply to a message to broadcast it.")
        return

    await message.reply("📡 Broadcast started… (implement user DB for full broadcast)")
    # Placeholder — full implementation needs a user database
