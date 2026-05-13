from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.models import AnalyzeGapRequest, GenerateReportSectionRequest, SearchPoliciesRequest
from backend.models.tables import Framework, Gap, GapStatus, Policy, Requirement
from backend.services.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/internal", tags=["internal"])


@router.post("/analyze-gap")
async def analyze_gap(
    request: AnalyzeGapRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Cross-index gap analysis — called by MCP analyze_gap tool."""
    try:
        from backend.rag.retrieval import retrieve_and_rerank
        from backend.rag.vector_stores import PolicyStore, RegulatoryStore
        from backend.services.config import settings

        reg_store = RegulatoryStore(settings.faiss_index_path)
        try:
            reg_store.load()
        except FileNotFoundError:
            return {
                "error": "Regulatory index not built yet. Ingest regulations first.",
                "regulatory_chunks": [],
                "policy_chunks": [],
            }

        pol_store = PolicyStore(persist_path=settings.chroma_persist_path)

        query = f"{request.requirement_ref} {request.policy_ref}"
        result = retrieve_and_rerank(query, reg_store, pol_store)

        return {
            "requirement_ref": request.requirement_ref,
            "policy_ref": request.policy_ref,
            "pairs": [
                {
                    "regulatory_text": p.regulatory.text,
                    "policy_text": p.policy.text,
                    "similarity": p.similarity,
                    "relevance_score": p.relevance_score,
                    "is_potential_gap": p.is_potential_gap,
                }
                for p in result.pairs
            ],
            "regulatory_chunks": [
                {"text": c.text, "metadata": c.metadata}
                for c, _ in result.regulatory_chunks[:5]
            ],
            "policy_chunks": [
                {"text": c.text, "metadata": c.metadata}
                for c, _ in result.policy_chunks[:5]
            ],
            "citation": {"source": "FAISS + Chroma cross-index retrieval"},
        }

    except Exception as e:
        logger.error("analyze-gap failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Gap analysis failed: {e}")


@router.post("/search-policies")
async def search_policies(
    request: SearchPoliciesRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Semantic search over policy chunks — called by MCP search_policies tool."""
    try:
        from backend.rag.embeddings import embed_query
        from backend.rag.vector_stores import PolicyStore
        from backend.services.config import settings

        store = PolicyStore(persist_path=settings.chroma_persist_path)
        query_emb = embed_query(request.query)
        results = store.search(query_emb, k=10)

        chunks = []
        for chunk, score in results:
            if request.filters:
                doc_filter = request.filters.get("document_name")
                if doc_filter and chunk.metadata.get("document_name") != doc_filter:
                    continue
                section_filter = request.filters.get("section")
                if section_filter and chunk.metadata.get("section_header") != section_filter:
                    continue

            chunks.append({
                "id": chunk.id,
                "text": chunk.text,
                "metadata": chunk.metadata,
                "score": score,
            })

        return {
            "query": request.query,
            "results": chunks,
            "total": len(chunks),
            "citation": {"source": "Chroma policy store"},
        }

    except Exception as e:
        logger.error("search-policies failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Policy search failed: {e}")


@router.post("/generate-report-section")
async def generate_report_section(
    request: GenerateReportSectionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate a formatted report section — called by MCP generate_report_section tool."""
    if not request.framework_id and not request.gap_id:
        raise HTTPException(400, "Provide either framework_id or gap_id")

    try:
        from backend.services.llm import generate_json
    except ImportError:
        raise HTTPException(500, "LLM service not available")

    if request.gap_id:
        gap_result = await db.execute(
            select(Gap, Requirement, Framework, Policy)
            .join(Requirement, Gap.requirement_id == Requirement.id)
            .join(Framework, Requirement.framework_id == Framework.id)
            .join(Policy, Gap.policy_id == Policy.id)
            .where(Gap.id == uuid.UUID(request.gap_id))
        )
        row = gap_result.one_or_none()
        if not row:
            raise HTTPException(404, "Gap not found")

        gap, requirement, framework, policy = row
        prompt = (
            f"Generate a compliance report section for this gap:\n"
            f"Framework: {framework.name} {framework.version}\n"
            f"Requirement: Article {requirement.article}, Section {requirement.section}\n"
            f"Full text: {requirement.full_text[:1000]}\n"
            f"Policy: {policy.filename}\n"
            f"Status: {gap.status.value}\n"
            f"Explanation: {gap.explanation}\n"
            f"Confidence: {gap.confidence_score}"
        )
    else:
        fw_result = await db.execute(
            select(Framework).where(Framework.id == uuid.UUID(request.framework_id))
        )
        framework = fw_result.scalar_one_or_none()
        if not framework:
            raise HTTPException(404, "Framework not found")

        gaps_result = await db.execute(
            select(Gap, Requirement)
            .join(Requirement, Gap.requirement_id == Requirement.id)
            .where(Requirement.framework_id == framework.id)
            .order_by(Gap.confidence_score.desc())
            .limit(20)
        )
        gaps = gaps_result.all()

        gap_summaries = "\n".join(
            f"- Art {r.article}: {g.status.value} ({g.confidence_score:.0%}) — {g.explanation[:100]}"
            for g, r in gaps
        )
        prompt = (
            f"Generate an executive summary report section for {framework.name} {framework.version}.\n"
            f"Total gaps analyzed: {len(gaps)}\n"
            f"Gap details:\n{gap_summaries}"
        )

    system = (
        "You are a compliance report writer. Generate a structured report section as JSON with keys: "
        "title, executive_summary, findings (list of {requirement, status, explanation, recommendation}), "
        "overall_risk_level (low/medium/high/critical)."
    )

    try:
        result = await generate_json(
            prompt=prompt,
            system_prompt=system,
            prefer="gemini",
            agent_name="report_writer",
        )
        result["citation"] = {"source": "LLM-generated from PostgreSQL gap data"}
        return result
    except Exception as e:
        logger.error("Report section generation failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Report generation failed: {e}")
