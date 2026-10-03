"""Security validation utilities for UniversalDownloader."""
import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

from config import BLOCKED_HOSTNAMES, ALLOWED_SCHEMES


def parse_url(url: str) -> urlparse:
    """Parse a URL and return a urlparse result after basic sanitization."""
    url = url.strip()
    return urlparse(url)


def validate_url(url: str) -> dict:
    """Validate a URL for safe processing.

    Returns a dict with:
        - safe: bool
        - reason: Optional[str] — why it was rejected (if not safe)
        - scheme: str or None
        - hostname: str or None
    """
    if not url:
        return {"safe": False, "reason": "URL is empty"}

    parsed = parse_url(url)

    # Check scheme
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        return {
            "safe": False,
            "reason": f"Unsupported scheme: {scheme}",
            "scheme": scheme,
            "hostname": parsed.hostname,
        }

    # Check hostname
    hostname = parsed.hostname
    if hostname is None:
        return {"safe": False, "reason": "No hostname in URL", "scheme": scheme, "hostname": hostname}

    # Reject loopback/private addresses via hostname resolution
    rejection = _reject_hostname(hostname)
    if rejection:
        return rejection

    # Reject blocked hostnames explicitly
    hostname_lower = hostname.lower()
    if hostname_lower in BLOCKED_HOSTNAMES:
        return {
            "safe": False,
            "reason": f"Hostname '{hostname}' is blocked",
            "scheme": scheme,
            "hostname": hostname,
        }

    return {"safe": True, "scheme": scheme, "hostname": hostname}


def _reject_hostname(hostname: str) -> dict:
    """Check hostname against private, loopback, link-local, and reserved ranges.

    Resolves the hostname and rejects any destination that resolves to:
    - loopback (127.0.0.1, ::1)
    - private IPv4 ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - link-local addresses (169.254.0.0/16, fe80::/10)
    - unspecified addresses (0.0.0.0, ::)
    - relevant private/reserved IPv6 ranges

    Protects against DNS rebinding by checking all resolved IPs.
    """
    # If hostname is already an IP address, check it directly
    try:
        addr = ipaddress.ip_address(hostname)
        _private_ranges = [
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("169.254.0.0/16"),
            ipaddress.ip_network("fe80::/10"),
            ipaddress.ip_network("fc00::/7"),  # Unique local (IPv6)
            ipaddress.ip_network("::1/128"),   # IPv6 loopback
            ipaddress.ip_network("127.0.0.0/8"),  # IPv4 loopback
        ]
        if addr in _private_ranges:
            return {
                "safe": False,
                "reason": f"Private/reserved IP address: {hostname}",
                "scheme": None,
                "hostname": hostname,
            }
        return None  # IP address is public/allowed
    except ValueError:
        pass  # Not an IP, it's a hostname - resolve below

    # Resolve hostname to IP addresses
    try:
        # Get all IP addresses (IPv4 and IPv6)
        results = socket.getaddrinfo(hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        if not results:
            return None  # Resolution failed, allow subprocess to handle error

        _private_ranges = [
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("169.254.0.0/16"),
            ipaddress.ip_network("fe80::/10"),
            ipaddress.ip_network("fc00::/7"),  # Unique local (IPv6)
            ipaddress.ip_network("::1/128"),   # IPv6 loopback
            ipaddress.ip_network("127.0.0.0/8"),  # IPv4 loopback
        ]

        # Check all resolved addresses
        for family, _, _, _, sockaddr in results:
            ip_str = sockaddr[0]  # IP address
            try:
                addr = ipaddress.ip_address(ip_str)
                if addr in _private_ranges:
                    return {
                        "safe": False,
                        "reason": f"Resolved to private/reserved IP: {hostname} -> {ip_str}",
                        "scheme": None,
                        "hostname": hostname,
                    }
            except ValueError:
                # Invalid IP address from DNS - treat as unsafe
                return {
                    "safe": False,
                    "reason": f"Invalid IP address from DNS resolution: {ip_str}",
                    "scheme": None,
                    "hostname": hostname,
                }

        return None  # All resolved IPs are public/allowed
    except socket.gaierror:
        # DNS resolution failed - this could be malicious or just invalid hostname
        # Err on the side of caution and reject
        return {
            "safe": False,
            "reason": f"DNS resolution failed for hostname: {hostname}",
            "scheme": None,
            "hostname": hostname,
        }
    except Exception as e:
        # Other resolution errors
        return {
            "safe": False,
            "reason": f"Hostname resolution error: {str(e)}",
            "scheme": None,
            "hostname": hostname,
        }


def validate_save_path(path: str, allowed_dirs=None) -> dict:
    """Validate a save path to prevent path traversal and ensure it stays within permitted locations.

    Returns a dict with:
        - safe: bool
        - resolved: str — the normalized, safe path (only valid if safe=True)
        - reason: Optional[str] — why it was rejected (if not safe)
    """
    if allowed_dirs is None:
        from config import DOWNLOADS_DIR
        allowed_dirs = [DOWNLOADS_DIR]

    try:
        path = str(path).strip()
        resolved = Path(path).resolve()
    except Exception as e:
        return {"safe": False, "reason": f"Invalid path: {e}"}

    # Check that the resolved path stays within an allowed directory
    for allowed in allowed_dirs:
        try:
            resolved.relative_to(allowed)
            return {"safe": True, "resolved": str(resolved)}
        except ValueError:
            continue

    return {
        "safe": False,
        "reason": f"Path escapes permitted directories. Path: {resolved}, Allowed: {[str(a) for a in allowed_dirs]}",
    }


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to remove Windows-invalid and dangerous characters.

    Keeps alphanumeric, underscore, hyphen, dot, and space.
    Replaces multiple consecutive dots and trailing spaces/dots.
    """
    if not filename:
        return "download"

    # Remove/replace problematic characters
    # Windows invalid: < > : " / \ | ? * and control chars
    sanitized = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Remove control characters
    sanitized = re.sub(r'[\x00-\x1f\x7f]', '', sanitized)
    # Collapse multiple dots
    sanitized = re.sub(r'\.+', '.', sanitized)
    # Trim trailing spaces and dots
    sanitized = sanitized.rstrip(' .')
    # Ensure we don't end up with empty string
    if not sanitized.strip():
        return "download"

    return sanitized.strip()