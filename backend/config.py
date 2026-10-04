"""Application configuration for UniversalDownloader."""
import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "universal_downloader.db"
DOWNLOADS_DIR = BASE_DIR / "downloads"
TEMP_DIR = BASE_DIR / "temp"

# Ensure runtime directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Flask
FLASK_HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

# yt-dlp / FFmpeg
import shutil
YTDLP_BIN = os.environ.get("YTDLP_BIN") or shutil.which("yt-dlp") or "yt-dlp"
FFMPEG_BIN = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg") or "ffmpeg"

# Concurrency
DEFAULT_MAX_CONCURRENCY = int(os.environ.get("DEFAULT_MAX_CONCURRENCY", "3"))
MAX_CONCURRENCY = int(os.environ.get("MAX_CONCURRENCY", "6"))

# Rate limiting (requests per minute per IP)
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", "120"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

# Bandwidth limit (bytes/sec, 0 = unlimited)
DEFAULT_BANDWIDTH_LIMIT = int(os.environ.get("DEFAULT_BANDWIDTH_LIMIT", "0"))

# Allowed URL schemes
ALLOWED_SCHEMES = {"http", "https"}

# Blocked hostnames (always reject)
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",
}

# Default settings
DEFAULT_SETTINGS = {
    "max_concurrency": str(DEFAULT_MAX_CONCURRENCY),
    "default_quality": "best",
    "default_format": "bestvideo+bestaudio",
    "subtitle_languages": "en",
    "auto_embed_subtitles": "true",
    "auto_organize": "true",
    "duplicate_detection": "true",
    "bandwidth_limit": str(DEFAULT_BANDWIDTH_LIMIT),
    "save_location": str(DOWNLOADS_DIR),
    "filename_template": "{title}.{ext}",
    "notifications": "true",
    "retry_enabled": "true",
    "max_retries": "3",
    "embed_metadata": "true",
    "embed_thumbnail": "true",
    "theme": "dark",
    "accent": "blue",
}

# Quality -> yt-dlp format spec mapping
QUALITY_FORMAT_MAP = {
    "best": "bestvideo*+bestaudio/best",
    "2160p": "bestvideo*[height<=2160]+bestaudio/best[height<=2160]/best",
    "1440p": "bestvideo*[height<=1440]+bestaudio/best[height<=1440]/best",
    "1080p": "bestvideo*[height<=1080]+bestaudio/best[height<=1080]/best",
    "720p": "bestvideo*[height<=720]+bestaudio/best[height<=720]/best",
    "480p": "bestvideo*[height<=480]+bestaudio/best[height<=480]/best",
    "360p": "bestvideo*[height<=360]+bestaudio/best[height<=360]/best",
    "audio": "bestaudio/best",
}


def load_settings():
    """Load settings from the database, falling back to defaults."""
    from database.db import get_db
    db = get_db()
    cursor = db.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    settings = dict(DEFAULT_SETTINGS)
    for row in rows:
        settings[row["key"]] = row["value"]
    return settings


def get_setting(key, default=None):
    """Get a single setting value."""
    settings = load_settings()
    return settings.get(key, default)