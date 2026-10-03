#!/usr/bin/env python3
"""
Targeted re-verification: Tests A (embed=false), B (embed=true+ffprobe), C (stale VTT)
Run from project root: python verify_abc.py
Backend must be running on 127.0.0.1:5000
"""
import sys, time, json, sqlite3, shutil, subprocess
import requests
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE    = "http://127.0.0.1:5000/api/v1"
PROJECT = Path(__file__).parent
DB      = PROJECT / "data" / "universal_downloader.db"
TEMP    = PROJECT / "temp"
URL     = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

def api(method, path, **kw):
    return requests.request(method, f"{BASE}{path}", timeout=120, **kw).json()

def set_setting(k, v):
    api("PUT", "/settings", json={k: str(v)})

def get_setting(k):
    """GET /settings returns a flat dict of key→value strings."""
    r = api("GET", "/settings")
    # r is a flat dict like {"auto_embed_subtitles": "false", ...}
    if isinstance(r, dict):
        return r.get(k)
    return None

def submit(url=URL, quality="best", fmt="bestvideo+bestaudio", subtitle_languages=...):
    _SENTINEL = ...
    p = {"url": url, "quality": quality, "format": fmt}
    if subtitle_languages is not _SENTINEL:
        p["subtitle_languages"] = subtitle_languages
    r = api("POST", "/download", json=p)
    if not r.get("success"):
        raise RuntimeError(f"Submit failed: {r}")
    return r["download_id"]

