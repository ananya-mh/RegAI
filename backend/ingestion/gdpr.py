from __future__ import annotations

import logging
import re
import uuid

import httpx
from bs4 import BeautifulSoup, Tag
from sqlalchemy.ext.asyncio import AsyncSession

from backend.ingestion.base import (
    ParsedNode,
    clear_requirements,
    get_or_create_framework,
    insert_requirement_tree,
)

logger = logging.getLogger(__name__)

GDPR_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679"
GDPR_VERSION = "2016/679"

CHAPTER_RE = re.compile(r"^CHAPTER\s+([IVXLCDM]+)", re.IGNORECASE)
SECTION_RE = re.compile(r"^Section\s+(\d+)", re.IGNORECASE)
ARTICLE_RE = re.compile(r"^Article\s+(\d+)", re.IGNORECASE)
PARAGRAPH_RE = re.compile(r"^(\d+)\.\s+(.+)", re.DOTALL)
SUBPOINT_RE = re.compile(r"^\(([a-z])\)\s+(.+)", re.DOTALL)
RECITAL_RE = re.compile(r"^\((\d+)\)\s+(.+)", re.DOTALL)

CHAPTER_CLASSES = frozenset({"ti-grseq-1", "ti-section-1"})
CHAPTER_SUBTITLE_CLASSES = frozenset({"sti-grseq-1", "sti-section-1"})
ARTICLE_CLASSES = frozenset({"ti-art"})
ARTICLE_SUBTITLE_CLASSES = frozenset({"sti-art"})


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _css_set(el: Tag) -> frozenset[str]:
    return frozenset(el.get("class", []))


def _has_class(el: Tag, targets: frozenset[str]) -> bool:
    return bool(_css_set(el) & targets)


async def download_gdpr_html() -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(GDPR_URL, follow_redirects=True)
        resp.raise_for_status()
        return resp.text


def parse_gdpr_html(html: str) -> list[ParsedNode]:
    soup = BeautifulSoup(html, "html.parser")
    tree: list[ParsedNode] = []

    recitals = ParsedNode(level="chapter", section="Recitals", full_text="Preamble recitals")
    in_preamble = True

    cur_chapter: ParsedNode | None = None
    cur_section: ParsedNode | None = None
    cur_article: ParsedNode | None = None
    cur_paragraph: ParsedNode | None = None

    body = soup.find("body") or soup
    elements = body.find_all(["p", "h1", "h2", "h3", "h4"])

    for el in elements:
        if not isinstance(el, Tag):
            continue
        text = _clean(el.get_text())
        if not text:
            continue

        # --- boundary between recitals and body ---
        if "HAVE ADOPTED THIS REGULATION" in text.upper():
            in_preamble = False
            if recitals.children:
                tree.append(recitals)
            continue

        # --- recitals ---
        if in_preamble:
            m = RECITAL_RE.match(text)
            if m:
                recitals.children.append(
                    ParsedNode(level="recital", clause=m.group(1), full_text=m.group(2))
                )
            continue

        # --- chapter ---
        m = CHAPTER_RE.match(text)
        if m or _has_class(el, CHAPTER_CLASSES):
            chapter_num = m.group(1) if m else text
            cur_chapter = ParsedNode(
                level="chapter", section=f"Chapter {chapter_num}", full_text=text
            )
            tree.append(cur_chapter)
            cur_section = None
            cur_article = None
            cur_paragraph = None
            continue

        # chapter subtitle
        if cur_chapter and cur_article is None and _has_class(el, CHAPTER_SUBTITLE_CLASSES):
            cur_chapter.section = f"{cur_chapter.section}: {text}"
            cur_chapter.full_text = f"{cur_chapter.full_text} — {text}"
            continue

        # --- section within chapter ---
        m = SECTION_RE.match(text)
        if m:
            cur_section = ParsedNode(
                level="section",
                section=f"Section {m.group(1)}",
                full_text=text,
            )
            if cur_chapter:
                cur_chapter.children.append(cur_section)
            else:
                tree.append(cur_section)
            cur_article = None
            cur_paragraph = None
            continue

        # section subtitle
        if cur_section and cur_article is None and not ARTICLE_RE.match(text):
            if not cur_section.full_text.endswith(text):
                cur_section.section = f"{cur_section.section}: {text}"
                cur_section.full_text = f"{cur_section.full_text} — {text}"
            continue

        # --- article ---
        m = ARTICLE_RE.match(text)
        if m or _has_class(el, ARTICLE_CLASSES):
            art_num = m.group(1) if m else ""
            if not art_num:
                num_match = re.search(r"\d+", text)
                art_num = num_match.group(0) if num_match else text
            cur_article = ParsedNode(level="article", article=art_num, full_text=text)
            parent = cur_section or cur_chapter
            if parent:
                parent.children.append(cur_article)
            else:
                tree.append(cur_article)
            cur_paragraph = None
            continue

        # article subtitle
        if cur_article and cur_article.section is None and _has_class(el, ARTICLE_SUBTITLE_CLASSES):
            cur_article.section = text
            cur_article.full_text = f"{cur_article.full_text} — {text}"
            continue

        # --- paragraph (1. text) ---
        m = PARAGRAPH_RE.match(text)
        if m and cur_article:
            cur_paragraph = ParsedNode(
                level="paragraph",
                article=cur_article.article,
                clause=m.group(1),
                full_text=m.group(2),
            )
            cur_article.children.append(cur_paragraph)
            continue

        # --- sub-point ((a) text) ---
        m = SUBPOINT_RE.match(text)
        if m:
            parent_clause = cur_paragraph.clause if cur_paragraph else ""
            node = ParsedNode(
                level="subpoint",
                article=cur_article.article if cur_article else None,
                clause=f"{parent_clause}({m.group(1)})",
                full_text=m.group(2),
            )
            target = cur_paragraph or cur_article
            if target:
                target.children.append(node)
            continue

        # --- continuation text ---
        if cur_paragraph:
            cur_paragraph.full_text += f" {text}"
        elif cur_article and not cur_article.children:
            cur_article.full_text += f" {text}"

    return tree


async def ingest_gdpr(session: AsyncSession, *, html: str | None = None) -> uuid.UUID:
    if html is None:
        logger.info("Downloading GDPR from EUR-Lex")
        html = await download_gdpr_html()

    logger.info("Parsing GDPR HTML")
    nodes = parse_gdpr_html(html)

    framework = await get_or_create_framework(
        session, name="GDPR", version=GDPR_VERSION, source_url=GDPR_URL
    )
    await clear_requirements(session, framework.id)

    count = await insert_requirement_tree(session, framework.id, nodes)
    await session.commit()

    logger.info("Ingested %d GDPR requirements under framework %s", count, framework.id)
    return framework.id
