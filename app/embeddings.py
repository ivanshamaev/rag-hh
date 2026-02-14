"""
Эмбеддинги через sentence-transformers (локально, поддерживает русский).
Размерность модели paraphrase-multilingual-MiniLM-L12-v2 — 384.
"""
from functools import lru_cache
from typing import Any

from sentence_transformers import SentenceTransformer

from app.config import settings


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model)


def embed(text: str) -> list[float]:
    """Один текст -> вектор размерности 384."""
    model = get_embedding_model()
    vec = model.encode(text, convert_to_numpy=True)
    return vec.tolist()


def embed_batch(texts: list[str], batch_size: int = 32) -> list[list[float]]:
    """Пакет текстов -> список векторов."""
    if not texts:
        return []
    model = get_embedding_model()
    vecs = model.encode(texts, batch_size=batch_size, convert_to_numpy=True)
    return [v.tolist() for v in vecs]
