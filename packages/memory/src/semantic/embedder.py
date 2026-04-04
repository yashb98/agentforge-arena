"""Hybrid Embedder — FastEmbed (local, free) for bulk + LiteLLM (proxy) for queries."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default model: BAAI/bge-small-en-v1.5 (384-dim, ONNX, CPU)
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384


class HybridEmbedder:
    """FastEmbed for bulk indexing (free, local). LiteLLM for queries (higher quality).

    If LiteLLM is unavailable, queries also fall back to FastEmbed.
    """

    def __init__(
        self,
        fastembed_model: Any = None,
        llm_client: Any = None,
    ) -> None:
        self._fastembed = fastembed_model
        self._llm_client = llm_client

    @classmethod
    def create(cls, llm_client: Any = None) -> HybridEmbedder:
        """Factory that initializes FastEmbed with the default model."""
        from fastembed import TextEmbedding

        fe = TextEmbedding(model_name=DEFAULT_MODEL)
        return cls(fastembed_model=fe, llm_client=llm_client)

    async def embed_bulk(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts using FastEmbed (local, free)."""
        if not texts:
            return []
        embeddings = list(self._fastembed.embed(texts))
        return [list(e) for e in embeddings]

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query. Uses LiteLLM if available, else FastEmbed."""
        if self._llm_client is not None:
            try:
                response = await self._llm_client.completion(
                    messages=[],
                    model="text-embedding-3-small",
                    max_tokens=1,
                )
                data = response.raw.get("data", [{}])
                if data and "embedding" in data[0]:
                    return data[0]["embedding"][:EMBEDDING_DIM]
            except Exception:
                logger.warning("LiteLLM embedding failed, falling back to FastEmbed")

        embeddings = list(self._fastembed.embed([text]))
        return list(embeddings[0])
