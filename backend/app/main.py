"""DataPilot FastAPI application entry point.

Run locally with:
    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import init_db
from .routers import analysis, analyst, auth, cleaning, datasets, profiling, projects, reports

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("datapilot")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_dirs()
    init_db()
    logger.info("DataPilot %s started", settings.APP_VERSION)
    logger.info("Database: %s", settings.DATABASE_URL.split("@")[-1])
    logger.info("Storage:  %s", settings.STORAGE_DIR)
    yield
    logger.info("DataPilot shutting down")


app = FastAPI(
    title="DataPilot API",
    version=settings.APP_VERSION,
    description=(
        "AI-assisted data analytics platform. All statistics are computed from "
        "uploaded data with pandas/NumPy/SciPy. Natural-language questions are "
        "answered by an optional local LLM (Ollama) for intent parsing or by the "
        "built-in rule-based engine — numbers are always computed, never generated."
    ),
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected server error occurred.",
            "error_type": type(exc).__name__,
        },
    )


api_prefix = settings.API_PREFIX

app.include_router(auth.router, prefix=api_prefix)
app.include_router(projects.router, prefix=api_prefix)
app.include_router(datasets.router, prefix=api_prefix)
app.include_router(profiling.router, prefix=api_prefix)
app.include_router(cleaning.router, prefix=api_prefix)
app.include_router(analysis.router, prefix=api_prefix)
app.include_router(analyst.router, prefix=api_prefix)
app.include_router(reports.router, prefix=api_prefix)


@app.get("/api/health", tags=["health"])
def health() -> dict:
    from .services.nlp import ollama_client

    llm = ollama_client.status()
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "sqlite" if settings.DATABASE_URL.startswith("sqlite") else "postgresql",
        "llm": {
            "enabled": llm["enabled"],
            "available": llm["available"],
            "model": llm["model"],
            "message": llm["message"],
        },
        "nl_engine": "llm+rule_based" if llm["available"] else "rule_based",
    }


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/api/docs",
        "health": "/api/health",
    }
