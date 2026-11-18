# DATAPILOT â€” AI-Assisted Data Analytics Platform

A complete, working B.Tech major project. Upload a dataset, profile it, clean it, explore it, run real
statistical tests, ask questions in plain English, and download a PDF report.

**No paid APIs. No AI provider required. No fabricated numbers.**

---

## 1. What it does

| # | Module | Implementation |
|---|--------|----------------|
| 1 | Auth & Project Management | PBKDF2-HMAC-SHA256 passwords, JWT sessions, per-user project/dataset isolation |
| 2 | Data Upload | CSV, TSV, XLSX, XLSM, JSON, NDJSON Â· encoding + separator sniffing Â· up to 100 MB |
| 3 | Automated Profiling | Type inference, missing values, duplicates, quartiles, IQR outliers, quality score |
| 4 | Data Cleaning | Imputation, dedupe, type correction, outlier handling â€” always as a **new version** |
| 5 | EDA | Histogram, bar, pie, scatter, box, line/trend, grouped aggregate, correlation heatmap |
| 6 | Statistical Analysis | Pearson, Spearman, Welch t-test, paired t-test, one-sample t, chi-square, ANOVA, CI, Shapiro-Wilk |
| 7 | Natural Language Analyst | Rule-based engine (mandatory) + optional local Ollama LLM |
| 8 | Dashboard | KPI payload computed live from the active dataset version |
| 9 | Reports | Server-side PDF (ReportLab, 9 sections, embedded charts) + standalone HTML |
| 10 | Database | SQLAlchemy 2.0 â€” SQLite locally, PostgreSQL in production, same models |
| 11 | Testing | 205 backend tests + end-to-end HTTP acceptance test |
| 12 | Documentation | This file |

---

## 2. Technology stack

