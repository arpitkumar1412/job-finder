# Job Matching Agent — Phase 1

Automated pipeline that fetches job postings from **Greenhouse** and **Lever**, computes **cosine similarity** against your resume using sentence-transformers, and stores matching results in **Google Sheets**.

---

## Project Structure

```
job-agent/
├── main.py                  # Entry-point – runs the full pipeline
├── fetchers/
│   ├── greenhouse.py        # Greenhouse Boards API fetcher
│   └── lever.py             # Lever Postings API fetcher
├── matcher/
│   └── similarity.py        # Embedding + cosine similarity logic
├── sheets/
│   └── sheets_writer.py     # Google Sheets writer (gspread)
├── config.py                # All tuneable settings in one place
├── requirements.txt         # Python dependencies
├── resume.txt               # Your plain-text resume (edit this!)
└── README.md                # This file
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11+ |
| pip | latest |

---

## 1. Clone & Install

```bash
git clone https://github.com/<your-username>/job-agent.git
cd job-agent
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 2. Google Sheets API Setup

### 2.1 Create a Google Cloud project
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or select an existing one).

### 2.2 Enable APIs
1. Navigate to **APIs & Services → Library**.
2. Search for and enable:
   - **Google Sheets API**
   - **Google Drive API**

### 2.3 Create a Service Account
1. Go to **APIs & Services → Credentials**.
2. Click **Create Credentials → Service Account**.
3. Name it (e.g. `job-agent-sa`) and click **Done**.
4. Under the newly created service account, go to **Keys → Add Key → Create new key → JSON**.
5. Download the JSON file and save it as **`service_account.json`** in the project root.

### 2.4 Share the Sheet
1. Create a Google Sheet named **"Job Matches"** (or whatever `config.GOOGLE_SHEET_NAME` is set to).
2. Share the sheet with the service account email found in your JSON key file (`client_email` field) — give it **Editor** access.

---

## 3. Configure

Edit **`config.py`** to customise:

| Setting | Description |
|---|---|
| `GREENHOUSE_COMPANIES` | List of Greenhouse board slugs to scrape |
| `LEVER_COMPANIES` | List of Lever company slugs to scrape |
| `SIMILARITY_THRESHOLD` | Minimum similarity score (0–100) to keep a match |
| `RESUME_PATH` | Path to your plain-text resume |
| `GOOGLE_SHEET_NAME` | Name of the Google Sheet to write results to |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | Path to the service account JSON key |

---

## 4. Add Your Resume

Replace the placeholder content in **`resume.txt`** with your full resume in plain text.

---

## 5. Run

```bash
python main.py
```

The pipeline will:
1. Load your resume.
2. Fetch jobs from all configured Greenhouse & Lever boards.
3. Compute cosine similarity using `all-MiniLM-L6-v2` embeddings.
4. Filter jobs above the configured threshold.
5. Append matching rows to Google Sheets.
6. Print a summary with your top matches.

---

## How It Works

```
resume.txt ──►┐
               ├─► sentence-transformers ─► cosine similarity ─► filter ─► Google Sheets
API jobs ─────►┘
```

- **Embedding model**: `sentence-transformers/all-MiniLM-L6-v2` (fast, 384-dim vectors)
- **Batch processing**: job descriptions are embedded in configurable batches
- **Resume is embedded once** and reused across all comparisons
- **HTML stripped** from job descriptions before embedding
- **Rows are appended** to the sheet — existing data is never overwritten

---

## Notes

- The Greenhouse and Lever public APIs require **no authentication**.
- If a company's board is private or returns an error, it is logged and skipped gracefully.
- The first run will download the embedding model (~80 MB) and cache it locally.

---

## License

MIT
