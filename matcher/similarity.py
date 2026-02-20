"""
Filter jobs using Google Gemini (free tier) with a rubric-based scoring
system for an SDE-II Backend Engineer.

Pipeline
--------
1. **Quick pre-filter** (regex) — drops obviously irrelevant titles
   (designer, recruiter, analyst, …) to minimise API calls.
2. **Gemini evaluation** — sends batches of jobs with a detailed scoring
   rubric (0-100) broken into sub-scores, then filters by threshold.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from google import genai
from google.genai import types

import config

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# System prompt with scoring rubric
# -------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are evaluating job postings for relevance to a backend Software Development Engineer II (SDE2).

Candidate profile:
- Current role: Software Development Engineer II at Microsoft
- Experience: ~3 years backend engineering
- Backend focus: APIs, distributed systems, backend services, caching, databases, infrastructure
- Languages: C#, C++, Java, Python
- Interested ONLY in backend or backend-heavy roles

Your task is to compute a role_score from 0 to 100 based on relevance.

Scoring criteria:

1. Backend relevance (0-40 points)
- 40 = pure backend role (backend services, APIs, distributed systems)
- 30 = mostly backend
- 20 = mixed backend and frontend
- 10 = minor backend
- 0 = no backend

2. Role title relevance (0-15 points)
- 15 = Backend Engineer, Software Engineer (Backend), Systems Engineer, Infrastructure Engineer
- 12 = Software Engineer (generic)
- 8 = Fullstack Engineer
- 0 = Frontend Engineer, Mobile Engineer
- 0 = Manager, Staff Engineer, Principal Engineer

3. Seniority match (0-15 points)
Based on required years of experience:
- 15 = 0-5 years required
- 12 = 5-7 years
- 8 = 7-10 years
- 3 = 10+ years
- 0 = Staff, Principal, or Management roles

Do NOT overly penalize higher experience requirements.

4. Tech stack match (0-20 points)
Give higher scores if job mentions backend technologies such as:
- C#, Java, Python, Go, C++
- APIs, distributed systems, microservices
- SQL, NoSQL, databases
- Cloud (Azure, AWS, GCP)
- Backend infrastructure

5. Role type penalty (subtract points if applicable)
Subtract:
- 40 points if primarily frontend
- 40 points if mobile-only
- 30 points if ML research role
- 50 points if management role

Final score must be clamped between 0 and 100.

Scoring interpretation:
- 90-100: Excellent match
- 75-89: Strong match
- 60-74: Moderate match
- 40-59: Weak match
- 0-39: Not relevant

You will receive a JSON array of jobs. For EACH job, return a JSON object:
{
  "index": <integer - the index from the input array>,
  "role_score": number,
  "backend_relevance": number,
  "title_relevance": number,
  "seniority_match": number,
  "tech_stack_match": number,
  "penalty": number,
  "final_recommendation": "APPLY" or "SKIP",
  "reason": "one sentence explanation",
  "role_type": "backend" | "frontend" | "ml" | "infra" | "mobile" | "manager" | "unknown"
}

Return ONLY a JSON array of these objects. No markdown fences, no extra text.

Be strict about rejecting frontend, mobile, ML research, and management roles.
Be lenient about years of experience requirements.
Prioritize backend engineering relevance above everything else."""


# -------------------------------------------------------------------
# Quick pre-filter (regex) — skip non-engineering roles entirely
# -------------------------------------------------------------------

_REJECT_TITLE_RE = re.compile(
    r"\b(?:"
    r"designer|design lead|ux|ui/ux|visual design"
    r"|recruiter|recruiting|talent|people partner"
    r"|marketing|content|copywriter|brand"
    r"|accountant|accounting|finance analyst|financial"
    r"|legal|counsel|paralegal|compliance officer"
    r"|sales|account executive|business development rep"
    r"|office manager|executive assistant|admin"
    r"|data analyst|business analyst|bi analyst"
    r"|customer support|customer success"
    r"|editorial|journalist|communications"
    r")\b",
    re.IGNORECASE,
)

_KEEP_TITLE_RE = re.compile(
    r"\b(?:"
    r"engineer|developer|sde|swe|architect|software"
    r"|infrastructure|platform|systems|backend|back-end"
    r"|devops|sre|security engineer|cloud"
    r")\b",
    re.IGNORECASE,
)


def _passes_prefilter(title: str) -> bool:
    """Fast regex gate — returns False for clearly non-engineering roles."""
    if _REJECT_TITLE_RE.search(title):
        return False
    if _KEEP_TITLE_RE.search(title):
        return True
    # Ambiguous title — let the LLM decide
    return True


# -------------------------------------------------------------------
# Gemini evaluation helpers
# -------------------------------------------------------------------

