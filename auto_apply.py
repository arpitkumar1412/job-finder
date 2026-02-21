#!/usr/bin/env python3
"""
Auto-Apply Pipeline
===================
Reads APPLY-recommended jobs from Google Sheets (with tailored resumes
already uploaded to Drive), downloads each resume, and submits applications
via Selenium on the corresponding ATS (Greenhouse / Lever).

Usage
-----
    python auto_apply.py

Prerequisites
-------------
1. Run ``main.py`` first to populate the sheet with scored jobs and
   tailored resumes.
2. Set applicant profile environment variables (or edit ``config.py``)::

       export APPLICANT_FIRST_NAME="Jane"
       export APPLICANT_LAST_NAME="Doe"
       export APPLICANT_EMAIL="jane.doe@example.com"
       export APPLICANT_PHONE="+1-555-0100"
       export APPLICANT_LINKEDIN="https://linkedin.com/in/janedoe"
       export APPLICANT_GITHUB="https://github.com/janedoe"

3. Google Chrome must be installed (Selenium + webdriver-manager handle
   the driver automatically).
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

import config
from sheets.sheets_reader import read_apply_jobs, _detect_source
from sheets.sheets_writer import update_application_status
from applier.driver import download_resume_from_drive
from applier.greenhouse_applier import apply_greenhouse
from applier.lever_applier import apply_lever

# ---------- Logging setup ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("auto_apply")


def _validate_profile() -> bool:
    """Check that minimum applicant info is configured."""
    required = [
        ("APPLICANT_FIRST_NAME", config.APPLICANT_FIRST_NAME),
        ("APPLICANT_LAST_NAME", config.APPLICANT_LAST_NAME),
        ("APPLICANT_EMAIL", config.APPLICANT_EMAIL),
    ]
    missing = [name for name, value in required if not value.strip()]
    if missing:
        logger.error(
            "Missing required applicant profile fields: %s. "
            "Set them as environment variables or in config.py.",
            ", ".join(missing),
        )
        return False
    return True


def _apply_single(
    job: dict[str, Any],
    resume_path: str,
    source: str,
) -> tuple[bool, str]:
    """Route to the correct ATS applier."""
    if source == "greenhouse":
        return apply_greenhouse(job, resume_path)
    elif source == "lever":
        return apply_lever(job, resume_path)
    else:
        return False, f"Unsupported ATS source: {source}"


def print_summary(
    total: int,
    applied: int,
    failed: int,
    skipped: int,
    elapsed: float,
) -> None:
    """Print a human-readable summary to stdout."""
    print("\n" + "=" * 60)
    print("  AUTO-APPLY PIPELINE — SUMMARY")
    print("=" * 60)
    print(f"  Total eligible jobs      : {total}")
    print(f"  Successfully applied     : {applied}")
    print(f"  Failed                   : {failed}")
    print(f"  Skipped (unsupported ATS): {skipped}")
    print(f"  Elapsed time             : {elapsed:.1f}s")
    print("=" * 60 + "\n")


def main() -> None:
    """Run the auto-apply pipeline."""
    t0 = time.time()

    # Validate applicant profile
    if not _validate_profile():
        sys.exit(1)

    # Step 1: Read eligible jobs from Google Sheets
    logger.info("Step 1/3 — Reading APPLY jobs from Google Sheets")
    jobs = read_apply_jobs()
    if not jobs:
        logger.info("No eligible jobs found for auto-apply.")
        print_summary(0, 0, 0, 0, time.time() - t0)
        return

    logger.info("Found %d jobs to apply to.", len(jobs))

    # Step 2: Apply to each job
    logger.info("Step 2/3 — Submitting applications")
    applied = 0
    failed = 0
    skipped = 0

    for i, job in enumerate(jobs):
        company = job.get("company", "unknown")
        title = job.get("title", "unknown")
        apply_url = str(job.get("apply_url", ""))
        resume_id = str(job.get("resume_id", ""))
        row_index = job.get("_sheet_row_index", 0)
        label = f"{company} — {title}"

        logger.info(
            "Job %d/%d: [%s] %s",
            i + 1, len(jobs), company, title,
        )

        # Detect ATS source
        source = _detect_source(apply_url)
        if source == "unknown":
            logger.warning("Unsupported ATS for [%s]: %s", label, apply_url)
            if row_index:
                try:
                    update_application_status(row_index, "SKIPPED — unsupported ATS")
                except Exception as exc:
                    logger.error("Failed to update sheet status: %s", exc)
            skipped += 1
            continue

        # Download resume from Drive
        resume_path = download_resume_from_drive(resume_id)
        if not resume_path:
            logger.error("Could not download resume for [%s]", label)
            if row_index:
                try:
                    update_application_status(row_index, "FAILED — resume download error")
                except Exception as exc:
                    logger.error("Failed to update sheet status: %s", exc)
            failed += 1
            continue

        try:
            # Apply
            success, message = _apply_single(job, resume_path, source)

            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            if success:
                status = f"APPLIED — {now}"
                applied += 1
            else:
                status = f"FAILED — {message}"
                failed += 1

            # Update sheet
            if row_index:
                try:
                    update_application_status(row_index, status)
                except Exception as exc:
                    logger.error("Failed to update sheet status: %s", exc)

        finally:
            # Clean up downloaded resume
            try:
                os.unlink(resume_path)
            except OSError:
                pass

        # Pause between applications to avoid rate limiting
        if i < len(jobs) - 1:
            time.sleep(config.AUTO_APPLY_WAIT)

    # Step 3: Summary
    logger.info("Step 3/3 — Done")
    print_summary(len(jobs), applied, failed, skipped, time.time() - t0)


if __name__ == "__main__":
    main()
