import os
import sys
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def reauth(channel_id: str):
    creds_path = f"credentials/{channel_id}_client_secret.json"
    token_path = f"tokens/{channel_id}_token.json"

    if not os.path.exists(creds_path):
        print(f"\n[ERROR] Credentials file not found at: {creds_path}")
        print(f"Please place your Google Cloud OAuth client secret JSON at {creds_path}\n")
        sys.exit(1)

    os.makedirs(os.path.dirname(os.path.abspath(token_path)), exist_ok=True)

    # InstalledAppFlow with manual code entry (no browser auto-open required)
    flow = InstalledAppFlow.from_client_secrets_file(
        creds_path,
        scopes=SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob" # Or localhost if supported
    )

    try:
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true"
        )
    except Exception:
        # Fallback if redirect_uri needs to be http://localhost
        flow = InstalledAppFlow.from_client_secrets_file(
            creds_path,
            scopes=SCOPES,
            redirect_uri="http://localhost"
        )
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true"
        )

    print("=" * 70)
    print(f"OAUTH AUTHORIZATION FOR: {channel_id}")
    print("=" * 70)
    print("\n1. Open this URL in your web browser (logged in as the channel's Gmail):")
    print(f"\n{auth_url}\n")
    print("2. Click 'Advanced' -> 'Go to app (unsafe)' -> 'Allow / Continue'.")
    print("3. Copy the authorization code from the browser window/URL and paste it below:\n")

    code = input("Enter Authorization Code: ").strip()
    if not code:
        print("[ERROR] No code entered.")
        sys.exit(1)

    flow.fetch_token(code=code)
    creds = flow.credentials

    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print(f"\n[SUCCESS] Token successfully minted and saved to: {token_path}")
    print("Refresh token is present:", bool(creds.refresh_token))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python reauth_nobrowser.py <channel_id>")
        print("Example: python reauth_nobrowser.py channel_1")
        sys.exit(1)
    
    reauth(sys.argv[1])
