"""
Fetch job postings from the Greenhouse Boards API.

API docs: https://developers.greenhouse.io/harvest.html
Public boards endpoint requires NO authentication.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)

GREENHOUSE_JOBS_URL = "https://boards-api.greenhouse.io/v1/boards/{company}/jobs"


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def _parse_job(raw: dict[str, Any], company: str) -> dict[str, Any] | None:
    """Parse a single Greenhouse job object into a normalised dict."""
    try:
        location_name = ""
        if raw.get("location"):
            location_name = raw["location"].get("name", "")

        description = raw.get("content", "") or ""
        description = _strip_html(description)

        apply_url = raw.get("absolute_url", "")

        return {
            "job_id": str(raw["id"]),
            "title": raw.get("title", ""),
            "company": company,
            "location": location_name,
            "description": description,
            "apply_url": apply_url,
            "source": "greenhouse",
        }
    except (KeyError, TypeError) as exc:
        logger.warning("Skipping malformed Greenhouse job: %s", exc)
        return None


def fetch_greenhouse_jobs(company: str) -> list[dict[str, Any]]:
    """
    Fetch all jobs for *company* from Greenhouse.

    Parameters
    ----------
    company : str
        The Greenhouse board token (e.g. ``"airbnb"``).

    Returns
    -------
    list[dict]
        List of normalised job dicts.
    """
    url = GREENHOUSE_JOBS_URL.format(company=company)
    logger.info("Fetching Greenhouse jobs for '%s' …", company)

    try:
        resp = requests.get(
            url,
            params={"content": "true"},
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Greenhouse request failed for '%s': %s", company, exc)
        return []

    data = resp.json()
    raw_jobs: list[dict] = data.get("jobs", [])
    logger.info("  → received %d raw postings", len(raw_jobs))

    jobs: list[dict[str, Any]] = []
    for raw in raw_jobs:
        parsed = _parse_job(raw, company)
        if parsed and parsed["description"]:
            jobs.append(parsed)

    logger.info("  → kept %d jobs with descriptions", len(jobs))
    return jobs


def fetch_all_greenhouse_jobs() -> list[dict[str, Any]]:
    """Fetch jobs for every company listed in ``config.GREENHOUSE_COMPANIES``."""
    all_jobs: list[dict[str, Any]] = []
    for company in config.GREENHOUSE_COMPANIES:
        all_jobs.extend(fetch_greenhouse_jobs(company))
    return all_jobs
