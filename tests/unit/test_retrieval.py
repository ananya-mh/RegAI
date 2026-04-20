from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.rag.chunking import Chunk
from backend.rag.retrieval import (
    compute_cross_matches,
    retrieve_and_rerank,
)


def _chunk(id_: str, text: str) -> Chunk:
    return Chunk(id=id_, text=text, metadata={})


class TestCrossMatching:
    def test_pairs_best_match(self):
        reg = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)
        pol = np.array([[0.9, 0.1, 0], [0.1, 0.9, 0]], dtype=np.float32)
        norms = np.linalg.norm(pol, axis=1, keepdims=True)
        pol = pol / norms

        matches = compute_cross_matches(reg, pol)

        assert matches[0][1] == 0  # reg[0] best matches pol[0]
        assert matches[1][1] == 1  # reg[1] best matches pol[1]

    def test_gap_flagged_below_threshold(self):
        reg = np.array([[1, 0, 0]], dtype=np.float32)
        pol = np.array([[0, 1, 0]], dtype=np.float32)

        matches = compute_cross_matches(reg, pol, gap_threshold=0.65)

        assert matches[0][3] is True  # orthogonal → similarity ~0 → gap

    def test_no_gap_above_threshold(self):
        reg = np.array([[1, 0, 0]], dtype=np.float32)
        pol = np.array([[0.95, 0.1, 0]], dtype=np.float32)
        pol = pol / np.linalg.norm(pol)
        pol = pol.reshape(1, -1)

        matches = compute_cross_matches(reg, pol, gap_threshold=0.65)

        assert matches[0][3] is False
        assert matches[0][2] > 0.65

    def test_multiple_regs_can_match_same_policy(self):
        reg = np.array(
            [[1, 0, 0], [0.9, 0.1, 0], [0, 0, 1]],
            dtype=np.float32,
        )
        reg = reg / np.linalg.norm(reg, axis=1, keepdims=True)
        pol = np.array([[1, 0, 0], [0, 0, 1]], dtype=np.float32)

        matches = compute_cross_matches(reg, pol)

        assert matches[0][1] == 0
        assert matches[1][1] == 0  # reg[1] also closest to pol[0]
        assert matches[2][1] == 1


class TestReRanking:
    @patch("backend.rag.retrieval.get_reranker")
    @patch("backend.rag.retrieval.embed_texts")
    @patch("backend.rag.retrieval.embed_query")
    def test_reranking_reorders_by_relevance(
        self,
        mock_embed_query: MagicMock,
        mock_embed_texts: MagicMock,
        mock_get_reranker: MagicMock,
    ) -> None:
        mock_embed_query.return_value = np.array([1, 0, 0], dtype=np.float32)

        def _embed_side_effect(texts: list[str]) -> np.ndarray:
            return np.eye(len(texts), 3, dtype=np.float32)

        mock_embed_texts.side_effect = _embed_side_effect

        mock_reranker = MagicMock()
        mock_reranker.predict.return_value = np.array([0.2, 0.9, 0.5])
        mock_get_reranker.return_value = mock_reranker

        reg_store = MagicMock()
        reg_store.search.return_value = [
            (_chunk("r1", "regulation A"), 0.9),
            (_chunk("r2", "regulation B"), 0.8),
            (_chunk("r3", "regulation C"), 0.7),
        ]

        pol_store = MagicMock()
        pol_store.search.return_value = [
            (_chunk("p1", "policy X"), 0.9),
            (_chunk("p2", "policy Y"), 0.8),
            (_chunk("p3", "policy Z"), 0.7),
        ]

        result = retrieve_and_rerank("test query", reg_store, pol_store, retrieval_k=3, top_k=3)

        assert result.pairs[0].relevance_score == pytest.approx(0.9)
        assert result.pairs[1].relevance_score == pytest.approx(0.5)
        assert result.pairs[2].relevance_score == pytest.approx(0.2)

    @patch("backend.rag.retrieval.get_reranker")
    @patch("backend.rag.retrieval.embed_texts")
    @patch("backend.rag.retrieval.embed_query")
    def test_empty_results_handled(
        self,
        mock_embed_query: MagicMock,
        mock_embed_texts: MagicMock,
        mock_get_reranker: MagicMock,
    ) -> None:
        mock_embed_query.return_value = np.array([1, 0, 0], dtype=np.float32)

        reg_store = MagicMock()
        reg_store.search.return_value = []
        pol_store = MagicMock()
        pol_store.search.return_value = [(_chunk("p1", "policy"), 0.9)]

        result = retrieve_and_rerank("test", reg_store, pol_store)

        assert result.pairs == []
        mock_get_reranker.assert_not_called()

    @patch("backend.rag.retrieval.get_reranker")
    @patch("backend.rag.retrieval.embed_texts")
    @patch("backend.rag.retrieval.embed_query")
    def test_top_k_limits_output(
        self,
        mock_embed_query: MagicMock,
        mock_embed_texts: MagicMock,
        mock_get_reranker: MagicMock,
    ) -> None:
        mock_embed_query.return_value = np.array([1, 0], dtype=np.float32)
        mock_embed_texts.side_effect = lambda t: np.eye(len(t), 2, dtype=np.float32)

        mock_reranker = MagicMock()
        mock_reranker.predict.return_value = np.array([0.5, 0.3, 0.9, 0.1])
        mock_get_reranker.return_value = mock_reranker

        reg_store = MagicMock()
        reg_store.search.return_value = [
            (_chunk(f"r{i}", f"reg {i}"), 0.9 - i * 0.1) for i in range(4)
        ]
        pol_store = MagicMock()
        pol_store.search.return_value = [
            (_chunk(f"p{i}", f"pol {i}"), 0.9 - i * 0.1) for i in range(4)
        ]

        result = retrieve_and_rerank("q", reg_store, pol_store, retrieval_k=4, top_k=2)

        assert len(result.pairs) == 2
        assert result.pairs[0].relevance_score >= result.pairs[1].relevance_score
