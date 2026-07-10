"""FastAPI dashboard + SSE stream."""
from __future__ import annotations
import asyncio, json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from ..db.schema import get_conn
from ..queue.streams import get_redis, STREAM_TOP

app = FastAPI(title="AQR Stream API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory registry of paused generators (set by orchestrator)
PAUSED: set[str] = set()


@app.get("/stats")
async def stats():
    conn = get_conn(read_only=True)
    try:
        overall = conn.execute("""
            SELECT
              (SELECT COUNT(*) FROM hypotheses) AS total,
              (SELECT COUNT(*) FROM hypotheses WHERE status='pending') AS pending,
              (SELECT COUNT(*) FROM hypotheses WHERE status='tested') AS tested,
              (SELECT COUNT(*) FROM hypotheses WHERE status='duplicate') AS duplicates,
              (SELECT COUNT(*) FROM backtest_results WHERE sharpe > 3) AS s_gt_3,
              (SELECT COUNT(*) FROM backtest_results WHERE sharpe > 5) AS s_gt_5,
              (SELECT SUM(cost_usd) FROM llm_calls WHERE DATE(called_at) = CURRENT_DATE) AS cost_today
        """).fetchone()
        gens = conn.execute("SELECT * FROM generator_stats").fetchall()
        return {
            "total": overall[0], "pending": overall[1], "tested": overall[2],
            "duplicates": overall[3], "sharpe_gt_3": overall[4], "sharpe_gt_5": overall[5],
            "cost_today_usd": float(overall[6] or 0),
            "generators": [dict(zip(
                ["type", "n_generated", "n_tested", "n_duplicate", "avg_sharpe",
                 "max_sharpe", "n_sharpe_gt_3", "n_sharpe_gt_5", "total_cost"], g
            )) for g in gens],
        }
    finally:
        conn.close()


@app.get("/top")
async def top(limit: int = 20):
    conn = get_conn(read_only=True)
    try:
        rows = conn.execute(f"""
            SELECT h.id, h.hypothesis, h.category, h.block_name, h.params,
                   r.sharpe, r.pvalue, r.best_regime, r.max_dd, r.n
            FROM hypotheses h JOIN backtest_results r ON h.id = r.hypothesis_id
            WHERE r.pvalue < 0.05 AND r.n > 200
            ORDER BY r.sharpe DESC LIMIT {int(limit)}
        """).fetchall()
        return [dict(zip(
            ["id","hypothesis","category","block_name","params",
             "sharpe","pvalue","best_regime","max_dd","n"], r
        )) for r in rows]
    finally:
        conn.close()


@app.get("/insights")
async def insights():
    conn = get_conn(read_only=True)
    try:
        rows = conn.execute("""
            SELECT id, insight_type, text, confidence, applies_to_generators, created_at
            FROM insights WHERE is_active = TRUE
            ORDER BY generation DESC, confidence DESC
        """).fetchall()
        return [dict(zip(["id","type","text","confidence","applies_to","created_at"], r))
                for r in rows]
    finally:
        conn.close()


@app.post("/generators/{gen_type}/pause")
async def pause_generator(gen_type: str):
    PAUSED.add(gen_type)
    return {"ok": True, "paused": list(PAUSED)}


@app.post("/generators/{gen_type}/resume")
async def resume_generator(gen_type: str):
    PAUSED.discard(gen_type)
    return {"ok": True, "paused": list(PAUSED)}


@app.get("/generators/paused")
async def get_paused():
    return {"paused": list(PAUSED)}


@app.get("/stream/top")
async def stream_top():
    """SSE-поток: новые находки Sharpe > 5."""
    r = await get_redis()
    async def gen():
        last_id = "$"
        while True:
            resp = await r.xread({STREAM_TOP: last_id}, block=30000)
            if not resp:
                yield ": keep-alive\n\n"
                continue
            for _, messages in resp:
                for msg_id, fields in messages:
                    last_id = msg_id
                    yield f"data: {fields['data']}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
