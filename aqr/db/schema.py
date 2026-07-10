"""DuckDB схема для стриминговой генерации."""
from __future__ import annotations
import os
import duckdb
from pathlib import Path


DB_PATH = Path(os.environ.get("DUCKDB_PATH", "./workspace/aqr.duckdb"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


SCHEMA_SQL = """
-- Гипотезы (все, включая дубликаты — для аудита)
CREATE TABLE IF NOT EXISTS hypotheses (
    id                 VARCHAR PRIMARY KEY,
    generator_type     VARCHAR NOT NULL,
    generator_version  VARCHAR,
    hypothesis         TEXT,
    rationale          TEXT,
    category           VARCHAR,
    assets             VARCHAR[],
    timeframe          VARCHAR,
    block_name         VARCHAR,
    params             JSON,
    expected_sharpe    DOUBLE,
    embedding          FLOAT[1536],
    seed_hypothesis_id VARCHAR,       -- для Exploiter/Mutator: от какой винигурировано
    status             VARCHAR DEFAULT 'pending',   -- pending/duplicate/tested/failed/rejected
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_hyp_status ON hypotheses(status);
CREATE INDEX IF NOT EXISTS idx_hyp_generator ON hypotheses(generator_type);
CREATE INDEX IF NOT EXISTS idx_hyp_category ON hypotheses(category);
CREATE INDEX IF NOT EXISTS idx_hyp_created ON hypotheses(created_at);

-- Результаты бэктеста
CREATE TABLE IF NOT EXISTS backtest_results (
    id                     VARCHAR PRIMARY KEY,
    hypothesis_id          VARCHAR REFERENCES hypotheses(id),
    n                      INTEGER,
    sharpe                 DOUBLE,
    sortino                DOUBLE,
    win_rate               DOUBLE,
    total_pct              DOUBLE,
    max_dd                 DOUBLE,
    pvalue                 DOUBLE,
    turnover               DOUBLE,
    tc_bp                  INTEGER,
    best_regime            VARCHAR,
    best_regime_sharpe     DOUBLE,
    regime_breakdown       JSON,
    sharpe_train_5bp       DOUBLE,
    sharpe_test_5bp        DOUBLE,
    tc_curve               JSON,
    backtest_duration_ms   INTEGER,
    worker_id              VARCHAR,
    tested_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_res_sharpe ON backtest_results(sharpe DESC);
CREATE INDEX IF NOT EXISTS idx_res_hyp ON backtest_results(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_res_tested ON backtest_results(tested_at);

-- Инсайты от meta-LLM (feedback loop)
CREATE TABLE IF NOT EXISTS insights (
    id                     VARCHAR PRIMARY KEY,
    generation             INTEGER,
    insight_type           VARCHAR,    -- pattern/warning/recommendation
    text                   TEXT,
    evidence_hypothesis_ids VARCHAR[],
    confidence             DOUBLE,
    applies_to_generators  VARCHAR[],
    is_active              BOOLEAN DEFAULT TRUE,
    created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_insights_active ON insights(is_active);
CREATE INDEX IF NOT EXISTS idx_insights_generation ON insights(generation);

-- Бюджет и стоимость (audit trail)
CREATE TABLE IF NOT EXISTS llm_calls (
    id              VARCHAR PRIMARY KEY,
    generator_type  VARCHAR,
    model           VARCHAR,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        DOUBLE,
    latency_ms      INTEGER,
    n_hypotheses    INTEGER,    -- сколько гипотез вернул этот call
    called_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_calls_gen ON llm_calls(generator_type);
CREATE INDEX IF NOT EXISTS idx_calls_at ON llm_calls(called_at);

-- Метрики генераторов (материализованное для дашборда)
CREATE OR REPLACE VIEW generator_stats AS
SELECT
    h.generator_type,
    COUNT(*) AS n_generated,
    COUNT(CASE WHEN h.status = 'tested' THEN 1 END) AS n_tested,
    COUNT(CASE WHEN h.status = 'duplicate' THEN 1 END) AS n_duplicate,
    AVG(r.sharpe) AS avg_sharpe,
    MAX(r.sharpe) AS max_sharpe,
    COUNT(CASE WHEN r.sharpe > 3 THEN 1 END) AS n_sharpe_gt_3,
    COUNT(CASE WHEN r.sharpe > 5 THEN 1 END) AS n_sharpe_gt_5,
    (SELECT SUM(cost_usd) FROM llm_calls WHERE generator_type = h.generator_type) AS total_cost
FROM hypotheses h
LEFT JOIN backtest_results r ON r.hypothesis_id = h.id
GROUP BY h.generator_type;
"""


def get_conn(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Возвращает соединение с DuckDB. Многопоточный доступ безопасен через WAL."""
    conn = duckdb.connect(str(DB_PATH), read_only=read_only)
    return conn


def init_schema():
    """Идемпотентная инициализация."""
    conn = get_conn()
    conn.execute(SCHEMA_SQL)
    conn.close()


if __name__ == "__main__":
    init_schema()
    print(f"Schema initialized at {DB_PATH}")
