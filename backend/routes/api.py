"""REST API routes for UniversalDownloader."""
from flask import request, jsonify, Blueprint
from database.db import get_db, save_settings, get_all_settings
from services.download_service import download_service
from utils.files import get_download_size, compute_file_hash, safe_delete, safe_move
from utils.template import validate_filename_template
import os
from pathlib import Path

api_bp = Blueprint("api", __name__)


def safe_int(value, default: int, min_val: int = 1, max_val: int = 1000) -> int:
    """Safely parse an integer query parameter with fallback and bounds checking."""
    try:
        val = int(value)
        return max(min_val, min(val, max_val))
    except (TypeError, ValueError):
        return default


# ---- URL Analysis ----

@api_bp.route("/analyze", methods=["POST"])
def analyze_url():
    """Analyze a URL and return media metadata."""
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    if not url:
        return jsonify({"error": "URL is required"}), 400

    result = download_service.analyze_url(url)
    if not result.get("valid"):
        return jsonify({"error": result.get("error", "Analysis failed")}), 400

    return jsonify(result)


# ---- Download Creation ----

@api_bp.route("/download", methods=["POST"])
def create_download():
    """Create a new download from a URL."""
    data = request.get_json(silent=True) or {}
    url = data.get("url")
    if not url:
        return jsonify({"error": "URL is required"}), 400

    quality = data.get("quality", "best")
    format_ = data.get("format", "bestvideo+bestaudio")
    subtitle_langs_raw = data.get("subtitle_languages")
    # Preserve three-way distinction:
    # None/missing -> None (default subtitle behavior)
    # "" or [] -> "" (explicitly disabled)
    # non-empty -> list of requested language codes
    if subtitle_langs_raw is None:
        subtitle_languages = None
    elif isinstance(subtitle_langs_raw, str):
        trimmed = subtitle_langs_raw.strip()
        subtitle_languages = "" if trimmed == "" else [s.strip() for s in trimmed.split(",") if s.strip()]
    elif isinstance(subtitle_langs_raw, list):
        filtered = [str(s).strip() for s in subtitle_langs_raw if str(s).strip()]
        subtitle_languages = filtered if filtered else ""
    else:
        subtitle_languages = None
    save_location = data.get("save_location")
    filename_template = data.get("filename_template")
    if filename_template is not None and str(filename_template).strip():
        filename_template = str(filename_template).strip()
        is_valid, err_reason = validate_filename_template(filename_template)
        if not is_valid:
            return jsonify({"error": f"Invalid filename template: {err_reason}"}), 400
    else:
        filename_template = None

    result = download_service.create_download(
        url=url,
        quality=quality,
        format_str=format_,
        subtitle_languages=subtitle_languages,
        save_location=save_location,
        filename_template=filename_template,
    )

    if not result.get("success"):
        return jsonify({"error": result.get("error", "Failed to create download")}), 400

    return jsonify(result)


# ---- Download Management ----

@api_bp.route("/downloads", methods=["GET"])
def get_downloads():
    """List all downloads with optional filtering."""
    status = request.args.get("status")
    media_type = request.args.get("media_type")
    page = safe_int(request.args.get("page"), default=1, min_val=1, max_val=100000)
    per_page = safe_int(request.args.get("per_page"), default=20, min_val=1, max_val=100)

    conn = get_db()
    query = "SELECT * FROM downloads WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)

    if media_type:
        query += " AND media_type = ?"
        params.append(media_type)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, (page - 1) * per_page])

    rows = conn.execute(query, params).fetchall()
    downloads = [dict(row) for row in rows]

    return jsonify({"downloads": downloads, "page": page, "per_page": per_page})


@api_bp.route("/download/<int:download_id>", methods=["GET"])
def get_download(download_id):
    """Get details for a specific download."""
    download = download_service.get_download_by_id(download_id)
    if not download:
        return jsonify({"error": "Download not found"}), 404

    return jsonify(download)


@api_bp.route("/download/<int:download_id>/pause", methods=["POST"])
def pause_download(download_id):
    """Pause an active download."""
    result = download_service.pause_download(download_id)
    if not result.get("success"):
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route("/download/<int:download_id>/resume", methods=["POST"])
def resume_download(download_id):
    """Resume a paused download."""
    result = download_service.resume_download(download_id)
    if not result.get("success"):
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route("/download/<int:download_id>/cancel", methods=["POST"])
def cancel_download(download_id):
    """Cancel an active or queued download."""
    result = download_service.cancel_download(download_id)
    if not result.get("success"):
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route("/download/<int:download_id>/retry", methods=["POST"])
def retry_download(download_id):
    """Retry a failed download."""
    result = download_service.retry_download(download_id)
    if not result.get("success"):
        return jsonify(result), 400
    return jsonify(result)


@api_bp.route("/download/<int:download_id>", methods=["DELETE"])
def remove_download(download_id):
    """Remove a download (queued, completed, failed, or cancelled)."""
    result = download_service.remove_download(download_id)
    if not result.get("success"):
        status_code = 404 if result.get("error") == "Download not found" else 400
        return jsonify(result), status_code
    return jsonify(result)


