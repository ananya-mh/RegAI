from __future__ import annotations

import logging

from backend.services.llm import generate_json

logger = logging.getLogger(__name__)

JUDGE_PROMPT = """\
You are an evaluation judge. Given a compliance assessment and the evidence chunks it was based on, score the assessment for factual grounding.

Score from 0.0 to 1.0:
- 1.0: Every claim in the assessment is directly supported by the evidence
- 0.7-0.9: Most claims supported, minor inferences reasonable
- 0.4-0.6: Some claims supported but significant unsupported statements
- 0.0-0.3: Assessment makes claims not found in or contradicted by evidence

Flag as unfaithful if the assessment references specific facts, numbers, or requirements that do not appear in the evidence.

Output JSON:
{
  "score": <0.0 to 1.0>,
  "flagged": <true if unfaithful>,
  "reasoning": "<explanation of scoring>"
}\
"""


async def score_faithfulness(
    assessment_text: str,
    evidence_texts: list[str],
) -> dict[str, float | bool | str]:
    evidence_combined = "\n\n---\n\n".join(evidence_texts) if evidence_texts else "No evidence provided."

    prompt = (
        f"Assessment:\n\"{assessment_text}\"\n\n"
        f"Evidence chunks:\n\"{evidence_combined}\""
    )

    try:
        result = await generate_json(
            prompt=prompt,
            system_prompt=JUDGE_PROMPT,
            temperature=0.1,
            prefer="gemini",
            agent_name="faithfulness_judge",
        )
        return {
            "score": min(1.0, max(0.0, float(result.get("score", 0.5)))),
            "flagged": bool(result.get("flagged", False)),
            "reasoning": str(result.get("reasoning", "")),
        }
    except Exception as e:
        logger.error("Faithfulness scoring failed: %s", e)
        return {"score": 0.0, "flagged": True, "reasoning": f"Scoring failed: {e}"}
