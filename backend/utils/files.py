"""File system utilities for UniversalDownloader."""
import os
import re
import shutil
import hashlib
from pathlib import Path
from typing import Iterable, Optional

from config import DATA_DIR, DOWNLOADS_DIR, TEMP_DIR
from utils.security import sanitize_filename, validate_save_path


def get_download_size(file_path: str) -> int:
    """Get the size of a file in bytes."""
    return Path(file_path).stat().st_size


def ensure_directory(path: str) -> None:
    """Ensure a directory exists and create it if not."""
    Path(path).mkdir(parents=True, exist_ok=True)


def safe_delete(file_path: str) -> dict:
    """Safely delete a file.

    Returns a dict with 'success' bool and 'reason' string.
    """
    p = Path(file_path)
    if not p.exists():
        return {"success": True, "reason": "File does not exist (already deleted)"}

    try:
        # Verify the path is within permitted directories
        validation = validate_save_path(file_path, allowed_dirs=[DOWNLOADS_DIR, TEMP_DIR])
        if not validation["safe"]:
            return {
                "success": False,
                "reason": f"Unsafe path: {validation['reason']}",
            }

        p.unlink()
        return {"success": True, "reason": "File deleted successfully"}
    except Exception as e:
        return {"success": False, "reason": str(e)}


def safe_move(source: str, destination_dir: str) -> dict:
    """Safely move a file within permitted directories.

    Returns a dict with 'success' bool and 'reason' string.
    """
    dest_validation = validate_save_path(destination_dir, allowed_dirs=[DOWNLOADS_DIR])
    if not dest_validation["safe"]:
        return {"success": False, "reason": f"Unsafe destination: {dest_validation['reason']}"}

    source_path = Path(source)
    if not source_path.exists():
        return {"success": False, "reason": "Source file does not exist"}

    try:
        destination_path = Path(destination_dir) / source_path.name
        shutil.move(str(source_path), str(destination_path))
        return {"success": True, "reason": "File moved", "destination": str(destination_path)}
    except Exception as e:
        return {"success": False, "reason": str(e)}


def sanitize_file_path(base_dir: str, filename: str) -> str:
    """Create a safe file path within base_dir."""
    safe_name = sanitize_filename(filename)
    return str(Path(base_dir) / safe_name)


def compute_file_hash(file_path: str) -> str:
    """Compute MD5 hash of a file for duplicate detection.

    Note: MD5 is used for file integrity comparison, NOT for security purposes.
    """
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
    except Exception:
        return ""
    return hash_md5.hexdigest()


def get_file_type(file_path: str) -> str:
    """Get the media type of a file."""
    ext = Path(file_path).suffix.lower()
    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv"}
    audio_exts = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".opus"}
    if ext in video_exts:
        return "video"
    if ext in audio_exts:
        return "audio"
    return "other"


def cleanup_temp_files() -> int:
    """Clean up temporary files."""
    cleaned = 0
    temp_path = Path(TEMP_DIR)
    if temp_path.exists():
        for item in temp_path.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                    cleaned += 1
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                    cleaned += 1
            except Exception:
                pass
    return cleaned


def organize_file(file_path: str, organize_by: str = "type") -> dict:
    """Organize a downloaded file into subdirectories by type.

    Categories: Video, Audio, Playlist, Other.
    """
    from utils.files import get_file_type

    file_type = get_file_type(file_path)
    if file_type == "other":
        return {"success": False, "reason": "Not a media file"}

    base_dir = Path(file_path).parent
    category_dir = base_dir / file_type.capitalize()
    category_dir.mkdir(exist_ok=True)

    dest = category_dir / Path(file_path).name
    try:
        shutil.move(file_path, str(dest))
        return {
            "success": True,
            "reason": f"Moved to {category_dir.name}",
            "destination": str(dest),
            "category": file_type,
        }
    except Exception as e:
        return {"success": False, "reason": str(e)}


# ---------------------------------------------------------------------------
# Per-task temp directory lifecycle (temp/dl_<id>/)
#
# Safety model:
#   * Only directories named exactly ``dl_<integer>`` whose resolved parent is
#     TEMP_DIR are ever touched.  The id is coerced to int, so path fragments
#     such as "../x" or absolute paths cannot be smuggled in.
#   * Symlinks / junctions / other reparse points are never followed and never
#     deleted (they are reported as kept), so deletion cannot escape TEMP_DIR.
#   * Files listed in ``protected_paths`` (paths still referenced by the DB)
#     are preserved.  The directory is removed only if it ends up empty.
#   * Idempotent: a missing directory is reported as already clean.
# ---------------------------------------------------------------------------
TASK_DIR_PATTERN = re.compile(r"dl_(\d+)")


