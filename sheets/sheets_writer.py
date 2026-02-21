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
    "role_score",
    "recommendation",
    "role_type",
    "backend_relevance",
    "title_relevance",
    "seniority_match",
    "tech_stack_match",
    "penalty",
    "reason",
    "apply_url",
    "resume_id",
    "resume_link",
    "application_status",
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


def clear_sheet() -> None:
    """Remove all data rows (keep nothing — header will be re-added)."""
    client = _get_client()
    try:
        sheet = client.open(config.GOOGLE_SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        return
    ws = sheet.sheet1
    ws.clear()
    logger.info("Cleared all rows from '%s'.", config.GOOGLE_SHEET_NAME)


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
            str(m.get("role_score", "")),
            m.get("recommendation", ""),
            m.get("role_type", ""),
            str(m.get("backend_relevance", "")),
            str(m.get("title_relevance", "")),
            str(m.get("seniority_match", "")),
            str(m.get("tech_stack_match", "")),
            str(m.get("penalty", "")),
            m.get("match_reasons", ""),
            m.get("apply_url", ""),
            m.get("resume_id", ""),
            m.get("resume_link", ""),
            m.get("application_status", ""),
        ])

    # Batch append for efficiency
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")
    logger.info("Appended %d rows to '%s'.", len(rows), config.GOOGLE_SHEET_NAME)
    return len(rows)


def update_application_status(row_index: int, status: str) -> None:
    """
    Update the application_status cell for a specific row.

    Parameters
    ----------
    row_index : int
        The 1-based row number in the sheet.
    status : str
        The status string to write (e.g. "APPLIED", "FAILED").
    """
    client = _get_client()

    try:
        sheet = client.open(config.GOOGLE_SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        logger.error(
            "Spreadsheet '%s' not found.", config.GOOGLE_SHEET_NAME,
        )
        return

    worksheet = sheet.sheet1

    # Find the column index for application_status
    header = worksheet.row_values(1)
    try:
        col_index = header.index("application_status") + 1  # 1-based
    except ValueError:
        # Column doesn't exist yet — append it to the header
        col_index = len(header) + 1
        worksheet.update_cell(1, col_index, "application_status")
        logger.info("Added 'application_status' column at position %d.", col_index)

    worksheet.update_cell(row_index, col_index, status)
    logger.info(
        "Updated row %d application_status to '%s'.", row_index, status,
    )
