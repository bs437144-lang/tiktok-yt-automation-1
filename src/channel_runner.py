import os
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from src.config import ChannelConfig
from src.db import Database
from src.tiktok_downloader import list_profile_videos, download_video
from src.youtube_uploader import YouTubeUploader, YouTubeAccountSuspendedError
from src.notifier import send_discord_notification

logger = logging.getLogger("channel_runner")

class ChannelRunner:
    def __init__(self, config: ChannelConfig, db: Database, dry_run: bool = False):
        self.config = config
        self.db = db
        self.dry_run = dry_run
        self.uploader = None

    def _get_uploader(self) -> YouTubeUploader:
        if self.uploader is None and not self.dry_run:
            self.uploader = YouTubeUploader(
                self.config.google_credentials_file,
                self.config.oauth_token_file
            )
        return self.uploader

    def pick_video_candidate(self, slot: int) -> List[Dict[str, Any]]:
        """
        Picks candidates based on channel upload_mode and slot.
        Prioritizes pending retries due today.
        """
        posted_ids = self.db.get_posted_video_ids()
        
        # 1. Check pending retries due today
        pending = self.db.get_pending_retries_due_today()
        if pending:
            logger.info(f"Found {len(pending)} pending retries due today. Prioritizing retry queue.")
            return pending

        # Determine target TikTok handle (handle slot 2 secondary account)
        target_username = self.config.tiktok_username
        if slot == 2 and self.config.tiktok_username_slot2:
            target_username = self.config.tiktok_username_slot2
            logger.info(f"Slot 2: Fetching from secondary profile @{target_username}")

        cookies_file = os.environ.get("TIKTOK_COOKIES_FILE", "cookies.txt")
        if not os.path.exists(cookies_file):
            cookies_file = None

        videos = list_profile_videos(target_username, cookiefile=cookies_file, max_entries=150)
        
        # If secondary account has no videos, fallback to primary (Section 6)
        if not videos and slot == 2 and self.config.tiktok_username_slot2:
            logger.info(f"Secondary @{target_username} exhausted/empty. Falling back to primary @{self.config.tiktok_username}")
            target_username = self.config.tiktok_username
            videos = list_profile_videos(target_username, cookiefile=cookies_file, max_entries=150)

        # Filter out already posted videos
        unposted = [v for v in videos if v["id"] not in posted_ids]
        logger.info(f"Profile @{target_username} has {len(unposted)} unposted videos out of {len(videos)} listed.")

        if not unposted:
            return []

        mode = self.config.upload_mode

        if mode == "popular_split":
            if slot == 1:
                # Slot 1: Newest unposted (default listing is newest first)
                return unposted
            else:
                # Slot 2: Most-viewed unposted
                return sorted(unposted, key=lambda x: int(x.get("view_count") or 0), reverse=True)

        elif mode == "short_only":
            return unposted

        elif mode == "popular_only":
            return sorted(unposted, key=lambda x: int(x.get("view_count") or 0), reverse=True)

        return unposted

    def run_slot(self, slot: int) -> Dict[str, Any]:
        started_at = datetime.now(timezone.utc).isoformat()
        date_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        logger.info(f"--- Running Channel '{self.config.id}' Slot {slot} (Date UTC: {date_utc}, Dry Run: {self.dry_run}) ---")

        # 1. Per-Day Slot Guard (Section 3 & 7)
        if not self.dry_run and self.db.is_slot_already_ran_today(self.config.id, slot, date_utc):
            logger.info(f"Slot {slot} for channel '{self.config.id}' already succeeded today. Skipping run.")
            self.db.record_run(self.config.id, slot, "skipped", started_at=started_at, date_utc=date_utc)
            return {"status": "skipped", "message": "Slot already ran successfully today"}

        # 2. Pick candidate videos
        candidates = self.pick_video_candidate(slot)
        if not candidates:
            logger.warning(f"No unposted content found for channel '{self.config.id}'.")
            self.db.record_run(self.config.id, slot, "no_content", started_at=started_at, date_utc=date_utc)
            send_discord_notification(
                os.environ.get("DISCORD_WEBHOOK_URL"),
                title=f"⚠️ No Content: {self.config.id} (Slot {slot})",
                description="Profile has no new videos to post (Content Exhaustion).",
                status="no_content",
                fields={"Channel": self.config.id, "Slot": slot, "Date": date_utc}
            )
            return {"status": "no_content"}

        # 3. Candidate loop up to max_download_candidates (15-20)
        max_candidates = min(len(candidates), self.config.max_download_candidates)
        downloaded_file = None
        chosen_video = None
        cookies_file = os.environ.get("TIKTOK_COOKIES_FILE", "cookies.txt")
        if not os.path.exists(cookies_file):
            cookies_file = None

        for idx in range(max_candidates):
            candidate = candidates[idx]
            video_url = candidate.get("url") or f"https://www.tiktok.com/@{self.config.tiktok_username}/video/{candidate['id']}"
            logger.info(f"Trying candidate [{idx+1}/{max_candidates}]: {candidate['id']} - {candidate.get('title', '')[:40]}")
            
            downloaded_file = download_video(video_url, output_dir="downloads", cookiefile=cookies_file)
            if downloaded_file:
                chosen_video = candidate
                break
            else:
                logger.warning(f"Candidate {candidate['id']} failed download or audio check. Queuing for retry tomorrow.")
                if not self.dry_run:
                    self.db.record_posted_video(
                        tiktok_id=candidate["id"],
                        youtube_video_id=None,
                        title=candidate.get("title", ""),
                        status="pending_retry",
                        slot=slot,
                        view_count=candidate.get("view_count", 0),
                        duration=candidate.get("duration", 0.0),
                        last_error="Download/audio check failed",
                        max_retry_days=self.config.max_retry_days
                    )

        if not downloaded_file or not chosen_video:
            error_msg = f"Failed to download any of the {max_candidates} candidates."
            logger.error(error_msg)
            self.db.record_run(self.config.id, slot, "failed", error_message=error_msg, started_at=started_at, date_utc=date_utc)
            send_discord_notification(
                os.environ.get("DISCORD_WEBHOOK_URL"),
                title=f"❌ Upload Failed: {self.config.id} (Slot {slot})",
                description=error_msg,
                status="failed",
                fields={"Channel": self.config.id, "Slot": slot, "Candidates Tried": max_candidates}
            )
            return {"status": "failed", "error": error_msg}

        # 4. Upload to YouTube
        video_title = self.config.fixed_title or chosen_video.get("title") or "TikTok Short"
        description = f"{video_title}\n\n{self.config.description_footer}".strip()

        if self.dry_run:
            logger.info(f"[DRY-RUN] Would upload {downloaded_file} as YouTube Short:")
            logger.info(f"  Title: {video_title}")
            logger.info(f"  Category: {self.config.youtube_category_id}")
            logger.info(f"  Tags: {self.config.default_tags}")
            yt_id = "DRY_RUN_ID"
        else:
            try:
                uploader = self._get_uploader()
                yt_id = uploader.upload_short(
                    video_path=downloaded_file,
                    title=video_title,
                    description=description,
                    tags=self.config.default_tags,
                    category_id=self.config.youtube_category_id
                )
            except YouTubeAccountSuspendedError as se:
                self.db.record_run(self.config.id, slot, "failed", error_message=str(se), started_at=started_at, date_utc=date_utc)
                send_discord_notification(
                    os.environ.get("DISCORD_WEBHOOK_URL"),
                    title=f"🚨 ACCOUNT TERMINATED: {self.config.id}",
                    description=str(se),
                    status="failed"
                )
                return {"status": "failed", "error": str(se)}
            except Exception as e:
                error_msg = f"Upload error: {e}"
                logger.error(error_msg)
                self.db.record_run(self.config.id, slot, "failed", error_message=error_msg, started_at=started_at, date_utc=date_utc)
                send_discord_notification(
                    os.environ.get("DISCORD_WEBHOOK_URL"),
                    title=f"❌ Upload Failed: {self.config.id} (Slot {slot})",
                    description=error_msg,
                    status="failed"
                )
                return {"status": "failed", "error": error_msg}

        # Clean up local scratch video
        try:
            if os.path.exists(downloaded_file):
                os.remove(downloaded_file)
        except Exception:
            pass

        # 5. Record Success in DB
        if not self.dry_run:
            self.db.record_posted_video(
                tiktok_id=chosen_video["id"],
                youtube_video_id=yt_id,
                title=video_title,
                status="uploaded",
                slot=slot,
                view_count=chosen_video.get("view_count", 0),
                duration=chosen_video.get("duration", 0.0)
            )
            self.db.record_run(
                self.config.id,
                slot,
                "success",
                video_id=yt_id,
                started_at=started_at,
                date_utc=date_utc
            )

        send_discord_notification(
            os.environ.get("DISCORD_WEBHOOK_URL"),
            title=f"✅ Short Uploaded: {self.config.id} (Slot {slot})",
            description=f"**Title:** {video_title}\n**URL:** https://youtu.be/{yt_id}",
            status="success",
            fields={
                "TikTok ID": chosen_video["id"],
                "YouTube ID": yt_id,
                "Mode": self.config.upload_mode,
                "Views": chosen_video.get("view_count", 0)
            }
        )

        return {"status": "success", "video_id": yt_id}