# ---- Queue Management ----

@api_bp.route("/queue", methods=["GET"])
def get_queue():
    """Get all queue items."""
    queue = download_service.get_queue()
    return jsonify({"queue": queue})


@api_bp.route("/queue/reorder", methods=["POST"])
def reorder_queue():
    """Reorder queue items."""
    data = request.get_json(silent=True) or {}
    items = data.get("items", [])

    if not items:
        return jsonify({"error": "No items provided"}), 400

    conn = get_db()
    try:
        for i, item in enumerate(items):
            queue_id = item.get("id")
            position = i + 1
            conn.execute(
                "UPDATE queue SET position = ? WHERE id = ?",
                (position, queue_id)
            )
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500


# ---- Statistics ----

@api_bp.route("/statistics", methods=["GET"])
def get_statistics():
    """Get download statistics."""
    stats = download_service.get_statistics()
    return jsonify(stats)


@api_bp.route("/history", methods=["GET"])
def get_history():
    """Get download history."""
    limit = safe_int(request.args.get("limit"), default=50, min_val=1, max_val=500)
    offset = safe_int(request.args.get("offset"), default=0, min_val=0, max_val=1000000)
    status_filter = request.args.get("status")

    history = download_service.get_history(limit=limit, offset=offset, status_filter=status_filter)
    return jsonify({"history": history, "limit": limit, "offset": offset})


# ---- Settings ----

@api_bp.route("/settings", methods=["GET"])
def get_settings():
    """Get application settings."""
    settings = get_all_settings()
    return jsonify(settings)


@api_bp.route("/settings", methods=["PUT"])
def update_settings():
    """Update application settings."""
    data = request.get_json(silent=True) or {}
    # Validate certain settings
    if "max_concurrency" in data:
        try:
            value = int(data["max_concurrency"])
            if value < 1 or value > 16:
                return jsonify({"error": "Max concurrency must be between 1 and 16"}), 400
            data["max_concurrency"] = str(value)
        except ValueError:
            return jsonify({"error": "Max concurrency must be an integer"}), 400

    if "bandwidth_limit" in data:
        try:
            value = int(data["bandwidth_limit"])
            if value < 0:
                return jsonify({"error": "Bandwidth limit must be >= 0"}), 400
            data["bandwidth_limit"] = str(value)
        except ValueError:
            return jsonify({"error": "Bandwidth limit must be an integer"}), 400

    if "filename_template" in data:
        template_val = str(data["filename_template"]).strip()
        is_valid, err_reason = validate_filename_template(template_val)
        if not is_valid:
            return jsonify({"error": f"Invalid filename template: {err_reason}"}), 400
        data["filename_template"] = template_val

    save_settings(data)
    return jsonify({"success": True})


# ---- Health Check ----

@api_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "service": "UniversalDownloader API"})


# ---- Security Events ----

@api_bp.route("/security/events", methods=["GET"])
def get_security_events():
    """Get security events."""
    limit = safe_int(request.args.get("limit"), default=50, min_val=1, max_val=500)
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM security_events ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return jsonify([dict(row) for row in rows])


# ---- Files ----

@api_bp.route("/files", methods=["GET"])
def list_files():
    """List downloaded files."""
    files = download_service.get_files()
    return jsonify({"files": files})


@api_bp.route("/files/<int:file_id>", methods=["DELETE"])
def delete_file(file_id):
    """Delete a downloaded file."""
    conn = get_db()
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        return jsonify({"error": "File not found"}), 404

    file_path = row["path"]
    if not file_path:
        return jsonify({"error": "File path not available"}), 400

    # Security check: ensure file is in allowed directory
    from config import DOWNLOADS_DIR, TEMP_DIR
    from utils.security import validate_save_path
    validation = validate_save_path(file_path, allowed_dirs=[DOWNLOADS_DIR, TEMP_DIR])
    if not validation["safe"]:
        return jsonify({"error": "Unsafe file path"}), 403

    # Delete file
    delete_result = safe_delete(file_path)
    if not delete_result["success"] and os.path.exists(file_path):
        return jsonify({"error": delete_result["reason"]}), 500

    # Delete record
    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
    conn.commit()

    return jsonify({"success": True, "message": "File deleted"})


@api_bp.route("/files/<int:file_id>/open", methods=["POST"])
def open_file(file_id):
    """Safely open a downloaded file using the default OS application."""
    conn = get_db()
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()

    if not row:
        return jsonify({"error": "File not found"}), 404

    file_path = row["path"]
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File does not exist on disk"}), 404

    from config import DOWNLOADS_DIR
    from utils.security import validate_save_path
    validation = validate_save_path(file_path, allowed_dirs=[DOWNLOADS_DIR])
    if not validation["safe"]:
        return jsonify({"error": "Access denied: file outside allowed downloads directory"}), 403

    try:
        norm_path = os.path.normpath(file_path)
        if os.name == "nt":
            os.startfile(norm_path)
        else:
            import subprocess
            subprocess.Popen(["xdg-open", norm_path])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Failed to open file: {e}"}), 500


