"""Backtest worker: consumer из Redis Stream, независимый процесс."""
from __future__ import annotations
import asyncio, uuid, time, logging, os, json
from ..queue.streams import HypothesisConsumer, get_redis
from ..db.schema import get_conn

log = logging.getLogger(__name__)


async def run_worker(worker_id: str):
    r = await get_redis()
    consumer = HypothesisConsumer(r, worker_id)
    await consumer.start()
    log.info(f"[worker {worker_id}] started")

    while True:
        try:
            batch = await consumer.read_batch(count=5, block_ms=5000)
            if not batch:
                continue
            for msg_id, hyp in batch:
                await process_one(hyp, worker_id)
                await consumer.ack(msg_id)
        except Exception as e:
            log.exception(f"[worker {worker_id}] error: {e}")
            await asyncio.sleep(5)


async def process_one(hyp: dict, worker_id: str):
    """Полный цикл: load data → backtest → regime → stress → save."""
    t0 = time.time()
    try:
        # 1. Load data (lazy cache)
        from ..data.loader_cache import load_market_data
        data = load_market_data(hyp["assets"], hyp["timeframe"])

        # 2. Backtest
        from ..strategies.blocks import get_block
        block = get_block(hyp["block_name"])
        signals, returns = block(data, **hyp.get("params", {}))
        metrics = compute_metrics(returns)

        # 3. Regime-conditional
        from ..regimes.trend_detector import label_regimes
        regimes = label_regimes(data)
        regime_stats = returns.groupby(regimes).agg(["mean", "std", "count"])
        best_regime = regime_stats["mean"].idxmax() if len(regime_stats) else None

        # 4. Stress-test (5-15 bp TC curve)
        from ..evaluate.stress import tc_curve
        tc_dict = tc_curve(returns, hyp.get("turnover", 0.1))

        # 5. Save
        result = {
            "id": str(uuid.uuid4()),
            "hypothesis_id": hyp["id"],
            **metrics,
            "best_regime": best_regime,
            "best_regime_sharpe": regime_stats["mean"].max() if len(regime_stats) else None,
            "regime_breakdown": regime_stats.to_json(),
            "tc_curve": json.dumps(tc_dict),
            "sharpe_test_5bp": tc_dict.get("5bp"),
            "backtest_duration_ms": int((time.time() - t0) * 1000),
            "worker_id": worker_id,
        }
        _save_result(result)
        _update_hyp_status(hyp["id"], "tested")

        # publish top если Sharpe > 5
        if metrics["sharpe"] > 5:
            r = await get_redis()
            await r.xadd("hypotheses:top", {"data": json.dumps({**hyp, **metrics})})
    except Exception as e:
        log.exception(f"backtest failed: {e}")
        _update_hyp_status(hyp["id"], "failed")


def compute_metrics(returns) -> dict:
    import numpy as np
    r = returns.dropna()
    if len(r) < 30:
        return {"n": len(r), "sharpe": 0, "sortino": 0, "win_rate": 0,
                "total_pct": 0, "max_dd": 0, "pvalue": 1}
    sharpe = float(r.mean() / r.std() * np.sqrt(252))
    downside = r[r < 0].std()
    sortino = float(r.mean() / downside * np.sqrt(252)) if downside > 0 else 0
    cum = (1 + r).cumprod()
    max_dd = float((cum / cum.cummax() - 1).min())
    from scipy import stats
    _, pval = stats.ttest_1samp(r, 0)
    return {
        "n": len(r), "sharpe": sharpe, "sortino": sortino,
        "win_rate": float((r > 0).mean()),
        "total_pct": float(cum.iloc[-1] - 1),
        "max_dd": max_dd, "pvalue": float(pval),
    }


def _save_result(res: dict):
    conn = get_conn()
    try:
        cols = ",".join(res.keys())
        placeholders = ",".join(["?"] * len(res))
        conn.execute(f"INSERT INTO backtest_results ({cols}) VALUES ({placeholders})",
                     list(res.values()))
    finally:
        conn.close()


def _update_hyp_status(hyp_id: str, status: str):
    conn = get_conn()
    try:
        conn.execute("UPDATE hypotheses SET status = ? WHERE id = ?", [status, hyp_id])
    finally:
        conn.close()


if __name__ == "__main__":
    worker_id = os.environ.get("WORKER_ID", f"w-{uuid.uuid4().hex[:6]}")
    asyncio.run(run_worker(worker_id))
