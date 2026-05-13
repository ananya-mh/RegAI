from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.models import AgentUsageOut, ProviderUsageOut, UsageSummaryOut
from backend.models.tables import LLMUsageLog
from backend.services.database import get_db

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("", response_model=UsageSummaryOut)
async def get_usage_summary(
    db: AsyncSession = Depends(get_db),
) -> UsageSummaryOut:
    totals_result = await db.execute(
        select(
            func.coalesce(func.sum(LLMUsageLog.estimated_cost), 0).label("total_cost"),
            func.coalesce(func.sum(LLMUsageLog.input_tokens), 0).label("total_input"),
            func.coalesce(func.sum(LLMUsageLog.output_tokens), 0).label("total_output"),
        )
    )
    totals = totals_result.one()

    provider_result = await db.execute(
        select(
            LLMUsageLog.provider,
            LLMUsageLog.model,
            func.count().label("calls"),
            func.sum(LLMUsageLog.input_tokens).label("input_tokens"),
            func.sum(LLMUsageLog.output_tokens).label("output_tokens"),
            func.sum(LLMUsageLog.estimated_cost).label("estimated_cost"),
        )
        .group_by(LLMUsageLog.provider, LLMUsageLog.model)
        .order_by(func.sum(LLMUsageLog.estimated_cost).desc())
    )
    by_provider = [
        ProviderUsageOut(
            provider=row.provider,
            model=row.model,
            calls=row.calls,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            estimated_cost=row.estimated_cost,
        )
        for row in provider_result
    ]

    agent_result = await db.execute(
        select(
            LLMUsageLog.agent_name,
            func.count().label("calls"),
            func.sum(LLMUsageLog.input_tokens).label("input_tokens"),
            func.sum(LLMUsageLog.output_tokens).label("output_tokens"),
            func.sum(LLMUsageLog.estimated_cost).label("estimated_cost"),
        )
        .group_by(LLMUsageLog.agent_name)
        .order_by(func.sum(LLMUsageLog.estimated_cost).desc())
    )
    by_agent = [
        AgentUsageOut(
            agent_name=row.agent_name,
            calls=row.calls,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            estimated_cost=row.estimated_cost,
        )
        for row in agent_result
    ]

    return UsageSummaryOut(
        total_cost=float(totals.total_cost),
        total_input_tokens=int(totals.total_input),
        total_output_tokens=int(totals.total_output),
        by_provider=by_provider,
        by_agent=by_agent,
    )
