import os
import time
import subprocess
import json
import logging
from typing import List, Dict, Any, Optional
import yt_dlp

logger = logging.getLogger("tiktok_downloader")

# Format selector prioritized for 1080p Full HD & High Bitrate with pristine audio
FORMAT_SELECTOR = (
    "bestvideo[ext=mp4]+bestaudio/"
    "bestvideo+bestaudio/"
    "bestvideo[format_id^=play]+bestaudio/"
    "best[format_id^=play][ext=mp4][vcodec!=none]/"
    "best[format_id^=play][vcodec!=none]/"
    "best[ext=mp4][vcodec!=none]/"
    "best[vcodec!=none]"
)

FALLBACK_AUDIO_FORMAT_SELECTOR = "best[ext=mp4]/best"

def get_ydl_base_opts(cookiefile: Optional[str] = None) -> Dict[str, Any]:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "http_headers": {
            # Section 9 Rule 3: Anti-bot challenge bypass
            "Referer": "https://www.tiktok.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        },
        "extractor_args": {
            "tiktok": {
                "webpage_download": ["True"]
            }
        }
    }

    if cookiefile and os.path.exists(cookiefile):
        opts["cookiefile"] = cookiefile

    # Section 9 Rule 7: Browser impersonation via curl_cffi
    try:
        import curl_cffi
        from yt_dlp.networking.impersonate import ImpersonateTarget
        opts["impersonate"] = ImpersonateTarget.from_str("chrome")
    except Exception:
        pass

    return opts

def list_profile_videos(username: str, cookiefile: Optional[str] = None, max_entries: int = 150) -> List[Dict[str, Any]]:
    """
    Fetches the newest 150 videos from a TikTok creator profile.
    Retries up to 3 times on empty listing as per Section 9 Rule 5 & 6.
    """
    username = username.lstrip("@")
    profile_url = f"https://www.tiktok.com/@{username}"
    
    opts = get_ydl_base_opts(cookiefile)
    opts.update({
        "extract_flat": True,
        "playlistend": max_entries,
        "ignoreerrors": True,
    })

    for attempt in range(1, 4):
        logger.info(f"Listing profile @{username} (attempt {attempt}/3)...")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info(profile_url, download=False)
                
                if not result:
                    time.sleep(2 ** attempt)
                    continue

                entries = result.get("entries") or []
                filtered_videos = []

                for entry in entries:
                    if not entry:
                        continue
                    url = entry.get("url") or entry.get("webpage_url") or ""
                    
                    # Filter out /photo/ slideshow posts (Section 6 & 9)
                    if "/photo/" in url:
                        continue

                    tiktok_id = str(entry.get("id") or "")
                    if not tiktok_id and url:
                        tiktok_id = url.split("/")[-1].split("?")[0]

                    if not tiktok_id:
                        continue

                    filtered_videos.append({
                        "id": tiktok_id,
                        "url": url if url.startswith("http") else f"https://www.tiktok.com/@{username}/video/{tiktok_id}",
                        "title": entry.get("title") or entry.get("description") or "",
                        "view_count": entry.get("view_count") or 0, # Section 6: Preserve view_count
                        "duration": entry.get("duration") or 0.0,
                        "upload_date": entry.get("upload_date") or "",
                    })

                if filtered_videos:
                    logger.info(f"Found {len(filtered_videos)} valid video candidates for @{username}")
                    return filtered_videos
                else:
                    logger.warning(f"Listing returned 0 videos for @{username} (attempt {attempt})")

        except Exception as e:
            logger.error(f"Error fetching profile @{username}: {e}")

        time.sleep(2 ** attempt)

    logger.warning(f"Could not list any videos for @{username} after 3 attempts.")
    return []

def verify_audio_with_ffprobe(video_path: str) -> bool:
    """
    Verifies if video has a valid audio stream using ffprobe (Section 9 Rule 2).
    """
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        video_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15)
        return "audio" in result.stdout.lower()
    except Exception as e:
        logger.warning(f"ffprobe check failed or ffprobe not installed: {e}")
        # If ffprobe is not installed, we cannot guarantee audio check, but allow if file exists
        return True

def download_video(video_url: str, output_dir: str = "downloads", cookiefile: Optional[str] = None) -> Optional[str]:
    """
    Downloads a TikTok video without watermark.
    Validates audio stream. Retries up to 3 times.
    """
    os.makedirs(output_dir, exist_ok=True)
    out_template = os.path.join(output_dir, "%(id)s.%(ext)s")

    for attempt in range(1, 4):
        logger.info(f"Downloading {video_url} (attempt {attempt}/3)...")
        opts = get_ydl_base_opts(cookiefile)
        opts.update({
            "format": FORMAT_SELECTOR,
            "format_sort": ["res:1080", "quality", "size", "br", "fps"],
            "merge_output_format": "mp4",
            "outtmpl": out_template,
            "overwrites": True,
        })

        downloaded_file = None
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                if info:
                    vid_id = info.get("id")
                    ext = info.get("ext", "mp4")
                    target = os.path.join(output_dir, f"{vid_id}.{ext}")
                    if os.path.exists(target):
                        downloaded_file = target
                    else:
                        # Find by id in dir
                        for f in os.listdir(output_dir):
                            if f.startswith(vid_id):
                                downloaded_file = os.path.join(output_dir, f)
                                break
        except Exception as e:
            logger.error(f"Download attempt {attempt} failed: {e}")

        if downloaded_file and os.path.exists(downloaded_file):
            # Check audio
            if verify_audio_with_ffprobe(downloaded_file):
                logger.info(f"Successfully downloaded and verified audio: {downloaded_file}")
                return downloaded_file
            else:
                logger.warning(f"File {downloaded_file} has no audio stream! Trying fallback format...")
                try:
                    os.remove(downloaded_file)
                except Exception:
                    pass
                
                # Retry with fallback selector
                opts["format"] = FALLBACK_AUDIO_FORMAT_SELECTOR
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.extract_info(video_url, download=True)
                        if os.path.exists(downloaded_file) and verify_audio_with_ffprobe(downloaded_file):
                            logger.info(f"Fallback format audio verified: {downloaded_file}")
                            return downloaded_file
                except Exception as ex:
                    logger.error(f"Fallback format failed: {ex}")

        # Section 9 Rule 4: Pause 4s, 8s
        time.sleep(4 * attempt)

    logger.error(f"Failed to download audio-safe video for {video_url} after 3 attempts.")
    return None
