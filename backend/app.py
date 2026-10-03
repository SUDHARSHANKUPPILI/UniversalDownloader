"""UniversalDownloader Flask application."""
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Ensure backend is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG
from database.db import init_db, get_db, close_db, get_all_settings
from services.download_service import download_service
from routes.api import api_bp

app = Flask(__name__)
CORS(app, resources={r"/api/v1/*": {"origins": ["http://localhost:5173", "http://127.0.0.1:5173"]}})

# Register blueprints
app.register_blueprint(api_bp, url_prefix="/api/v1")


from collections import defaultdict
import time
import threading

_rate_history = defaultdict(list)
_rate_lock = threading.Lock()

@app.before_request
def check_rate_limit():
    """Lightweight in-memory sliding-window rate limiter."""
    if request.path.startswith("/api/v1/"):
        from config import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS
        from database.db import get_connection
        ip = request.remote_addr or "127.0.0.1"
        now = time.time()
        with _rate_lock:
            cutoff = now - RATE_LIMIT_WINDOW_SECONDS
            _rate_history[ip] = [t for t in _rate_history[ip] if t > cutoff]
            if len(_rate_history[ip]) >= RATE_LIMIT_REQUESTS:
                try:
                    conn = get_connection()
                    conn.execute(
                        "INSERT INTO security_events (event_type, severity, description, ip_address) VALUES (?, ?, ?, ?)",
                        ("rate_limit_exceeded", "warning", f"Rate limit of {RATE_LIMIT_REQUESTS} req/min exceeded", ip),
                    )
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
                return jsonify({"error": "Rate limit exceeded. Please wait a moment."}), 429
            _rate_history[ip].append(now)

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.teardown_appcontext
def teardown_db(exception):
    """Close the thread-local database connection after each request."""
    close_db()


# Initialize database
init_db()

# Recover any interrupted downloads from last run
download_service.recover_interrupted()

# Start the worker pool
download_service.start_worker_pool()


# Health check
@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "UniversalDownloader"})


# Serve frontend static files
FRONTEND_BUILD_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_BUILD_DIR.exists():
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_spa(path):
        if path.startswith("api/"):
            return jsonify({"error": "Not found"}), 404
        target = FRONTEND_BUILD_DIR / path
        if path != "" and target.is_file():
            return send_from_directory(FRONTEND_BUILD_DIR, path)
        return send_from_directory(FRONTEND_BUILD_DIR, "index.html")


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)