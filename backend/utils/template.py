"""Filename template parsing, validation, and sanitization for UniversalDownloader."""
import re
from pathlib import Path
from typing import Dict, Optional, Tuple, Set

# Allowed template placeholder variables
ALLOWED_TEMPLATE_VARS: Set[str] = {
    "title",
    "uploader",
    "date",
    "id",
    "ext",
    "playlist_title",
    "playlist_index",
}

DEFAULT_FILENAME_TEMPLATE = "{title}.{ext}"

# Windows reserved device names
WINDOWS_RESERVED_NAMES: Set[str] = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}

# Regex matching valid placeholder {var_name}
PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def validate_filename_template(template: str) -> Tuple[bool, Optional[str]]:
    """Validate a user-supplied filename template.

    Rejects:
    - Empty or whitespace-only templates
    - Directory separators (/ or \\) and directory traversal (..)
    - Absolute path indicators (e.g. drive letters or leading slashes)
    - Unmatched or nested braces
    - Empty variables ({})
    - Unknown/unsupported placeholder variables
    """
    if not template or not template.strip():
        return False, "Filename template cannot be empty"

    stripped = template.strip()

    # Reject path separators and traversal indicators
    if "/" in stripped or "\\" in stripped:
        return False, "Path separators ('/' or '\\') are not allowed in filename templates"
    if ".." in stripped:
        return False, "Directory traversal ('..') is not allowed in filename templates"
    if re.match(r"^[a-zA-Z]:", stripped):
        return False, "Absolute paths are not allowed in filename templates"

    # Check for unmatched or nested braces
    # Remove all valid placeholders {var} and verify no stray { or } remains
    remainder = PLACEHOLDER_REGEX.sub("", stripped)
    if "{" in remainder or "}" in remainder:
        if "{}" in stripped:
            return False, "Empty variable '{}' is not allowed in template"
        return False, "Malformed template: unmatched or invalid braces found"

    # Find all placeholder matches
    matches = PLACEHOLDER_REGEX.findall(stripped)
    if not matches:
        return False, "Template must contain at least one variable (e.g. {title})"

    for var in matches:
        if var not in ALLOWED_TEMPLATE_VARS:
            allowed_sorted = ", ".join(f"{{{v}}}" for v in sorted(ALLOWED_TEMPLATE_VARS))
            return False, f"Unknown variable '{{{var}}}' in template. Allowed: {allowed_sorted}"

    return True, None


def sanitize_filename_component(component: str) -> str:
    """Sanitize an individual metadata component before template insertion."""
    if not component:
        return ""
    # Strip invalid Windows characters and control chars
    s = re.sub(r'[<>:"/\\|?*]', '', str(component))
    s = re.sub(r'[\x00-\x1f\x7f]', '', s)
    s = s.replace("..", "")
    return s.strip()


def sanitize_rendered_filename(filename: str, fallback_ext: str = "mp4") -> str:
    """Sanitize a rendered filename to ensure complete Windows compatibility and safety.

    - Strips invalid Windows characters: < > : " / \\ | ? *
    - Removes control characters
    - Prevents directory traversal and absolute path escaping
    - Handles Windows reserved device names (CON, NUL, AUX, etc.)
    - Trims trailing spaces and periods
    - Bounds filename length to safe limits
    - Preserves file extension
    """
    if not filename:
        return f"download.{fallback_ext.lstrip('.')}"

    # Remove invalid characters
    cleaned = re.sub(r'[<>:"/\\|?*]', '', filename)
    cleaned = re.sub(r'[\x00-\x1f\x7f]', '', cleaned)
    cleaned = cleaned.replace("..", "")

    # Split stem and suffix
    p = Path(cleaned)
    stem = p.stem.strip(" .")
    suffix = p.suffix.strip(" .")

    if not suffix:
        suffix = fallback_ext.lstrip(".")
    if not stem:
        stem = "download"

    # Collapse repeated spaces and dots
    stem = re.sub(r"\s+", " ", stem)
    stem = re.sub(r"\.+", ".", stem)

    # Check for Windows reserved names (case-insensitive)
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        stem = f"_{stem}"

    # Bound stem length (180 chars is safe for Windows NTFS MAX_PATH with directory prefix)
    if len(stem) > 180:
        stem = stem[:180].rstrip(" .")

    return f"{stem}.{suffix}"


def render_filename(
    template: str,
    metadata: Dict,
    default_ext: str = "mp4"
) -> str:
    """Render a filename template with metadata dictionary and sanitize result."""
    clean_ext = (metadata.get("ext") or default_ext or "mp4").lstrip(".")

    # Format upload date (e.g. 20261004 or YYYYMMDD)
    raw_date = metadata.get("upload_date") or metadata.get("date") or ""
    date_val = str(raw_date)[:10].replace("-", "")

    values = {
        "title": sanitize_filename_component(metadata.get("title") or "download"),
        "uploader": sanitize_filename_component(metadata.get("uploader") or metadata.get("channel") or ""),
        "date": sanitize_filename_component(date_val),
        "id": sanitize_filename_component(metadata.get("id") or ""),
        "ext": clean_ext,
        "playlist_title": sanitize_filename_component(metadata.get("playlist_title") or metadata.get("playlist") or ""),
        "playlist_index": sanitize_filename_component(str(metadata.get("playlist_index") or metadata.get("playlist_position") or "")),
    }

    # If template is empty or invalid, fall back to default
    if not template or not template.strip():
        template = DEFAULT_FILENAME_TEMPLATE

    rendered = template
    for var, val in values.items():
        rendered = rendered.replace(f"{{{var}}}", val)

    # If the template did not specify {ext}, ensure extension is appended
    if not rendered.lower().endswith(f".{clean_ext.lower()}"):
        rendered = f"{rendered}.{clean_ext}"

    # Clean up empty placeholder remnants, e.g. " - " when uploader is empty
    rendered = re.sub(r"^\s*-\s*", "", rendered)
    rendered = re.sub(r"\s*-\s*$", "", rendered)
    rendered = re.sub(r"\s+", " ", rendered)

    return sanitize_rendered_filename(rendered, fallback_ext=clean_ext)


def resolve_unique_filename(directory: Path, filename: str) -> Path:
    """Resolve filename collisions using the standard pattern: File.ext -> File (1).ext -> File (2).ext."""
    target = directory / filename
    if not target.exists():
        return target

    p = Path(filename)
    stem = p.stem
    ext = p.suffix
    counter = 1
    while True:
        candidate = directory / f"{stem} ({counter}){ext}"
        if not candidate.exists():
            return candidate
        counter += 1
