"""
Read job-match data from a Google Sheet for auto-apply.

Reads rows marked as "APPLY" that have a resume uploaded (resume_id present)
and have not yet been applied to (application_status is empty).
"""

from __future__ import annotations

import logging
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_client() -> gspread.Client:
    """Authenticate and return a gspread client."""
    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


def read_apply_jobs() -> list[dict[str, Any]]:
    """
    Read rows from the Google Sheet that are ready for auto-apply.

    A row is eligible if:
    - recommendation == "APPLY"
    - apply_url is non-empty
    - resume_id is non-empty (resume has been uploaded to Drive)
    - application_status is empty (not yet applied)

    Returns
    -------
    list[dict]
        Each dict contains keys matching the sheet header row.
    """
    client = _get_client()

    try:
        sheet = client.open(config.GOOGLE_SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        logger.error(
            "Spreadsheet '%s' not found. "
            "Make sure it exists and is shared with the service account.",
            config.GOOGLE_SHEET_NAME,
        )
        return []

    worksheet = sheet.sheet1
    all_records = worksheet.get_all_records()

    if not all_records:
        logger.info("No data rows found in sheet.")
        return []

    eligible: list[dict[str, Any]] = []
    for i, row in enumerate(all_records):
        recommendation = str(row.get("recommendation", "")).strip().upper()
        apply_url = str(row.get("apply_url", "")).strip()
        resume_id = str(row.get("resume_id", "")).strip()
        status = str(row.get("application_status", "")).strip()

        if (
            recommendation == "APPLY"
            and apply_url
            and resume_id
            and not status
        ):
            row["_sheet_row_index"] = i + 2  # +2: 1-indexed + header row
            eligible.append(row)

    logger.info(
        "Found %d eligible jobs for auto-apply (out of %d total rows).",
        len(eligible),
        len(all_records),
    )
    return eligible


def _detect_source(apply_url: str) -> str:
    """Detect the ATS source from the apply URL by checking the hostname."""
    from urllib.parse import urlparse

    try:
        hostname = urlparse(apply_url).hostname or ""
    except Exception:
        return "unknown"

    # Split hostname into parts and check the registered domain
    parts = hostname.split(".")
    if len(parts) >= 2:
        registered_domain = ".".join(parts[-2:])
        if registered_domain == "greenhouse.io":
            return "greenhouse"
        if registered_domain == "lever.co":
            return "lever"
    return "unknown"
