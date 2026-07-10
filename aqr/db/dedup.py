"""Semantic deduplication через FAISS + embedding cache."""
from __future__ import annotations
import os, pickle, hashlib
from pathlib import Path
import numpy as np


FAISS_INDEX_PATH = Path(os.environ.get("FAISS_INDEX_PATH", "./workspace/faiss.index"))
EMBEDDING_DIM = 1536


class SemanticDedup:
    """
    Отбрасывает семантически близкие гипотезы.
    Threshold: cosine distance < 0.15 (~0.85 similarity) считается дубликатом.
    """

    def __init__(self, dim: int = EMBEDDING_DIM, threshold: float = 0.15):
        import faiss
        self.dim = dim
        self.threshold = threshold
        if FAISS_INDEX_PATH.exists():
            self.index = faiss.read_index(str(FAISS_INDEX_PATH))
        else:
            self.index = faiss.IndexFlatIP(dim)   # inner product on normalized = cosine
        # Кэш по hash содержимого — избежать повторных embed'ов одного текста
        self._text_hash_cache: dict[str, np.ndarray] = {}

    async def _embed(self, text: str) -> np.ndarray:
        """Кэшированный embedding через OpenAI text-embedding-3-small."""
        h = hashlib.sha1(text.encode()).hexdigest()
        if h in self._text_hash_cache:
            return self._text_hash_cache[h]
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        resp = await client.embeddings.create(
            model="text-embedding-3-small", input=text[:8000]
        )
        vec = np.array(resp.data[0].embedding, dtype=np.float32)
        vec = vec / np.linalg.norm(vec)  # для inner-product = cosine
        self._text_hash_cache[h] = vec
        return vec

    async def is_duplicate(self, text: str) -> tuple[bool, float]:
        """
        Returns (is_dup, similarity_to_nearest).
        """
        emb = await self._embed(text)
        if self.index.ntotal == 0:
            self.index.add(emb.reshape(1, -1))
            return False, 0.0
        sims, _ = self.index.search(emb.reshape(1, -1), k=1)
        best_sim = float(sims[0][0])
        if best_sim >= (1 - self.threshold):
            return True, best_sim
        self.index.add(emb.reshape(1, -1))
        return False, best_sim

    def save(self):
        import faiss
        faiss.write_index(self.index, str(FAISS_INDEX_PATH))
