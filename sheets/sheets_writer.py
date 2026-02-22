"""
Append job-match results to a Google Sheet using gspread + a Service Account.

Prerequisites
-------------
1. Create a Google Cloud project and enable the **Google Sheets API**.
2. Create a Service Account → download the JSON key → save as
   ``service_account.json`` (or whatever ``config.GOOGLE_SERVICE_ACCOUNT_FILE`` points to).
3. Share the target Google Sheet with the Service Account email
   (``...@...iam.gserviceaccount.com``) giving it **Editor** access.

Pull tracking
-------------
A hidden tab named ``_pull_metadata`` stores the timestamp of the last pull
and all previously seen job IDs so that each run only writes *new* postings.
Every run creates a fresh tab titled with the run's date and time.
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

# Tab used to persist pull timestamps and seen job IDs across runs.
METADATA_TAB_NAME = "_pull_metadata"

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


def _get_or_create_worksheet(
    sheet: gspread.Spreadsheet, title: str
) -> gspread.Worksheet:
    """Return the worksheet *title*, creating it if it does not exist."""
    try:
        return sheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return sheet.add_worksheet(title=title, rows=10000, cols=len(HEADER_ROW))


def _ensure_header(worksheet: gspread.Worksheet) -> None:
    """Add the header row if the sheet is empty."""
    existing = worksheet.row_values(1)
    if not existing:
        worksheet.append_row(HEADER_ROW, value_input_option="USER_ENTERED")
        logger.info("Wrote header row to sheet.")


def get_last_pull_info() -> tuple[str | None, set[str]]:
    """
    Read the ``_pull_metadata`` tab and return ``(last_pull_timestamp, seen_job_ids)``.

    Returns ``(None, set())`` when no metadata has been stored yet.
    """
    client = _get_client()
    try:
        sheet = client.open(config.GOOGLE_SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        return None, set()

    try:
        ws = sheet.worksheet(METADATA_TAB_NAME)
    except gspread.WorksheetNotFound:
        return None, set()

    all_values = ws.get_all_values()
    last_pull_timestamp: str | None = None
    seen_job_ids: set[str] = set()

    for row in all_values:
        if not row:
            continue
        key = row[0]
        value = row[1] if len(row) > 1 else ""
        if key == "last_pull_timestamp":
            last_pull_timestamp = value
        elif key == "job_id" and value:
            seen_job_ids.add(value)

    return last_pull_timestamp, seen_job_ids


def save_pull_metadata(pull_timestamp: str, seen_job_ids: set[str]) -> None:
    """
    Overwrite the ``_pull_metadata`` tab with *pull_timestamp* and all *seen_job_ids*.

    Parameters
    ----------
    pull_timestamp : str
        ISO-ish UTC string for the current pull (e.g. ``"2024-01-01 12:00:00 UTC"``).
    seen_job_ids : set[str]
        Complete set of job IDs that have been seen across *all* pulls so far.
    """
    client = _get_client()
    try:
        sheet = client.open(config.GOOGLE_SHEET_NAME)
    except gspread.SpreadsheetNotFound:
        logger.error(
            "Spreadsheet '%s' not found — cannot save pull metadata.",
            config.GOOGLE_SHEET_NAME,
        )
        return

    ws = _get_or_create_worksheet(sheet, METADATA_TAB_NAME)
    ws.clear()

    rows: list[list[str]] = [["last_pull_timestamp", pull_timestamp]]
    for job_id in sorted(seen_job_ids):
        rows.append(["job_id", job_id])

    ws.update(rows, value_input_option="USER_ENTERED")
    logger.info(
        "Saved pull metadata: timestamp=%s, %d job IDs.", pull_timestamp, len(seen_job_ids)
    )


def write_matches(matches: list[dict[str, Any]], tab_title: str | None = None) -> int:
    """
    Write matched jobs to a new timestamped tab in the configured Google Sheet.

    Each call creates a tab named *tab_title* (defaults to the current UTC
    ``YYYY-MM-DD HH:MM``) so that every pull run has its own tab.

    Parameters
    ----------
    matches : list[dict]
        Each dict must contain keys that map to ``HEADER_ROW``.
    tab_title : str | None
        Explicit tab name; auto-generated from the current time when omitted.

    Returns
    -------
    int
        The number of rows written.
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

    now_utc = datetime.now(timezone.utc)
    now_str = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")

    if tab_title is None:
        tab_title = now_utc.strftime("%Y-%m-%d %H:%M")

    worksheet = _get_or_create_worksheet(sheet, tab_title)
    _ensure_header(worksheet)

    rows: list[list[str]] = []
    for m in matches:
        rows.append([
            now_str,
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

    worksheet.append_rows(rows, value_input_option="USER_ENTERED")
    logger.info("Wrote %d rows to tab '%s' in '%s'.", len(rows), tab_title, config.GOOGLE_SHEET_NAME)
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
