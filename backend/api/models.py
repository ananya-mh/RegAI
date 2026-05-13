from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)


class ChatChunk(BaseModel):
    type: str = "text"
    content: str


# ── Frameworks ───────────────────────────────────────────────────────────────

class FrameworkOut(BaseModel):
    id: uuid.UUID
    name: str
    version: str
    source_url: str | None
    ingested_at: datetime

    model_config = {"from_attributes": True}


class FrameworkStatusOut(BaseModel):
    framework: FrameworkOut
    total_requirements: int
    assessed: int
    compliant: int
    partial: int
    non_compliant: int
    coverage_pct: float


# ── Gaps ─────────────────────────────────────────────────────────────────────

class GapOut(BaseModel):
    id: uuid.UUID
    requirement_id: uuid.UUID
    policy_id: uuid.UUID
    status: str
    explanation: str
    evidence: dict[str, Any] | None
    confidence_score: float
    detected_at: datetime
    requirement_article: str | None = None
    requirement_section: str | None = None
    framework_name: str | None = None
    policy_filename: str | None = None

    model_config = {"from_attributes": True}


class GapListOut(BaseModel):
    gaps: list[GapOut]
    total: int


# ── Remediation ──────────────────────────────────────────────────────────────

class RemediationCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    priority: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    effort_estimate: str | None = None
    assignee: str | None = None


class RemediationTaskOut(BaseModel):
    id: uuid.UUID
    gap_id: uuid.UUID
    title: str
    description: str | None
    priority: str
    effort_estimate: str | None
    assignee: str | None
    status: str
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


# ── Policy Upload ────────────────────────────────────────────────────────────

class PolicyOut(BaseModel):
    id: uuid.UUID
    filename: str
    upload_date: datetime
    parsed_text_path: str | None

    model_config = {"from_attributes": True}


class PolicyUploadOut(BaseModel):
    policy: PolicyOut
    chunks_created: int


# ── Usage / Cost ─────────────────────────────────────────────────────────────

class UsageSummaryOut(BaseModel):
    total_cost: float
    total_input_tokens: int
    total_output_tokens: int
    by_provider: list[ProviderUsageOut]
    by_agent: list[AgentUsageOut]


class ProviderUsageOut(BaseModel):
    provider: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float


class AgentUsageOut(BaseModel):
    agent_name: str | None
    calls: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float


# ── Internal (MCP server) ───────────────────────────────────────────────────

class AnalyzeGapRequest(BaseModel):
    requirement_ref: str
    policy_ref: str


class SearchPoliciesRequest(BaseModel):
    query: str
    filters: dict[str, str | None] | None = None


class GenerateReportSectionRequest(BaseModel):
    framework_id: str | None = None
    gap_id: str | None = None
