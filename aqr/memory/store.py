"""
4-tier hierarchical memory store для автономного research engine.

L1: memory_events        — сырые события (30 дней retention)
L2: insights             — рабочая память (24-72ч, было)
L3: heuristics           — устойчивые паттерны (weeks-months)
L4: laws                 — фундаментальные истины (permanent)

Semantic retrieval через FAISS для каждого уровня.
"""
from __future__ import annotations
import uuid, json
from datetime import timedelta
from pathlib import Path
from typing import Optional
import numpy as np

from ..db.schema import get_conn


MEMORY_SCHEMA = """
-- L1: сырые события агентов
CREATE TABLE IF NOT EXISTS memory_events (
    id           VARCHAR PRIMARY KEY,
    agent        VARCHAR,
    event_type   VARCHAR,     -- llm_call/decision/error/observation
    content      TEXT,
    metadata     JSON,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_events_agent ON memory_events(agent);
CREATE INDEX IF NOT EXISTS idx_events_created ON memory_events(created_at);

-- L3: устойчивые эвристики
CREATE TABLE IF NOT EXISTS heuristics (
    id                  VARCHAR PRIMARY KEY,
    text                TEXT,
    domain              VARCHAR,       -- arb/pairs/regime/etc
    supporting_evidence VARCHAR[],     -- hypothesis_ids
    n_evidence          INTEGER,
    confidence          DOUBLE,
    embedding           FLOAT[1536],
    promoted_from       VARCHAR,       -- insight_id
    last_validated_at   TIMESTAMP,
    validation_count    INTEGER DEFAULT 0,
    valid_streak        INTEGER DEFAULT 0,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_heur_domain ON heuristics(domain);
CREATE INDEX IF NOT EXISTS idx_heur_conf ON heuristics(confidence DESC);

-- L4: фундаментальные законы (immutable, ручное подтверждение)
CREATE TABLE IF NOT EXISTS laws (
    id                  VARCHAR PRIMARY KEY,
    text                TEXT,
    domain              VARCHAR,
    scope               VARCHAR,       -- moex/global/asset_class
    supporting_evidence VARCHAR[],
    n_evidence          INTEGER,
    confirmed_by_human  BOOLEAN DEFAULT FALSE,
    embedding           FLOAT[1536],
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Аудит промоций/демоций
CREATE TABLE IF NOT EXISTS memory_transitions (
    id            VARCHAR PRIMARY KEY,
    entity_id     VARCHAR,
    from_tier     VARCHAR,     -- L1/L2/L3/L4
    to_tier       VARCHAR,
    reason        TEXT,
    triggered_by  VARCHAR,     -- agent или "auto"
    transitioned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class MemoryStore:
    """
    Единый интерфейс к 4-уровневой памяти.
    """

    def __init__(self, embedder=None):
        self._init_schema()
        self.embedder = embedder  # объект с async embed(text) → np.ndarray

    def _init_schema(self):
        conn = get_conn()
        conn.execute(MEMORY_SCHEMA)
        conn.close()

    # ── L1: events ────────────────────────────────────────────────
    def log_event(self, agent: str, event_type: str, content: str,
                  metadata: Optional[dict] = None) -> str:
        eid = str(uuid.uuid4())
        conn = get_conn()
        try:
            conn.execute("""
                INSERT INTO memory_events (id, agent, event_type, content, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, [eid, agent, event_type, content, json.dumps(metadata or {})])
        finally:
            conn.close()
        return eid

    def cleanup_old_events(self, days: int = 30):
        conn = get_conn()
        try:
            conn.execute(
                f"DELETE FROM memory_events WHERE created_at < NOW() - INTERVAL {days} DAY"
            )
        finally:
            conn.close()

    # ── L2 → L3: promotion ────────────────────────────────────────
    async def promote_insights_to_heuristics(self, min_evidence: int = 100,
                                              min_confidence: float = 0.85,
                                              min_age_hours: int = 72):
        """
        L2 → L3: insight существует >72ч, evidence >100 гипотез, confidence >0.85,
        и всё ещё подтверждается на свежих данных.
        """
        conn = get_conn()
        try:
            candidates = conn.execute(f"""
                SELECT id, text, applies_to_generators, confidence,
                       evidence_hypothesis_ids, created_at
                FROM insights
                WHERE is_active = TRUE
                  AND created_at < NOW() - INTERVAL {min_age_hours} HOUR
                  AND array_length(evidence_hypothesis_ids) >= {min_evidence}
                  AND confidence >= {min_confidence}
                  AND id NOT IN (SELECT promoted_from FROM heuristics WHERE promoted_from IS NOT NULL)
            """).fetchall()

            promoted = 0
            for cid, text, applies_to, conf, evid, _ in candidates:
                # Проверка на свежесть паттерна: тот же паттерн должен
                # подтверждаться и в последние 6 часов
                still_valid = await self._validate_on_recent(text, hours=6)
                if not still_valid:
                    continue

                emb = await self._embed(text) if self.embedder else None
                hid = str(uuid.uuid4())
                domain = (applies_to or ["general"])[0]
                conn.execute("""
                    INSERT INTO heuristics (id, text, domain, supporting_evidence,
                                            n_evidence, confidence, embedding,
                                            promoted_from, last_validated_at, valid_streak)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
                """, [hid, text, domain, evid, len(evid or []), conf,
                      emb.tolist() if emb is not None else None, cid])
                self._log_transition(cid, "L2", "L3", "auto_promotion_criteria_met")
                promoted += 1
            return promoted
        finally:
            conn.close()

    # ── L3 revalidation ───────────────────────────────────────────
    async def revalidate_heuristics(self):
        """
        Каждый heuristic периодически проверяется:
        - если >7 дней без проверки → validate on recent data
        - streak считается: сколько подряд валидаций прошёл
        - если streak падает или confidence < 0.5 → demote to L2
        """
        conn = get_conn()
        try:
            stale = conn.execute("""
                SELECT id, text, valid_streak FROM heuristics
                WHERE last_validated_at < NOW() - INTERVAL 7 DAY OR last_validated_at IS NULL
            """).fetchall()

            for hid, text, streak in stale:
                valid = await self._validate_on_recent(text, hours=24)
                if valid:
                    conn.execute("""
                        UPDATE heuristics SET last_validated_at = CURRENT_TIMESTAMP,
                                              validation_count = validation_count + 1,
                                              valid_streak = valid_streak + 1
                        WHERE id = ?
                    """, [hid])
                else:
                    # Демоут в L2 (обратно в активный insight на пересмотр)
                    conn.execute("""
                        INSERT INTO insights (id, insight_type, text, confidence, is_active)
                        VALUES (?, 'demoted_heuristic', ?, 0.4, TRUE)
                    """, [str(uuid.uuid4()), text])
                    conn.execute("DELETE FROM heuristics WHERE id = ?", [hid])
                    self._log_transition(hid, "L3", "L2", "failed_recent_validation")
        finally:
            conn.close()

    # ── L3 → L4: promotion to law ─────────────────────────────────
    async def promote_heuristics_to_laws(self, min_streak: int = 4,
                                          min_age_days: int = 30):
        """
        Heuristic >30 дней, streak >=4 (месяц устойчивых validations) → кандидат в закон.
        Финальное подтверждение — от человека через UI (confirmed_by_human).
        """
        conn = get_conn()
        try:
            candidates = conn.execute(f"""
                SELECT id, text, domain, supporting_evidence, n_evidence, confidence
                FROM heuristics
                WHERE valid_streak >= {min_streak}
                  AND created_at < NOW() - INTERVAL {min_age_days} DAY
                  AND id NOT IN (
                      SELECT DISTINCT entity_id FROM memory_transitions
                      WHERE to_tier = 'L4'
                  )
            """).fetchall()

            for hid, text, domain, evid, n_evid, conf in candidates:
                lid = str(uuid.uuid4())
                conn.execute("""
                    INSERT INTO laws (id, text, domain, scope, supporting_evidence,
                                      n_evidence, confirmed_by_human)
                    VALUES (?, ?, ?, 'moex', ?, ?, FALSE)
                """, [lid, text, domain, evid, n_evid])
                self._log_transition(hid, "L3", "L4", "streak_reached")
        finally:
            conn.close()

    # ── Retrieval ─────────────────────────────────────────────────
    async def retrieve_context(self, generator_type: str, category: Optional[str] = None,
                                k_heuristics: int = 15) -> dict:
        """
        Умная выборка для инжекта в промпт генератора:
        - все активные Laws в домене
        - топ-K релевантных Heuristics через vector search
        - свежие Insights (L2)
        """
        conn = get_conn(read_only=True)
        try:
            laws = conn.execute("""
                SELECT text FROM laws
                WHERE confirmed_by_human = TRUE
                ORDER BY created_at DESC LIMIT 30
            """).fetchall()

            # L3 — простая выборка по domain
            if category:
                heuristics = conn.execute("""
                    SELECT text, confidence FROM heuristics
                    WHERE domain = ? OR domain = 'general'
                    ORDER BY confidence DESC LIMIT ?
                """, [category, k_heuristics]).fetchall()
            else:
                heuristics = conn.execute("""
                    SELECT text, confidence FROM heuristics
                    ORDER BY confidence DESC LIMIT ?
                """, [k_heuristics]).fetchall()

            insights = conn.execute("""
                SELECT text FROM insights
                WHERE is_active = TRUE
                  AND (? = ANY(applies_to_generators) OR 'all' = ANY(applies_to_generators))
                ORDER BY confidence DESC LIMIT 10
            """, [generator_type]).fetchall()

            return {
                "laws": [r[0] for r in laws],
                "heuristics": [{"text": t, "confidence": c} for t, c in heuristics],
                "fresh_insights": [r[0] for r in insights],
            }
        finally:
            conn.close()

    # ── Utils ─────────────────────────────────────────────────────
    async def _embed(self, text: str) -> Optional[np.ndarray]:
        if not self.embedder:
            return None
        return await self.embedder.embed(text)

    async def _validate_on_recent(self, insight_text: str, hours: int = 6) -> bool:
        """
        Placeholder: LLM/статистическая проверка что паттерн ещё работает
        на данных последних N часов. В MVP всегда True.
        """
        # TODO: реальная валидация через meta-LLM или прямой SQL-запрос
        return True

    def _log_transition(self, entity_id: str, from_tier: str, to_tier: str, reason: str):
        conn = get_conn()
        try:
            conn.execute("""
                INSERT INTO memory_transitions (id, entity_id, from_tier, to_tier, reason, triggered_by)
                VALUES (?, ?, ?, ?, ?, 'auto')
            """, [str(uuid.uuid4()), entity_id, from_tier, to_tier, reason])
        finally:
            conn.close()

    def stats(self) -> dict:
        conn = get_conn(read_only=True)
        try:
            return {
                "L1_events": conn.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0],
                "L2_insights_active": conn.execute("SELECT COUNT(*) FROM insights WHERE is_active").fetchone()[0],
                "L3_heuristics": conn.execute("SELECT COUNT(*) FROM heuristics").fetchone()[0],
                "L4_laws": conn.execute("SELECT COUNT(*) FROM laws").fetchone()[0],
                "L4_confirmed": conn.execute("SELECT COUNT(*) FROM laws WHERE confirmed_by_human").fetchone()[0],
            }
        finally:
            conn.close()


if __name__ == "__main__":
    m = MemoryStore()
    print("Memory tiers:", m.stats())
