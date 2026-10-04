"""yt-dlp service for URL analysis and download management."""
import json
import hashlib
import subprocess
import platform
import os
import re
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

from config import YTDLP_BIN, FFMPEG_BIN, QUALITY_FORMAT_MAP, TEMP_DIR
from utils.security import sanitize_filename

# ---------------------------------------------------------------------------
# Single yt-dlp launcher.
#
# Windows Application Control (AppLocker) blocks direct execution of
# yt-dlp.exe via WinError 4551.  Invoking yt-dlp as a Python module via
# the CURRENT interpreter is exempt from that restriction and is the
# preferred launch method.  ALL subprocess calls must use this list as the
# executable prefix rather than YTDLP_BIN directly.
#
# sys.executable resolves to the same python.exe that is running the Flask
# server, so there is no hardcoded path and no venv/system conflict.
# ---------------------------------------------------------------------------
YT_DLP_CMD: List[str] = [sys.executable, "-m", "yt_dlp"]


# Selective English subtitle language patterns.
#
# yt-dlp --sub-langs matches each pattern with re.fullmatch (case-insensitive),
# so these patterns only match the exact language code — never a translated
# track such as "en-de" or "en-fr".
#
# Priority order: manual English first, then auto-generated English, then
# English (original) captions. Regional variants (en-US, en-GB, etc.) are
# included so legitimate English variants are not missed.
ENGLISH_SUBTITLE_PATTERNS = [
    "en",          # Manual English
    "en-en",       # Auto-generated English
    "en-orig",     # English (original) captions
    "en-US",       # Manual English (US)
    "en-GB",       # Manual English (UK)
    "en-AU",       # Manual English (Australia)
    "en-CA",       # Manual English (Canada)
    "en-NZ",       # Manual English (New Zealand)
    "en-IE",       # Manual English (Ireland)
    "en-ZA",       # Manual English (South Africa)
    "en-IN",       # Manual English (India)
    "en-PH",       # Manual English (Philippines)
    "en-SG",       # Manual English (Singapore)
    "en-HK",       # Manual English (Hong Kong)
    "en-NG",       # Manual English (Nigeria)
    "en-GH",       # Manual English (Ghana)
    "en-KW",       # Manual English (Kuwait)
    "en-JM",       # Manual English (Jamaica)
    "en-TT",       # Manual English (Trinidad and Tobago)
    "en-BZ",       # Manual English (Belize)
    "en-KI",       # Manual English (Kiribati)
    "en-MH",       # Manual English (Marshall Islands)
    "en-PW",       # Manual English (Palau)
    "en-SB",       # Manual English (Solomon Islands)
    "en-VU",       # Manual English (Vanuatu)
    "en-CK",       # Manual English (Cook Islands)
]


def build_yt_dlp_args(
    url: str,
    output_template: str,
    quality: str = "best",
    subtitles: List[str] | None = None,
    write_thumbnail: bool = True,
    embed_subtitles: bool = True,
    embed_metadata: bool = True,
    embed_thumbnail: bool = True,
    format: str | None = None,
    extract_audio: bool = False,
    limit_rate: str | None = None,
    skip_subtitles: bool = False,
) -> List[str]:
    """Build a safe argument list for yt-dlp subprocess execution."""
    args = list(YT_DLP_CMD)  # copy so callers can't mutate the shared list

    if limit_rate and str(limit_rate) != "0":
        args.extend(["--limit-rate", str(limit_rate)])

    # Output template
    args.extend(["-o", output_template])

    # Format selection
    if format:
        if format == "bestvideo+bestaudio":
            args.extend(["-f", "bestvideo+bestaudio/best"])
        else:
            args.extend(["-f", format])
    elif quality in QUALITY_FORMAT_MAP:
        args.extend(["-f", QUALITY_FORMAT_MAP[quality]])
    else:
        args.extend(["-f", "bestvideo+bestaudio/best"])

    if FFMPEG_BIN:
        args.extend(["--ffmpeg-location", FFMPEG_BIN])

    # Audio extraction (only when requested)
    if extract_audio:
        args.extend(["--extract-audio", "--audio-format", "mp3", "--audio-quality", "0"])

    # Handle subtitles - only when subtitles are requested and skip_subtitles=False
    if not skip_subtitles and subtitles is None:
        # Default to English subtitles for video downloads when not explicitly specified
        # No subtitle flags for audio-only downloads (extract_audio=True)
        if extract_audio:
            subtitles = []
        else:
            # Match selective English patterns only (manual + auto English, no translations)
            subtitles = list(ENGLISH_SUBTITLE_PATTERNS)

    if not skip_subtitles and subtitles:
        # --write-subs: download manual subtitles
        # --write-auto-subs: fall back to auto-generated subtitles
        # --sub-langs: match language patterns (e.g., en, en-en, en-US)
        args.extend([
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            ",".join(subtitles),
        ])
        if embed_subtitles:
            args.append("--embed-subs")

    # Metadata
    if write_thumbnail:
        args.append("--write-thumbnail")
    if embed_metadata:
        args.append("--add-metadata")
    if embed_thumbnail:
        args.append("--embed-thumbnail")

    # Playlist extraction
    args.append("--no-overwrites")
    args.append("--continue")
    # Resilience against YouTube HTTP 429 blocks
    args.extend(["--extractor-args", "youtube:player_client=android,web"])
    # Use progress-json for reliable parsing
    args.extend(["--newline", "--no-warnings"])

    args.append(url)

    return args


