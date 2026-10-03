"""Core download service for UniversalDownloader.

Manages download lifecycle: create, queue, claim, execute, pause, resume, cancel.
Uses yt-dlp with process-based execution and a worker pool for concurrency.
"""

import json
import hashlib
import os
import platform
import subprocess
import threading
import time
import signal
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from config import (
    DOWNLOADS_DIR,
    TEMP_DIR,
    FFMPEG_BIN,
    YTDLP_BIN,
    DEFAULT_MAX_CONCURRENCY,
    QUALITY_FORMAT_MAP,
    MAX_CONCURRENCY,
)
from services.yt_dlp_service import (
    spawn_download_process,
    terminate_process_tree,
    parse_progress_line,
    ENGLISH_SUBTITLE_PATTERNS,
    YT_DLP_CMD,
    analyze_url as yt_dlp_analyze_url,
)
from database.db import get_db, get_connection, transaction, row_to_dict, rows_to_dict
from services.process_manager import terminate_subprocess, is_windows
from utils.security import validate_url, sanitize_filename, validate_save_path
from utils.files import (
    compute_file_hash,
    get_file_type,
    sanitize_file_path,
    organize_file,
    cleanup_task_temp_dir,
    list_task_temp_dirs,
)


def analyze_url_impl(url: str) -> dict:
    """Analyze a URL using the yt-dlp service."""
    return yt_dlp_analyze_url(url)


_claim_lock = threading.RLock()

ISO_639_MAP: Dict[str, str] = {
    "en": "eng",
    "es": "spa",
    "fr": "fre",
    "de": "ger",
    "it": "ita",
    "pt": "por",
    "hi": "hin",
    "te": "tel",
    "ta": "tam",
    "ja": "jpn",
    "ko": "kor",
    "zh": "chi",
    "ru": "rus",
    "ar": "ara",
    "nl": "dut",
    "pl": "pol",
    "tr": "tur",
    "sv": "swe",
    "no": "nor",
    "da": "dan",
    "fi": "fin",
    "cs": "cze",
    "el": "gre",
    "he": "heb",
    "id": "ind",
    "vi": "vie",
    "th": "tha",
    "uk": "ukr",
}


def normalize_subtitle_language_tag(lang: Optional[str]) -> str:
    """Map a language code (e.g. 'en', 'en-US', 'es', 'fr') to an ISO 639-2 3-letter code for FFmpeg metadata."""
    if not lang:
        return "eng"
    code = lang.strip().lower()
    primary = code.split("-")[0].split("_")[0]
    if primary in ISO_639_MAP:
        return ISO_639_MAP[primary]
    if len(code) == 3 and code.isalpha():
        return code
    return ISO_639_MAP.get(primary, "eng")



