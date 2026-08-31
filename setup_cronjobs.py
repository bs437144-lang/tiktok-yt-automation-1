import time
import requests
from typing import Dict, Any

def create_cron_job(api_key: str, title: str, target_url: str, github_pat: str, hours: int, minutes: int):
    """
    Creates a cron job on cron-job.org calling GitHub Actions workflow_dispatch.
    """
    url = "https://api.cron-job.org/jobs"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "job": {
            "title": title,
            "url": target_url,
            "enabled": True,
            "saveResponses": True,
            "schedule": {
                "timezone": "UTC",
                "expiresAt": 0,
                "hours": [hours],
                "minutes": [minutes],
                "mdays": [-1],
                "months": [-1],
                "wdays": [-1]
            },
            "requestMethod": 1, # POST
            "requestHeaders": {
                "Accept": "application/vnd.github.v3+json",
                "Authorization": f"token {github_pat}",
                "Content-Type": "application/json",
                "User-Agent": "cron-job.org"
            },
            "requestBody": '{"ref":"main"}'
        }
    }

    resp = requests.put(url, headers=headers, json=payload)
    if resp.status_code in (200, 201):
        print(f"[OK] Created cron job: '{title}' ({hours:02d}:{minutes:02d} UTC)")
    else:
        print(f"[ERROR] Failed to create job '{title}': {resp.status_code} {resp.text}")
    
    # Section 7: Pause 15s between calls to prevent 429 rate-limiting
    time.sleep(15)
