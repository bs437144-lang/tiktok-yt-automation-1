import os
import json
import logging
from typing import List, Optional, Dict, Any
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger("youtube_uploader")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

class YouTubeAccountSuspendedError(Exception):
    pass

class YouTubeUploader:
    def __init__(self, credentials_file: str, token_file: str):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.youtube = self._get_authenticated_service()

    def _get_authenticated_service(self):
        creds = None
        if os.path.exists(self.token_file):
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            except Exception as e:
                logger.error(f"Error loading credentials from {self.token_file}: {e}")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired OAuth token...")
                creds.refresh(Request())
                os.makedirs(os.path.dirname(os.path.abspath(self.token_file)), exist_ok=True)
                with open(self.token_file, "w", encoding="utf-8") as token:
                    token.write(creds.to_json())
            else:
                raise FileNotFoundError(
                    f"Valid OAuth token not found at {self.token_file}. "
                    f"Please run 'reauth_nobrowser.py' to generate token first."
                )

        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    def upload_short(self, video_path: str, title: str, description: str = "", 
                     tags: Optional[List[str]] = None, category_id: str = "22") -> Optional[str]:
        """
        Uploads a video as a YouTube Short (public, not made for kids).
        Returns the uploaded YouTube Video ID.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found at {video_path}")

        # Clean title for YouTube (max 100 characters)
        clean_title = title.strip()
        if not clean_title:
            clean_title = "Shorts Video #shorts"
        if "#shorts" not in clean_title.lower() and "#short" not in clean_title.lower():
            if len(clean_title) <= 92:
                clean_title = f"{clean_title} #shorts"
        clean_title = clean_title[:100]

        if tags is None:
            tags = []
        if "Shorts" not in tags:
            tags.append("Shorts")
        if "shorts" not in tags:
            tags.append("shorts")

        body = {
            "snippet": {
                "title": clean_title,
                "description": description.strip(),
                "tags": tags,
                "categoryId": category_id
            },
            "status": {
                "privacyStatus": "public", # Section 7: uploaded directly as public
                "selfDeclaredMadeForKids": False,
            }
        }

        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024 * 4 # 4MB chunk size
        )

        logger.info(f"Initiating YouTube upload for '{clean_title}'...")
        try:
            request = self.youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"Upload progress: {int(status.progress() * 100)}%")

            video_id = response.get("id")
            logger.info(f"Upload successful! Video ID: {video_id} (https://youtu.be/{video_id})")
            return video_id

        except HttpError as e:
            if "authenticatedUserAccountSuspended" in str(e) or e.resp.status == 403:
                logger.critical(f"FATAL: YouTube channel account is suspended / terminated! {e}")
                raise YouTubeAccountSuspendedError(f"Channel suspended: {e}")
            logger.error(f"YouTube upload failed with HttpError: {e}")
            raise e
        except Exception as e:
            logger.error(f"Unexpected error during YouTube upload: {e}")
            raise e
