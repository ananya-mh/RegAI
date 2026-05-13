from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from backend.agents.schemas import AgentState, GapAssessment, Intent, RequirementInterpretation


MOCK_LOOKUP_RESULT = {
    "content": [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "regulation_id": "GDPR-Art17",
                    "framework": "GDPR",
                    "found": True,
                    "requirements": [
                        {
                            "id": "req-001",
                            "article": "17",
                            "section": None,
                            "clause": "1",
                            "full_text": (
                                "The data subject shall have the right to obtain from the "
                                "controller the erasure of personal data concerning him or "
                                "her without undue delay and the controller shall have the "
                                "obligation to erase personal data without undue delay."
                            ),
                            "plain_language_summary": None,
                        }
                    ],
                    "citation": {"source": "PostgreSQL requirements table", "ids": ["req-001"]},
                }
            ),
        }
    ]
}

MOCK_GAP_RESULT = {
    "content": [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "regulatory_chunks": [
                        {
                            "text": (
                                "The data subject shall have the right to obtain from the "
                                "controller the erasure of personal data without undue delay."
                            )
                        }
                    ],
                    "policy_chunks": [
                        {
                            "text": (
                                "Users may request deletion of their account data by contacting "
                                "support. Requests are processed within 90 days."
                            )
                        }
                    ],
                    "similarity": 0.72,
                    "is_potential_gap": False,
                    "citation": {"source": "FAISS + Chroma cross-index"},
                }
            ),
        }
    ]
}


MOCK_SUPERVISOR_JSON = {
    "intent": "gap_analysis",
    "reasoning": "User wants to check compliance of a policy against GDPR Article 17",
    "regulation_refs": ["GDPR-Art17"],
    "policy_refs": ["data retention policy"],
}

MOCK_INTERPRETER_JSON = {
    "plain_language_summary": (
        "Individuals can request that an organization delete all their personal data promptly."
    ),
    "operational_meaning": (
        "Organizations must implement a data deletion process that fulfills requests within 30 days."
    ),
    "evidence_of_compliance": (
        "Documented deletion procedure, records of fulfilled requests, data inventory."
    ),
    "key_terms": ["data subject", "controller", "erasure", "undue delay"],
    "related_requirements": ["GDPR-Art12", "GDPR-Art13"],
}

MOCK_GAP_ANALYSIS_JSON = {
    "status": "partial",
    "chain_of_thought": "The regulation requires erasure without undue delay...",
    "explanation": (
        "The policy acknowledges data deletion rights but the 90-day processing window "
        "exceeds GDPR's 30-day requirement."
    ),
    "regulation_evidence": [
        "erasure of personal data without undue delay"
    ],
    "policy_evidence": [
        "Requests are processed within 90 days"
    ],
    "confidence_score": 0.85,
    "gaps_identified": ["Response time exceeds 30-day GDPR requirement"],
}


def _make_generate_json_side_effect():
    """Return different JSON based on which agent is calling."""
    call_count = 0

    async def side_effect(prompt, system_prompt=None, temperature=0.1, prefer="gemini", agent_name=None, max_tokens=4096):
        nonlocal call_count
        call_count += 1
        if agent_name == "supervisor":
            return MOCK_SUPERVISOR_JSON
        elif agent_name == "regulatory_interpreter":
            return MOCK_INTERPRETER_JSON
        elif agent_name == "gap_analyzer":
            return MOCK_GAP_ANALYSIS_JSON
        return {"error": f"unexpected agent: {agent_name}"}

    return side_effect


