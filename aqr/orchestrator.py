"""Оркестратор: запуск всей фабрики (генераторы + workers + insight loop + API)."""
from __future__ import annotations
import asyncio, logging, os, multiprocessing as mp
import uvicorn
from .generators.explorer import Explorer
from .generators.exploiter import Exploiter
from .generators.mutator import Mutator
from .generators.base import GeneratorConfig
from .insight_loop import loop_forever as insight_loop
from .db.schema import init_schema
from .workers.backtest_worker import run_worker

log = logging.getLogger(__name__)


DEFAULT_GENERATORS = [
    GeneratorConfig(name="explorer-1", generator_type="explorer",
                    model="claude-sonnet-4-5", temperature=1.0,
                    max_hyp_per_call=5, calls_per_minute=6, daily_budget_usd=15),
    GeneratorConfig(name="exploiter-1", generator_type="exploiter",
                    model="claude-haiku-4", temperature=0.7,
                    max_hyp_per_call=20, calls_per_minute=30, daily_budget_usd=15),
    GeneratorConfig(name="exploiter-2", generator_type="exploiter",
                    model="claude-haiku-4", temperature=0.9,
                    max_hyp_per_call=20, calls_per_minute=30, daily_budget_usd=15),
    GeneratorConfig(name="mutator-1", generator_type="mutator",
                    model="claude-haiku-4", temperature=0.8,
                    max_hyp_per_call=10, calls_per_minute=15, daily_budget_usd=5),
]

N_WORKERS = int(os.environ.get("N_BACKTEST_WORKERS", "10"))


async def run_generators():
    tasks = []
    for cfg in DEFAULT_GENERATORS:
        cls = {"explorer": Explorer, "exploiter": Exploiter, "mutator": Mutator}[cfg.generator_type]
        gen = cls(cfg)
        tasks.append(asyncio.create_task(gen.start()))
    await asyncio.gather(*tasks)


async def run_api():
    config = uvicorn.Config("aqr.api.server:app", host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def _worker_entrypoint(worker_id: str):
    asyncio.run(run_worker(worker_id))


async def main():
    init_schema()
    log.info("Schema initialized")

    # Workers — отдельные процессы
    workers = []
    for i in range(N_WORKERS):
        p = mp.Process(target=_worker_entrypoint, args=(f"w{i}",), daemon=True)
        p.start()
        workers.append(p)
    log.info(f"Started {N_WORKERS} backtest workers")

    # Всё остальное — async в главном процессе
    await asyncio.gather(
        run_generators(),
        insight_loop(interval_sec=3600),
        run_api(),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    asyncio.run(main())
