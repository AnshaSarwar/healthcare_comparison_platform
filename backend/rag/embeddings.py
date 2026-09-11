from __future__ import annotations

import hashlib
import json
import logging

from openai import OpenAI

from backend.core.config import get_settings
from backend.rag.cache import get_redis

logger = logging.getLogger(__name__)


class CachedOpenAIEmbeddings:
    """OpenAI embeddings with a Redis exact-text cache."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model = settings.ollama_embedding_model
        self._inner = OpenAI(
            api_key=settings.openai_api_key or None,
            base_url=settings.ollama_base_url or None,
        )

    def _cache_key(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"emb:{self._model}:{digest}"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        client = get_redis()
        results: list[list[float] | None] = [None] * len(texts)
        missing_indexes: list[int] = []
        missing_texts: list[str] = []

        for index, text in enumerate(texts):
            if client is not None:
                raw = client.get(self._cache_key(text))
                if raw:
                    try:
                        results[index] = json.loads(raw)
                        continue
                    except json.JSONDecodeError:
                        pass
            missing_indexes.append(index)
            missing_texts.append(text)

        if missing_texts:
            response = self._inner.embeddings.create(model=self._model, input=missing_texts)
            vectors = [item.embedding for item in response.data]
            for index, vector in zip(missing_indexes, vectors, strict=True):
                results[index] = vector
                if client is not None:
                    client.set(self._cache_key(texts[index]), json.dumps(vector), ex=60 * 60 * 24 * 7)

        filled: list[list[float]] = []
        for vector in results:
            if vector is None:
                raise RuntimeError("Embedding cache returned an incomplete batch")
            filled.append(vector)
        return filled

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def get_embeddings() -> CachedOpenAIEmbeddings:
    return CachedOpenAIEmbeddings()