class TestSupervisorClassification:
    @pytest.mark.anyio
    async def test_classifies_gap_analysis(self) -> None:
        from backend.agents.supervisor import classify_intent

        with patch("backend.agents.supervisor.generate_json", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = MOCK_SUPERVISOR_JSON
            state = AgentState(query="Does our data retention policy comply with GDPR Article 17?")
            result = await classify_intent(state)

        assert result.intent == Intent.GAP_ANALYSIS
        assert "GDPR-Art17" in result.regulation_refs
        assert "data retention policy" in result.policy_refs

    @pytest.mark.anyio
    async def test_classifies_general_question(self) -> None:
        from backend.agents.supervisor import classify_intent

        with patch("backend.agents.supervisor.generate_json", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {
                "intent": "general_question",
                "reasoning": "User is asking for explanation",
                "regulation_refs": ["GDPR-Art25"],
                "policy_refs": [],
            }
            state = AgentState(query="What does Article 25 of GDPR mean?")
            result = await classify_intent(state)

        assert result.intent == Intent.GENERAL_QUESTION
        assert "GDPR-Art25" in result.regulation_refs

    @pytest.mark.anyio
    async def test_falls_back_on_parse_error(self) -> None:
        from backend.agents.supervisor import classify_intent

        with patch("backend.agents.supervisor.generate_json", new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = json.JSONDecodeError("bad json", "", 0)
            state = AgentState(query="something")
            result = await classify_intent(state)

        assert result.intent == Intent.GENERAL_QUESTION


class TestRegulatoryInterpreter:
    @pytest.mark.anyio
    async def test_interprets_requirement(self) -> None:
        from backend.agents.interpreter import interpret_requirements

        mock_mcp = AsyncMock()
        mock_mcp.call_tool.return_value = MOCK_LOOKUP_RESULT

        with (
            patch("backend.agents.interpreter.get_mcp_client", return_value=mock_mcp),
            patch("backend.agents.interpreter.generate_json", new_callable=AsyncMock) as mock_gen,
        ):
            mock_gen.return_value = MOCK_INTERPRETER_JSON
            state = AgentState(
                query="What does GDPR Article 17 require?",
                intent=Intent.GENERAL_QUESTION,
                regulation_refs=["GDPR-Art17"],
            )
            result = await interpret_requirements(state)

        assert len(result.interpretations) == 1
        interp = result.interpretations[0]
        assert interp.regulation_id == "GDPR-Art17"
        assert interp.framework == "GDPR"
        assert "delete" in interp.plain_language_summary.lower()
        mock_mcp.call_tool.assert_called_once_with(
            "lookup_requirement", {"regulation_id": "GDPR-Art17"}
        )

    @pytest.mark.anyio
    async def test_handles_not_found(self) -> None:
        from backend.agents.interpreter import interpret_requirements

        mock_mcp = AsyncMock()
        mock_mcp.call_tool.return_value = {
            "content": [
                {"type": "text", "text": json.dumps({"found": False, "regulation_id": "FAKE-Art99"})}
            ]
        }

        with patch("backend.agents.interpreter.get_mcp_client", return_value=mock_mcp):
            state = AgentState(
                query="test",
                intent=Intent.GENERAL_QUESTION,
                regulation_refs=["FAKE-Art99"],
            )
            result = await interpret_requirements(state)

        assert len(result.interpretations) == 1
        assert "not found" in result.interpretations[0].plain_language_summary.lower()


class TestGapAnalyzer:
    @pytest.mark.anyio
    async def test_analyzes_gap(self) -> None:
        from backend.agents.gap_analyzer import analyze_gaps

        mock_mcp = AsyncMock()
        mock_mcp.call_tool.return_value = MOCK_GAP_RESULT

        with (
            patch("backend.agents.gap_analyzer.get_mcp_client", return_value=mock_mcp),
            patch("backend.agents.gap_analyzer.generate_json", new_callable=AsyncMock) as mock_gen,
        ):
            mock_gen.return_value = MOCK_GAP_ANALYSIS_JSON
            state = AgentState(
                query="Check our data retention policy against GDPR Art 17",
                intent=Intent.GAP_ANALYSIS,
                regulation_refs=["GDPR-Art17"],
                policy_refs=["data retention policy"],
                interpretations=[
                    RequirementInterpretation(
                        regulation_id="GDPR-Art17",
                        framework="GDPR",
                        article="Art17",
                        plain_language_summary="Right to erasure",
                        operational_meaning="Must delete data on request within 30 days",
                        evidence_of_compliance="Deletion records",
                    )
                ],
            )
            result = await analyze_gaps(state)

        assert len(result.gap_assessments) == 1
        gap = result.gap_assessments[0]
        assert gap.status == "partial"
        assert gap.confidence_score == 0.85
        assert gap.requirement_id == "GDPR-Art17"
        assert "90-day" in gap.explanation or "90" in gap.explanation
        mock_mcp.call_tool.assert_called_once()

    @pytest.mark.anyio
    async def test_handles_mcp_failure(self) -> None:
        from backend.agents.gap_analyzer import analyze_gaps

        mock_mcp = AsyncMock()
        mock_mcp.call_tool.side_effect = Exception("MCP server unreachable")

        with patch("backend.agents.gap_analyzer.get_mcp_client", return_value=mock_mcp):
            state = AgentState(
                query="test",
                intent=Intent.GAP_ANALYSIS,
                regulation_refs=["GDPR-Art17"],
                policy_refs=["some policy"],
            )
            result = await analyze_gaps(state)

        assert len(result.gap_assessments) == 1
        assert result.gap_assessments[0].status == "non-compliant"
        assert result.gap_assessments[0].confidence_score == 0.0

    @pytest.mark.anyio
    async def test_defaults_policy_to_all(self) -> None:
        from backend.agents.gap_analyzer import analyze_gaps

        mock_mcp = AsyncMock()
        mock_mcp.call_tool.return_value = MOCK_GAP_RESULT

        with (
            patch("backend.agents.gap_analyzer.get_mcp_client", return_value=mock_mcp),
            patch("backend.agents.gap_analyzer.generate_json", new_callable=AsyncMock) as mock_gen,
        ):
            mock_gen.return_value = MOCK_GAP_ANALYSIS_JSON
            state = AgentState(
                query="Analyze GDPR Art 17 compliance",
                intent=Intent.GAP_ANALYSIS,
                regulation_refs=["GDPR-Art17"],
                policy_refs=[],
            )
            result = await analyze_gaps(state)

        assert len(result.gap_assessments) == 1
        assert result.gap_assessments[0].policy_id == "all"


class TestFullPipeline:
    @pytest.mark.anyio
    async def test_supervisor_to_interpreter_to_gap_analyzer(self) -> None:
        """End-to-end test: Supervisor classifies → Interpreter looks up → Gap Analyzer assesses."""
        mock_mcp = AsyncMock()

        def route_mcp_call(tool_name, arguments=None):
            if tool_name == "lookup_requirement":
                return MOCK_LOOKUP_RESULT
            elif tool_name == "analyze_gap":
                return MOCK_GAP_RESULT
            raise ValueError(f"Unexpected tool: {tool_name}")

        mock_mcp.call_tool.side_effect = route_mcp_call

        gen_side_effect = _make_generate_json_side_effect()

        with (
            patch("backend.agents.supervisor.generate_json", new_callable=AsyncMock, side_effect=gen_side_effect),
            patch("backend.agents.interpreter.get_mcp_client", return_value=mock_mcp),
            patch("backend.agents.interpreter.generate_json", new_callable=AsyncMock, side_effect=gen_side_effect),
            patch("backend.agents.gap_analyzer.get_mcp_client", return_value=mock_mcp),
            patch("backend.agents.gap_analyzer.generate_json", new_callable=AsyncMock, side_effect=gen_side_effect),
        ):
            from backend.agents.graph import run_query

            result = await run_query(
                "Does our data retention policy comply with GDPR Article 17?"
            )

        assert result.intent == Intent.GAP_ANALYSIS
        assert len(result.interpretations) == 1
        assert result.interpretations[0].regulation_id == "GDPR-Art17"
        assert len(result.gap_assessments) == 1
        assert result.gap_assessments[0].status == "partial"
        assert result.response  # non-empty response generated

    @pytest.mark.anyio
    async def test_general_question_skips_gap_analysis(self) -> None:
        """General questions go supervisor → interpreter → respond (no gap analyzer)."""
        mock_mcp = AsyncMock()
        mock_mcp.call_tool.return_value = MOCK_LOOKUP_RESULT

        async def gen_side_effect(prompt, system_prompt=None, temperature=0.1, prefer="gemini", agent_name=None, max_tokens=4096):
            if agent_name == "supervisor":
                return {
                    "intent": "general_question",
                    "reasoning": "Asking what a regulation means",
                    "regulation_refs": ["GDPR-Art17"],
                    "policy_refs": [],
                }
            elif agent_name == "regulatory_interpreter":
                return MOCK_INTERPRETER_JSON
            return {}

        with (
            patch("backend.agents.supervisor.generate_json", new_callable=AsyncMock, side_effect=gen_side_effect),
            patch("backend.agents.interpreter.get_mcp_client", return_value=mock_mcp),
            patch("backend.agents.interpreter.generate_json", new_callable=AsyncMock, side_effect=gen_side_effect),
        ):
            from backend.agents.graph import run_query

            result = await run_query("What does GDPR Article 17 require?")

        assert result.intent == Intent.GENERAL_QUESTION
        assert len(result.interpretations) == 1
        assert len(result.gap_assessments) == 0
        assert "delete" in result.response.lower() or "erasure" in result.response.lower()
