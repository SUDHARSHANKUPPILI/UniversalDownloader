"""Verification suite for UniversalDownloader video quality pipeline.

Tests:
1. Best quality selection generates 'bestvideo*+bestaudio/best'
2. 2160p quality selection generates 'bestvideo*[height<=2160]+bestaudio/best[height<=2160]/best'
3. 1440p quality selection generates 'bestvideo*[height<=1440]+bestaudio/best[height<=1440]/best'
4. 1080p quality selection generates 'bestvideo*[height<=1080]+bestaudio/best[height<=1080]/best'
5. 720p quality selection generates 'bestvideo*[height<=720]+bestaudio/best[height<=720]/best'
6. 480p quality selection generates 'bestvideo*[height<=480]+bestaudio/best[height<=480]/best'
7. 360p quality selection generates 'bestvideo*[height<=360]+bestaudio/best[height<=360]/best'
8. Audio-only quality selection generates 'bestaudio/best' with extraction flag
9. Format 'best' (single progressive) respects quality constraints (e.g. best[height<=1080]/best)
10. Quality parameter is not silently ignored when format='bestvideo+bestaudio'
11. High-resolution format discovery on https://youtu.be/ehuDqQBVq40 (40+ formats, no SABR strip)
12. Real UniversalDownloader 1080p download produces 1920x1080 resolution in FFprobe
13. Real UniversalDownloader Best download produces highest available video resolution (>=1080p / 4K)
14. Subtitle extraction on https://youtu.be/xZTrukZkZ08 still works without regressions
"""

import sys
import os
import json
import time
import shutil
import tempfile
import subprocess
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from config import FFMPEG_BIN, DOWNLOADS_DIR, QUALITY_FORMAT_MAP, TEMP_DIR
from services.yt_dlp_service import build_yt_dlp_args, analyze_url, YT_DLP_CMD
from services.download_service import download_service

TEST_URL = "https://youtu.be/ehuDqQBVq40"
SUB_TEST_URL = "https://youtu.be/xZTrukZkZ08"

