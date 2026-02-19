#!/usr/bin/env python3
"""
Job Matching Agent — Phase 1
=============================
Fetches job postings from Greenhouse & Lever, computes cosine similarity
against a local resume, and writes matching results to Google Sheets.
"""

from __future__ import annotations

import logging
import pathlib
import sys
import time
from typing import Any

import config
from fetchers.greenhouse import fetch_all_greenhouse_jobs
from fetchers.lever import fetch_all_lever_jobs
from matcher.similarity import rank_jobs
from sheets.sheets_writer import write_matches

# ---------- Logging setup ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def load_resume(path: str = config.RESUME_PATH) -> str:
    """Read resume text from a local file."""
    resume_file = pathlib.Path(path)
    if not resume_file.exists():
        logger.error("Resume file not found: %s", resume_file.resolve())
        sys.exit(1)
    text = resume_file.read_text(encoding="utf-8").strip()
    if not text:
        logger.error("Resume file is empty: %s", resume_file.resolve())
        sys.exit(1)
    logger.info("Loaded resume (%d chars) from %s", len(text), resume_file)
    return text


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

    return jobs


def print_summary(
    total_fetched: int,
    matches: list[dict[str, Any]],
    rows_written: int,
    elapsed: float,
) -> None:
    """Print a human-readable summary to stdout."""
    print("\n" + "=" * 60)
    print("  JOB MATCHING PIPELINE — SUMMARY")
    print("=" * 60)
    print(f"  Total jobs fetched       : {total_fetched}")
    print(f"  Similarity threshold     : {config.SIMILARITY_THRESHOLD}%")
    print(f"  Jobs above threshold     : {len(matches)}")
    print(f"  Rows written to Sheets   : {rows_written}")
    print(f"  Elapsed time             : {elapsed:.1f}s")

    if matches:
        print("\n  Top 10 matches:")
        print(f"  {'Score':>6}  {'Company':<18} {'Title'}")
        print("  " + "-" * 56)
        for m in matches[:10]:
            print(
                f"  {m['similarity_score']:>5.1f}%  "
                f"{m['company']:<18} "
                f"{m['title'][:50]}"
            )
    else:
        print("\n  No jobs matched the threshold.")
    print("=" * 60 + "\n")


def main() -> None:
    """Run the full Phase 1 pipeline."""
    t0 = time.time()

    # 1. Load resume
    logger.info("Step 1/5 — Loading resume")
    resume_text = load_resume()

    # 2. Fetch jobs
    logger.info("Step 2/5 — Fetching jobs from all sources")
    all_jobs = fetch_all_jobs()
    if not all_jobs:
        logger.warning("No jobs fetched — nothing to match.")
        print_summary(0, [], 0, time.time() - t0)
        return

    # 3. Compute similarity & filter
    logger.info("Step 3/5 — Computing similarity scores")
    matches = rank_jobs(resume_text, all_jobs, threshold=config.SIMILARITY_THRESHOLD)

    # 4. Write to Google Sheets
    logger.info("Step 4/5 — Writing matches to Google Sheets")
    try:
        rows_written = write_matches(matches)
    except Exception as exc:
        logger.error("Failed to write to Google Sheets: %s", exc)
        logger.info("Continuing without Sheets — results printed below.")
        rows_written = 0

    # 5. Summary
    logger.info("Step 5/5 — Done")
    print_summary(len(all_jobs), matches, rows_written, time.time() - t0)


if __name__ == "__main__":
    main()
