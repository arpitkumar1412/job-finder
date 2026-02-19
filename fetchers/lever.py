"""
Fetch job postings from the Lever public postings API.

Endpoint: https://api.lever.co/v0/postings/{company}?mode=json
No authentication required for public boards.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)

LEVER_POSTINGS_URL = "https://api.lever.co/v0/postings/{company}"


def _strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def _build_description(posting: dict[str, Any]) -> str:
    """
    Lever postings store the description in ``descriptionPlain`` or
    across multiple ``lists`` / ``additional`` / ``descriptionBody`` fields.
    We concatenate everything useful and strip HTML.
    """
    parts: list[str] = []

    if posting.get("descriptionPlain"):
        parts.append(posting["descriptionPlain"])

    for section in posting.get("lists", []):
        if section.get("text"):
            parts.append(section["text"])
        if section.get("content"):
            # content is HTML
            parts.append(_strip_html(section["content"]))

    if posting.get("additional"):
        parts.append(_strip_html(posting["additional"]))
    if posting.get("descriptionBody"):
        parts.append(_strip_html(posting["descriptionBody"]))

    return _strip_html(" ".join(parts))


def _parse_posting(raw: dict[str, Any], company: str) -> dict[str, Any] | None:
    """Parse a single Lever posting into a normalised dict."""
    try:
        categories = raw.get("categories", {})
        location = categories.get("location", "") or raw.get("workplaceType", "")

        description = _build_description(raw)

        return {
            "job_id": str(raw["id"]),
            "title": raw.get("text", ""),
            "company": company,
            "location": location,
            "description": description,
            "apply_url": raw.get("hostedUrl", "") or raw.get("applyUrl", ""),
            "source": "lever",
        }
    except (KeyError, TypeError) as exc:
        logger.warning("Skipping malformed Lever posting: %s", exc)
        return None


def fetch_lever_jobs(company: str) -> list[dict[str, Any]]:
    """
    Fetch all public postings for *company* from Lever.

    Parameters
    ----------
    company : str
        The Lever company slug (e.g. ``"openai"``).

    Returns
    -------
    list[dict]
        List of normalised job dicts.
    """
    url = LEVER_POSTINGS_URL.format(company=company)
    logger.info("Fetching Lever postings for '%s' …", company)

    try:
        resp = requests.get(
            url,
            params={"mode": "json"},
            timeout=config.REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Lever request failed for '%s': %s", company, exc)
        return []

    raw_postings: list[dict] = resp.json()
    if not isinstance(raw_postings, list):
        logger.error("Unexpected Lever response type for '%s'", company)
        return []

    logger.info("  → received %d raw postings", len(raw_postings))

    jobs: list[dict[str, Any]] = []
    for raw in raw_postings:
        parsed = _parse_posting(raw, company)
        if parsed and parsed["description"]:
            jobs.append(parsed)

    logger.info("  → kept %d postings with descriptions", len(jobs))
    return jobs


def fetch_all_lever_jobs() -> list[dict[str, Any]]:
    """Fetch jobs for every company listed in ``config.LEVER_COMPANIES``."""
    all_jobs: list[dict[str, Any]] = []
    for company in config.LEVER_COMPANIES:
        all_jobs.extend(fetch_lever_jobs(company))
    return all_jobs
