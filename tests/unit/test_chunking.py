from __future__ import annotations

import uuid

import numpy as np
import pytest

from backend.rag.chunking import chunk_regulatory
from backend.rag.embeddings import EMBEDDING_DIM


def _can_load_model() -> bool:
    try:
        from sentence_transformers import SentenceTransformer

        SentenceTransformer("BAAI/bge-base-en-v1.5")
    except Exception:
        return False
    else:
        return True


def _make_requirement(
    article: str | None = None,
    section: str | None = None,
    clause: str | None = None,
    full_text: str = "",
    parent_id: uuid.UUID | None = None,
    framework_id: uuid.UUID | None = None,
) -> dict:
    return {
        "id": uuid.uuid4(),
        "framework_id": framework_id or uuid.uuid4(),
        "article": article,
        "section": section,
        "clause": clause,
        "full_text": full_text,
        "parent_requirement_id": parent_id,
    }


class TestRegulatoryChunking:
    def test_clause_boundaries_respected(self):
        fw_id = uuid.uuid4()
        r1 = _make_requirement(
            article="1",
            clause="1",
            full_text="First clause of article one. " * 15,
            framework_id=fw_id,
        )
        r2 = _make_requirement(
            article="1",
            clause="2",
            full_text="Second clause of article one. " * 15,
            framework_id=fw_id,
        )

        chunks = chunk_regulatory([r1, r2], framework_name="GDPR")

        assert len(chunks) == 2
        assert "First clause" in chunks[0].text
        assert "Second clause" in chunks[1].text
        assert "Second clause" not in chunks[0].text

    def test_long_clause_splits_at_sentence_boundary(self):
        long_text = ". ".join(f"Sentence number {i} with some extra words here" for i in range(100))
        req = _make_requirement(article="5", clause="1", full_text=long_text)

        chunks = chunk_regulatory([req], max_tokens=50)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk.text.split()) <= 55  # some tolerance

    def test_short_clause_kept_as_single_chunk(self):
        req = _make_requirement(
            article="3", clause="1", full_text="Data must be encrypted at rest."
        )
        chunks = chunk_regulatory([req])
        assert len(chunks) == 1

    def test_structural_parents_skipped_when_short(self):
        fw_id = uuid.uuid4()
        chapter = _make_requirement(
            section="Chapter I", full_text="General provisions", framework_id=fw_id
        )
        article = _make_requirement(
            article="1",
            full_text="The entity shall protect data. " * 20,
            parent_id=chapter["id"],
            framework_id=fw_id,
        )
        chunks = chunk_regulatory([chapter, article], min_tokens=10)
        texts = [c.text for c in chunks]
        assert not any("General provisions" == t for t in texts)
        assert any("The entity shall protect data." in t for t in texts)

    def test_metadata_preserved(self):
        fw_id = uuid.uuid4()
        req = _make_requirement(
            article="17",
            section="Right to Erasure",
            clause="1",
            full_text="The data subject shall have the right to obtain erasure. " * 10,
            framework_id=fw_id,
        )
        chunks = chunk_regulatory([req], framework_name="GDPR")

        assert len(chunks) == 1
        meta = chunks[0].metadata
        assert meta["article"] == "17"
        assert meta["section"] == "Right to Erasure"
        assert meta["clause"] == "1"
        assert meta["framework_id"] == str(fw_id)
        assert "GDPR" in meta["parent_path"]
        assert "Article 17" in meta["parent_path"]

    def test_parent_path_built_correctly(self):
        fw_id = uuid.uuid4()
        chapter = _make_requirement(
            section="Chapter II", full_text="Principles", framework_id=fw_id
        )
        article = _make_requirement(
            article="5",
            full_text="Principles relating to processing. " * 15,
            parent_id=chapter["id"],
            framework_id=fw_id,
        )
        chunks = chunk_regulatory([chapter, article], framework_name="GDPR")
        article_chunks = [c for c in chunks if c.metadata.get("article") == "5"]
        assert article_chunks
        path = article_chunks[0].metadata["parent_path"]
        assert "GDPR" in path
        assert "Chapter II" in path
        assert "Article 5" in path

    def test_empty_text_skipped(self):
        req = _make_requirement(full_text="")
        chunks = chunk_regulatory([req])
        assert len(chunks) == 0


class TestEmbeddingDimensions:
    @pytest.mark.skipif(not _can_load_model(), reason="Embedding model not available")
    def test_embedding_output_shape(self):
        from backend.rag.embeddings import embed_texts

        vecs = embed_texts(["test sentence"])
        assert vecs.shape == (1, EMBEDDING_DIM)
        assert vecs.dtype == np.float32

    @pytest.mark.skipif(not _can_load_model(), reason="Embedding model not available")
    def test_embeddings_are_normalized(self):
        from backend.rag.embeddings import embed_texts

        vecs = embed_texts(["hello world", "another test"])
        norms = np.linalg.norm(vecs, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)
