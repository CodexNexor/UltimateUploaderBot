# Ultimate Uploader Bot

Ultimate Uploader Bot is a Pyrogram-based Telegram URL uploader and archive extraction bot. It downloads direct links, HLS/DASH streams, social media videos, and scraped media links, then uploads the result to Telegram with progress updates and automatic cleanup.

SEO keywords: Telegram URL uploader bot, Telegram file uploader, Pyrogram uploader bot, Telegram archive extractor, Telegram unzip bot, HLS downloader bot, yt-dlp Telegram bot, direct link uploader bot.

## Features

| Area | What It Does |
| --- | --- |
| URL uploads | Downloads direct HTTP/HTTPS links and uploads them to Telegram |
| Stream support | Handles HLS `.m3u8` and DASH `.mpd` links with `yt-dlp` and `ffmpeg` |
| Social platforms | Supports URLs handled by `yt-dlp`, including YouTube, Instagram, X/Twitter, and Facebook |
| Web extraction | Scans webpages for downloadable media links and shows selectable results |
| Archive extraction | Extracts ZIP, RAR, 7z, TAR, TAR.GZ, TGZ, TAR.BZ2, TAR.XZ, and GZ files |
| Password archives | Supports passwords for ZIP, RAR, and 7z where the extractor supports them |
| Upload formats | Sends files as video, audio, document, or photo |
| Safety cleanup | Asks before sending downloaded files, deletes after 5 minutes without confirmation, and removes files after upload |
| Status tools | Shows disk, CPU, RAM, and per-user temporary storage usage |

## Security And Privacy

This project is designed so secrets stay local:

- Real credentials belong in `.env`.
- `.env` is ignored by Git through `.gitignore`.
- `.env` is ignored by Docker builds through `.dockerignore`.
- `.env.example` contains placeholders only.
- Downloads and thumbnails are temporary and ignored by Git.

Never commit your `BOT_TOKEN`, `API_HASH`, Telegram user IDs you want private, session files, downloaded files, or logs containing private URLs.

If you accidentally publish a bot token, revoke it immediately with [@BotFather](https://t.me/BotFather), create a new token, and update your local `.env`.

## Requirements

- Python 3.10 or newer
- Telegram bot token from [@BotFather](https://t.me/BotFather)
- Telegram API ID and API hash from [my.telegram.org](https://my.telegram.org)
- `ffmpeg`
- `unrar`
- `p7zip-full`

## Installation

### 1. Install System Packages

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg unrar p7zip-full
```

### 2. Clone The Repository

```bash
git clone https://github.com/CodexNexor/UltimateUploaderBot.git
cd UltimateUploaderBot
```

### 3. Create A Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Configure Environment Variables

```bash
cp .env.example .env
nano .env
```

Fill in:

```bash
BOT_TOKEN=your_bot_token_here
API_ID=your_api_id
API_HASH=your_api_hash
OWNER_ID=your_telegram_user_id
```

Optional settings:

```bash
ADMIN_IDS=
LOG_CHANNEL=0
FORCE_SUB_CHANNEL=
DOWNLOAD_LOCATION=./DOWNLOADS
THUMB_LOCATION=./THUMBNAILS
FFMPEG_PATH=ffmpeg
UPLOAD_CONFIRM_TIMEOUT=300
```

### 6. Run The Bot

```bash
python bot.py
```

## Docker Installation

### 1. Build The Image

```bash
docker build -t ultimate-uploader-bot .
```

### 2. Run The Container

```bash
docker run -d \
  --name ultimate-uploader-bot \
  --env-file .env \
  --restart unless-stopped \
  ultimate-uploader-bot
```

### 3. View Logs

```bash
docker logs -f ultimate-uploader-bot
```

### 4. Stop The Bot

```bash
docker stop ultimate-uploader-bot
```

## Configuration Reference

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `BOT_TOKEN` | Yes | empty | Bot token from BotFather |
| `API_ID` | Yes | `0` | Telegram API ID from my.telegram.org |
| `API_HASH` | Yes | empty | Telegram API hash from my.telegram.org |
| `OWNER_ID` | Yes | `0` | Telegram numeric user ID for owner-only commands |
| `ADMIN_IDS` | No | empty | Comma-separated extra admin user IDs |
| `LOG_CHANNEL` | No | `0` | Telegram log channel ID, if used |
| `FORCE_SUB_CHANNEL` | No | empty | Channel ID required for force subscribe, if used |
| `DOWNLOAD_LOCATION` | No | `./DOWNLOADS` | Temporary download directory |
| `THUMB_LOCATION` | No | `./THUMBNAILS` | Temporary thumbnail directory |
| `FFMPEG_PATH` | No | `ffmpeg` | Path to the ffmpeg binary |
| `UPLOAD_CONFIRM_TIMEOUT` | No | `300` | Seconds to wait for upload confirmation before deleting the downloaded file |

## Bot Commands

| Command | Description |
| --- | --- |
| `/start` | Show the welcome message |
| `/help` | Show detailed usage help |
| `/extract <url>` | Scan a webpage for downloadable media links |
| `/password <password>` | Set a password for a pending archive extraction |
| `/status` | Show server disk, CPU, RAM, and temporary file usage |
| `/clean` | Delete your temporary files |
| `/cancel` | Cancel your active task |
| `/broadcast` | Owner-only broadcast placeholder |

## Usage Examples

Direct file upload:

```text
https://example.com/video.mp4
```

Direct file upload with a custom filename:

```text
https://example.com/video.mp4 | MyVideo.mp4
```

HLS stream:

```text
https://example.com/playlist.m3u8
```

Scan a webpage:

```text
/extract https://example.com/download-page
```

Extract an archive:

```text
Send a .zip, .rar, .7z, .tar, .tar.gz, .tgz, .tar.bz2, .tar.xz, or .gz file to the bot.
```

Password-protected archive:

```text
/password your_password_here
```

## Upload Confirmation And Cleanup

After a URL file finishes downloading, the bot asks the user whether to send or delete it.

- Press `Send` to upload it to Telegram.
- Press `Delete` to remove it from the VPS.
- If there is no response within `UPLOAD_CONFIRM_TIMEOUT` seconds, the file is deleted automatically.
- After a successful or failed upload attempt, the downloaded file and generated thumbnail are removed.

This keeps the VPS from storing user files after the task is finished.

## Project Structure

```text
UltimateUploaderBot/
├── bot.py
├── config.py
├── requirements.txt
├── Dockerfile
├── .env.example
├── helper_funcs/
│   ├── downloader.py
│   ├── extractor.py
│   ├── metadata.py
│   ├── progress.py
│   └── url_analyzer.py
└── plugins/
    ├── admin.py
    ├── start.py
    ├── unzip.py
    └── url_upload.py
```

## Troubleshooting

`API_ID` or `API_HASH` error:

Check that both values are set in `.env` and are copied exactly from my.telegram.org.

`ffmpeg` not found:

Install ffmpeg or set `FFMPEG_PATH` in `.env`.

RAR extraction fails:

Install `unrar` and confirm it is available in your server PATH.

7z extraction fails:

Install `p7zip-full`.

Large upload fails:

Telegram file size limits depend on account and bot/API behavior. Keep files within Telegram-supported limits and make sure your VPS has enough temporary disk space during download/upload.

## Deployment Notes

- Use a VPS with enough disk space for the largest file you plan to process.
- Use `systemd`, Docker restart policies, or a process manager to keep the bot online.
- Keep `.env` permissions private on shared servers.
- Rotate your bot token if it is ever exposed.

## License

No license is currently declared. Add a license before accepting external contributions.
