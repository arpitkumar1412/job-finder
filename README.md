# Job Matching Agent

Automated pipeline that fetches job postings, scores them with **Gemini**, tailors a **LaTeX resume** per match using **Claude**, compiles to PDF, uploads to **Google Drive**, and logs everything to **Google Sheets**.

---

## Project Structure

```
job-agent/
├── main.py                  # Entry-point – runs the 5-step pipeline
├── config.py                # All tuneable settings in one place
├── requirements.txt         # Python dependencies
├── resume_template.tex      # LaTeX resume template (1 page)
├── resume.cls               # Custom LaTeX class for the resume
├── fetchers/
│   ├── greenhouse.py        # Greenhouse Boards API fetcher
│   └── lever.py             # Lever Postings API fetcher
├── matcher/
│   └── similarity.py        # Regex pre-filter + Gemini rubric scoring
├── resume/
│   ├── tailor.py            # Claude-based LaTeX resume customisation
│   ├── compiler.py          # pdflatex compilation (.tex → PDF)
│   └── drive_uploader.py    # Google Drive upload (OAuth2)
├── sheets/
│   └── sheets_writer.py     # Google Sheets writer (gspread)
└── README.md
```

---

## Pipeline Overview

```
Greenhouse / Lever APIs
        │
        ▼
  1. Fetch jobs ──► 2. Gemini scoring (rubric 0-100)
                              │
                    ┌─────────┴─────────┐
                    │  APPLY (≥ 60)     │  SKIP (< 60)
                    ▼                   ▼
          3. Claude tailors       (discarded)
             LaTeX resume
                    │
                    ▼
          4. pdflatex → PDF
                    │
                    ▼
          5. Upload to Google Drive
                    │
                    ▼
          6. Write to Google Sheets
             (score, link, resume URL)
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | |
| pdflatex | any | MiKTeX or TeX Live |
| GCP project | — | Sheets API + Drive API enabled |

---

## 1. Clone & Install

```bash
git clone https://github.com/arpitkumar1412/job-finder.git
cd job-finder
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 2. API Keys

The pipeline needs two LLM API keys passed as environment variables:

| Variable | Service | Free tier? |
|---|---|---|
| `GEMINI_API_KEY` | Google Gemini (job scoring) | Yes — gemini-2.5-flash-lite |
| `ANTHROPIC_API_KEY` | Anthropic Claude (resume tailoring) | No — ~$3/M input tokens |

```powershell
# Windows PowerShell
$env:GEMINI_API_KEY = "your-gemini-key"
$env:ANTHROPIC_API_KEY = "your-anthropic-key"
```

```bash
# macOS / Linux
export GEMINI_API_KEY="your-gemini-key"
export ANTHROPIC_API_KEY="your-anthropic-key"
```

---

## 3. Google Cloud Setup

### 3.1 Enable APIs

In your [GCP Console](https://console.cloud.google.com/), enable:
- **Google Sheets API**
- **Google Drive API**

### 3.2 Service Account (for Sheets)

1. **APIs & Services → Credentials → Create Credentials → Service Account**.
2. Download the JSON key and save as **`service_account.json`** in the project root.
3. Create a Google Sheet named **"Job Matches"**.
4. Share the sheet with the service account's `client_email` (Editor access).

### 3.3 OAuth2 Client (for Drive uploads)

1. **APIs & Services → Credentials → Create Credentials → OAuth client ID → Desktop app**.
2. Download the JSON and save as **`client_secret.json`** in the project root.
3. On the **OAuth consent screen**, add your email as a test user.
4. On first run, a browser window will open for authorisation. The token is cached in `drive_token.json`.

---

## 4. Configure

Edit **`config.py`**:

| Setting | Default | Description |
|---|---|---|
| `GREENHOUSE_COMPANIES` | airbnb, figma, stripe, cloudflare | Company board slugs to scrape |
| `LEVER_COMPANIES` | _(empty)_ | Lever company slugs |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Gemini model for scoring |
| `GEMINI_BATCH_SIZE` | 10 | Jobs per Gemini API call |
| `GEMINI_RATE_LIMIT_PAUSE` | 30.0 | Seconds between Gemini batches |
| `SCORE_THRESHOLD` | 60 | Minimum score (0-100) to keep a job |
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Claude model for resume tailoring |
| `RESUME_TEMPLATE` | `resume_template.tex` | Your LaTeX resume source |
| `RESUME_CLS` | `resume.cls` | LaTeX class file |
| `DRIVE_ROOT_FOLDER_ID` | _(your folder ID)_ | Google Drive folder for resumes |
| `GOOGLE_SHEET_NAME` | `Job Matches` | Target Google Sheet name |

---

## 5. Resume Template

Place your LaTeX resume as `resume_template.tex` and the class file as `resume.cls` in the project root. The template must:

- Compile with `pdflatex` (no XeLaTeX / LuaLaTeX dependencies)
- Fit on **exactly 1 page**
- Use ASCII characters (no Unicode minus, em-dash, etc.)

---

## 6. Run

```bash
python main.py
```

The pipeline will:
1. **Fetch** jobs from all configured Greenhouse & Lever boards.
2. **Score** each job with Gemini using a rubric (backend relevance, title match, seniority, tech stack).
3. **Tailor** a LaTeX resume per APPLY-recommended job using Claude (with prompt caching + batch API for cost savings).
4. **Compile** each tailored `.tex` to PDF via `pdflatex`.
5. **Upload** PDFs to Google Drive (per-company subfolders).
6. **Write** results to Google Sheets (score, sub-scores, recommendation, resume link).

---

## Cost Optimisation

The Claude resume-tailoring step uses two Anthropic cost-saving features:

| Feature | Saving | How |
|---|---|---|
| **Prompt caching** | ~90% on cached input tokens | System prompt + resume template marked `cache_control: ephemeral` |
| **Message Batches API** | 50% on all tokens | All resume requests submitted as a single batch |

Gemini scoring uses the free-tier `gemini-2.5-flash-lite` model with 30-second spacing between batches.

---

## Scoring Rubric

| Sub-score | Points | What it measures |
|---|---|---|
| `backend_relevance` | 0–40 | How backend-focused the role is |
| `title_relevance` | 0–15 | Title match (SDE, Backend Engineer, etc.) |
| `seniority_match` | 0–15 | Seniority fit (SDE-II / 3-5 yrs) |
| `tech_stack_match` | 0–20 | Overlap with candidate's tech stack |
| `penalty` | 0–10 | Deductions for red flags (PhD required, etc.) |

Jobs scoring ≥ 60 get recommendation **APPLY** and a tailored resume.

---

## Notes

- Greenhouse and Lever public APIs require **no authentication**.
- If a company board is private or returns an error, it is logged and skipped.
- The `drive_token.json` is auto-created on first OAuth2 authorisation.
- Resume PDFs are validated to be exactly 1 page; overflows are logged as warnings.

---

## License

MIT
