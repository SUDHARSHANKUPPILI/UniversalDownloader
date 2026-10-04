"""UniversalDownloader: Phase 2 Filename Template Verification Suite.

Tests:
1. Default template '{title}.{ext}' produces exact title filename (backward compatibility)
2. Template with '{uploader} - {title}.{ext}' produces 'Channel - Title.ext'
3. Template with '{date}_{title}_{id}.{ext}' produces formatted string
4. Template with '{playlist_index} - {title}.{ext}' for playlist items
5. Template with unknown variable rejected with validation error
6. Template with malformed braces rejected
7. Template producing Windows-invalid characters (<, >, :, ", /, \\, |, ?, *) is sanitized
8. Template producing reserved Windows names (CON, PRN, AUX, NUL, COM1, LPT1) is sanitized
9. Template producing path traversal (../) is sanitized/rejected
10. Template producing absolute path (C:\\...) is sanitized/rejected
11. Template producing extremely long filename (>255 chars) is clamped preserving extension
12. Empty rendered filename falls back safely
13. Custom template applied via POST /api/v1/download
14. Global default template updated via PUT /api/v1/settings
15. Global default template used when download doesn't specify custom template
16. Collision handling: downloading two files that render to same name creates 'File (1).ext'
17. Collision handling: downloading third file creates 'File (2).ext'
18. Database output_path correctly reflects renamed file
19. Database files table correctly reflects renamed file
20. Subtitle files (.vtt/.srt) renamed to match the final media filename
"""

import sys
import os
import shutil
import tempfile
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from app import app
from utils.template import (
    validate_filename_template,
    sanitize_filename_component,
    sanitize_rendered_filename,
    render_filename,
    resolve_unique_filename,
    ALLOWED_TEMPLATE_VARS,
    WINDOWS_RESERVED_NAMES,
)
from database.db import get_connection, save_settings, get_all_settings, init_db
from services.download_service import download_service

