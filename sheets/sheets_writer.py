"""
Append job-match results to a Google Sheet using gspread + a Service Account.

Prerequisites
-------------
1. Create a Google Cloud project and enable the **Google Sheets API**.
2. Create a Service Account → download the JSON key → save as
   ``service_account.json`` (or whatever ``config.GOOGLE_SERVICE_ACCOUNT_FILE`` points to).
3. Share the target Google Sheet with the Service Account email
   (``...@...iam.gserviceaccount.com``) giving it **Editor** access.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

import config

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADER_ROW = [
    "timestamp",
    "company",
    "title",
    "location",
    "similarity_score",
    "apply_url",
]


def _get_client() -> gspread.Client:
    """Authenticate and return a gspread client."""
    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=SCOPES,
    )
    return gspread.authorize(creds)


def _ensure_header(worksheet: gspread.Worksheet) -> None:
    """Add the header row if the sheet is empty."""
    existing = worksheet.row_values(1)
    if not existing:
        worksheet.append_row(HEADER_ROW, value_input_option="USER_ENTERED")
        logger.info("Wrote header row to sheet.")


def write_matches(matches: list[dict[str, Any]]) -> int:
    """
    Append matched jobs to the configured Google Sheet.

    Parameters
    ----------
    matches : list[dict]
        Each dict must contain keys that map to ``HEADER_ROW``.

    Returns
    -------
    int
        The number of rows appended.
    """
    if not matches:
        logger.info("No matches to write — skipping Sheets update.")
        return 0

    client = _get_client()

    try:
        sheet = client.open(config.GOOGLE_SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        logger.error(
            "Spreadsheet '%s' not found. "
            "Make sure it exists and is shared with the service account.",
            config.GOOGLE_SHEET_NAME,
        )
        raise

    worksheet = sheet.sheet1  # first tab
    _ensure_header(worksheet)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    rows: list[list[str]] = []
    for m in matches:
        rows.append([
            now,
            m.get("company", ""),
            m.get("title", ""),
            m.get("location", ""),
            str(m.get("similarity_score", "")),
            m.get("apply_url", ""),
        ])

    # Batch append for efficiency
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")
    logger.info("Appended %d rows to '%s'.", len(rows), config.GOOGLE_SHEET_NAME)
    return len(rows)
