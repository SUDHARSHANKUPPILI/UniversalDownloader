# UniversalDownloader

UniversalDownloader is a modern web-based media and subtitle downloading application powered by yt-dlp and FFmpeg, featuring an interactive React + TypeScript user interface and a robust Python Flask backend.

---

## Architecture Overview

* **Frontend:** React 19, TypeScript, Vite, Tailwind CSS, Lucide icons, Framer Motion, and React Router.
* **Backend:** Python Flask API server managing task queues, concurrent worker pools, and process execution.
* **Database:** SQLite (`data/universal_downloader.db`) with schema migrations and thread-safe connection pooling.
* **Extraction Engine:** `yt-dlp` executed as a Python module (`python -m yt_dlp`).
* **Media & Subtitle Processing:** FFmpeg for remuxing, stream mapping, and subtitle container embedding.

---

## Directory Structure

```text
UniversalDownloader/
├── backend/
│   ├── app.py                  # Flask entrypoint & SPA static asset server
│   ├── config.py               # Application configuration & directory constants
│   ├── database/
│   │   ├── db.py               # SQLite connection management & helpers
│   │   └── schema.sql          # Database schema (downloads, queue, files, subtitles, settings)
│   ├── routes/
│   │   └── api.py              # REST API blueprint (/api/v1)
│   ├── services/
│   │   ├── download_service.py # Download lifecycle, worker pool, queue & temp cleanup
│   │   ├── process_manager.py  # Subprocess execution & process tree termination
│   │   └── yt_dlp_service.py   # AppLocker-safe yt-dlp invocation & format options
│   └── utils/
│       ├── files.py            # Hashing, MIME detection, safe temp dir resolution & cleanup
│       └── security.py         # URL validation, SSRF protection, path sanitization
├── frontend/
│   ├── src/                    # React components, pages, hooks, and API client
│   ├── index.html              # HTML entrypoint
│   ├── package.json            # Frontend dependencies & scripts
│   ├── tsconfig.json           # TypeScript configuration
│   └── vite.config.ts          # Vite build configuration
├── data/                       # Local SQLite database (universal_downloader.db, Git-ignored)
├── downloads/                  # Final user media & standalone subtitle destination (Git-ignored)
├── temp/                       # Temporary task staging directories temp/dl_<id>/ (Git-ignored)
├── verify_6_fixes.py           # Core regression verification suite (15 tests)
├── verify_abc.py               # Subtitle embedding and stale VTT verification suite
├── verify_audit_fixes.py       # Backend audit robustness verification suite (7 tests)
├── verify_e2e_edge.py          # Microsoft Edge CDP headless browser E2E test
├── verify_naming_templates.py  # Filename templates & collision suite (20 tests)
├── verify_notifications.py     # Download & queue notifications suite (9 tests)
├── verify_temp_cleanup.py      # Temp directory lifecycle & path safety suite (9 tests)
├── verify_video_quality.py     # Video quality & format resolution suite (14 tests)
├── .gitignore                  # Root Git ignore rules
└── README.md                   # Project documentation
```

---

## Prerequisites

1. **Python 3.11+**:
   Ensure `python` is available in your PATH.
   ```powershell
   python --version
   ```
2. **Node.js (v18+) and npm**:
   ```powershell
   node --version
   npm --version
   ```
3. **FFmpeg & FFprobe**:
   Must be installed and available in PATH (or specified via `FFMPEG_BIN` environment variable).
   ```powershell
   ffmpeg -version
   ffprobe -version
   ```
4. **Python Dependencies**:
   Install the required Python packages into your environment:
   ```powershell
   python -m pip install flask flask-cors yt-dlp
   python -m yt_dlp --version
   ```

---

## Important Windows / AppLocker Note

On Windows systems with Application Control or AppLocker policies enabled, direct execution of `yt-dlp.exe` may be blocked (`WinError 4551`). 

To guarantee 100% reliability and security compliance, UniversalDownloader invokes `yt-dlp` directly through the active Python interpreter:
```python
[sys.executable, "-m", "yt_dlp", ...]
```
**Do not** replace this with direct `yt-dlp.exe` subprocess calls.

---

## Quick Start (Windows One-Click Launcher)

UniversalDownloader includes a single-click / single-command launcher that automatically verifies your environment, ensures the frontend is built, starts the server, and opens your browser:

* **Double-click:** Run `start.bat` in Windows File Explorer.
* **Or run in PowerShell:**
  ```powershell
  .\start.ps1
  ```
* **Options:**
  * `.\start.ps1 -Dev`: Starts both Flask API and Vite development server (with hot module replacement) concurrently.
  * `.\start.ps1 -NoBrowser`: Runs server without automatically launching the web browser.

---

## Manual Startup & Development

### 1. Start the Flask Backend Server
From the project root:
```powershell
python backend/app.py
```
The API server starts on `http://127.0.0.1:5000`.

### 2. Start the Frontend Development Server
From a separate terminal:
```powershell
cd frontend
npm install
npm run dev
```
The Vite development server runs on `http://localhost:5173` and communicates with the backend on port 5000.

---

## Production / Single-Server Mode

The Flask backend is configured to serve the compiled frontend as a single-page application (SPA):

1. **Build the Frontend:**
   ```powershell
   cd frontend
   npm run build
   cd ..
   ```
   This compiles TypeScript and generates production static assets in `frontend/dist/`.