def build_probe_args(file_path: str) -> List[str]:
    """Build FFprobe arguments."""
    return [FFMPEG_BIN, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", file_path]


def analyze_url(url: str) -> dict:
    """Analyze a URL and return media metadata."""
    args = YT_DLP_CMD + [
        "--flat-playlist",
        "-J",
        "--no-warnings",
        "--extractor-args", "youtube:player_client=android,web",
        url,
    ]

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            # 60 s: allows for python -m yt_dlp cold-start (~5–15 s import time)
            # plus YouTube metadata fetch (~5–15 s), with margin for slow networks.
            timeout=60,
        )

        if result.returncode != 0:
            return {"error": f"yt-dlp analysis failed: {result.stderr[:300]}", "valid": False}

        data = json.loads(result.stdout.strip())
        is_playlist = data.get("playlist_count", 0) > 0 or bool(data.get("entries"))

        return {
            "valid": True,
            "id": data.get("id"),
            "title": data.get("title", "Unknown"),
            "uploader": data.get("uploader"),
            "duration": data.get("duration"),
            "thumbnail": data.get("thumbnail"),
            "is_playlist": is_playlist,
            "playlist_count": data.get("playlist_count", len(data.get("entries", []))) if is_playlist else None,
            "webpage_url": data.get("webpage_url"),
            "formats_count": len(data.get("formats", [])),
            "description": data.get("description"),
            "upload_date": data.get("upload_date"),
            "view_count": data.get("view_count"),
            "channel_url": data.get("channel_url"),
        }

    except subprocess.TimeoutExpired:
        return {"error": "Analysis timed out", "valid": False}
    except json.JSONDecodeError:
        return {"error": "Could not parse analysis results", "valid": False}
    except Exception as e:
        return {"error": str(e), "valid": False}


def get_audio_id(url: str) -> str:
    """Get a unique identifier for a download (for duplicate detection)."""
    args = YT_DLP_CMD + ["-j", "--no-warnings", "--print", "id", url]
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return hashlib.md5(url.encode()).hexdigest()[:16]


def compute_file_hash(file_path: str) -> Optional[str]:
    """Compute MD5 hash of a file for duplicate detection.

    Note: MD5 is used for file integrity comparison, NOT for security purposes.
    """
    if not Path(file_path).exists():
        return None
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return None


def get_output_path_from_ydl(outdir: str, filename: str) -> str:
    """Get the expected output path for a download."""
    safe_name = sanitize_filename(filename)
    return str(Path(outdir) / f"{safe_name}.mp3")


def spawn_download_process(
    url: str,
    output_path: str,
    quality: str = "best",
    subtitles: List[str] | None = None,
    format: str | None = None,
    on_progress=None,
    on_complete=None,
    on_error=None,
    extract_audio: bool = False,
    limit_rate: str | None = None,
    embed_subtitles: bool = True,
    skip_subtitles: bool = False,
) -> subprocess.Popen:
    """Spawn a yt-dlp download process.

    Args:
        url: URL to download
        output_path: Output file path pattern
        quality: Quality preset
        subtitles: List of subtitle languages
        format: Override format string
        extract_audio: Extract audio only
        limit_rate: Download speed limit
        embed_subtitles: Whether to embed subtitles in the output file
        skip_subtitles: If True, skip all subtitle-related yt-dlp flags

    Returns:
        subprocess.Popen object
    """
    args = build_yt_dlp_args(
        url=url,
        output_template=output_path,
        quality=quality,
        subtitles=subtitles,
        format=format,
        extract_audio=extract_audio,
        limit_rate=limit_rate,
        embed_subtitles=embed_subtitles,
        skip_subtitles=skip_subtitles,
    )

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,  # Combine stderr into stdout for unified parsing
        text=True,
        bufsize=0,  # Unbuffered for real-time line reading
        cwd=str(TEMP_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        encoding='utf-8',
        errors='replace',
    )

    return proc


