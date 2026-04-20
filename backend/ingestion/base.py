from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tables import Framework, Requirement

logger = logging.getLogger(__name__)


@dataclass
class ParsedNode:
    level: str
    article: str | None = None
    section: str | None = None
    clause: str | None = None
    full_text: str = ""
    children: list[ParsedNode] = field(default_factory=list)


async def get_or_create_framework(
    session: AsyncSession,
    *,
    name: str,
    version: str,
    source_url: str | None = None,
) -> Framework:
    stmt = select(Framework).where(Framework.name == name, Framework.version == version)
    result = await session.execute(stmt)
    framework = result.scalar_one_or_none()

    if framework is not None:
        return framework

    framework = Framework(
        id=uuid.uuid4(),
        name=name,
        version=version,
        source_url=source_url,
    )
    session.add(framework)
    await session.flush()
    return framework


async def clear_requirements(session: AsyncSession, framework_id: uuid.UUID) -> None:
    await session.execute(delete(Requirement).where(Requirement.framework_id == framework_id))
    await session.flush()


async def insert_requirement_tree(
    session: AsyncSession,
    framework_id: uuid.UUID,
    nodes: list[ParsedNode],
    parent_id: uuid.UUID | None = None,
) -> int:
    count = 0
    for node in nodes:
        req_id = uuid.uuid4()
        session.add(
            Requirement(
                id=req_id,
                framework_id=framework_id,
                article=node.article,
                section=node.section,
                clause=node.clause,
                full_text=node.full_text,
                parent_requirement_id=parent_id,
            )
        )
        count += 1
        if node.children:
            count += await insert_requirement_tree(
                session, framework_id, node.children, parent_id=req_id
            )
    return count
