from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from backend.api.models import ChatRequest
from backend.agents.graph import run_query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


async def _stream_response(query: str):
    yield {"event": "status", "data": json.dumps({"stage": "classifying"})}

    try:
        result = await run_query(query)
    except Exception as e:
        logger.error("Agent pipeline error: %s", e, exc_info=True)
        yield {
            "event": "error",
            "data": json.dumps({"message": f"Pipeline error: {e}"}),
        }
        yield {"event": "done", "data": "{}"}
        return

    if result.supervisor_decision:
        yield {
            "event": "status",
            "data": json.dumps({
                "stage": "classified",
                "intent": result.intent.value if result.intent else "unknown",
                "reasoning": result.supervisor_decision.reasoning,
            }),
        }

    if result.interpretations:
        yield {
            "event": "interpretations",
            "data": json.dumps([
                {
                    "regulation_id": i.regulation_id,
                    "framework": i.framework,
                    "summary": i.plain_language_summary,
                    "operational_meaning": i.operational_meaning,
                }
                for i in result.interpretations
            ]),
        }

    if result.gap_assessments:
        yield {
            "event": "gaps",
            "data": json.dumps([
                {
                    "requirement_id": g.requirement_id,
                    "policy_id": g.policy_id,
                    "status": g.status,
                    "explanation": g.explanation,
                    "confidence_score": g.confidence_score,
                    "regulation_evidence": g.regulation_evidence,
                    "policy_evidence": g.policy_evidence,
                }
                for g in result.gap_assessments
            ]),
        }

    response_text = result.response or "No response generated."
    chunks = [response_text[i : i + 100] for i in range(0, len(response_text), 100)]
    for chunk in chunks:
        yield {
            "event": "text",
            "data": json.dumps({"content": chunk}),
        }

    yield {"event": "done", "data": "{}"}


@router.post("/chat")
async def chat(request: ChatRequest):
    return EventSourceResponse(_stream_response(request.message))
