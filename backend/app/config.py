"""Application configuration for DataPilot.

All values can be overridden with environment variables or a .env file placed in
the backend/ directory. Nothing here requires a paid service.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # -> backend/
PROJECT_ROOT = BASE_DIR.parent


def _load_dotenv() -> None:
    """Minimal .env loader so we do not need python-dotenv as a hard dependency."""
    for candidate in (BASE_DIR / ".env", PROJECT_ROOT / ".env"):
        if not candidate.exists():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_load_dotenv()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Runtime settings resolved from the environment."""

    APP_NAME: str = "DataPilot"
    APP_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"

    # --- Database -------------------------------------------------------
    # SQLite is the default so the project runs with zero infrastructure.
    # For PostgreSQL set, e.g.:
    #   postgresql+psycopg2://datapilot:secret@localhost:5432/datapilot
    DATABASE_URL: str = os.getenv(
        "DATAPILOT_DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'data' / 'datapilot.db').as_posix()}",
    )

    # --- Storage --------------------------------------------------------
    DATA_DIR: Path = Path(os.getenv("DATAPILOT_DATA_DIR", str(BASE_DIR / "data")))
    STORAGE_DIR: Path = Path(
        os.getenv("DATAPILOT_STORAGE_DIR", str(BASE_DIR / "data" / "storage"))
    )
    REPORT_DIR: Path = Path(
        os.getenv("DATAPILOT_REPORT_DIR", str(BASE_DIR / "data" / "reports"))
    )
    CHART_CACHE_DIR: Path = Path(
        os.getenv("DATAPILOT_CHART_DIR", str(BASE_DIR / "data" / "charts"))
    )

    # --- Uploads --------------------------------------------------------
    MAX_UPLOAD_MB: int = int(os.getenv("DATAPILOT_MAX_UPLOAD_MB", "100"))
    ALLOWED_EXTENSIONS: tuple[str, ...] = (".csv", ".tsv", ".xlsx", ".xlsm", ".json", ".jsonl", ".ndjson")

    # --- Security -------------------------------------------------------
    SECRET_KEY: str = os.getenv(
        "DATAPILOT_SECRET_KEY",
        "dev-insecure-key-change-me-in-production-8f3a1c9b2e",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("DATAPILOT_TOKEN_EXPIRE_MINUTES", str(60 * 24 * 7))
    )
    ALGORITHM: str = "HS256"

    # --- CORS -----------------------------------------------------------
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "DATAPILOT_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,"
            "http://127.0.0.1:3000,http://localhost:4173,http://127.0.0.1:4173",
        ).split(",")
        if origin.strip()
    ]

    # --- Optional local LLM (Ollama) -----------------------------------
    OLLAMA_ENABLED: bool = _as_bool(os.getenv("DATAPILOT_OLLAMA_ENABLED"), True)
    OLLAMA_BASE_URL: str = os.getenv("DATAPILOT_OLLAMA_URL", "http://127.0.0.1:11434")
    OLLAMA_MODEL: str = os.getenv("DATAPILOT_OLLAMA_MODEL", "llama3.2")
    OLLAMA_TIMEOUT_SECONDS: float = float(os.getenv("DATAPILOT_OLLAMA_TIMEOUT", "12"))

    # --- Analysis limits -------------------------------------------------
    PREVIEW_ROWS: int = 50
    MAX_SCATTER_POINTS: int = 2000
    MAX_CHART_CATEGORIES: int = 30

    def ensure_dirs(self) -> None:
        for directory in (
            self.DATA_DIR,
            self.STORAGE_DIR,
            self.REPORT_DIR,
            self.CHART_CACHE_DIR,
        ):
            directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