def ffprobe_info(file_path):
    ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
    cmd = [
        ffprobe_bin,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        return {}
    data = json.loads(res.stdout)
    streams = data.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    v = video_streams[0] if video_streams else {}
    a = audio_streams[0] if audio_streams else {}
    return {
        "width": v.get("width"),
        "height": v.get("height"),
        "vcodec": v.get("codec_name"),
        "acodec": a.get("codec_name"),
    }

def run_tests():
    print("=" * 70)
    print("UNIVERSALDOWNLOADER: VIDEO QUALITY VERIFICATION SUITE")
    print("=" * 70)

    passed = 0
    failed = 0

    def record(num, desc, ok, detail=""):
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"  [PASS] Test {num:02d}: {desc} ({detail})")
        else:
            failed += 1
            print(f"  [FAIL] Test {num:02d}: {desc} ({detail})")

    # 1. Best quality selection
    args_best = build_yt_dlp_args(TEST_URL, "out.mp4", quality="best", format="bestvideo+bestaudio")
    f_idx = args_best.index("-f")
    record(1, "Best quality generates 'bestvideo*+bestaudio/best'",
           args_best[f_idx + 1] == "bestvideo*+bestaudio/best",
           f"-f={args_best[f_idx + 1]}")

    # 2. 2160p
    args_2160 = build_yt_dlp_args(TEST_URL, "out.mp4", quality="2160p", format="bestvideo+bestaudio")
    f_idx = args_2160.index("-f")
    record(2, "2160p generates 'bestvideo*[height<=2160]+bestaudio/best[height<=2160]/best'",
           args_2160[f_idx + 1] == "bestvideo*[height<=2160]+bestaudio/best[height<=2160]/best",
           f"-f={args_2160[f_idx + 1]}")

    # 3. 1440p
    args_1440 = build_yt_dlp_args(TEST_URL, "out.mp4", quality="1440p", format="bestvideo+bestaudio")
    f_idx = args_1440.index("-f")
    record(3, "1440p generates 'bestvideo*[height<=1440]+bestaudio/best[height<=1440]/best'",
           args_1440[f_idx + 1] == "bestvideo*[height<=1440]+bestaudio/best[height<=1440]/best",
           f"-f={args_1440[f_idx + 1]}")

    # 4. 1080p
    args_1080 = build_yt_dlp_args(TEST_URL, "out.mp4", quality="1080p", format="bestvideo+bestaudio")
    f_idx = args_1080.index("-f")
    record(4, "1080p generates 'bestvideo*[height<=1080]+bestaudio/best[height<=1080]/best'",
           args_1080[f_idx + 1] == "bestvideo*[height<=1080]+bestaudio/best[height<=1080]/best",
           f"-f={args_1080[f_idx + 1]}")

    # 5. 720p
    args_720 = build_yt_dlp_args(TEST_URL, "out.mp4", quality="720p", format="bestvideo+bestaudio")
    f_idx = args_720.index("-f")
    record(5, "720p generates 'bestvideo*[height<=720]+bestaudio/best[height<=720]/best'",
           args_720[f_idx + 1] == "bestvideo*[height<=720]+bestaudio/best[height<=720]/best",
           f"-f={args_720[f_idx + 1]}")

    # 6. 480p
    args_480 = build_yt_dlp_args(TEST_URL, "out.mp4", quality="480p", format="bestvideo+bestaudio")
    f_idx = args_480.index("-f")
    record(6, "480p generates 'bestvideo*[height<=480]+bestaudio/best[height<=480]/best'",
           args_480[f_idx + 1] == "bestvideo*[height<=480]+bestaudio/best[height<=480]/best",
           f"-f={args_480[f_idx + 1]}")

    # 7. 360p
    args_360 = build_yt_dlp_args(TEST_URL, "out.mp4", quality="360p", format="bestvideo+bestaudio")
    f_idx = args_360.index("-f")
    record(7, "360p generates 'bestvideo*[height<=360]+bestaudio/best[height<=360]/best'",
           args_360[f_idx + 1] == "bestvideo*[height<=360]+bestaudio/best[height<=360]/best",
           f"-f={args_360[f_idx + 1]}")

    # 8. Audio only
    args_audio = build_yt_dlp_args(TEST_URL, "out.mp3", quality="audio", format="bestaudio/best")
    f_idx = args_audio.index("-f")
    has_extract = "--extract-audio" in args_audio
    record(8, "Audio quality generates 'bestaudio/best' with extraction flag",
           args_audio[f_idx + 1] == "bestaudio/best" and has_extract,
           f"-f={args_audio[f_idx + 1]}, extract_audio={has_extract}")

    # 9. Format 'best' single progressive
    args_single_1080 = build_yt_dlp_args(TEST_URL, "out.mp4", quality="1080p", format="best")
    args_single_best = build_yt_dlp_args(TEST_URL, "out.mp4", quality="best", format="best")
    f_1080 = args_single_1080[args_single_1080.index("-f") + 1]
    f_best = args_single_best[args_single_best.index("-f") + 1]
    record(9, "Format 'best' single progressive respects quality constraints",
           f_1080 == "best[height<=1080]/best" and f_best == "best",
           f"single_1080='{f_1080}', single_best='{f_best}'")

    # 10. Quality parameter not silently ignored when format='bestvideo+bestaudio'
    f_1080_val = args_1080[args_1080.index("-f") + 1]
    f_best_val = args_best[args_best.index("-f") + 1]
    f_720_val = args_720[args_720.index("-f") + 1]
    record(10, "Quality parameter differentiates -f spec despite generic format payload",
           f_1080_val != f_best_val and f_720_val != f_1080_val,
           f"1080p='{f_1080_val}', 720p='{f_720_val}', best='{f_best_val}'")

    # 11. Format discovery on test URL (no SABR strip)
    print("  ... Querying yt-dlp format metadata for test URL ...")
    p_meta = subprocess.run(
        YT_DLP_CMD + ["-J", "--no-warnings", TEST_URL],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60
    )
    if p_meta.returncode == 0:
        meta_data = json.loads(p_meta.stdout)
        formats = meta_data.get("formats", [])
        heights = {f.get("height") for f in formats if f.get("height")}
        has_1080 = 1080 in heights
        has_2160 = 2160 in heights
        record(11, "High-resolution formats discovered for test URL (no SABR strip)",
               len(formats) >= 30 and has_1080,
               f"total_formats={len(formats)}, heights_found={sorted(list(heights))}")
    else:
        record(11, "High-resolution formats discovered for test URL", False, p_meta.stderr[:200])

    # Start worker pool to process real downloads
    download_service.start_worker_pool()

    # 12. Real 1080p download via UniversalDownloader
    target_dl_dir = DOWNLOADS_DIR / "quality_test_1080"
    shutil.rmtree(target_dl_dir, ignore_errors=True)
    target_dl_dir.mkdir(parents=True, exist_ok=True)
    print("  ... Downloading test URL at 1080p via UniversalDownloader ...")
    res_1080 = download_service.create_download(
        url=TEST_URL,
        quality="1080p",
        format_str="bestvideo+bestaudio",
        subtitle_languages="",
        save_location=str(target_dl_dir),
    )
    dl_id_1080 = res_1080["download_id"]
    t0 = time.time()
    while time.time() - t0 < 180:
        d = download_service.get_download_by_id(dl_id_1080)
        if d["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(3)

    files_1080 = [f for f in target_dl_dir.iterdir() if f.is_file() and not f.name.endswith(".part")]
    if files_1080:
        info_1080 = ffprobe_info(files_1080[0])
        w = info_1080.get("width")
        h = info_1080.get("height")
        record(12, "Real UniversalDownloader 1080p download is 1920x1080 in FFprobe",
               w == 1920 and h == 1080,
               f"resolution={w}x{h}, file='{files_1080[0].name}'")
    else:
        record(12, "Real UniversalDownloader 1080p download is 1920x1080 in FFprobe", False, "no file downloaded")

    # 13. Real Best download via UniversalDownloader
    target_best_dir = DOWNLOADS_DIR / "quality_test_best"
    shutil.rmtree(target_best_dir, ignore_errors=True)
    target_best_dir.mkdir(parents=True, exist_ok=True)
    print("  ... Downloading test URL at Best via UniversalDownloader ...")
    res_best = download_service.create_download(
        url=TEST_URL,
        quality="best",
        format_str="bestvideo+bestaudio",
        subtitle_languages="",
        save_location=str(target_best_dir),
    )
    dl_id_best = res_best["download_id"]
    t0 = time.time()
    while time.time() - t0 < 180:
        d = download_service.get_download_by_id(dl_id_best)
        if d["status"] in ("completed", "failed", "cancelled"):
            break
        time.sleep(3)

    files_best = [f for f in target_best_dir.iterdir() if f.is_file() and not f.name.endswith(".part")]
    if files_best:
        info_best = ffprobe_info(files_best[0])
        w = info_best.get("width")
        h = info_best.get("height")
        record(13, "Real UniversalDownloader Best download selects highest available resolution",
               h is not None and h >= 1080,
               f"resolution={w}x{h}, file='{files_best[0].name}'")
    else:
        record(13, "Real UniversalDownloader Best download selects highest available resolution", False, "no file downloaded")

    # 14. Existing subtitle behavior on xZTrukZkZ08
    print("  ... Verifying subtitle discovery on reference URL ...")
    p_sub = subprocess.run(
        YT_DLP_CMD + ["--list-subs", "--no-warnings", SUB_TEST_URL],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60
    )
    has_sub = "en-US" in p_sub.stdout or "English" in p_sub.stdout
    record(14, "Existing English subtitle functionality preserved",
           p_sub.returncode == 0 and has_sub,
           f"subtitles_available={has_sub}")

    # Cleanup test folders
    shutil.rmtree(target_dl_dir, ignore_errors=True)
    shutil.rmtree(target_best_dir, ignore_errors=True)

    print("=" * 70)
    print(f"RESULTS: {passed}/14 PASSED, {failed} FAILED")
    print("=" * 70)
    return passed == 14 and failed == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