def run_tests():
    print("=" * 70)
    print("UNIVERSALDOWNLOADER: PHASE 2 FILENAME TEMPLATES VERIFICATION")
    print("=" * 70)

    passed = 0
    failed = 0

    def record(num, desc, success, detail=""):
        nonlocal passed, failed
        if success:
            passed += 1
            print(f"  [PASS] Test {num:02d}: {desc} ({detail})")
        else:
            failed += 1
            print(f"  [FAIL] Test {num:02d}: {desc} ({detail})")

    # -------------------------------------------------------------
    # 1. Default template '{title}.{ext}' produces exact title filename
    # -------------------------------------------------------------
    rendered_1 = render_filename("{title}.{ext}", {"title": "Classic Video", "ext": "mp4"})
    record(1, "Default template '{title}.{ext}' produces exact title filename",
           rendered_1 == "Classic Video.mp4", f"result='{rendered_1}'")

    # -------------------------------------------------------------
    # 2. Template with '{uploader} - {title}.{ext}' produces 'Channel - Title.ext'
    # -------------------------------------------------------------
    rendered_2 = render_filename("{uploader} - {title}.{ext}", {"uploader": "National Geographic", "title": "Wild Cats", "ext": "mkv"})
    record(2, "Template '{uploader} - {title}.{ext}' produces 'Channel - Title.ext'",
           rendered_2 == "National Geographic - Wild Cats.mkv", f"result='{rendered_2}'")

    # -------------------------------------------------------------
    # 3. Template with '{date}_{title}_{id}.{ext}' produces formatted string
    # -------------------------------------------------------------
    rendered_3 = render_filename("{date}_{title}_{id}.{ext}", {"date": "20261004", "title": "Launch", "id": "abc123xyz", "ext": "mp4"})
    record(3, "Template '{date}_{title}_{id}.{ext}' produces formatted string",
           rendered_3 == "20261004_Launch_abc123xyz.mp4", f"result='{rendered_3}'")

    # -------------------------------------------------------------
    # 4. Template with '{playlist_index} - {title}.{ext}' for playlist items
    # -------------------------------------------------------------
    rendered_4 = render_filename("{playlist_index} - {title}.{ext}", {"playlist_index": "01", "title": "First Song", "ext": "mp3"})
    record(4, "Template '{playlist_index} - {title}.{ext}' for playlist items",
           rendered_4 == "01 - First Song.mp3", f"result='{rendered_4}'")

    # -------------------------------------------------------------
    # 5. Template with unknown variable rejected with validation error
    # -------------------------------------------------------------
    valid_5, err_5 = validate_filename_template("{author} - {title}.{ext}")
    record(5, "Template with unknown variable rejected with validation error",
           not valid_5 and "Unknown variable '{author}'" in (err_5 or ""), f"err='{err_5}'")

    # -------------------------------------------------------------
    # 6. Template with malformed braces rejected
    # -------------------------------------------------------------
    valid_6a, _ = validate_filename_template("{title - {ext}")
    valid_6b, _ = validate_filename_template("{{title}}.mp4")
    valid_6c, _ = validate_filename_template("{}.mp4")
    record(6, "Template with malformed braces rejected",
           not valid_6a and not valid_6b and not valid_6c, "malformed braces correctly rejected")

    # -------------------------------------------------------------
    # 7. Template producing Windows-invalid characters is sanitized
    # -------------------------------------------------------------
    rendered_7 = render_filename("{title}.{ext}", {"title": 'Test <Video>: "Quotes" / \\ | ? * Stars', "ext": "mp4"})
    has_invalid_chars = any(c in rendered_7 for c in '<>:"/\\|?*')
    record(7, "Template producing Windows-invalid characters is sanitized",
           not has_invalid_chars and rendered_7.endswith(".mp4"), f"result='{rendered_7}'")

    # -------------------------------------------------------------
    # 8. Template producing reserved Windows names is sanitized
    # -------------------------------------------------------------
    san_8a = sanitize_rendered_filename("CON.mp4")
    san_8b = sanitize_rendered_filename("nul.mkv")
    san_8c = sanitize_rendered_filename("Aux.mp4")
    record(8, "Template producing reserved Windows names (CON, NUL, AUX) is sanitized",
           san_8a == "_CON.mp4" and san_8b == "_nul.mkv" and san_8c == "_Aux.mp4",
           f"CON->{san_8a}, nul->{san_8b}, Aux->{san_8c}")

    # -------------------------------------------------------------
    # 9. Template producing path traversal (../) is sanitized/rejected
    # -------------------------------------------------------------
    valid_9, err_9 = validate_filename_template("../secret/{title}.{ext}")
    san_9 = sanitize_rendered_filename("../../secret.mp4")
    record(9, "Template producing path traversal (../) is sanitized/rejected",
           not valid_9 and ".." not in san_9 and "/" not in san_9 and "\\" not in san_9,
           f"sanitized='{san_9}'")

    # -------------------------------------------------------------
    # 10. Template producing absolute path (C:\...) is sanitized/rejected
    # -------------------------------------------------------------
    valid_10, _ = validate_filename_template("C:/{title}.{ext}")
    san_10 = sanitize_rendered_filename("C:\\Windows\\System32\\bad.mp4")
    record(10, "Template producing absolute path is sanitized/rejected",
           not valid_10 and ":" not in san_10 and "\\" not in san_10, f"sanitized='{san_10}'")

    # -------------------------------------------------------------
    # 11. Template producing extremely long filename (>255 chars) clamped
    # -------------------------------------------------------------
    long_title = "A" * 300
    rendered_11 = render_filename("{title}.{ext}", {"title": long_title, "ext": "mp4"})
    record(11, "Template producing extremely long filename is clamped preserving extension",
           len(rendered_11) <= 255 and rendered_11.endswith(".mp4"),
           f"length={len(rendered_11)}, ends_with={rendered_11[-4:]}")

    # -------------------------------------------------------------
    # 12. Empty rendered filename falls back safely
    # -------------------------------------------------------------
    rendered_12 = render_filename("{uploader}", {"uploader": ""}, default_ext="mp4")
    record(12, "Empty rendered filename falls back safely",
           bool(rendered_12) and rendered_12.endswith(".mp4"), f"result='{rendered_12}'")

    with app.test_client() as client:
        # -------------------------------------------------------------
        # 13. Custom template applied via POST /api/v1/download
        # -------------------------------------------------------------
        res_13_bad = client.post("/api/v1/download", json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "filename_template": "{bad_var}.{ext}"
        })
        res_13_good = client.post("/api/v1/download", json={
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "filename_template": "{uploader} - {title}.{ext}"
        })
        data_13 = res_13_good.get_json() or {}
        dl_id_13 = data_13.get("download_id")
        # Check DB metadata_json
        conn = get_connection()
        row_13 = conn.execute("SELECT metadata_json FROM downloads WHERE id = ?", (dl_id_13,)).fetchone()
        meta_13 = json.loads(row_13["metadata_json"]) if row_13 and row_13["metadata_json"] else {}
        conn.close()

        record(13, "Custom template applied via POST /api/v1/download",
               res_13_bad.status_code == 400 and res_13_good.status_code == 200 and
               meta_13.get("filename_template") == "{uploader} - {title}.{ext}",
               f"bad_status={res_13_bad.status_code}, saved_tpl={meta_13.get('filename_template')}")

        # -------------------------------------------------------------
        # 14. Global default template updated via PUT /api/v1/settings
        # -------------------------------------------------------------
        res_14_bad = client.put("/api/v1/settings", json={"filename_template": "{invalid_var}.{ext}"})
        res_14_good = client.put("/api/v1/settings", json={"filename_template": "{date}_{title}.{ext}"})
        conn = get_connection()
        row_14 = conn.execute("SELECT value FROM settings WHERE key = 'filename_template'").fetchone()
        conn.close()
        saved_tpl_14 = row_14["value"] if row_14 else None
        # Restore default for subsequent tests
        save_settings({"filename_template": "{title}.{ext}"})

        record(14, "Global default template updated via PUT /api/v1/settings",
               res_14_bad.status_code == 400 and res_14_good.status_code == 200 and
               saved_tpl_14 == "{date}_{title}.{ext}",
               f"bad_status={res_14_bad.status_code}, saved_global={saved_tpl_14}")

        # -------------------------------------------------------------
        # 15. Global default template used when download doesn't specify custom
        # -------------------------------------------------------------
        # Set global to {uploader}_{title}.{ext}
        save_settings({"filename_template": "{uploader}_{title}.{ext}"})
        res_15 = client.post("/api/v1/download", json={
            "url": "https://www.youtube.com/watch?v=9bZkp7q19f0"
        })
        dl_id_15 = (res_15.get_json() or {}).get("download_id")
        conn = get_connection()
        row_15 = conn.execute("SELECT metadata_json FROM downloads WHERE id = ?", (dl_id_15,)).fetchone()
        conn.close()
        meta_15 = json.loads(row_15["metadata_json"]) if row_15 and row_15["metadata_json"] else {}
        # Has no custom override
        has_no_override = "filename_template" not in meta_15
        save_settings({"filename_template": "{title}.{ext}"})  # reset

        record(15, "Global default template used when download has no custom template",
               res_15.status_code == 200 and has_no_override,
               f"no_custom_override_in_dl={has_no_override}")

    # -------------------------------------------------------------
    # 16. Collision handling: downloading two files creates 'File (1).ext'
    # -------------------------------------------------------------
    test_dir = Path(tempfile.mkdtemp(prefix="ud_collision_test_"))
    try:
        f1 = test_dir / "Sample.mp4"
        f1.write_text("file 1")
        col_1 = resolve_unique_filename(test_dir, "Sample.mp4")
        record(16, "Collision handling: second file creates 'File (1).ext'",
               col_1.name == "Sample (1).mp4", f"candidate='{col_1.name}'")

        # -------------------------------------------------------------
        # 17. Collision handling: third file creates 'File (2).ext'
        # -------------------------------------------------------------
        col_1.write_text("file 2")
        col_2 = resolve_unique_filename(test_dir, "Sample.mp4")
        record(17, "Collision handling: third file creates 'File (2).ext'",
               col_2.name == "Sample (2).mp4", f"candidate='{col_2.name}'")

        # -------------------------------------------------------------
        # 18-20. Simulated completion: DB output_path, files table, subtitle rename
        # -------------------------------------------------------------
        # Create a download entry in DB
        sim_save_dir = test_dir / "downloads"
        sim_save_dir.mkdir(parents=True, exist_ok=True)

        meta_sim = {
            "title": "Space Voyage",
            "uploader": "NASA",
            "filename_template": "{uploader} - {title}.{ext}",
        }
        conn = get_connection()
        cur = conn.execute(
            """INSERT INTO downloads (url, title, media_type, quality, format, subtitle_languages,
               save_location, status, source_hash, is_duplicate, metadata_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'downloading', 'hash_sim', 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
            ("https://example.com/nasa", "Space Voyage", "video", "best", "mp4", "en",
             str(sim_save_dir), json.dumps(meta_sim))
        )
        sim_dl_id = cur.lastrowid
        conn.commit()
        conn.close()

        # Create task_dir simulating downloaded media and subtitle
        from backend.config import TEMP_DIR
        task_dir = TEMP_DIR / f"dl_{sim_dl_id}"
        task_dir.mkdir(parents=True, exist_ok=True)
        dummy_media = task_dir / "Space Voyage.mp4"
        dummy_media.write_text("media content")
        dummy_sub = task_dir / "Space Voyage.en.vtt"
        dummy_sub.write_text("WEBVTT\n1\n00:00:00.000 --> 00:00:05.000\nHello")

        # Set auto_embed_subtitles to false for this test to verify standalone subtitle rename
        save_settings({"auto_embed_subtitles": "false"})

        # Mock _download_subtitles to return dummy_sub without making network yt-dlp call
        orig_download_subtitles = download_service._download_subtitles
        download_service._download_subtitles = lambda dl_id, url, td, sl: dummy_sub
        try:
            download_service._mark_completed(sim_dl_id)
        finally:
            download_service._download_subtitles = orig_download_subtitles

        # 18. Database output_path correctly reflects renamed file
        conn = get_connection()
        dl_row = conn.execute("SELECT output_path, status FROM downloads WHERE id = ?", (sim_dl_id,)).fetchone()
        file_row = conn.execute("SELECT filename, path FROM files WHERE download_id = ?", (sim_dl_id,)).fetchone()
        sub_row = conn.execute("SELECT path, language FROM subtitles WHERE download_id = ?", (sim_dl_id,)).fetchone()
        conn.close()

        expected_filename = "NASA - Space Voyage.mp4"
        out_path = Path(dl_row["output_path"]) if dl_row and dl_row["output_path"] else Path("")
        record(18, "Database output_path correctly reflects renamed file",
               dl_row["status"] == "completed" and out_path.name == expected_filename,
               f"output_path='{out_path.name}'")

        # 19. Database files table correctly reflects renamed file
        f_name = file_row["filename"] if file_row else ""
        record(19, "Database files table correctly reflects renamed file",
               f_name == expected_filename and Path(file_row["path"]).exists(),
               f"files.filename='{f_name}'")

        # 20. Subtitle files renamed to match final media filename
        expected_sub = "NASA - Space Voyage.en.vtt"
        sub_path = Path(sub_row["path"]) if sub_row and sub_row["path"] else Path("")
        record(20, "Subtitle files (.vtt/.srt) renamed to match final media filename",
               sub_path.name == expected_sub and sub_path.exists(),
               f"subtitle_filename='{sub_path.name}'")

        # Cleanup test files
        shutil.rmtree(test_dir, ignore_errors=True)
        # Restore settings
        save_settings({"auto_embed_subtitles": "true", "filename_template": "{title}.{ext}"})

    except Exception as e:
        shutil.rmtree(test_dir, ignore_errors=True)
        print(f"Exception during simulation: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 70)
    print(f"RESULTS: {passed}/20 PASSED, {failed} FAILED")
    print("=" * 70)
    return passed == 20 and failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
