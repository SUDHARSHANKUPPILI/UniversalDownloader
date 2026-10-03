-- UniversalDownloader SQLite schema

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    media_type TEXT NOT NULL,
    quality TEXT,
    format TEXT,
    subtitle_languages TEXT,
    save_location TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    progress REAL NOT NULL DEFAULT 0,
    total_size INTEGER,
    downloaded_size INTEGER,
    speed REAL,
    eta_seconds INTEGER,
    thumbnail TEXT,
    duration INTEGER,
    uploader TEXT,
    playlist_id TEXT,
    playlist_position INTEGER,
    playlist_total INTEGER,
    output_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    completed_at TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    source_hash TEXT,
    file_hash TEXT,
    metadata_json TEXT,
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (playlist_id) REFERENCES downloads(id)
);

CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
CREATE INDEX IF NOT EXISTS idx_downloads_created_at ON downloads(created_at);
CREATE INDEX IF NOT EXISTS idx_downloads_playlist_id ON downloads(playlist_id);
CREATE INDEX IF NOT EXISTS idx_downloads_source_hash ON downloads(source_hash);

CREATE TABLE IF NOT EXISTS queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    download_id INTEGER NOT NULL UNIQUE,
    position INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    claimed_by TEXT,
    claimed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (download_id) REFERENCES downloads(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_queue_position ON queue(position);
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);

CREATE TABLE IF NOT EXISTS workers (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'idle',
    current_download_id INTEGER,
    started_at TEXT,
    last_heartbeat TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (current_download_id) REFERENCES downloads(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    download_id INTEGER UNIQUE,
    path TEXT NOT NULL,
    filename TEXT NOT NULL,
    size INTEGER,
    media_type TEXT,
    file_hash TEXT,
    duration INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (download_id) REFERENCES downloads(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash);

CREATE TABLE IF NOT EXISTS statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_statistics_metric_time ON statistics(metric_name, recorded_at);

CREATE TABLE IF NOT EXISTS network_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    speed REAL,
    bytes_transferred INTEGER,
    active_connections INTEGER,
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    ip_address TEXT,
    url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_security_events_time ON security_events(created_at);

CREATE TABLE IF NOT EXISTS subtitles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    download_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    format TEXT NOT NULL,
    path TEXT,
    embedded INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (download_id) REFERENCES downloads(id) ON DELETE CASCADE
);
