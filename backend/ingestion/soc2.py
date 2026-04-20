from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

import pymupdf
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import (
    ParsedNode,
    clear_requirements,
    get_or_create_framework,
    insert_requirement_tree,
)

logger = logging.getLogger(__name__)

SOC2_VERSION = "2017"

CATEGORIES: dict[str, str] = {
    "CC": "Common Criteria (Security)",
    "A": "Availability",
    "PI": "Processing Integrity",
    "C": "Confidentiality",
    "P": "Privacy",
}

CRITERION_RE = re.compile(r"(CC|A|PI|C|P)(\d+)\.(\d+)\b")
CATEGORY_HEADER_RE = re.compile(
    r"^(CC\d+|A\d+|PI\d+|C\d+|P\d+)\s*[-\u2013\u2014:]\s*(.+)",
    re.IGNORECASE,
)
POINT_OF_FOCUS_RE = re.compile(r"^(?:Points?\s+of\s+Focus|Supplemental\s+Criteria)", re.IGNORECASE)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    doc = pymupdf.open(str(pdf_path))
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n".join(pages)


def parse_soc2_text(text: str) -> list[ParsedNode]:
    lines = text.split("\n")
    tree: list[ParsedNode] = []

    category_nodes: dict[str, ParsedNode] = {}
    group_nodes: dict[str, ParsedNode] = {}
    current_criterion: ParsedNode | None = None
    current_group: ParsedNode | None = None

    i = 0
    while i < len(lines):
        line = _clean(lines[i])
        i += 1

        if not line:
            continue

        # --- category group header (e.g. "CC1 — Control Environment") ---
        m = CATEGORY_HEADER_RE.match(line)
        if m:
            group_id = m.group(1).upper()
            group_title = m.group(2).strip()

            cat_prefix = re.match(r"(CC|A|PI|C|P)", group_id)
            cat_key = cat_prefix.group(1) if cat_prefix else group_id

            if cat_key not in category_nodes:
                cat_node = ParsedNode(
                    level="category",
                    section=CATEGORIES.get(cat_key, cat_key),
                    full_text=CATEGORIES.get(cat_key, cat_key),
                )
                category_nodes[cat_key] = cat_node
                tree.append(cat_node)

            current_group = ParsedNode(
                level="group",
                section=f"{group_id}: {group_title}",
                full_text=f"{group_id} — {group_title}",
            )
            group_nodes[group_id] = current_group
            category_nodes[cat_key].children.append(current_group)
            current_criterion = None
            continue

        # --- individual criterion (e.g. "CC1.1" or "CC1.1 The entity...") ---
        m = CRITERION_RE.match(line)
        if m:
            cat_key = m.group(1)
            group_num = m.group(2)
            criterion_num = m.group(3)
            criterion_id = f"{cat_key}{group_num}.{criterion_num}"
            group_id = f"{cat_key}{group_num}"

            remainder = line[m.end() :].strip().lstrip(".:\u2013\u2014- ")

            if cat_key not in category_nodes:
                cat_node = ParsedNode(
                    level="category",
                    section=CATEGORIES.get(cat_key, cat_key),
                    full_text=CATEGORIES.get(cat_key, cat_key),
                )
                category_nodes[cat_key] = cat_node
                tree.append(cat_node)

            if group_id not in group_nodes:
                current_group = ParsedNode(
                    level="group",
                    section=group_id,
                    full_text=group_id,
                )
                group_nodes[group_id] = current_group
                category_nodes[cat_key].children.append(current_group)

            current_criterion = ParsedNode(
                level="criterion",
                article=criterion_id,
                clause=criterion_num,
                full_text=remainder if remainder else criterion_id,
            )
            group_nodes[group_id].children.append(current_criterion)
            continue

        # --- skip "points of focus" headers ---
        if POINT_OF_FOCUS_RE.match(line):
            continue

        # --- continuation text for current criterion ---
        if current_criterion and len(line) > 20:
            current_criterion.full_text += f" {line}"

    return tree


async def ingest_soc2(session: AsyncSession, pdf_path: str | Path) -> uuid.UUID:
    path = Path(pdf_path)
    if not path.exists():
        msg = f"SOC 2 PDF not found: {path}"
        raise FileNotFoundError(msg)

    logger.info("Extracting text from %s", path.name)
    text = extract_text_from_pdf(path)

    logger.info("Parsing SOC 2 Trust Services Criteria")
    nodes = parse_soc2_text(text)

    framework = await get_or_create_framework(
        session,
        name="SOC 2",
        version=SOC2_VERSION,
        source_url=None,
    )
    await clear_requirements(session, framework.id)

    count = await insert_requirement_tree(session, framework.id, nodes)
    await session.commit()

    logger.info("Ingested %d SOC 2 criteria under framework %s", count, framework.id)
    return framework.id
