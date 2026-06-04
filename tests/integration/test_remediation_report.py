from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.schemas import AgentState, GapAssessment, Intent, RequirementInterpretation


MOCK_REMEDIATION_JSON = {
    "tasks": [
        {
            "title": "Implement 30-day data deletion SLA",
            "description": "Update data deletion process to comply with GDPR 30-day requirement",
            "priority": "high",
            "effort_estimate": "3-5 days",
        },
        {
            "title": "Add machine-readable export format",
            "description": "Support CSV/JSON export alongside existing PDF",
            "priority": "medium",
            "effort_estimate": "2-3 days",
        },
    ]
}

MOCK_REPORT_JSON = {
    "title": "GDPR Compliance Assessment",
    "executive_summary": "Assessment reveals partial compliance with key gaps in data deletion timelines.",
    "overall_risk_level": "medium",
    "findings": [
        {
            "requirement": "GDPR-Art17",
            "status": "partial",
            "explanation": "Data deletion process exceeds 30-day requirement.",
            "recommendation": "Implement automated deletion with 30-day SLA.",
        }
    ],
    "remediation_roadmap": "Priority: fix deletion timeline, then add export formats.",
}


def _gap(status: str = "partial", confidence: float = 0.85) -> GapAssessment:
    return GapAssessment(
        requirement_id="GDPR-Art17",
        policy_id="data-retention-policy",
        status=status,
        explanation="90-day deletion exceeds 30-day requirement",
        regulation_evidence=["erasure without undue delay"],
        policy_evidence=["processed within 90 days"],
        confidence_score=confidence,
    )


def _state_with_gaps(gaps: list[GapAssessment]) -> AgentState:
    return AgentState(
        query="Check GDPR Art 17 compliance",
        intent=Intent.GAP_ANALYSIS,
        regulation_refs=["GDPR-Art17"],
        policy_refs=["data-retention-policy"],
        interpretations=[
            RequirementInterpretation(
                regulation_id="GDPR-Art17",
                framework="GDPR",
                article="Art17",
                plain_language_summary="Right to erasure",
                operational_meaning="Must delete data within 30 days",
                evidence_of_compliance="Deletion records",
            )
        ],
        gap_assessments=gaps,
    )


class TestRemediationPlanner:
    @pytest.mark.anyio
    async def test_generates_tasks(self) -> None:
        from backend.agents.remediation_planner import plan_remediation

        state = _state_with_gaps([_gap("partial")])

        with patch(
            "backend.agents.remediation_planner.generate_json",
            new_callable=AsyncMock,
            return_value=MOCK_REMEDIATION_JSON,
        ):
            result = await plan_remediation(state)

        assert len(result.remediation_tasks) == 2
        assert result.remediation_tasks[0]["title"] == "Implement 30-day data deletion SLA"
        assert result.remediation_tasks[0]["priority"] == "high"

    @pytest.mark.anyio
    async def test_skips_compliant_gaps(self) -> None:
        from backend.agents.remediation_planner import plan_remediation

        state = _state_with_gaps([_gap("compliant")])

        result = await plan_remediation(state)
        assert len(result.remediation_tasks) == 0

    @pytest.mark.anyio
    async def test_handles_llm_failure(self) -> None:
        from backend.agents.remediation_planner import plan_remediation

        state = _state_with_gaps([_gap("non-compliant")])

        with patch(
            "backend.agents.remediation_planner.generate_json",
            new_callable=AsyncMock,
            side_effect=Exception("LLM unavailable"),
        ):
            result = await plan_remediation(state)

        assert len(result.remediation_tasks) == 1
        assert "Manual review" in result.remediation_tasks[0]["description"]

    @pytest.mark.anyio
    async def test_empty_gaps(self) -> None:
        from backend.agents.remediation_planner import plan_remediation

        state = AgentState(query="test", intent=Intent.GAP_ANALYSIS)
        result = await plan_remediation(state)
        assert len(result.remediation_tasks) == 0


class TestReportWriter:
    @pytest.mark.anyio
    async def test_generates_report(self) -> None:
        from backend.agents.report_writer import write_report

        state = _state_with_gaps([_gap("partial")])
        state.remediation_tasks = [
            {"title": "Fix deletion", "priority": "high", "effort_estimate": "3 days"}
        ]

        with patch(
            "backend.agents.report_writer.generate_json",
            new_callable=AsyncMock,
            return_value=MOCK_REPORT_JSON,
        ):
            result = await write_report(state)

        assert len(result.report_sections) == 1
        assert result.report_sections[0]["overall_risk_level"] == "medium"
        assert result.response
        assert "GDPR" in result.response

    @pytest.mark.anyio
    async def test_handles_empty_state(self) -> None:
        from backend.agents.report_writer import write_report

        state = AgentState(query="test", intent=Intent.GENERAL_QUESTION)
        result = await write_report(state)
        assert len(result.report_sections) == 0

    @pytest.mark.anyio
    async def test_handles_llm_failure(self) -> None:
        from backend.agents.report_writer import write_report

        state = _state_with_gaps([_gap()])

        with patch(
            "backend.agents.report_writer.generate_json",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            result = await write_report(state)

        assert len(result.report_sections) == 1
        assert "error" in result.report_sections[0]["executive_summary"].lower()
