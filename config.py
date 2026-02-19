"""
Configuration for the Job Matching Agent.
"""

# ---------- Company boards to scrape ----------
GREENHOUSE_COMPANIES: list[str] = [
    "airbnb",
    "netflix",
    "figma",
    "stripe",
    "cloudflare",
]

LEVER_COMPANIES: list[str] = [
    "openai",
    "netflix",
    "figma",
    "anthropic",
    "databricks",
]

# ---------- Similarity settings ----------
SIMILARITY_THRESHOLD: float = 60.0          # keep jobs with score >= this value (0-100)
EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_BATCH_SIZE: int = 64              # batch size for encoding job descriptions

# ---------- Resume ----------
RESUME_PATH: str = "resume.txt"

# ---------- Google Sheets ----------
GOOGLE_SHEET_NAME: str = "Job Matches"
GOOGLE_SERVICE_ACCOUNT_FILE: str = "service_account.json"

# ---------- Networking ----------
REQUEST_TIMEOUT: int = 30                   # seconds
