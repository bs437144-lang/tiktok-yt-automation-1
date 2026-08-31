import os
import sys
import base64
import requests
from nacl import encoding, public

def encrypt_secret(public_key_b64: str, secret_value: str) -> str:
    """Encrypt a secret value using GitHub repository public key (libSodium SealedBox)."""
    public_key = public.PublicKey(public_key_b64.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")

def set_github_secret(github_pat: str, owner: str, repo: str, secret_name: str, secret_value: str):
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {github_pat}"
    }

    # 1. Get Repo Public Key
    key_url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/public-key"
    r = requests.get(key_url, headers=headers)
    if r.status_code != 200:
        raise Exception(f"Failed to fetch public key for {owner}/{repo}: {r.status_code} {r.text}")
    
    key_data = r.json()
    key_id = key_data["key_id"]
    public_key_b64 = key_data["key"]

    # 2. Encrypt Secret
    encrypted_value = encrypt_secret(public_key_b64, secret_value)

    # 3. Put Secret
    put_url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/{secret_name}"
    payload = {
        "encrypted_value": encrypted_value,
        "key_id": key_id
    }
    r = requests.put(put_url, headers=headers, json=payload)
    if r.status_code in (201, 204):
        print(f"[OK] Secret '{secret_name}' successfully set on GitHub!")
    else:
        print(f"[ERROR] Failed to set secret '{secret_name}': {r.status_code} {r.text}")

def file_to_b64(filepath: str) -> str:
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

if __name__ == "__main__":
    print("GitHub Secrets Helper")
    print("Run this to auto-upload credentials/tokens to GitHub Actions.")
