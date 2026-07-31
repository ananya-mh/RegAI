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

    try:
        await _persist_gaps(result.gap_assessments)
    except Exception:
        logger.warning("Failed to persist gap assessments", exc_info=True)

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


async def _persist_gaps(assessments: list) -> None:
    """Persist gap assessments produced by the chat pipeline to the gaps table.

    Agents work with reference strings (e.g. "GDPR-Art17"); resolve them to real
    requirement/policy rows so the /gaps view and dashboard reflect the results.
    Upserts one gap per (requirement, policy) pair to avoid duplicates on re-runs.
    """
    if not assessments:
        return

    import re

    from sqlalchemy import select

    from backend.models.tables import Framework, Gap, GapStatus, Policy, Requirement
    from backend.services.database import async_session

    async with async_session() as session:
        for a in assessments:
            parts = a.requirement_id.split("-")
            framework_name = parts[0]
            article = re.sub(r"^Art", "", "-".join(parts[1:]), flags=re.IGNORECASE) or None

            req_stmt = (
                select(Requirement)
                .join(Framework, Requirement.framework_id == Framework.id)
                .where(Framework.name.ilike(framework_name))
            )
            if article:
                req_stmt = req_stmt.where(Requirement.article == article)
            requirement = (await session.execute(req_stmt)).scalars().first()
            if requirement is None:
                continue

            policy = None
            ref = (a.policy_id or "").strip()
            if ref and ref.lower() != "all":
                policy = (
                    await session.execute(
                        select(Policy)
                        .where(Policy.filename.ilike(f"%{ref}%"))
                        .order_by(Policy.upload_date.desc())
                    )
                ).scalars().first()
            if policy is None:
                policy = (
                    await session.execute(
                        select(Policy).order_by(Policy.upload_date.desc())
                    )
                ).scalars().first()
            if policy is None:
                continue

            try:
                status = GapStatus(a.status)
            except ValueError:
                status = GapStatus.NON_COMPLIANT

            evidence = {
                "regulation_evidence": a.regulation_evidence,
                "policy_evidence": a.policy_evidence,
                "citations": a.citations,
            }

            existing = (
                await session.execute(
                    select(Gap).where(
                        Gap.requirement_id == requirement.id,
                        Gap.policy_id == policy.id,
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                session.add(
                    Gap(
                        requirement_id=requirement.id,
                        policy_id=policy.id,
                        status=status,
                        explanation=a.explanation,
                        evidence=evidence,
                        confidence_score=a.confidence_score,
                    )
                )
            else:
                existing.status = status
                existing.explanation = a.explanation
                existing.evidence = evidence
                existing.confidence_score = a.confidence_score

        await session.commit()