def terminate_process_tree(process: subprocess.Popen) -> dict:
    """Terminate a process and all its children (Windows-safe)."""
    import signal
    import psutil

    killed = False
    reason = ""

    try:
        if platform.system() == "Windows":
            # Use taskkill to kill the process tree
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                killed = True
                reason = "Process tree terminated via taskkill"
            else:
                # Fallback to Popen methods
                try:
                    process.terminate()
                    process.wait(timeout=5)
                    killed = True
                    reason = "Terminated via SIGTERM"
                except subprocess.TimeoutExpired:
                    process.kill()
                    killed = True
                    reason = "Killed via SIGKILL"
        else:
            # Unix: kill process group
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                killed = True
                reason = "Terminated via SIGTERM (process group)"
            except ProcessLookupError:
                killed = True
                reason = "Process already terminated"
            except Exception:
                try:
                    process.terminate()
                    killed = True
                    reason = "Terminated via SIGTERM (fallback)"
                except Exception:
                    pass

    except Exception as e:
        try:
            process.terminate()
            killed = True
            reason = f"Terminated via SIGTERM: {e}"
        except Exception:
            pass

    return {"killed": killed, "reason": reason}


def get_process_status(process: subprocess.Popen) -> dict:
    """Get the current status of a download process."""
    result = process.poll()
    if result is not None:
        return {"running": False, "exit_code": result}
    return {"running": True}


def _parse_size(value: str | None) -> Optional[float]:
    """Parse a human-readable size string into bytes."""
    if not value:
        return None
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGT]i?B|B)?", value, re.IGNORECASE)
    if not match:
        return None
    try:
        number = float(match.group(1))
        unit = (match.group(2) or "B").lower()
        multipliers = {
            "b": 1,
            "kb": 1000,
            "kib": 1024,
            "mb": 1000**2,
            "mib": 1024**2,
            "gb": 1000**3,
            "gib": 1024**3,
            "tb": 1000**4,
            "tib": 1024**4,
        }
        return number * multipliers.get(unit, 1)
    except (ValueError, TypeError):
        return None


def _parse_eta(value: str | None) -> Optional[int]:
    """Parse ETA string (HH:MM:SS or MM:SS) into seconds."""
    if not value:
        return None
    parts = [int(p) for p in value.split(":")]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 1:
        return parts[0]
    return None


def parse_progress_line(line: str) -> Optional[Dict]:
    """Parse a yt-dlp progress line and return progress info.

    Handles both:
    1. JSON progress lines (yt-dlp --progress-json when available)
    2. Human-readable --newline output (fallback for older yt-dlp versions)

    Example human-readable format:
    [download]  50.0% of 100.00MiB at 2.50MiB/s ETA 00:05
    """
    line = line.strip()
    if not line:
        return None

    # Try to parse as JSON first (structured, preferred)
    if line.startswith("{"):
        try:
            data = json.loads(line)
            return {
                "status": data.get("status"),
                "downloaded_bytes": data.get("downloaded_bytes", 0),
                "total_bytes": data.get("total_bytes"),
                "total_bytes_estimate": data.get("total_bytes_estimate"),
                "speed": data.get("speed"),
                "eta": data.get("eta"),
                "filename": data.get("filename"),
                "filepath": data.get("filepath") or data.get("filename"),
                "_eta_str": data.get("_eta_str"),
            }
        except (json.JSONDecodeError, ValueError):
            pass

    # Fall back to parsing --newline human-readable output
    # yt-dlp --newline format: [download] 50.0% of 100.00MiB at 2.50MiB/s ETA 00:05
    match = re.match(
        r"\[(?P<kind>download|ffmpeg|postprocess)\]\s+"
        r"(?P<pct>[0-9]+(?:\.[0-9]+)?)%\s+of\s+"
        r"(?P<total>[0-9]+(?:\.[0-9]+)?(?:\s*[KMGT]i?B|B)?)\s*"
        r"(?:at\s+(?P<speed>[0-9]+(?:\.[0-9]+)?(?:\s*[KMGT]i?B|B)/s)\s*)?"
        r"(?:ETA\s+(?P<eta>\d{1,3}:\d{2}(?::\d{2})?))?\s*$",
        line,
        re.IGNORECASE,
    )
    if not match:
        # Handle lines without percentage (e.g., "100% of 100.00MiB") or
        # variants where ETA is shown as a single number
        return None

    pct = float(match.group("pct"))
    total_bytes = _parse_size(match.group("total"))
    speed = _parse_size(match.group("speed"))
    eta = _parse_eta(match.group("eta"))
    downloaded_bytes = int(total_bytes * pct / 100) if total_bytes is not None else 0

    return {
        "status": "downloading" if pct < 100 else "finished",
        "downloaded_bytes": downloaded_bytes,
        "total_bytes": total_bytes,
        "total_bytes_estimate": total_bytes,
        "speed": speed,
        "eta": eta,
        "filename": None,
        "filepath": None,
        "_eta_str": match.group("eta"),
    }
