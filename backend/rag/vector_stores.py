from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import chromadb
import faiss
import numpy as np
from numpy.typing import NDArray

from backend.rag.chunking import Chunk
from backend.rag.embeddings import embed_texts

logger = logging.getLogger(__name__)


class RegulatoryStore:
    """FAISS-backed vector store for regulatory chunks (static, rebuilt on ingestion)."""

    def __init__(self, index_path: str | Path) -> None:
        self.index_path = Path(index_path)
        self._index: faiss.IndexFlatIP | None = None
        self._chunks: list[Chunk] = []

    @property
    def size(self) -> int:
        return self._index.ntotal if self._index else 0

    def build(self, chunks: list[Chunk]) -> None:
        texts = [c.text for c in chunks]
        embeddings = embed_texts(texts).astype(np.float32)

        self._index = faiss.IndexFlatIP(embeddings.shape[1])
        self._index.add(embeddings)
        self._chunks = list(chunks)
        logger.info("Built FAISS index with %d vectors", self._index.ntotal)

    def save(self) -> None:
        if self._index is None:
            msg = "No index to save — call build() first"
            raise RuntimeError(msg)

        self.index_path.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self.index_path / "index.faiss"))

        data = [{"id": c.id, "text": c.text, "metadata": c.metadata} for c in self._chunks]
        with open(self.index_path / "chunks.json", "w") as f:
            json.dump(data, f)
        logger.info("Saved FAISS index to %s", self.index_path)

    def load(self) -> None:
        index_file = self.index_path / "index.faiss"
        chunks_file = self.index_path / "chunks.json"

        if not index_file.exists():
            msg = f"FAISS index not found at {index_file}"
            raise FileNotFoundError(msg)

        self._index = faiss.read_index(str(index_file))
        with open(chunks_file) as f:
            data: list[dict[str, Any]] = json.load(f)
        self._chunks = [Chunk(id=d["id"], text=d["text"], metadata=d["metadata"]) for d in data]
        logger.info("Loaded FAISS index with %d vectors", self._index.ntotal)

    def search(
        self,
        query_embedding: NDArray[np.float32],
        k: int = 15,
    ) -> list[tuple[Chunk, float]]:
        if self._index is None or self._index.ntotal == 0:
            return []

        query = query_embedding.reshape(1, -1).astype(np.float32)
        scores, indices = self._index.search(query, min(k, self._index.ntotal))

        results: list[tuple[Chunk, float]] = []
        for idx, score in zip(indices[0], scores[0], strict=True):
            if idx >= 0:
                results.append((self._chunks[int(idx)], float(score)))
        return results


class PolicyStore:
    """Chroma-backed vector store for policy chunks (persistent, append-friendly)."""

    COLLECTION_NAME = "policies"

    def __init__(
        self,
        persist_path: str | Path | None = None,
        host: str = "localhost",
        port: int = 8001,
    ) -> None:
        if persist_path:
            self._client = chromadb.PersistentClient(path=str(persist_path))
        else:
            self._client = chromadb.HttpClient(host=host, port=port)

        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def size(self) -> int:
        return self._collection.count()

    def add(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return

        texts = [c.text for c in chunks]
        embeddings = embed_texts(texts)

        self._collection.upsert(
            ids=[c.id for c in chunks],
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=[c.metadata for c in chunks],
        )
        logger.info("Added %d chunks to Chroma (total: %d)", len(chunks), self._collection.count())

    def search(
        self,
        query_embedding: NDArray[np.float32],
        k: int = 15,
    ) -> list[tuple[Chunk, float]]:
        count = self._collection.count()
        if count == 0:
            return []

        results = self._collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=min(k, count),
            include=["documents", "metadatas", "distances"],
        )

        chunks: list[tuple[Chunk, float]] = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        for i in range(len(ids)):
            chunk = Chunk(id=ids[i], text=docs[i], metadata=metas[i])
            similarity = 1.0 - dists[i]
            chunks.append((chunk, similarity))

        return chunks

    def delete_by_document(self, document_name: str) -> None:
        self._collection.delete(where={"document_name": document_name})

    def reset(self) -> None:
        self._client.delete_collection(self.COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
