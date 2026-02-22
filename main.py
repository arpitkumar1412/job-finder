#!/usr/bin/env python3
"""
Job Matching Agent
==================
Fetches job postings from Greenhouse & Lever, scores them with Gemini,
tailors a LaTeX resume per matched job via Claude, compiles to PDF,
uploads to Google Drive, and writes everything to Google Sheets.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any

import config
from fetchers.greenhouse import fetch_all_greenhouse_jobs
from fetchers.lever import fetch_all_lever_jobs
from fetchers.linkedin import fetch_linkedin_jobs
from matcher.similarity import filter_jobs
from resume.tailor import tailor_resumes_batch
from resume.compiler import compile_latex
from resume.drive_uploader import upload_pdf
from sheets.sheets_writer import write_matches, get_last_pull_info, save_pull_metadata

# ---------- Logging setup ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def fetch_all_jobs() -> list[dict[str, Any]]:
    """Fetch jobs from every configured source."""
    jobs: list[dict[str, Any]] = []

    logger.info("=== Fetching Greenhouse jobs ===")
    greenhouse_jobs = fetch_all_greenhouse_jobs()
    jobs.extend(greenhouse_jobs)
    logger.info("Greenhouse total: %d jobs", len(greenhouse_jobs))

    logger.info("=== Fetching Lever jobs ===")
    lever_jobs = fetch_all_lever_jobs()
    jobs.extend(lever_jobs)
    logger.info("Lever total: %d jobs", len(lever_jobs))

    if config.LINKEDIN_ENABLED:
        logger.info("=== Fetching LinkedIn jobs ===")
        try:
            linkedin_jobs = fetch_linkedin_jobs()
            jobs.extend(linkedin_jobs)
            logger.info("LinkedIn total: %d jobs", len(linkedin_jobs))
        except Exception as exc:
            logger.error("LinkedIn scraping failed: %s", exc)

    return jobs


def print_summary(
    total_fetched: int,
    matches: list[dict[str, Any]],
    resumes_generated: int,
    rows_written: int,
    elapsed: float,
) -> None:
    """Print a human-readable summary to stdout."""
    print("\n" + "=" * 60)
    print("  JOB AGENT PIPELINE — SUMMARY")
    print("=" * 60)
    print(f"  Total jobs fetched       : {total_fetched}")
    print(f"  Gemini model             : {config.GEMINI_MODEL}")
    print(f"  Score threshold          : {config.SCORE_THRESHOLD}")
    print(f"  Jobs accepted            : {len(matches)}")
    print(f"  Resumes tailored         : {resumes_generated}")
    print(f"  Rows written to Sheets   : {rows_written}")
    print(f"  Elapsed time             : {elapsed:.1f}s")

    if matches:
        print(f"\n  {'Score':>5}  {'Type':<9} {'Company':<16} {'Title':<42} {'Resume'}")
        print("  " + "-" * 90)
        for m in matches[:25]:
            resume_link = m.get("resume_link", "")
            resume_tag = "✓" if resume_link else "—"
            print(
                f"  {m.get('role_score', 0):>5}  "
                f"{m.get('role_type', '?'):<9} "
                f"{m['company']:<16} "
                f"{m['title'][:42]:<42} "
                f"{resume_tag}"
            )
        if len(matches) > 25:
            print(f"  … and {len(matches) - 25} more")
    else:
        print("\n  No jobs matched the filter.")
    print("=" * 60 + "\n")


def main() -> None:
    """Run the full pipeline: fetch → score → tailor → upload → sheets."""
    t0 = time.time()
    now_utc = datetime.now(timezone.utc)
    pull_timestamp = now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    tab_title = now_utc.strftime("%Y-%m-%d %H:%M")

    # 0. Retrieve last-pull metadata (timestamp + already-seen job IDs)
    logger.info("Step 0/5 — Loading last-pull metadata from Google Sheets")
    try:
        last_pull_timestamp, seen_job_ids = get_last_pull_info()
        if last_pull_timestamp:
            logger.info("Last pull was at: %s (%d job IDs already seen)",
                        last_pull_timestamp, len(seen_job_ids))
        else:
            logger.info("No previous pull found — will fetch all jobs.")
    except Exception as exc:
        logger.warning("Could not read pull metadata: %s — treating as first run.", exc)
        last_pull_timestamp, seen_job_ids = None, set()

    # 1. Fetch jobs
    logger.info("Step 1/5 — Fetching jobs from all sources")
    all_jobs = fetch_all_jobs()
    if not all_jobs:
        logger.warning("No jobs fetched — nothing to filter.")
        print_summary(0, [], 0, 0, time.time() - t0)
        return

    # Filter to only jobs not seen in previous pulls
    if seen_job_ids:
        new_jobs = [j for j in all_jobs if j.get("job_id") not in seen_job_ids]
        logger.info(
            "New jobs since last pull: %d (out of %d total, %d already seen)",
            len(new_jobs), len(all_jobs), len(seen_job_ids),
        )
    else:
        new_jobs = all_jobs
        logger.info("First run — processing all %d fetched jobs.", len(new_jobs))

    if not new_jobs:
        logger.info("No new jobs since last pull at %s — nothing to write.", last_pull_timestamp)
        # Still update the pull timestamp so the next run knows when we last checked.
        try:
            save_pull_metadata(pull_timestamp, seen_job_ids)
        except Exception as exc:
            logger.error("Failed to save pull metadata: %s", exc)
        print_summary(len(all_jobs), [], 0, 0, time.time() - t0)
        return

    # 2. Filter via Gemini
    logger.info("Step 2/5 — Scoring jobs with Gemini (%s, threshold=%d)",
                config.GEMINI_MODEL, config.SCORE_THRESHOLD)
    matches = filter_jobs(new_jobs)

    # 3. Tailor resumes for APPLY matches (batch API + prompt caching)
    logger.info("Step 3/5 — Tailoring resumes with Claude (%s)", config.CLAUDE_MODEL)
    resumes_generated = 0

    # Collect APPLY jobs that need a tailored resume
    apply_jobs = [j for j in matches if j.get("recommendation") == "APPLY"]
    logger.info("%d APPLY jobs need tailored resumes.", len(apply_jobs))

    if apply_jobs:
        # Batch-tailor all resumes in one API call (50 % batch + prompt-cache savings)
        tailored: dict[int, str] = tailor_resumes_batch(apply_jobs)

        # Compile each tailored LaTeX → PDF and upload to Drive
        for idx, job in enumerate(apply_jobs):
            if idx not in tailored:
                logger.warning("No tailored LaTeX for %s — %s, skipping.", job.get("company"), job.get("title"))
                continue
            try:
                pdf_bytes = compile_latex(tailored[idx], job)
                file_id, web_link = upload_pdf(pdf_bytes, job)
                job["resume_id"] = file_id
                job["resume_link"] = web_link
                resumes_generated += 1
            except Exception as exc:
                logger.error(
                    "Compile/upload failed for %s — %s: %s",
                    job.get("company"), job.get("title"), exc,
                )

    # 4. Write new matches to a timestamped tab in Google Sheets
    logger.info("Step 4/5 — Writing new matches to Google Sheets tab '%s'", tab_title)
    try:
        rows_written = write_matches(matches, tab_title=tab_title)
    except Exception as exc:
        logger.error("Failed to write to Google Sheets: %s", exc)
        logger.info("Continuing without Sheets — results printed below.")
        rows_written = 0

    # Persist updated metadata: timestamp + union of old and new job IDs
    new_seen_ids = seen_job_ids | {j["job_id"] for j in all_jobs if j.get("job_id")}
    try:
        save_pull_metadata(pull_timestamp, new_seen_ids)
    except Exception as exc:
        logger.error("Failed to save pull metadata: %s", exc)

    # 5. Summary
    logger.info("Step 5/5 — Done")
    print_summary(len(all_jobs), matches, resumes_generated, rows_written, time.time() - t0)


if __name__ == "__main__":
    main()