class DownloadService:
    """Service for managing all download operations."""

    def __init__(self):
        self._pause_flags: Dict[int, bool] = {}
        self._cancel_flags: Dict[int, bool] = {}
        self._download_processes: Dict[int, subprocess.Popen] = {}
        self._download_filepath: Dict[int, str] = {}  # Captured output paths
        self._last_error: Dict[int, str] = {}
        self._process_lock = threading.RLock()
        self._worker_pool_started = False
        self._worker_pool_thread: Optional[threading.Thread] = None
        self._worker_id = f"worker-{os.getpid()}"
        self._max_workers = DEFAULT_MAX_CONCURRENCY

    def _load_max_workers(self) -> int:
        try:
            conn = get_connection()
            row = conn.execute("SELECT value FROM settings WHERE key = 'max_concurrency'").fetchone()
            conn.close()
            if row:
                return min(int(row["value"]), MAX_CONCURRENCY)
        except Exception:
            pass
        return DEFAULT_MAX_CONCURRENCY

    def analyze_url(self, url: str) -> dict:
        """Analyze a URL and return metadata."""
        validation = validate_url(url)
        if not validation["safe"]:
            try:
                conn = get_connection()
                reason = validation.get("reason", "URL validation failed")
                severity = "critical" if any(k in reason.lower() for k in ["blocked", "private", "loopback"]) else "warning"
                conn.execute(
                    "INSERT INTO security_events (event_type, severity, description, url) VALUES (?, ?, ?, ?)",
                    ("ssrf_blocked", severity, reason, url),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
            return {"valid": False, "error": validation["reason"]}

        return analyze_url_impl(url)

    # ---- Download Creation ----

    def create_download(self, url: str, quality: str = "best",
                        format_str: str = "bestvideo+bestaudio",
                        subtitle_languages: List[str] | str | None = None,
                        save_location: str | None = None) -> dict:
        """Create a new download and add it to the queue."""
        validation = validate_url(url)
        if not validation["safe"]:
            try:
                conn = get_connection()
                reason = validation.get("reason", "URL validation failed")
                severity = "critical" if any(k in reason.lower() for k in ["blocked", "private", "loopback"]) else "warning"
                conn.execute(
                    "INSERT INTO security_events (event_type, severity, description, url) VALUES (?, ?, ?, ?)",
                    ("invalid_url", severity, reason, url),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
            return {"success": False, "error": validation["reason"]}

        analysis = self.analyze_url(url)
        if not analysis.get("valid"):
            return {"success": False, "error": analysis.get("error", "Analysis failed")}

        title = analysis.get("title", "Unknown")
        is_playlist = analysis.get("is_playlist", False)
        is_audio_only = quality == "audio" or ("audio" in format_str.lower() and "video" not in format_str.lower())
        media_type = "playlist" if is_playlist else ("audio" if is_audio_only else "video")

        save_location = save_location or str(DOWNLOADS_DIR)
        path_validation = validate_save_path(save_location)
        if not path_validation["safe"]:
            try:
                conn = get_connection()
                conn.execute(
                    "INSERT INTO security_events (event_type, severity, description) VALUES (?, ?, ?)",
                    ("unsafe_path", "critical", f"Blocked unsafe save location: {save_location}"),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
            return {"success": False, "error": path_validation["reason"]}

        sanitized_title = sanitize_filename(title)
        output_template = str(Path(save_location) / f"{sanitized_title}.%(ext)s")

        source_hash = hashlib.md5(url.encode()).hexdigest()

        if subtitle_languages is None:
            sub_langs_db = None
        elif isinstance(subtitle_languages, str):
            sub_langs_db = subtitle_languages.strip()
        elif isinstance(subtitle_languages, list):
            sub_langs_db = ",".join(subtitle_languages) if subtitle_languages else ""
        else:
            sub_langs_db = None

        with transaction() as conn:
            existing = conn.execute(
                "SELECT id FROM downloads WHERE source_hash = ? AND status = 'completed'",
                (source_hash,),
            ).fetchone()
            is_duplicate = existing is not None

            cursor = conn.execute(
                """
                INSERT INTO downloads
                (url, title, media_type, quality, format, subtitle_languages, save_location,
                 status, source_hash, is_duplicate, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (url, title, media_type, quality, format_str,
                 sub_langs_db,
                 save_location, source_hash, int(is_duplicate)),
            )
            download_id = cursor.lastrowid

            cursor = conn.execute(
                "INSERT INTO queue (download_id, position, status) VALUES (?, (SELECT COALESCE(MAX(position), 0) + 1 FROM queue), 'queued')",
                (download_id,),
            )

            if is_duplicate:
                conn.execute(
                    "INSERT INTO security_events (event_type, severity, description) VALUES ('duplicate_detected', 'info', ?)",
                    (f"Duplicate detected for URL: {url}",),
                )

        self._update_download_metadata(download_id, analysis)

        return {
            "success": True,
            "download_id": download_id,
            "title": title,
            "is_playlist": is_playlist,
            "is_duplicate": is_duplicate,
            "media_type": media_type,
        }

    # ---- Queue Management ----

    def get_queue(self) -> List[dict]:
        """Get all queue items ordered by position."""
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT q.*, d.title, d.status as download_status, d.progress, d.media_type, d.quality, d.format, d.speed, d.eta_seconds, d.total_size, d.downloaded_size
            FROM queue q
            JOIN downloads d ON q.download_id = d.id
            ORDER BY q.position ASC
            """
        ).fetchall()
        conn.close()
        return rows_to_dict(rows)

    def claim_next_task(self, worker_id: str) -> Optional[dict]:
        """Atomically claim the next queued task. Returns None if no tasks available."""
        with _claim_lock:
            conn = get_connection()
            try:
                task = conn.execute(
                    """
                    SELECT * FROM queue
                    WHERE status = 'queued' AND claimed_by IS NULL
                    ORDER BY position ASC
                    LIMIT 1
                    """
                ).fetchone()
                if task is None:
                    return None

                cursor = conn.execute(
                    """
                    UPDATE queue SET claimed_by = ?, claimed_at = CURRENT_TIMESTAMP, status = 'downloading'
                    WHERE id = ? AND claimed_by IS NULL
                    """,
                    (worker_id, task["id"]),
                )
                if cursor.rowcount == 0:
                    return None

                conn.execute(
                    "UPDATE downloads SET status = 'downloading', started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status IN ('queued', 'paused')",
                    (task["download_id"],),
                )
                conn.commit()
                return row_to_dict(task)
            finally:
                conn.close()

    # ---- Download Control ----

    def pause_download(self, download_id: int) -> dict:
        """Pause an active download.

        Sets the pause flag BEFORE terminating the process so the worker loop
        reliably marks the task as paused (not failed) when the process exits.
        """
        with self._process_lock:
            # Set pause flag first so the worker loop can distinguish pause from failure
            self._pause_flags[download_id] = True
            self._cancel_flags.pop(download_id, None)

            conn = get_connection()
            conn.execute(
                "UPDATE downloads SET status = 'paused', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status IN ('downloading', 'queued')",
                (download_id,),
            )
            conn.execute(
                "UPDATE queue SET claimed_by = NULL, status = 'paused' WHERE download_id = ?",
                (download_id,),
            )
            conn.commit()
            conn.close()

            proc = None
            if download_id in self._download_processes:
                proc = self._download_processes[download_id]
                del self._download_processes[download_id]

        if proc:
            terminate_process_tree(proc)

        return {"success": True}

    def resume_download(self, download_id: int) -> dict:
        """Resume a paused download."""
        with self._process_lock:
            conn = get_connection()
            conn.execute(
                "UPDATE downloads SET status = 'queued', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'paused'",
                (download_id,),
            )
            conn.execute(
                "UPDATE queue SET claimed_by = NULL, status = 'queued' WHERE download_id = ?",
                (download_id,),
            )
            conn.commit()
            conn.close()

            self._pause_flags.pop(download_id, None)
            self._cancel_flags.pop(download_id, None)
            return {"success": True}

    def cancel_download(self, download_id: int) -> dict:
        """Cancel an active or queued download."""
        with self._process_lock:
            # Set cancel flag first so the worker loop can distinguish cancellation
            self._cancel_flags[download_id] = True
            self._pause_flags.pop(download_id, None)

            conn = get_connection()
            conn.execute(
                "UPDATE downloads SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status IN ('downloading', 'queued', 'paused')",
                (download_id,),
            )
            conn.execute(
                "UPDATE queue SET status = 'cancelled', claimed_by = NULL WHERE download_id = ?",
                (download_id,),
            )
            conn.commit()
            conn.close()

            proc = None
            if download_id in self._download_processes:
                proc = self._download_processes[download_id]
                del self._download_processes[download_id]

        if proc:
            terminate_process_tree(proc)

        try:
            cleanup_task_temp_dir(download_id)
        except Exception:
            pass

        return {"success": True}

    def retry_download(self, download_id: int) -> dict:
        """Retry a failed download."""
        with self._process_lock:
            conn = get_connection()
            current = conn.execute("SELECT retry_count, max_retries FROM downloads WHERE id = ?", (download_id,)).fetchone()
            if not current:
                conn.close()
                return {"success": False, "error": "Download not found"}
            if current["retry_count"] >= current["max_retries"]:
                conn.close()
                return {"success": False, "error": "Max retries exceeded"}

            cursor = conn.execute(
                "UPDATE downloads SET status = 'queued', retry_count = retry_count + 1, error_message = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'failed'",
                (download_id,),
            )
            conn.execute(
                "UPDATE queue SET status = 'queued', claimed_by = NULL WHERE download_id = ?",
                (download_id,),
            )
            conn.commit()
            conn.close()
            return {"success": True}

    def remove_download(self, download_id: int) -> dict:
        """Remove a download (queued, completed, failed, or cancelled)."""
        with self._process_lock:
            conn = get_connection()
            row = conn.execute("SELECT status FROM downloads WHERE id = ?", (download_id,)).fetchone()
            if not row:
                conn.close()
                return {"success": False, "error": "Download not found"}

            status = row["status"]
            if status not in ("queued", "completed", "failed", "cancelled"):
                conn.close()
                return {"success": False, "error": f"Cannot remove active download with status '{status}'"}

            conn.execute("DELETE FROM queue WHERE download_id = ?", (download_id,))
            cursor = conn.execute(
                "DELETE FROM downloads WHERE id = ? AND status IN ('queued', 'completed', 'failed', 'cancelled')",
                (download_id,),
            )
            conn.commit()
            count = cursor.rowcount
            conn.close()
            if count > 0:
                try:
                    cleanup_task_temp_dir(download_id)
                except Exception:
                    pass
            return {"success": count > 0}

    def get_download_by_id(self, download_id: int) -> Optional[dict]:
        """Get a single download by ID."""
        conn = get_connection()
        row = conn.execute("SELECT * FROM downloads WHERE id = ?", (download_id,)).fetchone()
        conn.close()
        return row_to_dict(row) if row else None

    # ---- Statistics ----

    def get_statistics(self) -> dict:
        """Get download statistics."""
        conn = get_connection()
        total = conn.execute("SELECT COUNT(*) as count FROM downloads").fetchone()["count"]
        completed = conn.execute("SELECT COUNT(*) as count FROM downloads WHERE status = 'completed'").fetchone()["count"]
        failed = conn.execute("SELECT COUNT(*) as count FROM downloads WHERE status = 'failed'").fetchone()["count"]
        cancelled = conn.execute("SELECT COUNT(*) as count FROM downloads WHERE status = 'cancelled'").fetchone()["count"]
        active = conn.execute("SELECT COUNT(*) as count FROM downloads WHERE status = 'downloading'").fetchone()["count"]
        queued = conn.execute("SELECT COUNT(*) as count FROM downloads WHERE status = 'queued'").fetchone()["count"]

        total_size = conn.execute("SELECT COALESCE(SUM(total_size), 0) as size FROM downloads").fetchone()["size"]
        downloaded_size = conn.execute("SELECT COALESCE(SUM(downloaded_size), 0) as size FROM downloads").fetchone()["size"]
        storage_used = conn.execute("SELECT COALESCE(SUM(size), 0) as size FROM files").fetchone()["size"]

        success_rate = (completed / total * 100) if total > 0 else 0
        conn.close()

        return {
            "total": total, "completed": completed, "failed": failed,
            "cancelled": cancelled, "active": active, "queued": queued,
            "total_size": total_size, "downloaded_size": downloaded_size,
            "storage_used": storage_used, "success_rate": round(success_rate, 1),
        }

    def get_history(self, limit: int = 50, offset: int = 0, status_filter: str | None = None) -> List[dict]:
        """Get download history."""
        conn = get_connection()
        query = "SELECT * FROM downloads WHERE 1=1"
        params = []
        if status_filter:
            query += " AND status = ?"
            params.append(status_filter)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return rows_to_dict(rows)

    def get_files(self) -> List[dict]:
        """Get all recorded files."""
        conn = get_connection()
        rows = conn.execute("SELECT * FROM files ORDER BY created_at DESC").fetchall()
        conn.close()
        return rows_to_dict(rows)

    # ---- Worker Pool ----

    def start_worker_pool(self):
        """Start the background worker pool."""
        if self._worker_pool_started:
            return
        self._worker_pool_started = True
        self._max_workers = self._load_max_workers()
        self._worker_pool_thread = threading.Thread(
            target=self._worker_loop,
            args=(self._max_workers,),
            daemon=True,
        )
        self._worker_pool_thread.start()

    def _worker_loop(self, max_workers: int):
        """Main worker loop: claim and execute downloads."""
        active_workers: Dict[int, subprocess.Popen] = {}

        while True:
            # Dynamically reload concurrency settings
            try:
                max_workers = self._load_max_workers()
            except Exception:
                pass

            # Clean up finished workers
            finished_ids = []
            for dl_id, proc in active_workers.items():
                if proc.poll() is not None:
                    finished_ids.append(dl_id)

            for dl_id in finished_ids:
                proc = active_workers.pop(dl_id)
                if proc.returncode == 0 and not self._cancel_flags.get(dl_id):
                    self._mark_completed(dl_id)
                elif not self._cancel_flags.get(dl_id):
                    if self._pause_flags.get(dl_id):
                        self._pause_flags.pop(dl_id, None)
                        self._mark_paused(dl_id)
                    else:
                        err_detail = self._last_error.pop(dl_id, None)
                        msg = f"Failed (exit {proc.returncode}): {err_detail}" if err_detail else f"Process exited with code {proc.returncode}"
                        self._mark_failed(dl_id, msg)
                else:
                    self._cancel_flags.pop(dl_id, None)
                    try:
                        cleanup_task_temp_dir(dl_id)
                    except Exception:
                        pass
                self._download_processes.pop(dl_id, None)
                self._pause_flags.pop(dl_id, None)
                self._cancel_flags.pop(dl_id, None)
                self._download_filepath.pop(dl_id, None)
                self._last_error.pop(dl_id, None)

            # Start new workers if capacity available
            while len(active_workers) < max_workers:
                task = self.claim_next_task(self._worker_id)
                if task is None:
                    break
                download_id = task["download_id"]
                if self._cancel_flags.get(download_id):
                    continue
                try:
                    proc = self._execute_download(download_id)
                    if proc:
                        active_workers[download_id] = proc
                        with self._process_lock:
                            self._download_processes[download_id] = proc
                except Exception as e:
                    self._mark_failed(download_id, str(e))

            time.sleep(0.5)

    def _execute_download(self, download_id: int) -> Optional[subprocess.Popen]:
        """Execute a single download using yt-dlp as subprocess."""
        conn = get_connection()
        download = conn.execute("SELECT * FROM downloads WHERE id = ?", (download_id,)).fetchone()
        conn.close()
        if not download:
            return None

        url = download["url"]
        title = download["title"]
        save_location = download["save_location"]
        format_str = download["format"] or "bestvideo+bestaudio"
        subtitle_langs = download["subtitle_languages"]
        quality = download["quality"] or "best"

        task_dir = TEMP_DIR / f"dl_{download_id}"
        task_dir.mkdir(parents=True, exist_ok=True)

        safe_title = sanitize_filename(title)
        outtmpl = str(task_dir / f"{safe_title}.%(ext)s")

        extract_audio = quality == "audio" or ("audio" in format_str.lower() and "video" not in format_str.lower())

        conn = get_connection()
        bw_row = conn.execute("SELECT value FROM settings WHERE key = 'bandwidth_limit'").fetchone()
        embed_subs_row = conn.execute("SELECT value FROM settings WHERE key = 'auto_embed_subtitles'").fetchone()
        conn.close()
        limit_rate = bw_row["value"] if bw_row and bw_row["value"] not in ("0", "", None) else None
        auto_embed_subtitles = embed_subs_row["value"].lower() == "true" if embed_subs_row else True

        # Handle subtitle languages: default to selective English patterns for video downloads if not specified
        if subtitle_langs:
            subtitle_list = subtitle_langs.split(",") if isinstance(subtitle_langs, str) else subtitle_langs
        else:
            # Only default to English subtitles for video downloads
            # Match manual English (en) and auto-generated English (en-en)
            # Explicitly NOT matching auto-translations like en-de, en-fr
            subtitle_list = list(ENGLISH_SUBTITLE_PATTERNS) if not extract_audio else None

        # The main video download runs WITHOUT subtitle flags. Subtitle retrieval is
        # a separate best-effort operation after the video is complete, so subtitle
        # HTTP failures (e.g., 429) cannot fail the video download.
        proc = spawn_download_process(
            url=url,
            output_path=outtmpl,
            quality=quality,
            subtitles=None,
            format=format_str,
            extract_audio=extract_audio,
            limit_rate=limit_rate,
            embed_subtitles=False,
            skip_subtitles=True,
        )

        # Start a thread to read progress from stderr
        progress_thread = threading.Thread(
            target=self._read_progress,
            args=(proc, download_id),
            daemon=True,
        )
        progress_thread.start()

        return proc

    def _read_progress(self, proc: subprocess.Popen, download_id: int):
        """Read stdout from yt-dlp and parse progress.

        yt-dlp's combined stdout/stderr (stderr merged into stdout via STDOUT)
        carries all progress output and final metadata.
        """
        last_lines = []
        try:
            for line in iter(proc.stdout.readline, ''):
                if self._cancel_flags.get(download_id):
                    break
                s = line.strip()
                if s:
                    last_lines.append(s)
                    if len(last_lines) > 10:
                        last_lines.pop(0)
                progress = parse_progress_line(line)
                if progress and progress.get("status") == "downloading":
                    self._update_progress_db(download_id, progress)
                # Capture output filepath on finished event
                elif progress and progress.get("status") == "finished":
                    self._download_filepath[download_id] = progress.get("filepath")
        except Exception:
            pass
        if last_lines:
            self._last_error[download_id] = " | ".join(last_lines[-3:])
        try:
            proc.stdout.close()
        except Exception:
            pass

    def _download_subtitles(self, download_id: int, url: str, task_dir: Path, subtitle_list: List[str]) -> Optional[Path]:
        """Download subtitles as a best-effort operation after video completion.

        Returns Path to the downloaded .vtt file on success, None on failure.
        Subtitle failures do not affect video completion status.
        """
        if not subtitle_list:
            return None

        try:
            # Record existing .vtt files before subtitle download
            existing_vtt_files = set(task_dir.glob("*.vtt"))

            # Create output template for subtitle files
            subtitle_outtmpl = str(task_dir / f"%(title)s.%(language)s.%(ext)s")

            # Build clean argument list for subtitle-only download
            subtitle_args = list(YT_DLP_CMD) + [  # python -m yt_dlp (AppLocker-safe)
                "--skip-download",
                "--write-subs",
                "--write-auto-subs",
                "--sub-format", "vtt",
                "--sub-langs", ",".join(subtitle_list),
                "-o", subtitle_outtmpl,
                url
            ]

            # Add FFmpeg location if configured
            if FFMPEG_BIN:
                subtitle_args.extend(["--ffmpeg-location", FFMPEG_BIN])

            # Add standard yt-dlp flags
            subtitle_args.extend([
                "--no-overwrites",
                "--continue",
                "--newline",
                "--no-warnings"
            ])

            try:
                subtitle_proc = subprocess.Popen(
                    subtitle_args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=0,
                    cwd=str(task_dir),
                    creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
                    encoding='utf-8',
                    errors='replace',
                )

                try:
                    subtitle_proc.wait(timeout=120)  # 2 minute timeout for subtitles
                except subprocess.TimeoutExpired:
                    terminate_process_tree(subtitle_proc)
                    self._last_error[download_id] = "Subtitle download timed out"
                    return None

                if subtitle_proc.returncode != 0:
                    output = ""
                    try:
                        output = subtitle_proc.stdout.read() if subtitle_proc.stdout else ""
                    except:
                        pass
                    self._last_error[download_id] = f"Subtitle download failed: {output[:200] if output else 'Unknown error'}"
                    return None

                # Find newly created subtitle files
                current_vtt_files = set(task_dir.glob("*.vtt"))
                new_vtt_files = current_vtt_files - existing_vtt_files

                if new_vtt_files:
                    # Return the first new subtitle file found
                    # Sort by modification time to get the most recent
                    sorted_files = sorted(new_vtt_files, key=lambda f: f.stat().st_mtime, reverse=True)
                    return sorted_files[0]
                else:
                    self._last_error[download_id] = "No new subtitle file found after download"
                    return None

            except Exception as e:
                self._last_error[download_id] = f"Subtitle exception: {str(e)[:200]}"
                return None
        except Exception:
            return None

    def _update_progress_db(self, download_id: int, progress: Dict):
        """Update progress in the database."""
        try:
            downloaded = progress.get("downloaded_bytes", 0) or 0
            total = progress.get("total_bytes") or progress.get("total_bytes_estimate") or 0
            speed = progress.get("speed") or 0
            eta = progress.get("eta") or 0
            pct = (downloaded / total * 100) if total > 0 else 0

            conn = get_connection()
            conn.execute(
                """UPDATE downloads SET progress = ?, downloaded_size = ?, speed = ?, eta_seconds = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
                (round(pct, 1), downloaded, speed, eta, download_id),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _mark_completed(self, download_id: int):
        """Mark download as completed and handle post-download tasks.

        Design: status='completed' is written LAST, after all post-processing
        (file moves, subtitle download, FFmpeg embed) is complete.  This
        eliminates the race where poll() returns 'completed' while subtitle
        processing is still running and a concurrent settings change could
        affect which embed value is read.

        auto_embed_subtitles is captured once at the start of this method and
        is NOT re-read from the settings table during subtitle processing.
        """
        # -----------------------------------------------------------------
        # Step 1 — Snapshot global settings that must remain stable for the
        # lifetime of this post-processing call.  We read them NOW, before
        # any file or status mutation, so a concurrent settings change
        # cannot influence this download's behaviour.
        # -----------------------------------------------------------------
        conn = get_connection()
        embed_subs_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'auto_embed_subtitles'"
        ).fetchone()
        conn.close()
        auto_embed_subtitles: bool = (
            embed_subs_row["value"].lower() == "true" if embed_subs_row else True
        )

        # -----------------------------------------------------------------
        # Step 2 — Load download record.
        # -----------------------------------------------------------------
        download = self.get_download_by_id(download_id)
        if not download:
            # Nothing to do; mark completed so the queue entry is cleaned up.
            conn = get_connection()
            conn.execute(
                "UPDATE downloads SET status = 'completed', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (download_id,),
            )
            conn.execute("UPDATE queue SET status = 'completed' WHERE download_id = ?", (download_id,))
            conn.commit()
            conn.close()
            return

        task_dir = TEMP_DIR / f"dl_{download_id}"
        final_save_dir = Path(download["save_location"])
        final_save_dir.mkdir(parents=True, exist_ok=True)

        # -----------------------------------------------------------------
        # Step 3 — Determine which files to move.
        # Subtitle/caption file extensions are EXCLUDED from the primary
        # media scan so that stale .vtt files in the temp dir (e.g. from a
        # previous subtitle attempt, or a test fixture) are never registered
        # as the primary download output.  Subtitle files are handled
        # exclusively by the subtitle-specific logic below.
        # -----------------------------------------------------------------
        _SUBTITLE_EXTS = {
            ".vtt", ".srt", ".ass", ".ssa", ".sub", ".sbv", ".lrc", ".ttml",
        }
        _NON_MEDIA_EXTS = {
            ".jpg", ".jpeg", ".webp", ".png", ".gif",
            ".nfo", ".txt", ".json", ".xml",
        } | _SUBTITLE_EXTS

        captured_path = self._download_filepath.pop(download_id, None)
        if captured_path and Path(captured_path).exists():
            media_files = [Path(captured_path)]
        elif task_dir.exists():
            media_files = [
                f for f in task_dir.iterdir()
                if f.is_file() and f.suffix.lower() not in _NON_MEDIA_EXTS
            ]
        else:
            media_files = []

        video_extensions = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
        final_video_file: Optional[Path] = None

        # -----------------------------------------------------------------
        # Step 4 — Move media files to the final save directory and record
        # them in the files / downloads tables.
        # -----------------------------------------------------------------
        conn = get_connection()
        for f in media_files:
            file_hash = compute_file_hash(str(f))
            file_size = f.stat().st_size
            media_type = get_file_type(str(f))

            dest_path = final_save_dir / f.name
            if dest_path.exists() and dest_path != f:
                dest_path = final_save_dir / f"{f.stem}_{int(time.time())}{f.suffix}"
            try:
                shutil.move(str(f), str(dest_path))
                file_record_path = str(dest_path)
                moved_to = dest_path
            except Exception:
                file_record_path = str(f)
                moved_to = f

            # Track the first video file for subtitle embedding
            if final_video_file is None and moved_to.suffix.lower() in video_extensions and moved_to.exists():
                final_video_file = moved_to

            conn.execute(
                """INSERT OR REPLACE INTO files (download_id, path, filename, size, media_type, file_hash)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (download_id, file_record_path, f.name, file_size, media_type, file_hash),
            )
            conn.execute(
                "UPDATE downloads SET output_path = ?, total_size = ?, downloaded_size = ?, progress = 100, file_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (file_record_path, file_size, file_size, file_hash, download_id),
            )

            if download["is_duplicate"] and file_hash:
                existing = conn.execute(
                    "SELECT id FROM files WHERE file_hash = ? AND download_id != ?",
                    (file_hash, download_id),
                ).fetchone()
                if existing:
                    conn.execute(
                        "INSERT INTO security_events (event_type, severity, description) VALUES ('duplicate_detected', 'info', ?)",
                        (f"Duplicate file detected: {f.name}",),
                    )
            conn.commit()
        conn.close()

        # -----------------------------------------------------------------
        # Step 5 — Subtitle handling (best-effort; never fails the video).
        # Uses auto_embed_subtitles captured at the very start of this call.
        # -----------------------------------------------------------------
        extract_audio = (
            download["quality"] == "audio"
            or (
                "audio" in (download["format"] or "").lower()
                and "video" not in (download["format"] or "").lower()
            )
        )

        if not extract_audio and task_dir.exists():
            subtitle_langs = download["subtitle_languages"]
            subtitle_list = None

            if subtitle_langs and isinstance(subtitle_langs, str) and subtitle_langs.strip():
                subtitle_list = [lang.strip() for lang in subtitle_langs.split(",") if lang.strip()]
            elif subtitle_langs is None:
                subtitle_list = list(ENGLISH_SUBTITLE_PATTERNS)
            # Empty string → treat as "subtitles disabled" (subtitle_list stays None)

            if subtitle_list:
                subtitle_path = self._download_subtitles(
                    download_id, download["url"], task_dir, subtitle_list
                )

                if subtitle_path and subtitle_path.exists():
                    subtitle_language = self._derive_subtitle_language(subtitle_path, subtitle_list)

                    # Use the auto_embed_subtitles value captured at the start —
                    # never re-read from the settings table here.
                    if auto_embed_subtitles:
                        # Record subtitle (embedded=0 until FFmpeg succeeds)
                        conn = get_connection()
                        conn.execute(
                            """INSERT OR REPLACE INTO subtitles
                            (download_id, language, format, path, embedded, created_at)
                            VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)""",
                            (download_id, subtitle_language, "vtt", str(subtitle_path)),
                        )
                        conn.commit()
                        conn.close()

                        if final_video_file and final_video_file.exists():
                            self._embed_subtitle(
                                download_id, final_video_file, subtitle_path, final_save_dir, subtitle_language
                            )
                        else:
                            self._last_error[download_id] = (
                                "No video file found for subtitle embedding"
                            )
                    else:
                        # Standalone subtitle: move file from task_dir to final_save_dir
                        dest_sub = final_save_dir / subtitle_path.name
                        if dest_sub.exists() and dest_sub != subtitle_path:
                            dest_sub = final_save_dir / f"{subtitle_path.stem}_{int(time.time())}{subtitle_path.suffix}"
                        try:
                            shutil.move(str(subtitle_path), str(dest_sub))
                            final_sub_record = str(dest_sub)
                        except Exception:
                            final_sub_record = str(subtitle_path)

                        conn = get_connection()
                        conn.execute(
                            """INSERT OR REPLACE INTO subtitles
                            (download_id, language, format, path, embedded, created_at)
                            VALUES (?, ?, ?, ?, 0, CURRENT_TIMESTAMP)""",
                            (download_id, subtitle_language, "vtt", final_sub_record),
                        )
                        conn.commit()
                        conn.close()
                elif subtitle_path is None:
                    error_msg = self._last_error.get(download_id, "Unknown subtitle error")
                    self._last_error[download_id] = f"Subtitle download warning: {error_msg}"

        # -----------------------------------------------------------------
        # Step 6 — All post-processing complete.  NOW expose status='completed'
        # so that API poll() calls only see the terminal state after every
        # file move, subtitle download, and embed operation is finished.
        # -----------------------------------------------------------------
        conn = get_connection()
        conn.execute(
            "UPDATE downloads SET status = 'completed', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (download_id,),
        )
        conn.execute("UPDATE queue SET status = 'completed' WHERE download_id = ?", (download_id,))
        conn.commit()
        conn.close()

        # -----------------------------------------------------------------
        # Step 7 — Temp directory cleanup.
        # Standalone subtitles and media files have already been moved to final_save_dir.
        # Embedded subtitles are contained inside the video container.
        # Protect any file path still referenced by files or non-embedded subtitles.
        # -----------------------------------------------------------------
        try:
            conn = get_connection()
            ref_files = conn.execute(
                "SELECT path FROM files WHERE download_id = ?", (download_id,)
            ).fetchall()
            ref_subs = conn.execute(
                "SELECT path FROM subtitles WHERE download_id = ? AND (embedded = 0 OR embedded IS NULL)",
                (download_id,),
            ).fetchall()
            conn.close()
            protected = {r["path"] for r in ref_files if r["path"]} | {r["path"] for r in ref_subs if r["path"]}
            cleanup_task_temp_dir(download_id, protected_paths=protected)
        except Exception:
            pass

    def _derive_subtitle_language(self, subtitle_path: Path, subtitle_list: List[str]) -> str:
        """Derive the subtitle language from the filename or fall back to the first requested language."""
        filename = subtitle_path.name
        # Filename patterns: Title.en.vtt, Title.en-US.vtt, Title.en-en.vtt, etc.
        # Try to extract language code from between the title and extension
        stem = subtitle_path.stem  # e.g. "MyVideo.en"
        parts = stem.rsplit(".", 1)
        if len(parts) == 2:
            lang_candidate = parts[1].lower()
            # Validate it looks like a language code
            if len(lang_candidate) >= 2 and lang_candidate.replace("-", "").replace("_", "").isalpha():
                return lang_candidate
        # Fall back to first requested language that is not a regional variant
        for lang in subtitle_list:
            if lang == lang.lower() and "-" not in lang and "_" not in lang:
                return lang
        return subtitle_list[0] if subtitle_list else "en"

    def _get_completed_video_file(self, download_id: int, final_save_dir: Path) -> Optional[Path]:
        """Get the exact completed video file for this download."""
        # Prefer the path captured during progress reading
        captured_path = self._download_filepath.pop(download_id, None)
        if captured_path and Path(captured_path).exists():
            return Path(captured_path)

        # Fall back: find the most recently added video file in final_save_dir
        video_extensions = {".mp4", ".mkv", ".webm", ".avi", ".mov"}
        video_files = [
            f for f in final_save_dir.iterdir()
            if f.is_file() and f.suffix.lower() in video_extensions
        ]
        if video_files:
            # Sort by modification time descending to get the newest first
            video_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            return video_files[0]
        return None

    def _embed_subtitle(self, download_id: int, video_file: Path, subtitle_path: Path, final_save_dir: Path, language: str = "en"):
        """Embed a subtitle into a video using FFmpeg.

        Uses container-appropriate subtitle codec.
        Writes to temp output, replaces original only on success.
        """
        temp_output = final_save_dir / f"{video_file.stem}_temp{video_file.suffix}"
        container = video_file.suffix.lower()

        # Select subtitle codec based on container
        if container in (".mp4", ".mov"):
            subtitle_codec = "mov_text"
        elif container == ".mkv":
            subtitle_codec = "srt"
        elif container == ".webm":
            # WebM/Matroska supports srt and webvtt, but FFmpeg's webvtt handling can be finicky
            # Use srt which is universally supported in Matroska containers
            subtitle_codec = "srt"
        else:
            # Unknown container - skip embedding
            self._last_error[download_id] = f"Unsupported container {container} for subtitle embedding"
            return

        try:
            lang_tag = normalize_subtitle_language_tag(language)
            ffmpeg_args = [
                FFMPEG_BIN,
                "-y",
                "-i", str(video_file),
                "-i", str(subtitle_path),
                "-c:v", "copy",
                "-c:a", "copy",
                "-c:s", subtitle_codec,
                "-map", "0",
                "-map", "1",
                "-metadata:s:s:0", f"language={lang_tag}",
                str(temp_output)
            ]

            ffmpeg_proc = subprocess.Popen(
                ffmpeg_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=str(final_save_dir)
            )

            try:
                stdout, stderr = ffmpeg_proc.communicate(timeout=60)
                if ffmpeg_proc.returncode == 0 and temp_output.exists():
                    # FFmpeg succeeded - replace original video
                    shutil.move(str(temp_output), str(video_file))
                    new_size = video_file.stat().st_size if video_file.exists() else None
                    new_hash = compute_file_hash(str(video_file)) if video_file.exists() else None

                    # Update subtitle record to show it's embedded and refresh file size & hash
                    conn = get_connection()
                    conn.execute(
                        "UPDATE subtitles SET embedded = 1 WHERE download_id = ? AND path = ?",
                        (download_id, str(subtitle_path))
                    )
                    if new_size is not None and new_hash:
                        conn.execute(
                            "UPDATE files SET size = ?, file_hash = ? WHERE download_id = ? AND path = ?",
                            (new_size, new_hash, download_id, str(video_file))
                        )
                        conn.execute(
                            "UPDATE downloads SET total_size = ?, downloaded_size = ?, file_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (new_size, new_size, new_hash, download_id)
                        )
                    conn.commit()
                    conn.close()
                else:
                    # FFmpeg failed - keep original video, log warning
                    if temp_output.exists():
                        temp_output.unlink()
                    error_msg = stderr[:200] if stderr else "Unknown FFmpeg error"
                    self._last_error[download_id] = f"Subtitle embedding failed: {error_msg}"
            except subprocess.TimeoutExpired:
                ffmpeg_proc.kill()
                if temp_output.exists():
                    temp_output.unlink()
                self._last_error[download_id] = "Subtitle embedding timed out"
            except Exception as e:
                if temp_output.exists():
                    temp_output.unlink()
                self._last_error[download_id] = f"Subtitle embedding exception: {str(e)[:200]}"
        except Exception as e:
            if temp_output.exists():
                temp_output.unlink()
            self._last_error[download_id] = f"Subtitle embedding setup failed: {str(e)[:200]}"

    def _mark_failed(self, download_id: int, error: str):
        """Mark download as failed."""
        conn = get_connection()
        conn.execute(
            "UPDATE downloads SET status = 'failed', error_message = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status != 'cancelled'",
            (error[:500], download_id),
        )
        conn.execute("UPDATE queue SET status = 'failed' WHERE download_id = ?", (download_id,))
        conn.commit()
        conn.close()

        try:
            cleanup_task_temp_dir(download_id)
        except Exception:
            pass

    def _mark_paused(self, download_id: int):
        """Mark download as paused."""
        conn = get_connection()
        conn.execute(
            "UPDATE downloads SET status = 'paused', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (download_id,),
        )
        conn.execute("UPDATE queue SET status = 'paused', claimed_by = NULL WHERE download_id = ?", (download_id,))
        conn.commit()
        conn.close()

    def _update_download_metadata(self, download_id: int, analysis: dict):
        """Update download record with analysis data."""
        conn = get_connection()
        conn.execute(
            """UPDATE downloads SET title = ?, thumbnail = ?, duration = ?, uploader = ?,
            metadata_json = ? WHERE id = ?""",
            (
                analysis.get("title"),
                analysis.get("thumbnail"),
                analysis.get("duration"),
                analysis.get("uploader"),
                json.dumps({k: v for k, v in analysis.items() if k not in ("formats",)}),
                download_id,
            ),
        )
        conn.commit()
        conn.close()

    # ---- Recovery ----

    def recover_interrupted(self):
        """Recover downloads that were interrupted (status=downloading but no active process) and clean orphaned temp task dirs."""
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM downloads WHERE status = 'downloading'"
        ).fetchall()
        for row in rows:
            conn.execute(
                "UPDATE downloads SET status = 'queued', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'downloading'",
                (row["id"],),
            )
            conn.execute(
                "UPDATE queue SET claimed_by = NULL, status = 'queued' WHERE download_id = ?",
                (row["id"],),
            )
        conn.commit()

        # Startup recovery: clean orphaned temp/dl_* dirs belonging to terminal downloads; do not touch active task dirs.
        try:
            for dl_id, task_path in list_task_temp_dirs():
                dl_row = conn.execute(
                    "SELECT status FROM downloads WHERE id = ?", (dl_id,)
                ).fetchone()
                # Active states: downloading, queued, paused -> NEVER touch
                if dl_row and dl_row["status"] in ("downloading", "queued", "paused"):
                    continue
                # Terminal states (completed, failed, cancelled) or orphaned (no DB record)
                ref_files = conn.execute("SELECT path FROM files WHERE download_id = ?", (dl_id,)).fetchall() if dl_row else []
                ref_subs = conn.execute(
                    "SELECT path FROM subtitles WHERE download_id = ? AND (embedded = 0 OR embedded IS NULL)", (dl_id,)
                ).fetchall() if dl_row else []
                protected = {r["path"] for r in ref_files if r["path"]} | {r["path"] for r in ref_subs if r["path"]}
                cleanup_task_temp_dir(dl_id, protected_paths=protected)
        except Exception:
            pass
        finally:
            conn.close()


# Global download service instance
download_service = DownloadService()