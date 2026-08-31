import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.init_tables()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_tables(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS posted_videos (
                    tiktok_id TEXT PRIMARY KEY,
                    youtube_video_id TEXT,
                    title TEXT,
                    posted_at TEXT,
                    status TEXT NOT NULL, -- uploaded, failed_permanent, skipped, pending_retry
                    retry_count INTEGER DEFAULT 0,
                    next_retry_date TEXT,
                    view_count INTEGER DEFAULT 0,
                    duration REAL DEFAULT 0,
                    slot INTEGER,
                    last_error TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL,
                    slot INTEGER NOT NULL,
                    run_date TEXT NOT NULL, -- YYYY-MM-DD (UTC)
                    status TEXT NOT NULL, -- success, skipped, no_content, failed
                    video_id TEXT,
                    started_at TEXT,
                    finished_at TEXT,
                    error_message TEXT
                )
            """)
            conn.commit()

    def checkpoint_wal(self):
        try:
            with self._get_connection() as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass

    def is_slot_already_ran_today(self, channel_id: str, slot: int, date_utc: Optional[str] = None) -> bool:
        if not date_utc:
            date_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id FROM runs 
                WHERE channel_id = ? AND slot = ? AND run_date = ? AND status = 'success'
                LIMIT 1
            """, (channel_id, slot, date_utc))
            return cursor.fetchone() is not None

    def record_run(self, channel_id: str, slot: int, status: str, video_id: Optional[str] = None, 
                   started_at: Optional[str] = None, finished_at: Optional[str] = None, 
                   error_message: Optional[str] = None, date_utc: Optional[str] = None):
        if not date_utc:
            date_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if not started_at:
            started_at = datetime.now(timezone.utc).isoformat()
        if not finished_at:
            finished_at = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO runs (channel_id, slot, run_date, status, video_id, started_at, finished_at, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (channel_id, slot, date_utc, status, video_id, started_at, finished_at, error_message))
            conn.commit()

    def get_posted_video_ids(self) -> set:
        """Returns set of all tiktok_ids that shouldn't be picked fresh."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tiktok_id FROM posted_videos")
            return {row["tiktok_id"] for row in cursor.fetchall()}

    def get_pending_retries_due_today(self, date_utc: Optional[str] = None) -> List[Dict[str, Any]]:
        if not date_utc:
            date_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM posted_videos 
                WHERE status = 'pending_retry' AND (next_retry_date <= ? OR next_retry_date IS NULL)
                ORDER BY retry_count ASC, posted_at ASC
            """, (date_utc,))
            return [dict(row) for row in cursor.fetchall()]

    def record_posted_video(self, tiktok_id: str, youtube_video_id: Optional[str], title: str, 
                             status: str, slot: int, view_count: int = 0, duration: float = 0.0, 
                             last_error: Optional[str] = None, max_retry_days: int = 7):
        now_iso = datetime.now(timezone.utc).isoformat()
        today_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT retry_count FROM posted_videos WHERE tiktok_id = ?", (tiktok_id,))
            row = cursor.fetchone()

            if row:
                current_retry = row["retry_count"] + 1
                if status == "pending_retry" and current_retry >= max_retry_days:
                    status = "failed_permanent"
                cursor.execute("""
                    UPDATE posted_videos 
                    SET youtube_video_id = COALESCE(?, youtube_video_id),
                        title = ?,
                        posted_at = ?,
                        status = ?,
                        retry_count = ?,
                        next_retry_date = ?,
                        view_count = ?,
                        duration = ?,
                        slot = ?,
                        last_error = ?
                    WHERE tiktok_id = ?
                """, (youtube_video_id, title, now_iso, status, current_retry, today_date, view_count, duration, slot, last_error, tiktok_id))
            else:
                retry_count = 1 if status == "pending_retry" else 0
                cursor.execute("""
                    INSERT INTO posted_videos (tiktok_id, youtube_video_id, title, posted_at, status, retry_count, next_retry_date, view_count, duration, slot, last_error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (tiktok_id, youtube_video_id, title, now_iso, status, retry_count, today_date, view_count, duration, slot, last_error))
            conn.commit()