2. **Run the Backend:**
   ```powershell
   python backend/app.py
   ```
   Navigate directly to `http://127.0.0.1:5000/`. Flask serves `index.html` and static assets while routing `/api/v1/*` requests to the REST API.

---

## Subtitle & Media Processing

### Automatic English Subtitles

UniversalDownloader automatically attempts to obtain English subtitles during normal downloads.

Behavior:

1. Prefer available manual/native English subtitles.
2. Fall back to English automatic captions when necessary.
3. Handle regional English language codes such as `en-US` and `en-GB`.
4. Embed subtitles when subtitle embedding is enabled.
5. Explicitly disabling subtitles remains supported.

* **Auto-Embed Enabled (`auto_embed_subtitles=true`):**
  yt-dlp retrieves subtitles as `.vtt`. FFmpeg remuxes the subtitle stream into the final video container with correct ISO-639 language tagging (`eng`, `spa`, `fre`, etc.). Temporary `.vtt` files are deleted after successful embedding.
* **Standalone Subtitles (`auto_embed_subtitles=false`):**
  Subtitles are downloaded, promoted from `temp/dl_<id>/` into `downloads/` alongside the video, and preserved as separate files.
* **Stale File Protection:**
  Subtitle files are excluded from the primary media discovery scan to prevent stale `.vtt` files from being misidentified as primary video outputs.

### Video Quality Selection

UniversalDownloader provides reliable video quality resolution without low-quality fallback:

* **Best Quality:** Selects the highest available video stream (`bestvideo*`) and pairs it with the highest quality audio stream (`bestaudio`), supporting up to 4K / 2160p and HDR streams.
* **Resolution Limits:** Supports explicit selection of `2160p` (4K), `1440p` (2K), `1080p` (Full HD), `720p` (HD), `480p`, and `360p`.
* **Safe Fallback:** If a requested resolution is not offered by the source video, the engine automatically selects the highest available resolution under or equal to the requested limit.
* **Audio Extraction:** Selecting `Audio Only` extracts high-quality audio (`bestaudio/best`) converted to MP3.

---

### Download & Queue Notifications

UniversalDownloader includes a unified notification system:

* **In-App Toast Notifications:** Instant feedback upon task completion, queue completion, or download failures.
* **Desktop Notifications:** Optional integration with the browser's native Notification API for background alerts when the tab is unfocused.
* **Smart Deduplication:** Polling, route transitions, and page refreshes never generate duplicate notification banners.

---

### Customizable Filename Templates

Users can configure global or per-download output filename patterns in Settings:

* **Available Variables:**
  * `{title}` — Sanitized video or audio title
  * `{uploader}` — Channel or uploader name
  * `{date}` — Upload date (`YYYYMMDD`)
  * `{id}` — Video identifier
  * `{ext}` — Media file extension
  * `{playlist_title}` — Name of the containing playlist (for playlists)
  * `{playlist_index}` — 2-digit zero-padded item number (e.g., `01`, `02`)
* **Security & Collisions:**
  * Path traversal (`../`) and absolute paths are automatically stripped.
  * Windows reserved filenames (`CON`, `NUL`, `AUX`, etc.) and invalid characters are sanitized.
  * Duplicate filenames automatically increment (`Title.mp4`, `Title (1).mp4`, `Title (2).mp4`).
  * Subtitle files (`.vtt`, `.srt`) are automatically synchronized with the resolved media filename.

---

## Troubleshooting

1. **Low video quality or missing formats:**
   * Ensure `yt-dlp` is up to date: `python -m pip install --upgrade yt-dlp`
2. **Audio extraction or subtitle embedding fails:**
   * Verify FFmpeg is installed and accessible in your system PATH: `ffmpeg -version`
3. **AppLocker or Execution Policy errors on Windows:**
   * Use `start.bat` which launches PowerShell with `-ExecutionPolicy Bypass`.
   * yt-dlp is executed via `python -m yt_dlp` to ensure AppLocker compliance.
4. **Port 5000 already in use:**
   * Stop existing processes on port 5000 or run: `.\start.ps1 -Port 5050`

---

## Verification & Testing Suites

UniversalDownloader includes comprehensive automated test suites:

```powershell
# 1. Temporary-directory lifecycle & path safety (9 tests)
python verify_temp_cleanup.py

# 2. Core backend regressions (15 tests)
python verify_6_fixes.py

# 3. Backend audit robustness (7 tests)
python verify_audit_fixes.py

# 4. End-to-end subtitle embedding & stale VTT protection (3 tests)
python verify_abc.py

# 5. Download & queue notification system (9 tests)
python verify_notifications.py

# 6. Filename templates & collision handling (20 tests)
python verify_naming_templates.py

# 7. Video quality selection & format discovery (14 tests)
python verify_video_quality.py

# 8. Full browser E2E test via Microsoft Edge CDP (16 tests)
python verify_e2e_edge.py
```

---

## Git & Runtime Data Notes

The following directories and files are generated at runtime and are strictly excluded from version control via `.gitignore`:
* `downloads/` — Downloaded media and standalone subtitles.
* `temp/` — Temporary staging directories for active downloads.
* `data/*.db` — SQLite database files and journals.
* `frontend/dist/` — Built frontend distribution assets.
* `.edge_test_profile/` — Browser test profiles.
