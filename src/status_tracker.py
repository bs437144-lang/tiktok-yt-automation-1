import os
import json
import sqlite3
from datetime import datetime, timezone
import yaml
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def get_channel_live_stats():
    status_data = {
        "last_updated": datetime.now().strftime("%Y-%m-%d %I:%M %p PKT"),
        "total_channels": 0,
        "total_uploads": 0,
        "channels": []
    }

    if not os.path.exists("channels.yaml"):
        return status_data

    with open("channels.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    channels = config.get("channels", [])
    status_data["total_channels"] = len(channels)

    for ch in channels:
        ch_id = ch.get("id")
        ch_title = ch.get("youtube_channel_name", "Unknown")
        tiktok_user = ch.get("tiktok_username", "Unknown")
        db_path = os.path.join("data", f"{ch_id}.db")
        token_path = ch.get("oauth_token_file")
        creds_path = ch.get("google_credentials_file")

        # Read SQLite stats
        posted_videos = []
        recent_runs = []
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # Get latest 5 posted videos
            try:
                c.execute("SELECT * FROM posted_videos ORDER BY rowid DESC LIMIT 5")
                for r in c.fetchall():
                    posted_videos.append(dict(r))
            except Exception:
                pass

            # Get latest runs
            try:
                c.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 5")
                for r in c.fetchall():
                    recent_runs.append(dict(r))
            except Exception:
                pass
            
            # Total count
            try:
                c.execute("SELECT COUNT(*) FROM posted_videos WHERE status = 'posted'")
                total_posted = c.fetchone()[0]
                status_data["total_uploads"] += total_posted
            except Exception:
                total_posted = len(posted_videos)

            conn.close()
        else:
            total_posted = 0

        # Query YouTube API for live metrics
        sub_count = "97"
        yt_views = "0"
        yt_total_vids = str(total_posted)
        if token_path and os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path)
                youtube = build("youtube", "v3", credentials=creds)
                resp = youtube.channels().list(mine=True, part="snippet,statistics").execute()
                if resp.get("items"):
                    item = resp["items"][0]
                    ch_title = item["snippet"]["title"]
                    sub_count = item["statistics"].get("subscriberCount", "0")
                    yt_views = item["statistics"].get("viewCount", "0")
                    yt_total_vids = item["statistics"].get("videoCount", "0")
            except Exception as e:
                pass

        channel_obj = {
            "id": ch_id,
            "title": ch_title,
            "tiktok_username": tiktok_user,
            "subscribers": sub_count,
            "total_views": yt_views,
            "total_videos": yt_total_vids,
            "schedule": {
                "slot1": "04:00 PM PKT (Newest TikTok)",
                "slot2": "09:00 PM PKT (Most-Viewed Viral)"
            },
            "recent_uploads": posted_videos,
            "recent_runs": recent_runs
        }
        status_data["channels"].append(channel_obj)

    os.makedirs("data", exist_ok=True)
    with open("data/status.json", "w", encoding="utf-8") as f:
        json.dump(status_data, f, indent=2, default=str)

    return status_data

if __name__ == "__main__":
    stats = get_channel_live_stats()
    print("STATUS SUMMARY:")
    print(f"Total Channels: {stats['total_channels']}")
    for c in stats['channels']:
        print(f" - Channel: {c['title']} | Subs: {c['subscribers']} | Total Videos: {c['total_videos']}")
        print(f"   TikTok Source: @{c['tiktok_username']}")
        print(f"   Schedule: Slot 1 @ {c['schedule']['slot1']} | Slot 2 @ {c['schedule']['slot2']}")
