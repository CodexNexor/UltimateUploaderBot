"""
/start and /help commands.
"""
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton


START_TEXT = """
🚀 **Ultimate URL Uploader + Unzip Bot**

Send me any link and I'll download & upload it to Telegram!

**What I can do:**
• 📥 Direct HTTP/HTTPS file download
• 📺 HLS / DASH stream download
• 🎬 YouTube, Instagram, Twitter, Facebook
• 🔍 Webpage scan & media link extraction
• 📦 Unzip RAR, ZIP, 7z, TAR (with password support)

**How to use:**
• Just paste any URL — I'll detect & download it
• Send a ZIP/RAR/7z file — I'll extract & send files
• Use `/extract <url>` to scan a webpage for media links

**Commands:**
`/start` — This message
`/help` — Detailed help
`/status` — Server storage status
`/clean` — Clean your downloaded files
`/cancel` — Cancel current task
"""

HELP_TEXT = """
📖 **Detailed Help**

**URL Upload:**
• Paste any direct link → bot downloads & uploads
• For webpages, use `/extract <url>` to scan for links
• Supports: mp4, mkv, mp3, zip, rar, pdf, apk, etc.
• Format: `URL` or `URL | custom_filename.ext`

**HLS / Streams:**
• `.m3u8` or `.mpd` links auto-detected
• Downloaded using yt-dlp + ffmpeg

**Social Media:**
• YouTube, Instagram, Twitter, Facebook — just paste link

**Unzip:**
• Send any `.zip .rar .7z .tar .tar.gz` file
• Bot extracts and sends all files
• Password? Reply with `/password <yourpass>` after sending

**Admin Commands:**
`/status` — Disk usage & download folder size
`/clean` — Remove your temp files on server
`/broadcast` — (Owner only) Broadcast to all users

**Tips:**
• Use `URL | filename.mp4` to set custom filename
• For Instagram/TikTok private links, may not work
"""


@Client.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Help", callback_data="help"),
            InlineKeyboardButton("📊 Status", callback_data="status"),
        ],
        [
            InlineKeyboardButton("🔗 Source", url="https://github.com/CodexNexor/UltimateUploaderBot"),
        ]
    ])
    await message.reply(START_TEXT, reply_markup=buttons, disable_web_page_preview=True)


@Client.on_message(filters.command("help"))
async def help_cmd(client: Client, message: Message):
    await message.reply(HELP_TEXT, disable_web_page_preview=True)


@Client.on_callback_query(filters.regex("^help$"))
async def help_cb(client, cb):
    await cb.message.edit(HELP_TEXT, disable_web_page_preview=True)
    await cb.answer()


@Client.on_callback_query(filters.regex("^start$"))
async def start_cb(client, cb):
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📖 Help", callback_data="help"),
            InlineKeyboardButton("📊 Status", callback_data="status"),
        ],
    ])
    await cb.message.edit(START_TEXT, reply_markup=buttons, disable_web_page_preview=True)
    await cb.answer()
