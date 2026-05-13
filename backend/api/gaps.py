from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.models import GapListOut, GapOut, RemediationCreateRequest, RemediationTaskOut
from backend.models.tables import (
    AuditLog,
    Framework,
    Gap,
    GapStatus,
    Policy,
    RemediationTask,
    Requirement,
    TaskPriority,
)
from backend.services.database import get_db

router = APIRouter(prefix="/api/gaps", tags=["gaps"])


@router.get("", response_model=GapListOut)
async def list_gaps(
    framework_id: uuid.UUID | None = Query(None),
    status: str | None = Query(None),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> GapListOut:
    base = (
        select(
            Gap,
            Requirement.article.label("requirement_article"),
            Requirement.section.label("requirement_section"),
            Framework.name.label("framework_name"),
            Policy.filename.label("policy_filename"),
        )
        .join(Requirement, Gap.requirement_id == Requirement.id)
        .join(Framework, Requirement.framework_id == Framework.id)
        .join(Policy, Gap.policy_id == Policy.id)
    )

    if framework_id:
        base = base.where(Requirement.framework_id == framework_id)
    if status:
        base = base.where(Gap.status == GapStatus(status))
    if min_confidence is not None:
        base = base.where(Gap.confidence_score >= min_confidence)

    count_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        base.order_by(Gap.detected_at.desc()).offset(offset).limit(limit)
    )
    rows = result.all()

    gaps = []
    for row in rows:
        gap = row[0]
        gap_out = GapOut.model_validate(gap)
        gap_out.requirement_article = row.requirement_article
        gap_out.requirement_section = row.requirement_section
        gap_out.framework_name = row.framework_name
        gap_out.policy_filename = row.policy_filename
        gaps.append(gap_out)

    return GapListOut(gaps=gaps, total=total)


@router.post("/{gap_id}/remediation", response_model=RemediationTaskOut)
async def create_remediation(
    gap_id: uuid.UUID,
    request: RemediationCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> RemediationTaskOut:
    gap_result = await db.execute(select(Gap).where(Gap.id == gap_id))
    gap = gap_result.scalar_one_or_none()
    if not gap:
        raise HTTPException(404, "Gap not found")

    task = RemediationTask(
        id=uuid.uuid4(),
        gap_id=gap_id,
        title=request.title,
        description=request.description,
        priority=TaskPriority(request.priority),
        effort_estimate=request.effort_estimate,
        assignee=request.assignee,
    )
    db.add(task)

    audit = AuditLog(
        action="remediation_task_created",
        entity_type="remediation_task",
        entity_id=task.id,
        details={"gap_id": str(gap_id), "title": request.title, "priority": request.priority},
        performed_by="api",
    )
    db.add(audit)

    await db.commit()
    await db.refresh(task)
    return RemediationTaskOut.model_validate(task)


@router.get("/remediation", response_model=list[RemediationTaskOut])
async def list_remediation_tasks(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[RemediationTaskOut]:
    stmt = select(RemediationTask).order_by(RemediationTask.created_at.desc())
    if status:
        stmt = stmt.where(RemediationTask.status == status)
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return [RemediationTaskOut.model_validate(t) for t in tasks]
