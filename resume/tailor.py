"""
Resume tailoring with Claude.

Uses several Anthropic cost-saving features:
  • **Prompt caching** — the system prompt and the LaTeX resume template
    are marked with ``cache_control: ephemeral`` so they are cached across
    requests (90 % savings on cached input tokens).
  • **Message Batches API** — all resume-tailoring requests are submitted
    as a single batch (50 % savings on all tokens).
  • **Cheaper model** — defaults to Haiku 3.5 instead of Sonnet 4.
  • **Template stripping** — commented-out LaTeX blocks are removed before
    sending to avoid wasting tokens on unused content.
  • **Description truncation** — job descriptions are capped at
    ``CLAUDE_JOB_DESC_MAX_CHARS`` characters to reduce input tokens.

When only one job needs a resume, the regular (non-batch) Messages API
is used instead, still with prompt caching.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

import anthropic

import config

logger = logging.getLogger(__name__)

# ── polling config ───────────────────────────────────────────────
_BATCH_POLL_INTERVAL: int = 10        # seconds between status checks
_BATCH_POLL_TIMEOUT: int  = 30 * 60   # give up after 30 min

# ── system prompt that guides the tailoring ──────────────────────
SYSTEM_PROMPT = """\
You are an expert resume editor.  The user will supply:

1. A **LaTeX resume source** (using a custom `resume.cls` class).
2. A **job posting** (title, company, location, description, and why it matched).

Your task
---------
Rewrite the LaTeX resume so it is **maximally relevant** for the job
while remaining **100 % truthful** — do NOT fabricate any experience,
skill, metric, or technology the candidate does not already have.

CRITICAL CONSTRAINT — ONE PAGE
-------------------------------
The original resume fits on **exactly one page**.  Your output MUST also
fit on exactly one page when compiled with pdflatex.  If you add content
(e.g. uncomment a bullet), you MUST remove or shorten other content to
compensate.  Err on the side of being concise.  A two-page resume will
be **rejected**.

Rules
-----
• Keep the document structure identical (`rSection`, `rSubsection`, etc.).
• Keep \\documentclass, \\usepackage, \\name, \\address, and \\begin{document}
  / \\end{document} exactly as they are — do NOT add new packages.
• Only alter the content *inside* the section bodies.
• You may **reorder** bullet points so the most relevant ones appear first.
• You may **rephrase** bullets to emphasise technologies or impact areas
  that appear in the job posting (e.g. mention "distributed systems" instead
  of "backend services" if the JD uses that term).
• You may **uncomment** commented-out sections/bullets if they add relevance
  (the template contains some commented blocks).  When uncommenting, make
  sure the LaTeX syntax is correct.
• You may **remove or comment out** less-relevant bullets to keep the resume
  to one page.  When in doubt, **cut the least-relevant bullet** rather
  than risk overflowing to a second page.
• Keep each bullet to **1–2 lines** of printed text.  Never let a single
  bullet wrap to 3+ printed lines.
• In the SKILLS section, reorder skills so the most relevant ones come first;
  you may add skills the candidate clearly has (inferred from their work)
  but do NOT invent skills.
• Do NOT change the candidate's name, contact info, degree, GPA, dates, or
  company names.
• Output ONLY the complete, compilable LaTeX source — no markdown fences,
  no explanations, no preamble.
• Ensure the output compiles cleanly with pdflatex — avoid Unicode characters
  outside the ASCII + standard LaTeX math range.  Use LaTeX commands like
  \\textendash, $<$, $>$, $\\rightarrow$, etc.
