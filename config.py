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
CLAUDE_MODEL: str = "claude-haiku-3-5-20241022"  # Haiku 3.5: $0.80/M in, $4/M out
CLAUDE_MAX_TOKENS: int = 2048                 # one-page resume ≈ 2 000 tokens
CLAUDE_JOB_DESC_MAX_CHARS: int = 1500         # truncate job descriptions to save input tokens
RESUME_TEMPLATE: str = "resume_template.tex"  # LaTeX source for the resume
RESUME_CLS: str = "resume.cls"                # LaTeX class file

# ---------- Google Drive (resume storage) ----------
DRIVE_ROOT_FOLDER: str = "Job Resumes"        # top-level Drive folder name
DRIVE_ROOT_FOLDER_ID: str = "1AS9ER8ZXoK1kSPtp9w6S-rDFz19GS78S"  # shared folder owned by user

# ---------- Google Sheets ----------
GOOGLE_SHEET_NAME: str = "Job Matches"
GOOGLE_SERVICE_ACCOUNT_FILE: str = "service_account.json"

# ---------- Applicant profile (used by auto-apply) ----------
APPLICANT_FIRST_NAME: str = os.getenv("APPLICANT_FIRST_NAME", "")
APPLICANT_LAST_NAME: str = os.getenv("APPLICANT_LAST_NAME", "")
APPLICANT_EMAIL: str = os.getenv("APPLICANT_EMAIL", "")
APPLICANT_PHONE: str = os.getenv("APPLICANT_PHONE", "")
APPLICANT_LINKEDIN: str = os.getenv("APPLICANT_LINKEDIN", "")
APPLICANT_GITHUB: str = os.getenv("APPLICANT_GITHUB", "")
APPLICANT_WEBSITE: str = os.getenv("APPLICANT_WEBSITE", "")

# ---------- Auto-apply settings ----------
AUTO_APPLY_WAIT: float = 2.0              # seconds between page interactions
AUTO_APPLY_PAGE_LOAD_WAIT: float = 10.0   # max wait for page elements (seconds)
SELENIUM_HEADLESS: bool = True            # run browser in headless mode

# ---------- LinkedIn scraper (Playwright) ----------
LINKEDIN_ENABLED: bool = True
LINKEDIN_SEARCH_URL: str = (
    "https://www.linkedin.com/jobs/search/"
    "?keywords=SDE2%20Backend&location=India&f_TPR=r86400"
)
LINKEDIN_MIN_DELAY: float = 5.0             # minimum seconds between page loads
LINKEDIN_MAX_DELAY: float = 15.0            # maximum seconds between page loads
LINKEDIN_MAX_PAGES: int = 5                 # max "See more jobs" clicks
# Residential proxy placeholder — set to a real proxy URL to avoid IP bans.
# Example: "http://user:pass@proxy.example.com:8080"
LINKEDIN_PROXY: str = os.getenv("LINKEDIN_PROXY", "")

# ---------- Networking ----------
REQUEST_TIMEOUT: int = 30                   # seconds
