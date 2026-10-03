"""UniversalDownloader — Focused Verification Suite for the 6 Critical/High Fixes.

Tests:
1. Fix 1: delete_file and delete_subtitle connection safety (no ProgrammingError).
2. Fix 2: Standalone subtitle file handling (moved to save_location, DB path points to final file, physical file exists).
3. Fix 3: remove_download for completed, failed, cancelled, queued, and rejection of active tasks.
4. Fix 4: Flask SPA serving (index.html fallback for client routes, static assets, api isolation).
5. Fix 5: Explicit subtitle disabling ("subtitle_languages": "") prevents subtitle download and DB rows.
6. Fix 6: Subtitle language metadata in FFmpeg embedding (maps ISO-639-1 to ISO-639-2 tag, no hardcoded eng).
"""

import sys
import os
import sqlite3
import shutil
import subprocess
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from app import app
from database.db import get_connection, init_db
from config import DOWNLOADS_DIR, TEMP_DIR, FFMPEG_BIN
from services.download_service import (
    download_service,
    normalize_subtitle_language_tag,
    ISO_639_MAP,
)

results = []

def record(test_id, name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append({"id": test_id, "name": name, "status": status, "detail": detail})
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {test_id}: {name} -> {status} ({detail})")


def run_tests():
    init_db()
    client = app.test_client()

    print("\n" + "=" * 65)
    print("RUNNING FOCUSED VERIFICATION FOR 6 CRITICAL/HIGH FIXES")
    print("=" * 65 + "\n")

    # -------------------------------------------------------------
    # FIX 4: Flask SPA Serving Tests
    # -------------------------------------------------------------
    print("--- Testing Fix 4: Flask SPA Serving ---")
    resp_root = client.get("/")
    resp_dash = client.get("/dashboard")
    resp_down = client.get("/downloads")
    resp_hist = client.get("/history")
    resp_sett = client.get("/settings")
    resp_health = client.get("/api/v1/health")
    resp_api_404 = client.get("/api/v1/nonexistent_test_route")

    spa_ok = (
        resp_root.status_code == 200 and b"<!doctype html>" in resp_root.data.lower() and
        resp_dash.status_code == 200 and b"<!doctype html>" in resp_dash.data.lower() and
        resp_down.status_code == 200 and b"<!doctype html>" in resp_down.data.lower() and
        resp_hist.status_code == 200 and b"<!doctype html>" in resp_hist.data.lower() and
        resp_sett.status_code == 200 and b"<!doctype html>" in resp_sett.data.lower()
    )
    record("FIX4-SPA", "SPA direct navigation returns index.html", spa_ok, f"root={resp_root.status_code}, dash={resp_dash.status_code}, sett={resp_sett.status_code}")

    api_isolation_ok = (
        resp_health.status_code == 200 and resp_health.is_json and resp_health.get_json().get("status") == "ok" and
        resp_api_404.status_code == 404 and resp_api_404.is_json
    )
    record("FIX4-API", "API routes isolated from SPA catch-all", api_isolation_ok, f"health={resp_health.status_code}, 404_json={resp_api_404.is_json}")

    # Test static assets
    asset_file = None
    dist_assets = Path("frontend/dist/assets")
    if dist_assets.exists():
        css_files = list(dist_assets.glob("*.css"))
        if css_files:
            asset_file = css_files[0].name
            resp_asset = client.get(f"/assets/{asset_file}")
            asset_ok = resp_asset.status_code == 200 and len(resp_asset.data) > 0
            record("FIX4-ASSET", "Static CSS asset served correctly", asset_ok, f"file={asset_file}, code={resp_asset.status_code}")

    # -------------------------------------------------------------
    # FIX 1: delete_file and delete_subtitle SQLite Connection Safety
    # -------------------------------------------------------------
    print("\n--- Testing Fix 1: delete_file and delete_subtitle Connection Safety ---")
    conn = get_connection()
    # Create a dummy file for deletion test
    dummy_file_path = DOWNLOADS_DIR / "test_delete_me.mp4"
    dummy_file_path.write_bytes(b"dummy mp4 content for testing")
    cursor = conn.execute(
        "INSERT INTO files (path, filename, size, media_type) VALUES (?, ?, ?, ?)",
        (str(dummy_file_path), dummy_file_path.name, len(b"dummy mp4 content for testing"), "video")
    )
    test_file_id = cursor.lastrowid

    # Create parent download and dummy subtitle
    c_dl = conn.execute(
        "INSERT INTO downloads (url, title, media_type, save_location, status) VALUES ('https://example.com/del', 'Del Sub', 'video', ?, 'completed')",
        (str(DOWNLOADS_DIR),)
    )
    parent_dl_id = c_dl.lastrowid
    dummy_sub_path = DOWNLOADS_DIR / "test_delete_me.vtt"
    dummy_sub_path.write_bytes(b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello")
    cursor = conn.execute(
        "INSERT INTO subtitles (download_id, language, format, path, embedded) VALUES (?, ?, ?, ?, 0)",
        (parent_dl_id, "en", "vtt", str(dummy_sub_path))
    )
    test_sub_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Test DELETE /api/v1/files/<id>
    resp_del_file = client.delete(f"/api/v1/files/{test_file_id}")
    del_file_ok = resp_del_file.status_code == 200 and resp_del_file.get_json().get("success") is True
    file_gone = not dummy_file_path.exists()
    record("FIX1-FILE", "DELETE /api/v1/files/<id> returns 200 without closed DB error", del_file_ok and file_gone, f"code={resp_del_file.status_code}, disk_removed={file_gone}")

    # Test DELETE /api/v1/subtitles/<id>
    resp_del_sub = client.delete(f"/api/v1/subtitles/{test_sub_id}")
    del_sub_ok = resp_del_sub.status_code == 200 and resp_del_sub.get_json().get("success") is True
    sub_gone = not dummy_sub_path.exists()
    record("FIX1-SUB", "DELETE /api/v1/subtitles/<id> returns 200 without closed DB error", del_sub_ok and sub_gone, f"code={resp_del_sub.status_code}, disk_removed={sub_gone}")

    # -------------------------------------------------------------
    # FIX 3: remove_download for terminal states vs active
    # -------------------------------------------------------------
    print("\n--- Testing Fix 3: remove_download Terminal States & Active Protection ---")
    conn = get_connection()
    # Insert test downloads in various states
    test_states = ["completed", "failed", "cancelled", "queued", "downloading"]
    test_ids = {}
    for st in test_states:
        c = conn.execute(
            "INSERT INTO downloads (url, title, media_type, save_location, status) VALUES (?, ?, ?, ?, ?)",
            (f"https://example.com/{st}", f"Test {st}", "video", str(DOWNLOADS_DIR), st)
        )
        dl_id = c.lastrowid
        conn.execute(
            "INSERT INTO queue (download_id, position, status, claimed_by) VALUES (?, 999, ?, ?)",
            (dl_id, st, "hold" if st == "queued" else None)
        )
        test_ids[st] = dl_id
    conn.commit()
    conn.close()

    # Test removal of completed
    r_comp = client.delete(f"/api/v1/download/{test_ids['completed']}")
    comp_ok = r_comp.status_code == 200 and r_comp.get_json().get("success") is True
    record("FIX3-COMP", "remove_download removes 'completed' download", comp_ok, f"code={r_comp.status_code}")

    # Test removal of failed
    r_fail = client.delete(f"/api/v1/download/{test_ids['failed']}")
    fail_ok = r_fail.status_code == 200 and r_fail.get_json().get("success") is True
    record("FIX3-FAIL", "remove_download removes 'failed' download", fail_ok, f"code={r_fail.status_code}")

    # Test removal of cancelled
    r_canc = client.delete(f"/api/v1/download/{test_ids['cancelled']}")
    canc_ok = r_canc.status_code == 200 and r_canc.get_json().get("success") is True
    record("FIX3-CANC", "remove_download removes 'cancelled' download", canc_ok, f"code={r_canc.status_code}")

    # Test removal of queued
    r_que = client.delete(f"/api/v1/download/{test_ids['queued']}")
    que_ok = r_que.status_code == 200 and r_que.get_json().get("success") is True
    record("FIX3-QUE", "remove_download removes 'queued' download", que_ok, f"code={r_que.status_code}")

    # Test removal of active/downloading (MUST BE REJECTED)
    r_act = client.delete(f"/api/v1/download/{test_ids['downloading']}")
    act_ok = r_act.status_code == 400 and r_act.get_json().get("success") is False
    record("FIX3-ACTIVE", "remove_download blocks removal of active 'downloading' task", act_ok, f"code={r_act.status_code}, err={r_act.get_json().get('error')}")

    # Clean up test_ids['downloading'] from db manually
    conn = get_connection()
    conn.execute("DELETE FROM queue WHERE download_id = ?", (test_ids["downloading"],))
    conn.execute("DELETE FROM downloads WHERE id = ?", (test_ids["downloading"],))
    conn.commit()
    conn.close()

    # -------------------------------------------------------------
    # FIX 5: Explicit Subtitle Disabling ("subtitle_languages": "")
    # -------------------------------------------------------------
    print("\n--- Testing Fix 5: Explicit Subtitle Disabling ---")
    # Test that create_download with "" sets subtitle_languages = "" in DB (not NULL)
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO downloads
        (url, title, media_type, quality, format, subtitle_languages, save_location, status)
        VALUES (?, ?, ?, ?, ?, '', ?, 'queued')""",
        ("https://example.com/no_subs", "No Subs Video", "video", "best", "best", str(DOWNLOADS_DIR))
    )
    no_sub_id = cursor.lastrowid
    conn.commit()

    # Simulate completion on no_sub_id (without subtitles)
    dummy_task_dir = TEMP_DIR / f"dl_{no_sub_id}"
    dummy_task_dir.mkdir(parents=True, exist_ok=True)
    dummy_video = dummy_task_dir / "No Subs Video.mp4"
    dummy_video.write_bytes(b"dummy video data")

    # Run _mark_completed
    download_service._mark_completed(no_sub_id)

    # Check subtitles table
    sub_count = conn.execute("SELECT COUNT(*) as cnt FROM subtitles WHERE download_id = ?", (no_sub_id,)).fetchone()["cnt"]
    conn.close()

    # Cleanup
    dest_video = DOWNLOADS_DIR / "No Subs Video.mp4"
    if dest_video.exists():
        dest_video.unlink()
    if dummy_task_dir.exists():
        shutil.rmtree(dummy_task_dir, ignore_errors=True)

    no_sub_ok = (sub_count == 0)
    record("FIX5-DISABLE", "Explicit 'subtitle_languages': '' results in 0 subtitle DB rows", no_sub_ok, f"sub_count={sub_count}")

    # -------------------------------------------------------------
    # FIX 6: Subtitle Language Metadata (ISO-639 Mapping & FFmpeg test)
    # -------------------------------------------------------------
    print("\n--- Testing Fix 6: Subtitle Language Metadata Mapping & FFmpeg Tagging ---")
    required_mappings = {
        "en": "eng", "es": "spa", "fr": "fre", "de": "ger",
        "it": "ita", "pt": "por", "hi": "hin", "te": "tel",
        "ta": "tam", "ja": "jpn", "ko": "kor", "zh": "chi",
    }
    all_maps_ok = True
    map_details = []
    for iso1, expected_tag in required_mappings.items():
        actual = normalize_subtitle_language_tag(iso1)
        if actual != expected_tag:
            all_maps_ok = False
            map_details.append(f"{iso1}->{actual} (expected {expected_tag})")
    record("FIX6-MAP", "ISO-639-1 to ISO-639-2 language tag mapping", all_maps_ok, "All 12 required languages mapped correctly" if all_maps_ok else ", ".join(map_details))

    # Test regional variant parsing
    reg_ok = (
        normalize_subtitle_language_tag("en-US") == "eng" and
        normalize_subtitle_language_tag("es-419") == "spa" and
        normalize_subtitle_language_tag("fr-CA") == "fre" and
        normalize_subtitle_language_tag("zh-Hans") == "chi"
    )
    record("FIX6-REGIONAL", "Regional language variants parsed to base 3-letter code", reg_ok, "en-US->eng, es-419->spa, fr-CA->fre, zh-Hans->chi")

    # Real FFmpeg remux test with Spanish ('es' -> 'spa') subtitle
    ffmpeg_tag_ok = False
    if FFMPEG_BIN:
        test_dir = DOWNLOADS_DIR / "fix6_test"
        test_dir.mkdir(exist_ok=True)
        test_mp4 = test_dir / "test_video.mp4"
        test_vtt = test_dir / "test_sub.vtt"

        # Generate a 1-second silent MP4 test video using ffmpeg
        gen_cmd = [
            FFMPEG_BIN, "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1",
            "-c:v", "libx264", "-c:a", "aac", str(test_mp4)
        ]
        test_vtt.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHola mundo\n", encoding="utf-8")

        try:
            subprocess.run(gen_cmd, capture_output=True, check=True)
            # Embed with language="es"
            download_service._embed_subtitle(8888, test_mp4, test_vtt, test_dir, language="es")

            # Probe with ffprobe
            ffprobe_bin = str(Path(FFMPEG_BIN).with_name("ffprobe.exe")) if FFMPEG_BIN else "ffprobe"
            probe_cmd = [
                ffprobe_bin, "-v", "quiet", "-print_format", "json",
                "-show_streams", str(test_mp4)
            ]
            probe_res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            import json
            probe_data = json.loads(probe_res.stdout)
            sub_streams = [s for s in probe_data.get("streams", []) if s.get("codec_type") == "subtitle"]

            if sub_streams:
                stream_lang = sub_streams[0].get("tags", {}).get("language")
                ffmpeg_tag_ok = (stream_lang == "spa")
                record("FIX6-FFMPEG", "FFmpeg embeds Spanish subtitle with language=spa tag", ffmpeg_tag_ok, f"actual_tag='{stream_lang}', expected='spa'")
            else:
                record("FIX6-FFMPEG", "FFmpeg embeds Spanish subtitle stream", False, "No subtitle stream found in output")
        except Exception as e:
            record("FIX6-FFMPEG", "FFmpeg remux test execution", False, str(e))
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    # -------------------------------------------------------------
    # FIX 2: Standalone Subtitle File Handling
    # -------------------------------------------------------------
    print("\n--- Testing Fix 2: Standalone Subtitle File Handling ---")
    conn = get_connection()
    c = conn.execute(
        """INSERT INTO downloads
        (url, title, media_type, quality, format, subtitle_languages, save_location, status)
        VALUES (?, ?, ?, ?, ?, 'en', ?, 'queued')""",
        ("https://example.com/standalone_test", "Standalone Video", "video", "best", "best", str(DOWNLOADS_DIR))
    )
    dl2_id = c.lastrowid
    conn.commit()

    task_dir2 = TEMP_DIR / f"dl_{dl2_id}"
    task_dir2.mkdir(parents=True, exist_ok=True)
    video2 = task_dir2 / "Standalone Video.mp4"
    video2.write_bytes(b"dummy video content 2")
    sub2 = task_dir2 / "Standalone Video.en.vtt"
    sub2.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nStandalone subtitle\n", encoding="utf-8")

    # Mock _download_subtitles to return our sub2 path
    orig_download_subs = download_service._download_subtitles
    download_service._download_subtitles = lambda dl_id, url, td, sl: sub2

    # Set settings auto_embed_subtitles = false
    conn.execute("UPDATE settings SET value = 'false' WHERE key = 'auto_embed_subtitles'")
    conn.commit()

    try:
        download_service._mark_completed(dl2_id)
        # Check database
        sub_row = conn.execute("SELECT path, embedded FROM subtitles WHERE download_id = ?", (dl2_id,)).fetchone()
        sub_path_db = sub_row["path"] if sub_row else None
        embedded_db = sub_row["embedded"] if sub_row else None

        # Verify physical file exists at DB path
        physical_exists = Path(sub_path_db).exists() if sub_path_db else False
        in_downloads = str(DOWNLOADS_DIR).lower() in str(sub_path_db).lower() if sub_path_db else False
        not_in_temp = str(TEMP_DIR).lower() not in str(sub_path_db).lower() if sub_path_db else False

        fix2_ok = (
            sub_row is not None and
            embedded_db == 0 and
            physical_exists and
            in_downloads and
            not_in_temp
        )
        record(
            "FIX2-STANDALONE",
            "Standalone subtitle moved to save_location and DB path points to final file",
            fix2_ok,
            f"embedded={embedded_db}, physical_exists={physical_exists}, db_path='{sub_path_db}'"
        )
    finally:
        download_service._download_subtitles = orig_download_subs
        # Clean up
        if sub_path_db and Path(sub_path_db).exists():
            Path(sub_path_db).unlink()
        final_vid = DOWNLOADS_DIR / "Standalone Video.mp4"
        if final_vid.exists():
            final_vid.unlink()
        if task_dir2.exists():
            shutil.rmtree(task_dir2, ignore_errors=True)
        conn.close()

    # -------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------
    print("\n" + "=" * 65)
    print("VERIFICATION SUITE SUMMARY")
    print("=" * 65)
    passed_count = sum(1 for r in results if r["status"] == "PASS")
    failed_count = sum(1 for r in results if r["status"] == "FAIL")

    for r in results:
        mark = "[PASS]" if r["status"] == "PASS" else "[FAIL]"
        print(f"  {mark} [{r['id']}] {r['name']}: {r['status']}")

    print("\nTOTAL:", len(results), f"| PASSED: {passed_count} | FAILED: {failed_count}")
    print("=" * 65 + "\n")
    return failed_count == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