"""


# ── helpers ──────────────────────────────────────────────────────

# Matches lines that are purely LaTeX comments (optional leading whitespace + %).
_COMMENT_LINE_RE = re.compile(r"^\s*%")


def _strip_latex_comments(tex: str) -> str:
    """Remove pure-comment lines from LaTeX source to save tokens.

    Lines that contain *code* followed by a ``%`` inline comment are kept
    intact — only lines whose first non-whitespace character is ``%`` are
    dropped.
    """
    return "\n".join(
        line for line in tex.splitlines()
        if not _COMMENT_LINE_RE.match(line)
    )


def _read_template() -> str:
    """Return the raw LaTeX content of the resume template, with comment
    lines stripped to reduce token count."""
    path = Path(config.RESUME_TEMPLATE)
    raw = path.read_text(encoding="utf-8")
    return _strip_latex_comments(raw)


def _truncate_description(text: str, max_chars: int | None = None) -> str:
    """Truncate a job description to *max_chars* characters."""
    limit = max_chars if max_chars is not None else config.CLAUDE_JOB_DESC_MAX_CHARS
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _job_text(job: dict[str, Any]) -> str:
    """Format the job-specific portion of the user message."""
    description = _truncate_description(
        job.get("description", "No description available."),
    )
    return (
        "=== JOB POSTING ===\n"
        f"Company : {job.get('company', 'N/A')}\n"
        f"Title   : {job.get('title', 'N/A')}\n"
        f"Location: {job.get('location', 'N/A')}\n"
        f"Type    : {job.get('role_type', 'N/A')}\n"
        f"Why it matched: {job.get('match_reasons', 'N/A')}\n\n"
        f"Description:\n{description}\n"
    )


def _system_block() -> list[dict]:
    """System prompt with prompt-caching enabled."""
    return [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _user_blocks(template_tex: str, job: dict[str, Any]) -> list[dict]:
    """User message content blocks — template is cached, job text is not."""
    return [
        {
            "type": "text",
            "text": f"=== RESUME TEMPLATE (LaTeX) ===\n{template_tex}",
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": _job_text(job),
        },
    ]


def _log_usage(label: str, usage) -> None:
    """Log token usage including cache stats."""
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    cache_create = getattr(usage, "cache_creation_input_tokens", 0)
    logger.info(
        "%s — tokens: in=%d  out=%d  cache_read=%d  cache_create=%d",
        label,
        usage.input_tokens,
        usage.output_tokens,
        cache_read,
        cache_create,
    )


def _validate_latex(tex: str) -> bool:
    return r"\begin{document}" in tex


# ── single-job (non-batch) with prompt caching ──────────────────

def tailor_resume(job: dict[str, Any]) -> str:
    """
    Call Claude to produce a tailored LaTeX resume for *job*.

    Uses prompt caching on the system prompt + resume template.
    Prefer ``tailor_resumes_batch`` when processing ≥ 2 jobs.
    """
    template_tex = _read_template()
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    logger.info(
        "Tailoring resume for %s — %s …",
        job.get("company", "?"),
        job.get("title", "?"),
    )

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.CLAUDE_MAX_TOKENS,
        temperature=0.3,
        system=_system_block(),
        messages=[{"role": "user", "content": _user_blocks(template_tex, job)}],
    )

    tailored_tex = response.content[0].text

    if not _validate_latex(tailored_tex):
        logger.error("Claude output does not look like valid LaTeX — returning template unchanged.")
        return template_tex

    _log_usage(f"Resume for {job.get('company')}", response.usage)
    return tailored_tex


# ── batch tailoring (Batches API + prompt caching) ──────────────

def tailor_resumes_batch(jobs: list[dict[str, Any]]) -> dict[int, str]:
    """
    Tailor resumes for multiple jobs using the Anthropic Message Batches API.

    Both the **system prompt** and the **resume template** are marked with
    ``cache_control: ephemeral`` so Anthropic caches them across every
    request in the batch — this stacks with the 50 % batch discount.

    Parameters
    ----------
    jobs : list[dict]
        APPLY-recommended jobs that need a tailored resume.

    Returns
    -------
    dict[int, str]
        Mapping from index in *jobs* to the tailored LaTeX source.
        Jobs whose tailoring failed are simply absent from the dict.
    """
    if not jobs:
        return {}

    # Fall back to non-batch for a single job (batch overhead not worth it)
    if len(jobs) == 1:
        tex = tailor_resume(jobs[0])
        return {0: tex} if _validate_latex(tex) else {}

    template_tex = _read_template()
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    # Build batch requests ------------------------------------------------
    requests = []
    for i, job in enumerate(jobs):
        requests.append(
            {
                "custom_id": f"job-{i}",
                "params": {
                    "model": config.CLAUDE_MODEL,
                    "max_tokens": config.CLAUDE_MAX_TOKENS,
                    "temperature": 0.3,
                    "system": _system_block(),
                    "messages": [
                        {
                            "role": "user",
                            "content": _user_blocks(template_tex, job),
                        }
                    ],
                },
            }
        )
        logger.info(
            "Queued resume #%d: %s — %s",
            i, job.get("company", "?"), job.get("title", "?"),
        )

    # Submit batch --------------------------------------------------------
    logger.info("Submitting batch of %d resume-tailoring requests …", len(requests))
    batch = client.messages.batches.create(requests=requests)
    logger.info("Batch created: id=%s  status=%s", batch.id, batch.processing_status)

    # Poll until the batch finishes ---------------------------------------
    t0 = time.time()
    while batch.processing_status != "ended":
        if time.time() - t0 > _BATCH_POLL_TIMEOUT:
            logger.error("Batch %s timed out after %ds — cancelling.", batch.id, _BATCH_POLL_TIMEOUT)
            try:
                client.messages.batches.cancel(batch.id)
            except Exception:
                pass
            break
        time.sleep(_BATCH_POLL_INTERVAL)
        batch = client.messages.batches.retrieve(batch.id)
        rc = batch.request_counts
        total = rc.processing + rc.succeeded + rc.errored + rc.canceled + rc.expired
        logger.info(
            "Batch %s — %d/%d done  (ok=%d err=%d cancel=%d expired=%d)",
            batch.id, rc.succeeded + rc.errored + rc.canceled + rc.expired, total,
            rc.succeeded, rc.errored, rc.canceled, rc.expired,
        )

    # Collect results -----------------------------------------------------
    results: dict[int, str] = {}
    for entry in client.messages.batches.results(batch.id):
        idx = int(entry.custom_id.split("-")[1])
        if entry.result.type == "succeeded":
            tex = entry.result.message.content[0].text
            if _validate_latex(tex):
                results[idx] = tex
                _log_usage(f"Resume #{idx} ({jobs[idx].get('company')})", entry.result.message.usage)
            else:
                logger.error("Resume #%d: output doesn't look like valid LaTeX — skipped.", idx)
        else:
            err_type = entry.result.type
            logger.error("Resume #%d: batch result type=%s", idx, err_type)

    logger.info(
        "Batch complete: %d/%d resumes tailored successfully.", len(results), len(jobs),
    )
    return results
