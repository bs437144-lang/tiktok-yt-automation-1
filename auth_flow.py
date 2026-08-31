import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

def authenticate():
    creds_path = "credentials/channel_1_client_secret.json"
    token_path = "tokens/channel_1_token.json"
    
    flow = InstalledAppFlow.from_client_secrets_file(
        creds_path,
        scopes=SCOPES
    )
    
    print("\nStarting local server on port 8080 and launching browser...")
    creds = flow.run_local_server(port=8080, open_browser=True)
    
    os.makedirs("tokens", exist_ok=True)
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    
    print("\n[SUCCESS] Token successfully minted and saved!")
    print(f"Has refresh_token: {bool(creds.refresh_token)}")

if __name__ == "__main__":
    authenticate()
