# DATAPILOT — AI-Assisted Data Analytics Platform

A complete, working B.Tech major project for end-to-end data analytics. Upload datasets, generate profiles, clean data, explore visualizations, perform statistical tests, ask questions in natural language, and download PDF reports.

**No paid APIs. No external AI provider required. No fabricated results.**

---

## 1. Features and Modules

| # | Module | Implementation |
|---|---|---|
| 1 | Authentication & Project Management | PBKDF2-HMAC-SHA256 password hashing, JWT sessions, and per-user project and dataset isolation |
| 2 | Data Upload | CSV, TSV, XLSX, XLSM, JSON, and NDJSON support, with encoding and separator detection; up to 100 MB |
| 3 | Automated Profiling | Data type inference, missing values, duplicates, quartiles, IQR-based outlier detection, and data quality scoring |
| 4 | Data Cleaning | Imputation, duplicate removal, type correction, and outlier handling. Changes are saved as new dataset versions |
| 5 | Exploratory Data Analysis (EDA) | Histograms, bar charts, pie charts, scatter plots, box plots, line charts, grouped aggregates, and correlation heatmaps |
| 6 | Statistical Analysis | Pearson and Spearman correlation, Welch's t-test, paired t-test, one-sample t-test, chi-square, ANOVA, confidence intervals, and Shapiro-Wilk |
| 7 | Natural Language Analyst | Rule-based query engine with optional local Ollama LLM integration |
| 8 | Dashboard | Live KPI calculations based on the active dataset version |
| 9 | Reports | Server-generated PDF reports using ReportLab, with nine sections and embedded charts, plus standalone HTML reports |
| 10 | Database | SQLAlchemy 2.0 with SQLite for local development and PostgreSQL support for production |
| 11 | Testing | 205 backend tests and an end-to-end HTTP acceptance test |
| 12 | Documentation | Setup instructions, project details, and technical documentation |

---

## 2. Technology Stack

**Backend:** Python 3.10+, FastAPI, Uvicorn, SQLAlchemy 2.0, Pydantic v2, Pandas, NumPy, SciPy, Scikit-learn, ReportLab, Matplotlib (Agg), PyArrow, and PyJWT.

**Frontend:** React 18, TypeScript, Tailwind CSS 3, Recharts, React Router 6, and Vite 5.

**Database:** SQLite by default, with PostgreSQL support through an environment variable.

**AI Integration:** Optional local [Ollama](https://ollama.com/) integration supporting models such as `llama3.2` and `qwen2.5`. The application works without an external AI provider.

All project dependencies are free and open source. The core application does not require paid APIs or API keys.

---

## 3. Installation on Windows

### 3.1 Prerequisites

Install the following:

1. **Python 3.10 or newer** — [Download Python](https://www.python.org/downloads/)

   During installation, enable **Add Python to PATH**.

   Verify the installation:

   ```bash
   python --version
   ```

2. **Node.js 18 or newer** — [Download Node.js](https://nodejs.org/)

   Verify the installation:

   ```bash
   node --version
   ```

### 3.2 Backend Setup

Open a terminal in the project root directory, where the `backend` and `frontend` folders are located.

Navigate to the backend:

```bash
cd backend
```

Create and activate a virtual environment:

```bash
python -m venv venv
venv\Scripts\activate
```

Upgrade pip and install the dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3.3 Start the Backend

Run the following command from the `backend` directory:

```bash
uvicorn app.main:app --reload --port 8000
```

The backend API will be available at:

- API: http://127.0.0.1:8000
- API documentation: http://127.0.0.1:8000/api/docs

Keep the backend terminal running while using the application.

---

## 4. Frontend Setup

Open a second terminal in the project root:

```bash
cd frontend
npm install
npm run dev
```

Open the local development URL displayed by Vite in your terminal.

---

## 5. Optional Local AI Integration

DATAPILOT includes a rule-based natural language query engine and can optionally integrate with a locally running Ollama instance.

The core application does not depend on Ollama or a paid AI service.

Refer to the environment configuration in `backend/.env.example` for the available settings.

---

## 6. Project Goals

DATAPILOT brings data ingestion, profiling, cleaning, exploration, statistical analysis, natural-language querying, and reporting together in one application.

Its goal is to make analytical workflows more accessible, reproducible, and easier to understand.
