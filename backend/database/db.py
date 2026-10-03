"""Database connection and persistence layer for UniversalDownloader."""
import sqlite3
import threading
import json
from pathlib import Path
from contextlib import contextmanager

from config import DB_PATH, DEFAULT_SETTINGS

_DB_LOCK = threading.RLock()
_connections_local = threading.local()


def get_connection():
    """Create a new SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db():
    """Return a connection for the current thread context.

    Uses thread-local storage so Flask requests and background workers
    each get their own connection safely.
    """
    if not hasattr(_connections_local, "conn") or _connections_local.conn is None:
        _connections_local.conn = get_connection()
    return _connections_local.conn


def close_db():
    """Close the thread-local connection."""
    conn = getattr(_connections_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _connections_local.conn = None


def init_db():
    """Initialize the database schema and seed default settings."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _DB_LOCK:
        conn = get_connection()
        try:
            schema_path = Path(__file__).with_name("schema.sql")
            schema = schema_path.read_text(encoding="utf-8")
            conn.executescript(schema)
            for key, value in DEFAULT_SETTINGS.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, value),
                )
            conn.commit()
        finally:
            conn.close()


@contextmanager
def transaction():
    """Context manager for a transaction using the thread-local connection."""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict."""
    if row is None:
        return None
    return dict(row)


def rows_to_dict(rows):
    """Convert a list of sqlite3.Row to a list of plain dicts."""
    return [row_to_dict(row) for row in rows]


def save_settings(settings):
    """Persist settings key/value pairs."""
    with transaction() as conn:
        for key, value in settings.items():
            if key not in DEFAULT_SETTINGS:
                continue
            if isinstance(value, bool):
                value = "true" if value else "false"
            elif isinstance(value, (dict, list)):
                value = json.dumps(value)
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, str(value)),
            )


def get_all_settings():
    """Load all settings as a dict."""
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = dict(DEFAULT_SETTINGS)
    for row in rows:
        if row["key"] in DEFAULT_SETTINGS:
            settings[row["key"]] = row["value"]
    return settings


def get_setting(key, default=None):
    """Get a single setting value."""
    settings = get_all_settings()
    return settings.get(key, default)