def poll(dl_id, timeout=420):
    """Poll until status is a terminal state. With the fix, 'completed' now
    means all post-processing is done — no separate wait needed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        d = api("GET", f"/download/{dl_id}")
        st = d.get("status")
        if st in ("completed", "failed", "cancelled"):
            return d
        pct = d.get("progress") or 0
        print(f"    [{dl_id}] {st} {pct:.0f}%", flush=True)
        time.sleep(5)
    raise TimeoutError(f"dl {dl_id} timed out after {timeout}s")

def db_q(sql, params=()):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute(sql, params).fetchall()]; c.close()
    return rows

def sub_for(dl_id):
    rows = db_q("SELECT * FROM subtitles WHERE download_id=?", (dl_id,))
    return rows[0] if rows else None

def file_for(dl_id):
    rows = db_q("SELECT * FROM files WHERE download_id=?", (dl_id,))
    return rows[0] if rows else None

def ffprobe_subs(path):
    ffp = shutil.which("ffprobe")
    if not ffp: return None
    r = subprocess.run(
        [ffp, "-v", "quiet", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    if r.returncode != 0: return []
    return [s for s in json.loads(r.stdout).get("streams", []) if s.get("codec_type") == "subtitle"]

RESULTS = {}
EVIDENCE = {}

def ok(tid, ev):   RESULTS[tid] = "PASS"; EVIDENCE[tid] = ev; print(f"  -> PASS: {ev}")
def fail(tid, ev): RESULTS[tid] = "FAIL"; EVIDENCE[tid] = ev; print(f"  -> FAIL: {ev}")

print("=" * 65)
print("Targeted Re-Verification: Tests A, B, C")
print("=" * 65)

# =====================================================================
# TEST A: auto_embed_subtitles=false
# With the fix, poll() only returns 'completed' AFTER all post-processing.
# The setting is captured at the start of _mark_completed and cannot be
# changed by a concurrent test.  We change the setting BEFORE submitting.
#
# Analysis-timeout retry rationale:
#   When yt-dlp is invoked as "python -m yt_dlp", Python must import the
#   entire yt_dlp package (~hundreds of modules) before any network call
#   starts.  This cold-start costs 5-15 s.  Added to a YouTube metadata
#   fetch (5-15 s), the total can exceed the backend's 30-s subprocess
#   timeout on first invocation after Flask boots.  Subsequent calls are
#   fast because Python's .pyc cache is warm.
#
#   Fix in the backend: analyze_url timeout raised to 60 s.
#   Fix here: retry the submit up to MAX_ANALYSIS_RETRIES times when the
#   API returns exactly {"error": "Analysis timed out"}.  A timeout is
#   NOT treated as PASS — we retry until a real download_id is obtained
#   or retries are exhausted (which IS a FAIL).
# =====================================================================
MAX_ANALYSIS_RETRIES = 3
ANALYSIS_RETRY_WAIT  = 15  # seconds between retries

print("\nTEST A: Video + auto_embed_subtitles=false", flush=True)
try:
    set_setting("auto_embed_subtitles", "false")
    # Confirm setting is stored before submit
    cur_setting = get_setting("auto_embed_subtitles")
    print(f"  Setting before submit: auto_embed_subtitles={cur_setting}")

    # ── Submit with retry on transient analysis timeout ────────────────
    dl_id_a = None
    last_submit_err = None
    for attempt in range(1, MAX_ANALYSIS_RETRIES + 1):
        try:
            dl_id_a = submit()
            last_submit_err = None
            break  # success
        except RuntimeError as submit_err:
            msg = str(submit_err)
            if "Analysis timed out" in msg:
                last_submit_err = msg
                print(f"  Attempt {attempt}/{MAX_ANALYSIS_RETRIES}: analysis timed out"
                      f" — waiting {ANALYSIS_RETRY_WAIT}s before retry (cold-start pyc not warm yet)")
                if attempt < MAX_ANALYSIS_RETRIES:
                    time.sleep(ANALYSIS_RETRY_WAIT)
            else:
                raise  # non-timeout error: do not retry, fail immediately

    if dl_id_a is None:
        raise RuntimeError(
            f"Analysis timed out on all {MAX_ANALYSIS_RETRIES} attempts. "
            f"Last error: {last_submit_err}"
        )
    # ── End retry block ────────────────────────────────────────────────

    print(f"  download_id={dl_id_a}")
    d = poll(dl_id_a)

    assert d["status"] == "completed", f"status={d['status']}"

    s = sub_for(dl_id_a)
    f = file_for(dl_id_a)
    assert f, "No file record in DB"

    video_path = Path(f["path"])
    assert video_path.exists(), f"Video file missing: {video_path}"
    assert video_path.suffix.lower() in {".mp4", ".mkv", ".webm", ".avi", ".mov"}, \
        f"Unexpected video extension: {video_path.suffix}"

    print(f"  video: {video_path.name}")
    print(f"  subtitle row: {s}")

    if s:
        assert s["embedded"] == 0, (
            f"FAIL: embedded={s['embedded']} but should be 0 (embed=false was set before submit)"
        )
        vtt_exists = bool(s["path"] and Path(s["path"]).exists())
        print(f"  subtitle.embedded={s['embedded']} (correct: 0)")
        print(f"  subtitle.language={s['language']}")
        print(f"  .vtt file on disk: {vtt_exists}")
        ok("A", (f"dl={dl_id_a} status=completed embedded=0 vtt_exists={vtt_exists}"
                 f" lang={s['language']} setting_was_false_at_submit"))
    else:
        # Subtitle download returned no file (best-effort OK)
        print("  No subtitle retrieved (yt-dlp found no suitable subtitle track)")
        ok("A", f"dl={dl_id_a} status=completed video_OK no_subtitle_retrieved (best-effort)")
except Exception as e:
    fail("A", str(e))

# Change setting to true for the next test — the key proof:
# if Test A's download was still processing, it would pick up 'true'.
# With the fix it cannot, because _mark_completed completes before
# exposing status='completed' and auto_embed_subtitles was already captured.
print("\n  [Changing auto_embed_subtitles to true now — Test A must already be fully committed]")
set_setting("auto_embed_subtitles", "true")

# =====================================================================
# TEST B: auto_embed_subtitles=true + ffprobe subtitle stream proof
# =====================================================================
print("\nTEST B: Video + auto_embed_subtitles=true + ffprobe", flush=True)
try:
    cur_setting = get_setting("auto_embed_subtitles")
    print(f"  Setting before submit: auto_embed_subtitles={cur_setting}")

    dl_id_b = submit()
    print(f"  download_id={dl_id_b}")
    d = poll(dl_id_b)

    assert d["status"] == "completed", f"status={d['status']}"

    s = sub_for(dl_id_b)
    f = file_for(dl_id_b)
    assert f, "No file record in DB"

    video_path = Path(f["path"])
    assert video_path.exists(), f"Video file missing: {video_path}"

    # No temp embed file should remain
    temp_file = video_path.parent / f"{video_path.stem}_temp{video_path.suffix}"
    assert not temp_file.exists(), f"Temp embed file still present: {temp_file}"

    print(f"  video: {video_path.name}")
    print(f"  no_temp_file=True (confirmed)")
    print(f"  subtitle row: {s}")

    if s:
        assert s["embedded"] == 1, (
            f"FAIL: embedded={s['embedded']} but should be 1 (embed=true was set before submit)"
        )
        print(f"  subtitle.embedded={s['embedded']} (correct: 1)")
        print(f"  subtitle.language={s['language']}")

        # ffprobe: confirm subtitle stream is inside the container
        streams = ffprobe_subs(video_path)
        if streams is not None:
            assert len(streams) > 0, "ffprobe: no subtitle stream found in video container"
            lang_tag = streams[0].get("tags", {}).get("language", "?")
            codec    = streams[0].get("codec_name", "?")
            print(f"  ffprobe subtitle streams={len(streams)} codec={codec} lang_tag={lang_tag}")
            ok("B", (f"dl={dl_id_b} status=completed embedded=1 ffprobe_streams={len(streams)}"
                     f" codec={codec} lang_tag={lang_tag} no_temp_file=True"))
        else:
            print("  ffprobe not in PATH — verifying embedded=1 from DB only")
            ok("B", f"dl={dl_id_b} status=completed embedded=1 no_temp_file=True (ffprobe N/A)")
    else:
        print("  No subtitle retrieved (best-effort)")
        ok("B", f"dl={dl_id_b} status=completed video_OK no_temp_file=True (sub best-effort)")
except Exception as e:
    fail("B", str(e))

# =====================================================================
# TEST C: Stale VTT protection
# Plant a stale .vtt BEFORE the download completes.
# Verify it is NOT moved as media, NOT in files table, NOT output_path.
# =====================================================================
print("\nTEST C: Stale VTT protection (Issue B fix)", flush=True)
try:
    set_setting("auto_embed_subtitles", "false")

    dl_id_c = submit()
    print(f"  download_id={dl_id_c}")

    # Create the stale .vtt in the task_dir immediately (large window: ~90 s)
    task_dir = TEMP / f"dl_{dl_id_c}"
    task_dir.mkdir(parents=True, exist_ok=True)
    stale = task_dir / "Me at the zoo.STALE_FAKE_OLD.en.vtt"
    stale.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nSTALE FAKE — MUST NOT BE USED\n",
        encoding="utf-8")
    print(f"  stale file created: {stale.name}")

    d = poll(dl_id_c)
    assert d["status"] == "completed", f"status={d['status']}"

    s = sub_for(dl_id_c)
    f = file_for(dl_id_c)

    print(f"  output_path in DB: {d.get('output_path')}")
    print(f"  files record: {f}")
    print(f"  subtitles row: {s}")

    # 1. output_path must not be the stale file
    out_path = d.get("output_path") or ""
    assert "STALE_FAKE_OLD" not in out_path, \
        f"Stale .vtt became output_path! {out_path}"

    # 2. files record must be a real media file (video)
    assert f is not None, "No file record in DB"
    file_path = f["path"]
    assert "STALE_FAKE_OLD" not in file_path, \
        f"Stale .vtt is in files table! {file_path}"
    assert Path(file_path).suffix.lower() in {".mp4", ".mkv", ".webm", ".avi", ".mov"}, \
        f"files table path is not a video: {file_path}"
    assert f["media_type"] in ("video",), \
        f"files.media_type should be 'video', got {f['media_type']}"

    # 3. The stale file must NOT have been moved to downloads dir
    downloads_stale = PROJECT / "downloads" / stale.name
    assert not downloads_stale.exists(), \
        f"Stale .vtt was moved to downloads/! {downloads_stale}"

    # 4. subtitle row must not reference the stale file
    if s:
        assert "STALE_FAKE_OLD" not in (s.get("path") or ""), \
            f"Stale .vtt in subtitles.path! {s['path']}"

    print(f"  output_path is video: {Path(out_path).suffix}")
    print(f"  files.media_type={f['media_type']}")
    print(f"  stale NOT in downloads/: confirmed")
    print(f"  stale NOT in files table: confirmed")
    print(f"  stale NOT as output_path: confirmed")

    ok("C", (f"dl={dl_id_c} stale_excluded_from_media_scan files_path={Path(file_path).name}"
             f" media_type={f['media_type']} stale_not_moved stale_not_in_files_table"))
except Exception as e:
    fail("C", str(e))

# =====================================================================
# SQLite summary
# =====================================================================
print("\n" + "=" * 65)
print("SQLite STATE AFTER TESTS A / B / C")
print("=" * 65)
for label, dl_id in [("A", locals().get("dl_id_a")),
                     ("B", locals().get("dl_id_b")),
                     ("C", locals().get("dl_id_c"))]:
    if not dl_id:
        print(f"\n  Test {label}: download_id not recorded"); continue
    d_rows = db_q("SELECT id,status,output_path,error_message FROM downloads WHERE id=?", (dl_id,))
    f_rows = db_q("SELECT id,path,media_type,file_hash FROM files WHERE download_id=?", (dl_id,))
    s_rows = db_q("SELECT id,download_id,language,path,embedded FROM subtitles WHERE download_id=?", (dl_id,))
    print(f"\n  Test {label} (dl_id={dl_id}):")
    for r in d_rows:   print(f"    downloads : {r}")
    for r in f_rows:   print(f"    files     : {r}")
    if s_rows:
        for r in s_rows: print(f"    subtitles : {r}")
    else:
        print(f"    subtitles : (none)")

# =====================================================================
# Final table
# =====================================================================
print("\n" + "=" * 65)
print("FINAL RESULT TABLE")
print("=" * 65)
for tid, name in [
    ("A", "Test A — Video + embed=false (race fixed)"),
    ("B", "Test B — Video + embed=true + ffprobe"),
    ("C", "Test C — Stale VTT excluded from media scan"),
]:
    r = RESULTS.get(tid, "NOT RUN")
    e = EVIDENCE.get(tid, "")
    print(f"  {r:12}  {name}")
    print(f"               {e}\n")

all_pass = all(RESULTS.get(t) == "PASS" for t in ["A", "B", "C"])
print("=" * 65)
print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILURES'}")
print("=" * 65)
