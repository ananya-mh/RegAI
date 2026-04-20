from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sentence_transformers import CrossEncoder

from backend.rag.chunking import Chunk
from backend.rag.embeddings import embed_query, embed_texts
from backend.rag.vector_stores import PolicyStore, RegulatoryStore

logger = logging.getLogger(__name__)

RERANKER_MODEL = "BAAI/bge-reranker-base"
GAP_THRESHOLD = 0.65

_reranker: CrossEncoder | None = None


def get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(RERANKER_MODEL)
    return _reranker


@dataclass
class RetrievalPair:
    regulatory: Chunk
    policy: Chunk
    similarity: float
    relevance_score: float
    is_potential_gap: bool


@dataclass
class RetrievalResult:
    pairs: list[RetrievalPair]
    regulatory_chunks: list[tuple[Chunk, float]]
    policy_chunks: list[tuple[Chunk, float]]


def compute_cross_matches(
    reg_embeddings: NDArray[np.float32],
    pol_embeddings: NDArray[np.float32],
    gap_threshold: float = GAP_THRESHOLD,
) -> list[tuple[int, int, float, bool]]:
    """Pure-math cross-matching: pair each regulation with its best policy match.

    Returns list of (reg_idx, pol_idx, similarity, is_potential_gap).
    """
    sim_matrix: NDArray[np.float32] = reg_embeddings @ pol_embeddings.T

    matches: list[tuple[int, int, float, bool]] = []
    for i in range(len(reg_embeddings)):
        best_j = int(np.argmax(sim_matrix[i]))
        best_sim = float(sim_matrix[i, best_j])
        matches.append((i, best_j, best_sim, best_sim < gap_threshold))
    return matches


def retrieve_and_rerank(
    query: str,
    regulatory_store: RegulatoryStore,
    policy_store: PolicyStore,
    retrieval_k: int = 15,
    top_k: int = 5,
    gap_threshold: float = GAP_THRESHOLD,
) -> RetrievalResult:
    """Three-stage retrieval pipeline.

    Stage 1: embed query, retrieve top-k from FAISS and Chroma in parallel.
    Stage 2: cross-match each regulatory chunk with best policy chunk.
    Stage 3: re-rank pairs with bge-reranker-base cross-encoder.
    """
    # Stage 1 — parallel retrieval
    query_emb = embed_query(query)
    reg_results = regulatory_store.search(query_emb, k=retrieval_k)
    pol_results = policy_store.search(query_emb, k=retrieval_k)

    if not reg_results or not pol_results:
        return RetrievalResult(
            pairs=[],
            regulatory_chunks=reg_results,
            policy_chunks=pol_results,
        )

    reg_chunks = [r[0] for r in reg_results]
    pol_chunks = [p[0] for p in pol_results]

    # Stage 2 — cross-matching
    reg_embs = embed_texts([c.text for c in reg_chunks])
    pol_embs = embed_texts([c.text for c in pol_chunks])
    matches = compute_cross_matches(reg_embs, pol_embs, gap_threshold)

    pairs: list[RetrievalPair] = []
    for reg_idx, pol_idx, sim, is_gap in matches:
        pairs.append(
            RetrievalPair(
                regulatory=reg_chunks[reg_idx],
                policy=pol_chunks[pol_idx],
                similarity=sim,
                relevance_score=0.0,
                is_potential_gap=is_gap,
            )
        )

    # Stage 3 — re-ranking with cross-encoder
    reranker = get_reranker()
    rerank_inputs: list[list[str]] = [
        [query, f"{p.regulatory.text} [SEP] {p.policy.text}"] for p in pairs
    ]
    scores: NDArray[np.float32] = reranker.predict(rerank_inputs)

    for pair, score in zip(pairs, scores, strict=True):
        pair.relevance_score = float(score)

    pairs.sort(key=lambda p: p.relevance_score, reverse=True)

    logger.info(
        "Retrieved %d reg + %d pol chunks, produced %d pairs (top-%d returned)",
        len(reg_results),
        len(pol_results),
        len(pairs),
        top_k,
    )

    return RetrievalResult(
        pairs=pairs[:top_k],
        regulatory_chunks=reg_results,
        policy_chunks=pol_results,
    )