def _is_link_like(path: Path) -> bool:
    """True for symlinks and Windows reparse points (junctions, mount points)."""
    try:
        if os.path.islink(path):
            return True
        st = os.lstat(path)
        attrs = getattr(st, "st_file_attributes", 0)
        reparse_flag = 0x400  # stat.FILE_ATTRIBUTE_REPARSE_POINT
        return bool(attrs & reparse_flag)
    except OSError:
        return False


def _norm(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def resolve_task_temp_dir(download_id) -> Optional[Path]:
    """Return TEMP_DIR/dl_<id> for a valid integer id, or None if unsafe/invalid."""
    if isinstance(download_id, bool):
        return None
    try:
        dl_id = int(download_id)
    except (TypeError, ValueError):
        return None
    if dl_id < 0:
        return None

    temp_root = Path(TEMP_DIR).resolve()
    candidate = temp_root / f"dl_{dl_id}"
    if candidate.exists() and _is_link_like(candidate):
        return None
    resolved = candidate.resolve()
    if _norm(resolved.parent) != _norm(temp_root):
        return None
    if not TASK_DIR_PATTERN.fullmatch(resolved.name):
        return None
    return resolved


def list_task_temp_dirs() -> list:
    """List (download_id, Path) for real dl_<id> directories directly inside TEMP_DIR."""
    found = []
    temp_root = Path(TEMP_DIR)
    if not temp_root.exists():
        return found
    for entry in temp_root.iterdir():
        m = TASK_DIR_PATTERN.fullmatch(entry.name)
        if not m or _is_link_like(entry) or not entry.is_dir():
            continue
        found.append((int(m.group(1)), entry))
    return sorted(found, key=lambda t: t[0])


def _purge_dir_contents(dir_path: Path, root: Path, protected: set, result: dict) -> None:
    """Delete non-protected files under dir_path (never following links)."""
    try:
        entries = list(os.scandir(dir_path))
    except OSError as e:
        result["errors"].append(f"{dir_path}: {e}")
        return
    for entry in entries:
        p = Path(entry.path)
        try:
            # Defence in depth: never act on anything outside the task root.
            if not _norm(p).startswith(_norm(root) + os.sep):
                result["errors"].append(f"outside task dir: {p}")
                continue
            if _is_link_like(p):
                result["kept"].append(str(p))  # never follow or remove links
                continue
            if entry.is_dir(follow_symlinks=False):
                _purge_dir_contents(p, root, protected, result)
                try:
                    os.rmdir(p)
                except OSError:
                    pass  # not empty (protected/locked content) - keep
                continue
            if _norm(p) in protected:
                result["kept"].append(str(p))
                continue
            os.unlink(p)
            result["removed"].append(p.name)
        except OSError as e:
            result["errors"].append(f"{p.name}: {e}")


def cleanup_task_temp_dir(download_id, protected_paths: Iterable = ()) -> dict:
    """Remove temporary artifacts from TEMP_DIR/dl_<id>, preserving protected files.

    Returns a dict describing what happened. Never raises.
    """
    result = {
        "download_id": download_id,
        "path": None,
        "removed": [],
        "kept": [],
        "errors": [],
        "dir_removed": False,
        "skipped": None,
    }
    task_dir = resolve_task_temp_dir(download_id)
    if task_dir is None:
        result["skipped"] = "invalid_or_unsafe_path"
        return result
    result["path"] = str(task_dir)
    if not task_dir.exists():
        result["skipped"] = "already_clean"
        return result
    if not task_dir.is_dir():
        result["skipped"] = "not_a_directory"
        return result

    protected = {_norm(p) for p in protected_paths if p}

    for attempt in range(2):
        result["errors"] = []
        result["kept"] = []
        _purge_dir_contents(task_dir, task_dir, protected, result)
        if not result["errors"]:
            break
        # Windows can hold file handles briefly after a process tree is killed.
        import time
        time.sleep(0.3)

    try:
        os.rmdir(task_dir)
        result["dir_removed"] = True
    except OSError:
        pass  # still contains protected/locked files - intentionally kept
    return result