"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
class SignupRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=160)
    password: str = Field(min_length=8, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    created_at: datetime
    last_login_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --------------------------------------------------------------------------
# Projects
# --------------------------------------------------------------------------
class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None


class DatasetSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: str
    name: str
    original_filename: str
    source_format: str
    file_size_bytes: int
    row_count: int | None = None
    column_count: int | None = None
    quality_score: float | None = None
    version_count: int = 0
    created_at: datetime


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: str
    name: str
    description: str
    created_at: datetime
    updated_at: datetime
    datasets: list[DatasetSummary] = []


# --------------------------------------------------------------------------
# Datasets
# --------------------------------------------------------------------------
class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_number: int
    label: str
    row_count: int
    column_count: int
    column_names: list[Any]
    dtypes: dict[str, Any]
    quality_score: float | None
    is_original: bool
    parent_version_id: int | None
    created_at: datetime


class DatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: str
    project_id: int
    name: str
    original_filename: str
    source_format: str
    file_size_bytes: int
    current_version_id: int | None
    created_at: datetime
    updated_at: datetime
    versions: list[VersionOut] = []


class DatasetRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


# --------------------------------------------------------------------------
# Cleaning
# --------------------------------------------------------------------------
ImputeStrategy = Literal["mean", "median", "mode", "drop_rows", "constant"]
OutlierStrategy = Literal["remove", "clip", "cap_percentile", "none"]


class MissingValueStep(BaseModel):
    column: str
    strategy: ImputeStrategy
    constant_value: Any | None = None


class TypeCorrectionStep(BaseModel):
    column: str
    target_type: Literal["numeric", "datetime", "category", "string", "boolean"]


class OutlierStep(BaseModel):
    column: str
    strategy: OutlierStrategy = "clip"
    multiplier: float = 1.5


class CleaningPlan(BaseModel):
    """A user-approved, explicit cleaning plan.

    Nothing is applied until this plan is submitted, so the user always approves
    changes before they touch the data. The original version is never modified.
    """

    missing_values: list[MissingValueStep] = []
    drop_duplicates: bool = False
    duplicate_subset: list[str] | None = None
    type_corrections: list[TypeCorrectionStep] = []
    outliers: list[OutlierStep] = []
    trim_whitespace: bool = False
    drop_constant_columns: bool = False
    drop_empty_columns: bool = False
    label: str = "Cleaning step"


class CleaningPreviewRequest(CleaningPlan):
    pass


class CleaningActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    dataset_id: int
    source_version_id: int
    result_version_id: int
    operation: str
    parameters: dict[str, Any]
    summary: str
    metrics_before: dict[str, Any]
    metrics_after: dict[str, Any]
    is_undone: bool
    created_at: datetime


# --------------------------------------------------------------------------
# Analysis / charts
# --------------------------------------------------------------------------
class ChartRequest(BaseModel):
    chart_type: Literal[
        "histogram",
        "bar",
        "pie",
        "scatter",
        "box",
        "line",
        "correlation_heatmap",
        "grouped_aggregate",
    ]
    x: str | None = None
    y: str | None = None
    group_by: str | None = None
    agg: Literal["mean", "sum", "count", "median", "min", "max"] = "mean"
    bins: int = 20
    top_n: int = 10
    version_id: int | None = None


class StatisticalTestRequest(BaseModel):
    test: Literal["pearson", "spearman", "ttest_ind", "ttest_rel", "ttest_1samp", "chi_square", "anova"]
    x: str | None = None
    y: str | None = None
    group_column: str | None = None
    group_a: str | None = None
    group_b: str | None = None
    all_groups: bool = False
    popmean: float | None = None
    alpha: float = 0.05
    version_id: int | None = None


class ConfidenceIntervalRequest(BaseModel):
    column: str
    confidence: float = 0.95
    version_id: int | None = None


class CorrelationRequest(BaseModel):
    method: Literal["pearson", "spearman"] = "pearson"
    columns: list[str] | None = None
    version_id: int | None = None


# --------------------------------------------------------------------------
# Natural language analyst
# --------------------------------------------------------------------------
class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: int | None = None
    prefer_llm: bool = True
    version_id: int | None = None


class QueryResponse(BaseModel):
    answer: str
    engine: Literal["llm", "rule_based"]
    engine_label: str
    intent: str
    operation: dict[str, Any]
    result: dict[str, Any]
    explanation: str
    conversation_id: int
    message_id: int
    supported_examples: list[str] = []
    warnings: list[str] = []
    chart: dict[str, Any] | None = None


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    engine: str
    intent: str | None
    payload: dict[str, Any] | None
    model_name: str | None
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: str
    dataset_id: int
    title: str
    created_at: datetime
    messages: list[ChatMessageOut] = []


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------
class ReportRequest(BaseModel):
    fmt: Literal["pdf", "html"] = "pdf"
    title: str = "DataPilot Analysis Report"
    include_charts: bool = True
    include_statistics: bool = True
    include_conversation: bool = True
    conversation_id: int | None = None
    version_id: int | None = None


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    uid: str
    dataset_id: int
    version_id: int
    title: str
    fmt: str
    created_at: datetime


# --------------------------------------------------------------------------
# Misc
# --------------------------------------------------------------------------
class LlmStatus(BaseModel):
    enabled: bool
    available: bool
    base_url: str
    model: str
    models: list[str] = []
    message: str

