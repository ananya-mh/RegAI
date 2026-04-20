from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-base-en-v1.5"
EMBEDDING_DIM = 768

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def embed_texts(texts: list[str]) -> NDArray[np.float32]:
    model = get_model()
    embeddings: NDArray[np.float32] = model.encode(texts, normalize_embeddings=True)
    return embeddings


def embed_query(text: str) -> NDArray[np.float32]:
    model = get_model()
    embedding: NDArray[np.float32] = model.encode([text], normalize_embeddings=True)[0]
    return embedding


class BGEEmbeddings:
    """LangChain-compatible embedding wrapper for bge-base-en-v1.5."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(texts).tolist()  # type: ignore[return-value]

    def embed_query(self, text: str) -> list[float]:
        return embed_query(text).tolist()  # type: ignore[return-value]

    def __call__(self, text: str) -> list[float]:
        return self.embed_query(text)