**Backend** â€” Python 3.10+, FastAPI, Uvicorn, SQLAlchemy 2.0, Pydantic v2, Pandas, NumPy, SciPy,
Scikit-learn, ReportLab, matplotlib (Agg), pyarrow, PyJWT.
**Frontend** â€” React 18, TypeScript, Tailwind CSS 3, Recharts, React Router 6, Vite 5.
**Database** â€” SQLite by default (zero setup). PostgreSQL by changing one environment variable.
**AI** â€” optional local [Ollama](https://ollama.com) (`llama3.2`, `qwen2.5`, â€¦). Entirely optional.

Every dependency is free and open source. No API keys, no billing, no cloud account.

---

## 3. Install on Windows

### 3.1 Prerequisites

1. **Python 3.10 or newer** â€” <https://www.python.org/downloads/>
   During setup, tick **â€œAdd python.exe to PATHâ€**. Verify in a new terminal:
   ```bat
   python --version
   ```
2. **Node.js 18 or newer** â€” <https://nodejs.org/> (LTS installer). Verify:
   ```bat
   node --version
   ```

### 3.2 Backend

From the folder containing `backend\` and `frontend\`:

```bat
cd backend
python -m venv venv
venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

Start it:

```bat
uvicorn app.main:app --reload --port 8000
```

Leave this terminal open. The API is now at <http://127.0.0.1:8000>
Interactive docs: <http://127.0.0.1:8000/docs>

The database file and report folder are created automatically on first run â€” **no database
installation is required**.

### 3.3 Frontend

Open a **second** terminal:

```bat
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. Register an account and start uploading.

> The Vite dev server proxies `/api` to `127.0.0.1:8000`, so both terminals must be running.

### 3.4 Optional: enable the local LLM

```bat
winget install Ollama.Ollama
ollama pull llama3.2
ollama serve
```

Restart the backend. The â€œAsk DATAPILOTâ€ tab will show *Local LLM (Ollama)* instead of
*Rule-based engine*. If Ollama is not running, **everything still works** â€” the rule-based engine
answers every question.

### 3.5 Verify the install

```bat
cd backend
python -m pytest tests\ -q
```

Expect `205 passed`.

---

## 4. Run on macOS / Linux

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# second terminal
cd frontend && npm install && npm run dev
```

---

## 5. Using PostgreSQL instead of SQLite

Create a database, then set one variable in `backend/.env`:

```ini
DATAPILOT_DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/datapilot
```

Install the driver (`pip install psycopg2-binary`) and restart. Tables are created automatically.
No model or code changes needed.

---

## 6. Configuration (`backend/.env`)

Copy `backend/.env.example` to `backend/.env`. Every value has a working default.

| Variable | Default | Purpose |
|---|---|---|
| `DATAPILOT_DATABASE_URL` | `sqlite:///backend/data/datapilot.db` | Database connection |
| `DATAPILOT_SECRET_KEY` | auto-generated | JWT signing key â€” set this in production |
| `DATAPILOT_MAX_UPLOAD_MB` | `100` | Upload size ceiling |
| `DATAPILOT_OLLAMA_ENABLED` | `true` | Allow local LLM usage |
| `DATAPILOT_OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama endpoint |
| `DATAPILOT_OLLAMA_MODEL` | `llama3.2` | Model name |

---

## 7. How the natural-language engine works

```
question
   â†’ intent identification      (19 whitelisted intents)
   â†’ column identification      (normalised tokens + plural stemming)
   â†’ validated operation        (unknown columns/types rejected)
   â†’ Pandas / NumPy / SciPy     (the only place numbers are produced)
   â†’ independent recomputation  (mismatch â‡’ result withheld)
   â†’ plain-language explanation
```

Hard guarantees, enforced by tests:

* The LLM **never computes** a number. It may only choose which operation runs and re-word the result.
* Any LLM-proposed column that does not exist is discarded and the rule-based path is used.
* New numeric tokens appearing in LLM prose that are absent from the computed facts are rejected.
* **No `eval`, `exec`, generated Python or generated SQL anywhere** â€” verified by `test_nlp.py`.
* Unsupported questions return an honest refusal plus the list of formats that *are* supported.
* Every answer shows which engine produced it: `Local LLM (Ollama)` or `Rule-based engine`.

Example questions you can ask:

```
How many rows are there?
Which region has the highest total revenue?
What is the average satisfaction_score by customer_segment?
Show top 5 products by sum of revenue
What is the correlation between units_sold and revenue?
Is revenue normally distributed?
What is the distribution of unit_price?
```

---

## 8. Data quality score (documented, not arbitrary)

`score = 0.40Â·completeness + 0.25Â·uniqueness + 0.20Â·validity + 0.15Â·outlier_health`

| Component | Definition |
|---|---|
| completeness | `100 Ã— (1 âˆ’ missing_cells / total_cells)` |
| uniqueness | `100 Ã— (1 âˆ’ duplicate_rows / total_rows)` |
| validity | `100 Ã— (1 âˆ’ uncoercible_typed_cells / typed_cells)` |
| outlier_health | `100 Ã— (1 âˆ’ IQR_outlier_cells / numeric_cells)` |

Grades: A â‰¥ 90, B â‰¥ 80, C â‰¥ 70, D â‰¥ 60, F below 60. The formula and each component are returned
with every profile so the number is always explainable.

---

## 9. Versioning model

The uploaded file is written once as raw bytes plus a Parquet snapshot and **never modified**.
Every cleaning plan creates a new `DatasetVersion` row and a new Parquet file. Undo simply re-points
`current_version_id` â€” history is never rewritten, and the original is always recoverable.

---

## 10. Project layout

```
backend/
  app/
    main.py              FastAPI app, CORS, routers, /api/health
    config.py            Settings + .env loader
    database.py          Engine, SessionLocal, SQLite PRAGMAs
    models.py            10 ORM tables
    schemas.py           Pydantic v2 request/response models
    security.py          PBKDF2 hashing + JWT
    deps.py              Auth, ownership and version dependencies
    routers/             auth, projects, datasets, profiling, cleaning,
                         analysis, analyst, reports
    services/
      ingest.py          CSV/TSV/XLSX/JSON parsing, Parquet snapshots
      type_inference.py  Kind detection and safe coercion
      profiling.py       Profiling + quality score + findings
      cleaning.py        Cleaning engine (immutable)
      statistics_engine.py  SciPy tests with assumptions + limitations
      eda.py             Chart data builders
      reports.py         ReportLab PDF + HTML
      nlp/               rule_engine, executor, ollama_client, analyst
  tests/                 205 tests
  data/                  datapilot.db, snapshots/, reports/  (git-ignored)
frontend/
  src/
    App.tsx, main.tsx
    lib/        api.ts (typed client), auth.tsx
    components/ shell.tsx, ui.tsx, chart.tsx
    pages/      auth, projects, profile, clean, explore, stats, analyst, reports
sample_data/            5 deterministic datasets
```

---

## 11. API reference (all under `/api`)

**Auth** â€” `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`
**Projects** â€” `GET|POST /projects`, `GET|PATCH|DELETE /projects/{id}`
**Datasets** â€” `POST /datasets/upload`, `GET /datasets`, `GET|PATCH|DELETE /datasets/{id}`,
`GET /datasets/{id}/preview`, `GET /datasets/{id}/versions`,
`POST /datasets/{id}/versions/{vid}/activate`, `GET /datasets/{id}/download`
**Profiling** â€” `GET /datasets/{id}/profile`, `/findings`, `/quality`, `/columns`
**Cleaning** â€” `GET /datasets/{id}/cleaning/recommendations`, `POST .../cleaning/preview`,
`POST .../cleaning/apply`, `GET .../cleaning/history`, `POST .../cleaning/undo/{action_id}`
**Analysis** â€” `GET /datasets/{id}/charts/suggestions`, `POST /datasets/{id}/charts`,
`GET /datasets/{id}/statistics/descriptive`, `POST .../statistics/test`,
`POST .../statistics/confidence-interval`, `POST .../statistics/correlations`,
`GET .../statistics/normality`, `GET /datasets/{id}/analysis/history`
**Analyst** â€” `GET /llm/status`, `GET /datasets/{id}/query/suggestions`, `POST /datasets/{id}/query`,
`GET /datasets/{id}/conversations`, `GET /conversations/{id}`
**Reports** â€” `POST /datasets/{id}/reports`, `GET /datasets/{id}/reports`,
`GET /reports/{uid}/download`, `DELETE /reports/{uid}`
**Dashboard** â€” `GET /datasets/{id}/dashboard`

Full interactive documentation with schemas: <http://127.0.0.1:8000/docs>

---

## 12. Sample datasets (`sample_data/`)

Regenerate at any time with `python sample_data/generate_samples.py` (deterministic, seed 42).

| File | Size | Purpose |
|---|---|---|
| `sales_data.csv` | 588 Ã— 9 | Missing values, 12 duplicate rows, 6 outliers, `$`-formatted text column |
| `iris.csv` | 150 Ã— 3 | Clean reference dataset |
| `employees.json` | 120 records | JSON record-array upload path |
| `inventory.xlsx` | 2 sheets | Excel multi-sheet handling |
| `tiny_known.csv` | 10 Ã— 5 | Hand-checkable values for verifying statistics |

Upload `sales_data.csv` first â€” it exercises every module in one pass.

---

## 13. Verified acceptance run

Executed against a live Uvicorn server with the real `sales_data.csv`:

```
register                    201 Created
session hydrate             PASS
upload CSV                  588 rows Ã— 9 cols
profile computed            quality 95.64 (A), 64 missing cells
cleaning applied            588 â†’ 576 rows (duplicates removed), new version v2
original preserved          PASS
quality improved            95.64 â†’ 99.66
chart aggregates            4 regions, total revenue 12,834,329
pearson                     r = 0.2303, p = 2.25279e-08
anova                       F = 3.903909, p = 0.008872
NL grouped extreme          group_extreme â†’ "North has the highest sum of revenue at 3.777e+06"
NL row count                row_count
NL correlation              correlation_pair
unsupported question        refused honestly + supported examples returned
dashboard KPIs              rows = 576 (matches cleaned version)
report generated            pdf
PDF downloaded              213,264 bytes, %PDF magic verified
undo restores version       PASS
```

Backend unit/integration suite: **205 passed**.

---

## 14. Known limitations (stated honestly)

* The rule-based engine handles 19 intents. Anything outside them is refused with guidance â€” by design.
* PDF charts are rendered with matplotlib, so they are static images, not interactive.
* Statistical tests assume the usual preconditions; each response lists its own assumptions and
  limitations so results are never presented as unconditional.
* The app is a single-user development deployment: no rate limiting, no email verification, no
  multi-tenant hardening. Add those before exposing it to the public internet.
* First upload of a large file is slower than later reads because Parquet snapshots are written eagerly.

---

## 15. Production notes

```bash
pip install uvicorn[standard]
export DATAPILOT_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
export DATAPILOT_DATABASE_URL="postgresql+psycopg2://..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
cd frontend && npm run build   # serve dist/ behind Nginx with /api proxied
```

Never commit `backend/.env`, `backend/data/`, or `frontend/dist/`.

---

MIT licensed. Built as a final-year B.Tech major project.

