from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.agents.schemas import (
    AgentState,
    GapAssessment,
    Intent,
    RequirementInterpretation,
    SupervisorDecision,
)


class TestIntent:
    def test_all_values(self) -> None:
        assert Intent.COMPLIANCE_CHECK == "compliance_check"
        assert Intent.GAP_ANALYSIS == "gap_analysis"
        assert Intent.REPORT_GENERATION == "report_generation"
        assert Intent.GENERAL_QUESTION == "general_question"

    def test_from_string(self) -> None:
        assert Intent("gap_analysis") == Intent.GAP_ANALYSIS


class TestAgentState:
    def test_defaults(self) -> None:
        state = AgentState(query="test")
        assert state.query == "test"
        assert state.intent is None
        assert state.regulation_refs == []
        assert state.policy_refs == []
        assert state.interpretations == []
        assert state.gap_assessments == []
        assert state.response == ""
        assert state.error is None

    def test_full_state(self) -> None:
        state = AgentState(
            query="test",
            intent=Intent.GAP_ANALYSIS,
            regulation_refs=["GDPR-Art17"],
            policy_refs=["policy1"],
        )
        assert state.intent == Intent.GAP_ANALYSIS
        assert len(state.regulation_refs) == 1


class TestSupervisorDecision:
    def test_serialization(self) -> None:
        decision = SupervisorDecision(
            intent=Intent.COMPLIANCE_CHECK,
            reasoning="test reason",
            regulation_refs=["GDPR-Art5"],
        )
        data = decision.model_dump()
        assert data["intent"] == "compliance_check"
        assert data["reasoning"] == "test reason"
        assert data["regulation_refs"] == ["GDPR-Art5"]


class TestRequirementInterpretation:
    def test_valid(self) -> None:
        interp = RequirementInterpretation(
            regulation_id="GDPR-Art17",
            framework="GDPR",
            article="Art17",
            plain_language_summary="Right to erasure",
            operational_meaning="Must delete data on request",
            evidence_of_compliance="Deletion records",
        )
        assert interp.regulation_id == "GDPR-Art17"
        assert interp.key_terms == []
        assert interp.citations == []

    def test_with_optional_fields(self) -> None:
        interp = RequirementInterpretation(
            regulation_id="GDPR-Art17",
            framework="GDPR",
            article="Art17",
            plain_language_summary="summary",
            operational_meaning="meaning",
            evidence_of_compliance="evidence",
            key_terms=["erasure", "controller"],
            related_requirements=["GDPR-Art12"],
            citations=[{"source": "test"}],
        )
        assert len(interp.key_terms) == 2
        assert len(interp.citations) == 1


class TestGapAssessment:
    def test_valid_confidence(self) -> None:
        gap = GapAssessment(
            requirement_id="GDPR-Art17",
            policy_id="policy1",
            status="partial",
            explanation="test",
            confidence_score=0.85,
        )
        assert gap.confidence_score == 0.85

    def test_confidence_bounds(self) -> None:
        with pytest.raises(ValidationError):
            GapAssessment(
                requirement_id="test",
                policy_id="test",
                status="compliant",
                explanation="test",
                confidence_score=1.5,
            )

        with pytest.raises(ValidationError):
            GapAssessment(
                requirement_id="test",
                policy_id="test",
                status="compliant",
                explanation="test",
                confidence_score=-0.1,
            )

    def test_edge_values(self) -> None:
        gap_zero = GapAssessment(
            requirement_id="t", policy_id="t", status="compliant",
            explanation="t", confidence_score=0.0,
        )
        gap_one = GapAssessment(
            requirement_id="t", policy_id="t", status="compliant",
            explanation="t", confidence_score=1.0,
        )
        assert gap_zero.confidence_score == 0.0
        assert gap_one.confidence_score == 1.0
