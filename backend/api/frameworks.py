from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.models import FrameworkOut, FrameworkStatusOut
from backend.models.tables import Framework, Gap, GapStatus, Requirement
from backend.services.database import get_db

router = APIRouter(prefix="/api/frameworks", tags=["frameworks"])


@router.get("", response_model=list[FrameworkOut])
async def list_frameworks(
    db: AsyncSession = Depends(get_db),
) -> list[FrameworkOut]:
    result = await db.execute(select(Framework).order_by(Framework.name))
    frameworks = result.scalars().all()
    return [FrameworkOut.model_validate(f) for f in frameworks]


@router.get("/{framework_id}/status", response_model=FrameworkStatusOut)
async def get_framework_status(
    framework_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FrameworkStatusOut:
    result = await db.execute(select(Framework).where(Framework.id == framework_id))
    framework = result.scalar_one_or_none()
    if not framework:
        raise HTTPException(404, "Framework not found")

    total_result = await db.execute(
        select(func.count(Requirement.id)).where(Requirement.framework_id == framework_id)
    )
    total_requirements = total_result.scalar() or 0

    gap_counts = await db.execute(
        select(Gap.status, func.count(Gap.id))
        .join(Requirement, Gap.requirement_id == Requirement.id)
        .where(Requirement.framework_id == framework_id)
        .group_by(Gap.status)
    )
    counts = {row[0]: row[1] for row in gap_counts}

    compliant = counts.get(GapStatus.COMPLIANT, 0)
    partial = counts.get(GapStatus.PARTIAL, 0)
    non_compliant = counts.get(GapStatus.NON_COMPLIANT, 0)
    assessed = compliant + partial + non_compliant
    coverage_pct = round((assessed / total_requirements * 100), 1) if total_requirements > 0 else 0.0

    return FrameworkStatusOut(
        framework=FrameworkOut.model_validate(framework),
        total_requirements=total_requirements,
        assessed=assessed,
        compliant=compliant,
        partial=partial,
        non_compliant=non_compliant,
        coverage_pct=coverage_pct,
    )
