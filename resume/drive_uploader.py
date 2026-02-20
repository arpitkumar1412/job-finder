"""
Upload tailored resume PDFs to Google Drive using OAuth2 user credentials.

On the first run the user is prompted to authorize via a browser.  The
refresh token is persisted to ``drive_token.json`` so subsequent runs
are non-interactive.

Folder structure on Drive
-------------------------
    Job Resumes/            ← DRIVE_ROOT_FOLDER_ID (pre-created, shared)
        airbnb/
            airbnb_12345.pdf
        stripe/
            stripe_67890.pdf

Each PDF is made publicly readable ("anyone with link") so the URL
can be pasted straight into the Google Sheet.
"""

from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CLIENT_SECRET_FILE = "client_secret.json"
TOKEN_FILE = "drive_token.json"


def _get_drive_service():
    """Authenticate via OAuth2 and return a Google Drive v3 service."""
    creds: Credentials | None = None

    # Load cached token
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # Refresh or run full auth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRET_FILE, SCOPES,
            )
            creds = flow.run_local_server(port=0)

        # Persist for next run
        Path(TOKEN_FILE).write_text(creds.to_json(), encoding="utf-8")
        logger.info("Saved OAuth2 token to %s", TOKEN_FILE)

    return build("drive", "v3", credentials=creds)


def _find_folder(service, name: str, parent_id: str | None = None) -> str | None:
    """Find a folder by name (optionally under a parent). Returns folder ID or None."""
    q = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    results = service.files().list(q=q, fields="files(id, name)", pageSize=5).execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def _create_folder(service, name: str, parent_id: str | None = None) -> str:
    """Create a folder (optionally under a parent). Returns the new folder ID."""
    metadata: dict[str, Any] = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]
    folder = service.files().create(body=metadata, fields="id").execute()
    logger.info("Created Drive folder '%s' (id=%s)", name, folder["id"])
    return folder["id"]


def _ensure_folder(service, name: str, parent_id: str | None = None) -> str:
    """Return the ID of a folder, creating it if it doesn't exist."""
    existing = _find_folder(service, name, parent_id)
    if existing:
        return existing
    return _create_folder(service, name, parent_id)


def upload_pdf(
    pdf_bytes: bytes,
    job: dict[str, Any],
) -> tuple[str, str]:
    """
    Upload a PDF resume to Google Drive.

    Parameters
    ----------
    pdf_bytes : bytes
        The compiled PDF content.
    job : dict
        Must contain ``company`` and at least one of ``job_id`` /
        ``greenhouse_id`` / ``id``.

    Returns
    -------
    (file_id, web_link) : tuple[str, str]
        The Drive file ID and a shareable web link.
    """
    service = _get_drive_service()

    company = job.get("company", "unknown").strip().lower()
    job_id = job.get("job_id") or job.get("greenhouse_id") or job.get("id") or "no_id"

    # Use the pre-existing shared folder as root (owned by user, shared
    # with service account — avoids storage-quota error).
    root_id = config.DRIVE_ROOT_FOLDER_ID
    company_id = _ensure_folder(service, company, parent_id=root_id)

    filename = f"{company}_{job_id}.pdf"

    # Check if file already exists (overwrite by deleting old one)
    q = (
        f"name = '{filename}' and '{company_id}' in parents and trashed = false"
    )
    existing = service.files().list(q=q, fields="files(id)").execute().get("files", [])
    for f in existing:
        service.files().delete(fileId=f["id"]).execute()
        logger.info("Deleted existing Drive file %s", f["id"])

    # Upload
    media = MediaIoBaseUpload(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        resumable=False,
    )
    file_metadata = {
        "name": filename,
        "parents": [company_id],
    }
    uploaded = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id, webViewLink")
        .execute()
    )
    file_id = uploaded["id"]
    web_link = uploaded.get("webViewLink", "")

    # Make it readable by anyone with the link
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    # Re-fetch the web link (it may change after permission update)
    file_info = service.files().get(fileId=file_id, fields="webViewLink").execute()
    web_link = file_info.get("webViewLink", web_link)

    logger.info(
        "Uploaded %s to Drive (id=%s): %s",
        filename, file_id, web_link,
    )
    return file_id, web_link
