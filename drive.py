"""Google OAuth 2.0 + Drive API helpers for PhotoSort.

Photos are downloaded into memory only, long enough to analyze them,
and are never written to disk on the server. OAuth client secrets and
user tokens are never hard-coded here — they're loaded from
Streamlit Secrets (or environment variables for local dev). See
README.md for setup instructions.
"""
import os
import re
from typing import Dict, List, Optional

import streamlit as st
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

# Read-only is all PhotoSort needs — it never edits or deletes anything
# in the user's Drive.
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

IMAGE_MIME_TYPES = [
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/tiff",
    "image/bmp",
]


def _get_client_config():
    """Load the OAuth client config from Streamlit Secrets, falling
    back to environment variables for local scripts/tests.

    Expected in .streamlit/secrets.toml:

        [google_oauth]
        client_id = "xxxx.apps.googleusercontent.com"
        client_secret = "xxxx"
        redirect_uri = "http://localhost:8501"
    """
    client_id = client_secret = redirect_uri = ""
    try:
        conf = st.secrets["google_oauth"]
        client_id = conf.get("client_id", "")
        client_secret = conf.get("client_secret", "")
        redirect_uri = conf.get("redirect_uri", "http://localhost:8501")
    except Exception:
        pass

    if not client_id:
        client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost:8501")

    config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }
    return config, redirect_uri


def is_configured() -> bool:
    """Whether OAuth client credentials have been set up at all."""
    config, _ = _get_client_config()
    return bool(config["web"]["client_id"] and config["web"]["client_secret"])


def get_authorization_url(state: Optional[str] = None) -> str:
    """Build the Google consent-screen URL the user clicks to sign in.

    `state` round-trips through Google and comes back on the redirect —
    used here to carry the pasted folder ID across the OAuth hop, since
    a full-page redirect to Google and back can lose session_state.
    """
    config, redirect_uri = _get_client_config()
    flow = Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redirect_uri)
    kwargs = {
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
    }
    if state:
        kwargs["state"] = state
    auth_url, _ = flow.authorization_url(**kwargs)
    return auth_url


def exchange_code_for_credentials(code: str) -> Credentials:
    """Exchange the ?code= param Google redirected back with for tokens."""
    config, redirect_uri = _get_client_config()
    flow = Flow.from_client_config(config, scopes=SCOPES, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    return flow.credentials


def credentials_to_dict(creds: Credentials) -> Dict:
    """Serialize credentials so they can be kept in st.session_state.

    This lives only in server memory for the duration of the session —
    it is never written to disk or committed anywhere.
    """
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    }


def credentials_from_dict(data: Dict) -> Credentials:
    return Credentials(**data)


def refresh_if_needed(creds: Credentials) -> Credentials:
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def build_service(creds: Credentials):
    return build("drive", "v3", credentials=creds)


# Matches a bare Drive file/folder ID (no slashes, Drive IDs run 25+ chars).
_BARE_ID_PATTERN = re.compile(r"^[-\w]{15,}$")


def extract_folder_id(text: str) -> Optional[str]:
    """Pull a Drive folder ID out of a pasted folder link.

    Accepts full share links like
    https://drive.google.com/drive/folders/<id>?usp=sharing,
    the u/0/ variant, an ?id=<id> style link, or a bare folder ID.
    Returns None if nothing that looks like a folder ID is found.
    """
    if not text:
        return None
    text = text.strip()

    match = re.search(r"/folders/([-\w]+)", text)
    if match:
        return match.group(1)

    match = re.search(r"[?&]id=([-\w]+)", text)
    if match:
        return match.group(1)

    if _BARE_ID_PATTERN.match(text):
        return text

    return None


def get_folder_name(service, folder_id: str) -> str:
    """Look up a folder's display name, for showing in the results header."""
    meta = service.files().get(fileId=folder_id, fields="name").execute()
    return meta.get("name", folder_id)


def list_images_in_folder(service, folder_id: str) -> List[Dict]:
    """List every image file directly inside a given Drive folder."""
    mime_query = " or ".join(f"mimeType = '{m}'" for m in IMAGE_MIME_TYPES)
    q = f"'{folder_id}' in parents and trashed = false and ({mime_query})"

    files: List[Dict] = []
    page_token = None
    while True:
        result = service.files().list(
            q=q,
            spaces="drive",
            fields="nextPageToken, files(id, name, mimeType, size, webViewLink)",
            pageSize=100,
            pageToken=page_token,
        ).execute()
        files.extend(result.get("files", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return files


def download_image_bytes(service, file_id: str) -> bytes:
    """Download one Drive file's bytes into memory (never to disk)."""
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()
