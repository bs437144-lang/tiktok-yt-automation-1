import os
import yaml
from typing import List, Dict, Any, Optional

ALLOWED_UPLOAD_MODES = {
    "popular_split",
    "short_only",
    "popular_only",
    "sequence",
    "split",
    "tiered_split",
    "dual",
    "longform_only",
    "trim_dual"
}

class ChannelConfig:
    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id")
        self.tiktok_username = data.get("tiktok_username", "").lstrip("@")
        self.tiktok_username_slot2 = data.get("tiktok_username_slot2", "").lstrip("@") if data.get("tiktok_username_slot2") else None
        self.youtube_channel_name = data.get("youtube_channel_name", "")
        self.owner_email = data.get("owner_email", "")
        self.google_credentials_file = data.get("google_credentials_file", f"credentials/{self.id}_client_secret.json")
        self.oauth_token_file = data.get("oauth_token_file", f"tokens/{self.id}_token.json")
        self.videos_per_day = data.get("videos_per_day", 2)
        self.description_footer = data.get("description_footer", "")
        self.default_tags = data.get("default_tags", ["Shorts", "TikTok", "Viral"])
        self.youtube_category_id = str(data.get("youtube_category_id", "22"))
        self.enabled = data.get("enabled", True)
        self.max_retry_days = data.get("max_retry_days", 7)
        self.shorts_max_seconds = data.get("shorts_max_seconds", 180)
        self.upload_mode = data.get("upload_mode", "popular_split")
        self.max_download_candidates = data.get("max_download_candidates", 20)
        self.slot_publish_times_utc = data.get("slot_publish_times_utc", {1: "22:00", 2: "00:00"})
        self.min_upload_date = data.get("min_upload_date")
        self.min_backlog_for_slot1 = data.get("min_backlog_for_slot1")
        self.fixed_title = data.get("fixed_title")

        self.validate()

    def validate(self):
        if not self.id:
            raise ValueError("Channel configuration must have a unique 'id'")
        if not self.tiktok_username:
            raise ValueError(f"Channel {self.id} must specify 'tiktok_username'")
        if self.upload_mode not in ALLOWED_UPLOAD_MODES:
            raise ValueError(f"Invalid upload_mode '{self.upload_mode}' for channel {self.id}. Must be one of {ALLOWED_UPLOAD_MODES}")
        if self.max_download_candidates < 10:
            # Rule from Section 9 & 15: Must be 15-20 to avoid failure cascades
            self.max_download_candidates = 20

def load_config(config_path: str = "channels.yaml") -> List[ChannelConfig]:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    if not data or "channels" not in data:
        raise ValueError("channels.yaml must contain a top-level 'channels' list")
    
    channels = [ChannelConfig(ch) for ch in data["channels"]]
    return channels

def get_channel_by_id(channel_id: str, config_path: str = "channels.yaml") -> Optional[ChannelConfig]:
    channels = load_config(config_path)
    for ch in channels:
        if ch.id == channel_id:
            return ch
    return None
