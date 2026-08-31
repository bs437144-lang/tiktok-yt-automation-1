import os
import requests
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("notifier")

def send_discord_notification(webhook_url: Optional[str], title: str, description: str, 
                              status: str = "info", fields: Optional[Dict[str, Any]] = None):
    if not webhook_url:
        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    
    if not webhook_url:
        logger.warning("No Discord Webhook URL provided. Skipping notification.")
        return

    color_map = {
        "success": 0x2ECC71,  # Green
        "skipped": 0xF1C40F,  # Yellow
        "no_content": 0xE67E22,# Orange
        "failed": 0xE74C3C,   # Red
        "info": 0x3498DB       # Blue
    }

    embed_fields = []
    if fields:
        for k, v in fields.items():
            embed_fields.append({
                "name": str(k),
                "value": str(v) if str(v) else "N/A",
                "inline": True
            })

    payload = {
        "username": "TikTok-YT Automation",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/1384/1384060.png",
        "embeds": [{
            "title": title,
            "description": description,
            "color": color_map.get(status, 0x3498DB),
            "fields": embed_fields,
            "footer": {
                "text": "Serverless GitHub Actions Runner"
            }
        }]
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code not in (200, 204):
            logger.warning(f"Discord notification returned status {resp.status_code}: {resp.text}")
    except Exception as e:
        logger.error(f"Failed to send Discord webhook: {e}")
