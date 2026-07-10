"""
Anti-crowding at generation time.

QuantaAlpha paper (arXiv 2602.07085) shows factor crowding is the central risk
of LLM alpha mining. Rather than filtering ex-post, enforce diversity at generation.

Two mechanisms:
1. Semantic diversity — reject hypotheses too similar to already-tried ones
   via FAISS on hypothesis embeddings
2. Category coverage — bias generation prompts away from over-explored areas
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class DiversityContext:
    """Injected into generator prompts to steer away from crowded areas."""

    already_tried_summaries: list[str]   # 10 recent similar attempts (for LLM to avoid)
    over_explored_categories: list[str]  # e.g. ["z-score momentum", "SMA crossovers"]
    under_explored_categories: list[str] # e.g. ["orderbook imbalance", "vol-of-vol"]
    diversity_target: float = 0.7        # min cosine distance to nearest neighbor

    def to_prompt_injection(self) -> str:
        parts = []
        if self.already_tried_summaries:
            parts.append("**Already extensively tested (AVOID variations of these):**")
            for s in self.already_tried_summaries[:10]:
                parts.append(f"  - {s}")
        if self.over_explored_categories:
            parts.append(f"\n**Over-explored categories (avoid):** {', '.join(self.over_explored_categories)}")
        if self.under_explored_categories:
            parts.append(f"\n**Under-explored (prioritize):** {', '.join(self.under_explored_categories)}")
        parts.append(
            f"\n**Diversity requirement:** Your hypothesis must be semantically "
            f"distinct (cosine distance > {self.diversity_target:.2f}) from prior ones."
        )
        return "\n".join(parts)


class DiversityGuard:
    """
    Pre-generation and post-generation diversity enforcement.

    Uses FAISS index of past hypothesis embeddings.
    """

    def __init__(
        self,
        faiss_index: Any,               # faiss.IndexFlatIP or similar
        embedder,                        # callable str -> np.ndarray
        min_distance: float = 0.15,      # cosine distance in [0, 2]; smaller = more similar
        category_history: dict[str, int] | None = None,
    ):
        self.index = faiss_index
        self.embed = embedder
        self.min_distance = min_distance
        self.category_history = category_history or {}

    def check_novelty(self, hypothesis_text: str) -> tuple[bool, float, str | None]:
        """
        Returns (is_novel, distance_to_nearest, nearest_id_if_similar).
        """
        emb = self.embed(hypothesis_text).astype(np.float32).reshape(1, -1)
        if self.index.ntotal == 0:
            return True, 2.0, None
        distances, ids = self.index.search(emb, k=1)
        d = float(distances[0][0])
        nearest_id = str(ids[0][0]) if ids[0][0] >= 0 else None
        is_novel = d > self.min_distance
        return is_novel, d, nearest_id if not is_novel else None

    def build_context_for_generator(
        self,
        recent_hypotheses: list[dict],
        top_n_avoid: int = 10,
    ) -> DiversityContext:
        """
        Build diversity context to inject into next generator prompt.
        """
        # Take most recent
        summaries = [h.get("summary", h.get("text", ""))[:200] for h in recent_hypotheses[:top_n_avoid]]

        # Count categories
        if self.category_history:
            sorted_cats = sorted(self.category_history.items(), key=lambda x: x[1], reverse=True)
            over_explored = [c for c, n in sorted_cats[:3]]
            under_explored = [c for c, n in sorted_cats[-3:] if n < 20]
        else:
            over_explored = []
            under_explored = []

        return DiversityContext(
            already_tried_summaries=summaries,
            over_explored_categories=over_explored,
            under_explored_categories=under_explored,
        )

    def register(self, hypothesis_id: str, hypothesis_text: str, category: str | None = None):
        """After generation passes checks, register in index + category counter."""
        emb = self.embed(hypothesis_text).astype(np.float32).reshape(1, -1)
        # For IndexIDMap-wrapped indices
        try:
            id_int = int(hypothesis_id[:8], 16) if isinstance(hypothesis_id, str) else int(hypothesis_id)
            self.index.add_with_ids(emb, np.array([id_int], dtype=np.int64))
        except (AttributeError, ValueError):
            self.index.add(emb)

        if category:
            self.category_history[category] = self.category_history.get(category, 0) + 1
