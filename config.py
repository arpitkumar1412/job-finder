"""
Configuration for the Job Matching Agent.
"""

# ---------- Company boards to scrape ----------
GREENHOUSE_COMPANIES: list[str] = [
    "airbnb",
    # "netflix",      # 404
    "figma",
    "stripe",
    "cloudflare",
]

LEVER_COMPANIES: list[str] = [
    # "openai",       # 404
    # "netflix",      # hangs / 0 results
    # "figma",        # 404
    # "anthropic",    # 404
    # "databricks",   # 404
]

# ---------- Gemini-based job filter (free tier) ----------
import os
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = "gemini-2.5-flash-lite"   # lighter model, better free-tier quotas
GEMINI_BATCH_SIZE: int = 10                   # jobs per API call (smaller = safer on token limits)
GEMINI_RATE_LIMIT_PAUSE: float = 30.0         # seconds between batches (2 RPM — generous spacing for free tier)
SCORE_THRESHOLD: int = 60                     # keep jobs with role_score >= this (0-100)

# ---------- Claude (resume tailoring) ----------
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = "claude-sonnet-4-20250514"  # Sonnet 4: $3/M in, $15/M out
RESUME_TEMPLATE: str = "resume_template.tex"  # LaTeX source for the resume
RESUME_CLS: str = "resume.cls"                # LaTeX class file

# ---------- Google Drive (resume storage) ----------
DRIVE_ROOT_FOLDER: str = "Job Resumes"        # top-level Drive folder name
DRIVE_ROOT_FOLDER_ID: str = "1AS9ER8ZXoK1kSPtp9w6S-rDFz19GS78S"  # shared folder owned by user

# ---------- Google Sheets ----------
GOOGLE_SHEET_NAME: str = "Job Matches"
GOOGLE_SERVICE_ACCOUNT_FILE: str = "service_account.json"

# ---------- Networking ----------
REQUEST_TIMEOUT: int = 30                   # seconds
