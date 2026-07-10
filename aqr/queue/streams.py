"""Redis Streams: producer + consumer + backpressure."""
from __future__ import annotations
import os, json, uuid
from typing import Optional
import redis.asyncio as aioredis


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# Stream names
STREAM_PENDING = "hypotheses:pending"
STREAM_TESTED  = "hypotheses:tested"
STREAM_TOP     = "hypotheses:top"
STREAM_ERRORS  = "hypotheses:errors"

# Consumer group
GROUP_WORKERS  = "backtest_workers"

# Backpressure thresholds
MAX_QUEUE_DEPTH_SOFT = int(os.environ.get("MAX_QUEUE_DEPTH_SOFT", "5000"))
MAX_QUEUE_DEPTH_HARD = int(os.environ.get("MAX_QUEUE_DEPTH_HARD", "20000"))


async def get_redis():
    return await aioredis.from_url(REDIS_URL, decode_responses=True)


async def ensure_group(r, stream: str, group: str):
    try:
        await r.xgroup_create(stream, group, id="0", mkstream=True)
    except Exception:
        pass  # уже существует


class HypothesisProducer:
    """Producer для генераторов."""
    def __init__(self, r):
        self.r = r

    async def push(self, hypothesis: dict) -> str:
        """Добавить гипотезу в очередь. Возвращает stream message id."""
        payload = {"data": json.dumps(hypothesis)}
        msg_id = await self.r.xadd(STREAM_PENDING, payload)
        return msg_id

    async def queue_depth(self) -> int:
        return await self.r.xlen(STREAM_PENDING)

    async def backpressure_wait(self) -> float:
        """Возвращает multiplier для замедления (1.0 = normal, 2.0 = wait 2x)."""
        depth = await self.queue_depth()
        if depth > MAX_QUEUE_DEPTH_HARD:
            return 10.0    # ждём сильно
        if depth > MAX_QUEUE_DEPTH_SOFT:
            return 3.0
        return 1.0


class HypothesisConsumer:
    """Consumer для workers."""
    def __init__(self, r, worker_id: str):
        self.r = r
        self.worker_id = worker_id

    async def start(self):
        await ensure_group(self.r, STREAM_PENDING, GROUP_WORKERS)

    async def read_batch(self, count: int = 10, block_ms: int = 5000) -> list[tuple[str, dict]]:
        """Возвращает список (msg_id, hypothesis_dict)."""
        resp = await self.r.xreadgroup(
            GROUP_WORKERS, self.worker_id,
            {STREAM_PENDING: ">"}, count=count, block=block_ms
        )
        if not resp:
            return []
        _, messages = resp[0]
        out = []
        for msg_id, fields in messages:
            hyp = json.loads(fields["data"])
            out.append((msg_id, hyp))
        return out

    async def ack(self, msg_id: str):
        await self.r.xack(STREAM_PENDING, GROUP_WORKERS, msg_id)

    async def publish_result(self, result: dict, top: bool = False):
        stream = STREAM_TOP if top else STREAM_TESTED
        await self.r.xadd(stream, {"data": json.dumps(result)})
