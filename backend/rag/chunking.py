from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.rag.embeddings import embed_texts

SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict[str, Any]


def _estimate_tokens(text: str) -> int:
    return len(text.split())


def _split_sentences(text: str) -> list[str]:
    parts = SENTENCE_RE.split(text)
    return [s.strip() for s in parts if s.strip()]


def _build_parent_path(
    req_id: uuid.UUID,
    req_map: dict[uuid.UUID, dict[str, Any]],
) -> str:
    parts: list[str] = []
    current_id: uuid.UUID | None = req_id
    while current_id and current_id in req_map:
        req = req_map[current_id]
        label = ""
        if req.get("article"):
            label = f"Article {req['article']}"
        if req.get("section"):
            label = req["section"] if not label else f"{label} ({req['section']})"
        if req.get("clause"):
            clause_label = f"Clause {req['clause']}"
            label = clause_label if not label else f"{label} {clause_label}"
        if not label:
            label = str(req.get("full_text", ""))[:50]
        parts.append(label)
        current_id = req.get("parent_requirement_id")
    parts.reverse()
    return " \u2192 ".join(parts)


# ---------------------------------------------------------------------------
# Regulatory chunking — clause-level, never split mid-clause
# ---------------------------------------------------------------------------


def chunk_regulatory(
    requirements: list[dict[str, Any]],
    framework_name: str = "",
    min_tokens: int = 200,
    max_tokens: int = 600,
) -> list[Chunk]:
    req_map: dict[uuid.UUID, dict[str, Any]] = {r["id"]: r for r in requirements}
    parent_ids = {
        r["parent_requirement_id"] for r in requirements if r.get("parent_requirement_id")
    }

    chunks: list[Chunk] = []
    for req in requirements:
        text = str(req.get("full_text", "")).strip()
        if not text or _estimate_tokens(text) < 5:
            continue

        if req["id"] in parent_ids and _estimate_tokens(text) < min_tokens:
            continue

        parent_path = _build_parent_path(req["id"], req_map)
        if framework_name:
            parent_path = (
                f"{framework_name} \u2192 {parent_path}" if parent_path else framework_name
            )

        metadata: dict[str, Any] = {
            "framework_id": str(req["framework_id"]),
            "requirement_id": str(req["id"]),
            "article": req.get("article"),
            "section": req.get("section"),
            "clause": req.get("clause"),
            "parent_path": parent_path,
        }

        tokens = _estimate_tokens(text)

        if tokens <= max_tokens:
            chunks.append(Chunk(id=str(req["id"]), text=text, metadata=metadata))
        else:
            chunks.extend(_split_long_clause(text, str(req["id"]), metadata, max_tokens))

    return chunks


def _split_long_clause(
    text: str,
    base_id: str,
    metadata: dict[str, Any],
    max_tokens: int,
) -> list[Chunk]:
    sentences = _split_sentences(text)
    chunks: list[Chunk] = []
    current: list[str] = []
    current_len = 0
    part = 1

    for sent in sentences:
        sent_len = _estimate_tokens(sent)
        if current and current_len + sent_len > max_tokens:
            chunks.append(
                Chunk(
                    id=f"{base_id}_p{part}",
                    text=" ".join(current),
                    metadata={**metadata, "part": part},
                )
            )
            current = [sent]
            current_len = sent_len
            part += 1
        else:
            current.append(sent)
            current_len += sent_len

    if current:
        chunk_id = f"{base_id}_p{part}" if part > 1 else base_id
        chunk_meta = {**metadata, "part": part} if part > 1 else metadata
        chunks.append(Chunk(id=chunk_id, text=" ".join(current), metadata=chunk_meta))

    return chunks


# ---------------------------------------------------------------------------
# Policy chunking — semantic similarity breakpoints (SemanticChunker approach)
# ---------------------------------------------------------------------------


def chunk_policy(
    text: str,
    document_name: str,
    upload_date: str,
    section_headers: list[tuple[int, str]] | None = None,
) -> list[Chunk]:
    raw_chunks = _semantic_split(text)

    header_lookup = section_headers or []
    chunks: list[Chunk] = []
    for i, chunk_text in enumerate(raw_chunks):
        chunk_start = text.find(chunk_text)
        section = _find_section_header(chunk_start, header_lookup) if header_lookup else None

        chunks.append(
            Chunk(
                id=f"{document_name}_{i}",
                text=chunk_text,
                metadata={
                    "document_name": document_name,
                    "section_header": section,
                    "upload_date": upload_date,
                    "chunk_index": i,
                },
            )
        )

    return chunks


def _semantic_split(
    text: str,
    breakpoint_percentile: float = 90.0,
) -> list[str]:
    sentences = _split_sentences(text)
    if len(sentences) <= 2:
        return [text.strip()] if text.strip() else []

    embeddings = embed_texts(sentences)

    distances: list[float] = []
    for i in range(len(embeddings) - 1):
        sim = float(np.dot(embeddings[i], embeddings[i + 1]))
        distances.append(1.0 - sim)

    if not distances:
        return [text.strip()]

    threshold = float(np.percentile(distances, breakpoint_percentile))

    chunks: list[str] = []
    current: list[str] = [sentences[0]]
    for i, dist in enumerate(distances):
        if dist > threshold:
            chunks.append(" ".join(current))
            current = [sentences[i + 1]]
        else:
            current.append(sentences[i + 1])

    if current:
        chunks.append(" ".join(current))

    return chunks


def _find_section_header(
    position: int,
    headers: list[tuple[int, str]],
) -> str | None:
    current: str | None = None
    for pos, header in headers:
        if pos <= position:
            current = header
        else:
            break
    return current
