from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Intent(StrEnum):
    COMPLIANCE_CHECK = "compliance_check"
    GAP_ANALYSIS = "gap_analysis"
    REPORT_GENERATION = "report_generation"
    GENERAL_QUESTION = "general_question"


class RequirementInterpretation(BaseModel):
    regulation_id: str = Field(description="Regulation reference, e.g. GDPR-Art17")
    framework: str = Field(description="Framework name, e.g. GDPR")
    article: str = Field(description="Article identifier")
    plain_language_summary: str = Field(
        description="What this requirement means in plain language"
    )
    operational_meaning: str = Field(
        description="What this means operationally for an organization"
    )
    evidence_of_compliance: str = Field(
        description="What evidence of compliance looks like"
    )
    key_terms: list[str] = Field(default_factory=list, description="Key legal terms defined")
    related_requirements: list[str] = Field(
        default_factory=list, description="Related regulation references"
    )
    citations: list[dict[str, Any]] = Field(
        default_factory=list, description="Source citations from MCP"
    )


class GapAssessment(BaseModel):
    requirement_id: str
    policy_id: str
    status: str = Field(description="compliant, partial, or non-compliant")
    explanation: str = Field(description="Detailed reasoning for the assessment")
    regulation_evidence: list[str] = Field(
        default_factory=list, description="Relevant regulation excerpts"
    )
    policy_evidence: list[str] = Field(
        default_factory=list, description="Relevant policy excerpts"
    )
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence in the assessment")
    citations: list[dict[str, Any]] = Field(default_factory=list)


class SupervisorDecision(BaseModel):
    intent: Intent
    reasoning: str = Field(description="Why this intent was chosen")
    regulation_refs: list[str] = Field(
        default_factory=list, description="Extracted regulation references"
    )
    policy_refs: list[str] = Field(
        default_factory=list, description="Extracted policy references"
    )


class AgentState(BaseModel):
    """Typed state flowing through the LangGraph StateGraph."""

    query: str = Field(description="Original user query")
    intent: Intent | None = None
    supervisor_decision: SupervisorDecision | None = None
    regulation_refs: list[str] = Field(default_factory=list)
    policy_refs: list[str] = Field(default_factory=list)
    interpretations: list[RequirementInterpretation] = Field(default_factory=list)
    gap_assessments: list[GapAssessment] = Field(default_factory=list)
    report_sections: list[dict[str, Any]] = Field(default_factory=list)
    remediation_tasks: list[dict[str, Any]] = Field(default_factory=list)
    response: str = ""
    error: str | None = None