def _truncate(text: str, max_chars: int = 800) -> str:
    """Truncate description to save tokens."""
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def _build_batch_payload(jobs: list[dict[str, Any]]) -> str:
    """Build the user-message JSON array for one Gemini batch."""
    items = []
    for i, job in enumerate(jobs):
        items.append({
            "index": i,
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "location": job.get("location", ""),
            "description": _truncate(job.get("description", "")),
        })
    return json.dumps(items, ensure_ascii=False)


def _init_gemini() -> genai.Client:
    """Return a configured Gemini client with extended timeout and no SDK retries."""
    return genai.Client(
        api_key=config.GEMINI_API_KEY,
        http_options={"timeout": 120_000, "api_version": "v1beta"},
    )


MAX_RETRIES = 5

def _call_gemini(client: genai.Client, batch_json: str) -> list[dict[str, Any]]:
    """Send a batch to Gemini and parse the JSON response."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=batch_json,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )
            raw = response.text or "[]"
            parsed = json.loads(raw)
            # The model may wrap the array in a key like {"results": [...]}
            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list):
                        parsed = v
                        break
            if isinstance(parsed, list):
                return parsed
            logger.warning("Gemini returned unexpected shape, treating as empty.")
            return []
        except json.JSONDecodeError:
            logger.warning("Gemini returned non-JSON (attempt %d/%d), retrying…", attempt, MAX_RETRIES)
            time.sleep(2 * attempt)
        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "Resource" in exc_str:
                wait = 30 + (15 * attempt)  # 45, 60, 75, 90, 105s — let quota window reset
                logger.warning("Rate limited (attempt %d/%d), waiting %ds…", attempt, MAX_RETRIES, wait)
                time.sleep(wait)
            elif any(kw in exc_str for kw in ("timeout", "Timeout", "ConnectionError", "RemoteDisconnected", "read")):
                wait = 5 * attempt
                logger.warning("Connection error (attempt %d/%d), waiting %ds… : %s", attempt, MAX_RETRIES, wait, exc_str[:120])
                time.sleep(wait)
            else:
                logger.warning("Gemini API error (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
                time.sleep(3 * attempt)

    logger.error("Gemini failed after %d attempts for this batch.", MAX_RETRIES)
    return []


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------

def filter_jobs(jobs: list[dict[str, Any]], *, early_stop: int = 0) -> list[dict[str, Any]]:
    """
    Two-stage filter:
    1. Regex pre-filter to drop obviously irrelevant titles.
    2. Gemini rubric-based scoring on remaining jobs (batched).

    If *early_stop* > 0, stop as soon as that many matches are found.

    Returns jobs with role_score >= SCORE_THRESHOLD, enriched with
    sub-scores, role_type, and recommendation.
    """
    if not jobs:
        logger.warning("No jobs to filter.")
        return []

    # --- Stage 1: quick pre-filter ---
    candidates = [j for j in jobs if _passes_prefilter(j.get("title", ""))]
    logger.info(
        "Pre-filter: %d / %d jobs passed title check.",
        len(candidates), len(jobs),
    )

    if not candidates:
        return []

    # --- Stage 2: Gemini scoring in batches ---
    client = _init_gemini()
    batch_size = config.GEMINI_BATCH_SIZE
    matched: list[dict[str, Any]] = []
    total_batches = (len(candidates) + batch_size - 1) // batch_size
    threshold = config.SCORE_THRESHOLD

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = start + batch_size
        batch = candidates[start:end]

        logger.info(
            "Gemini batch %d/%d  (%d jobs) …",
            batch_idx + 1, total_batches, len(batch),
        )

        payload = _build_batch_payload(batch)
        verdicts = _call_gemini(client, payload)

        for v in verdicts:
            idx = v.get("index")
            if idx is None or idx >= len(batch):
                continue
            score = v.get("role_score", 0)
            if score >= threshold:
                job_copy = dict(batch[idx])
                job_copy["role_score"] = score
                job_copy["backend_relevance"] = v.get("backend_relevance", 0)
                job_copy["title_relevance"] = v.get("title_relevance", 0)
                job_copy["seniority_match"] = v.get("seniority_match", 0)
                job_copy["tech_stack_match"] = v.get("tech_stack_match", 0)
                job_copy["penalty"] = v.get("penalty", 0)
                job_copy["role_type"] = v.get("role_type", "unknown")
                job_copy["recommendation"] = v.get("final_recommendation", "SKIP")
                job_copy["match_reasons"] = v.get("reason", "")
                matched.append(job_copy)

        # Early stop if requested
        if early_stop > 0 and len(matched) >= early_stop:
            logger.info("Early stop: found %d match(es), stopping.", len(matched))
            break

        # Pace requests to stay within free-tier rate limits
        if batch_idx < total_batches - 1:
            time.sleep(config.GEMINI_RATE_LIMIT_PAUSE)

    # Sort by score descending, then company
    matched.sort(key=lambda j: (-j.get("role_score", 0), j.get("company", "")))

    logger.info(
        "Gemini filter complete: %d / %d candidates scored >= %d (%d total fetched).",
        len(matched), len(candidates), threshold, len(jobs),
    )
    return matched