@api_bp.route("/files/<int:file_id>/reveal", methods=["POST"])
def reveal_file(file_id):
    """Safely reveal a downloaded file in Windows Explorer."""
    conn = get_db()
    row = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,)).fetchone()

    if not row:
        return jsonify({"error": "File not found"}), 404

    file_path = row["path"]
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File does not exist on disk"}), 404

    from config import DOWNLOADS_DIR
    from utils.security import validate_save_path
    validation = validate_save_path(file_path, allowed_dirs=[DOWNLOADS_DIR])
    if not validation["safe"]:
        return jsonify({"error": "Access denied: file outside allowed downloads directory"}), 403

    try:
        import subprocess
        norm_path = os.path.normpath(file_path)
        if os.name == "nt":
            subprocess.Popen(["explorer", f"/select,{norm_path}"])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(norm_path)])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Failed to reveal file: {e}"}), 500


# ---- Subtitles ----

@api_bp.route("/subtitles", methods=["GET"])
def list_subtitles():
    """List all subtitles."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM subtitles ORDER BY created_at DESC").fetchall()
    return jsonify({"subtitles": [dict(row) for row in rows]})


@api_bp.route("/subtitles/<int:subtitle_id>", methods=["DELETE"])
def delete_subtitle(subtitle_id):
    """Delete a subtitle file."""
    conn = get_db()
    row = conn.execute("SELECT * FROM subtitles WHERE id = ?", (subtitle_id,)).fetchone()

    if not row:
        return jsonify({"error": "Subtitle not found"}), 404

    subtitle_path = row["path"]
    if subtitle_path:
        from config import DOWNLOADS_DIR, TEMP_DIR
        from utils.security import validate_save_path
        validation = validate_save_path(subtitle_path, allowed_dirs=[DOWNLOADS_DIR, TEMP_DIR])
        if validation["safe"]:
            try:
                if os.path.exists(subtitle_path):
                    os.remove(subtitle_path)
            except Exception:
                pass

    conn.execute("DELETE FROM subtitles WHERE id = ?", (subtitle_id,))
    conn.commit()

    return jsonify({"success": True})


# ---- Network Information ----

@api_bp.route("/network", methods=["GET"])
def get_network_info():
    """Get network interface information."""
    try:
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        return jsonify({
            "hostname": hostname,
            "local_ip": local_ip,
            "status": "connected"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---- Duplicate Detection ----

@api_bp.route("/duplicates", methods=["GET"])
def get_duplicates():
    """Get list of potential duplicate downloads."""
    from database.db import get_connection as _new_conn
    # Use get_connection() (always fresh) rather than get_db() (thread-local).
    # The old code called get_db() / conn.close() in a loop; after the first
    # close(), get_db() returned the already-closed connection -> 500.
    conn = _new_conn()
    try:
        rows = conn.execute(
            """SELECT f.file_hash, COUNT(*) as count, GROUP_CONCAT(f.download_id) as download_ids
               FROM files f
               WHERE f.file_hash IS NOT NULL AND f.file_hash != ''
               GROUP BY f.file_hash
               HAVING count > 1"""
        ).fetchall()

        duplicates = []
        for row in rows:
            file_hash = row["file_hash"]
            count = row["count"]
            download_ids = row["download_ids"].split(",")
            placeholders = ",".join(["?"] * len(download_ids))
            download_rows = conn.execute(
                f"SELECT id, title, url, status, created_at FROM downloads WHERE id IN ({placeholders})",
                download_ids,
            ).fetchall()
            duplicates.append({
                "file_hash": file_hash,
                "count": count,
                "downloads": [dict(dr) for dr in download_rows],
            })
    finally:
        conn.close()

    return jsonify({"duplicates": duplicates})


# ---- Analytics ----

@api_bp.route("/analytics", methods=["GET"])
def get_analytics():
    """Get analytics data for charts."""
    conn = get_db()

    # Downloads by day (last 30 days)
    daily = conn.execute(
        """SELECT DATE(created_at) as day, COUNT(*) as count,
                  SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                  SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
           FROM downloads
           WHERE created_at >= datetime('now', '-30 days')
           GROUP BY DATE(created_at)
           ORDER BY day ASC"""
    ).fetchall()

    # Total stats
    total_stats = conn.execute("SELECT COUNT(*) as total, COALESCE(SUM(total_size), 0) as total_size FROM downloads").fetchone()

    # Success rate per month
    monthly = conn.execute(
        """SELECT strftime('%Y-%m', created_at) as month,
                  COUNT(*) as total,
                  SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
           FROM downloads
           GROUP BY strftime('%Y-%m', created_at)
           ORDER BY month DESC LIMIT 12"""
    ).fetchall()

    return jsonify({
        "daily": [dict(r) for r in daily],
        "monthly": [dict(r) for r in monthly],
        "total_downloads": total_stats["total"],
        "total_size": total_stats["total_size"],
    })