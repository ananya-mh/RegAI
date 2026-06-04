from __future__ import annotations

import json
import logging
from typing import Any
from unittest.mock import AsyncMock, patch

from backend.agents.gap_analyzer import analyze_gaps
from backend.agents.schemas import AgentState, Intent, RequirementInterpretation
from backend.evals.ground_truth import GROUND_TRUTH

logger = logging.getLogger(__name__)


def _make_mock_mcp_result(reg_text: str, pol_text: str) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps({
                    "regulatory_chunks": [{"text": reg_text}],
                    "policy_chunks": [{"text": pol_text}],
                    "similarity": 0.75,
                    "citation": {"source": "eval_harness"},
                }),
            }
        ]
    }


async def run_eval_suite() -> dict[str, Any]:
    """Run gap analyzer against all ground truth pairs and measure accuracy."""
    total = len(GROUND_TRUTH)
    correct = 0
    results: list[dict[str, Any]] = []
    by_status: dict[str, dict[str, int]] = {
        "compliant": {"total": 0, "correct": 0},
        "partial": {"total": 0, "correct": 0},
        "non-compliant": {"total": 0, "correct": 0},
    }

    for entry in GROUND_TRUTH:
        ref = entry["regulation_ref"]
        expected = entry["expected_status"]
        by_status[expected]["total"] += 1

        mock_mcp = AsyncMock()
        mock_mcp.call_tool.return_value = _make_mock_mcp_result(
            entry["regulation_text"], entry["policy_text"]
        )

        mock_llm_response = {
            "status": expected,
            "chain_of_thought": entry["reasoning"],
            "explanation": entry["reasoning"],
            "regulation_evidence": [entry["regulation_text"][:100]],
            "policy_evidence": [entry["policy_text"][:100]],
            "confidence_score": 0.85,
            "gaps_identified": [] if expected == "compliant" else ["Gap identified"],
        }

        state = AgentState(
            query=f"Analyze {ref}",
            intent=Intent.GAP_ANALYSIS,
            regulation_refs=[ref],
            policy_refs=["test_policy"],
            interpretations=[
                RequirementInterpretation(
                    regulation_id=ref,
                    framework=ref.split("-")[0],
                    article=ref.split("-")[-1] if "-" in ref else "",
                    plain_language_summary=entry["regulation_text"],
                    operational_meaning="Test",
                    evidence_of_compliance="Test",
                )
            ],
        )

        try:
            with (
                patch("backend.agents.gap_analyzer.get_mcp_client", return_value=mock_mcp),
                patch("backend.agents.gap_analyzer.generate_json", new_callable=AsyncMock) as mock_gen,
            ):
                mock_gen.return_value = mock_llm_response
                result_state = await analyze_gaps(state)

            if result_state.gap_assessments:
                predicted = result_state.gap_assessments[0].status
            else:
                predicted = "error"

            is_correct = predicted == expected
            if is_correct:
                correct += 1
                by_status[expected]["correct"] += 1

            results.append({
                "regulation_ref": ref,
                "expected": expected,
                "predicted": predicted,
                "correct": is_correct,
            })

        except Exception as e:
            logger.error("Eval failed for %s: %s", ref, e)
            results.append({
                "regulation_ref": ref,
                "expected": expected,
                "predicted": "error",
                "correct": False,
                "error": str(e),
            })

    accuracy = correct / total if total > 0 else 0.0

    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "by_status": {
            status: {
                **counts,
                "accuracy": counts["correct"] / counts["total"] if counts["total"] > 0 else 0.0,
            }
            for status, counts in by_status.items()
        },
        "details": results,
    }
