"""
Минимальный FastAPI роутер для сквозного пайплайна.

Endpoints:
- POST /pipeline/runs          — стартовать run от свободного запроса
- GET  /pipeline/runs/{id}     — снимок состояния (все накопленные события)
- GET  /pipeline/runs/{id}/stream — SSE-стрим событий (для UI живой ленты)
"""
from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .events import BUS
from .executor import PipelineExecutor
from .planner import ChatPlanner


router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class RunRequest(BaseModel):
    goal: str


class RunStarted(BaseModel):
    run_id: str
    plan: dict[str, Any]


@router.post("/runs", response_model=RunStarted)
async def start_run(req: RunRequest) -> RunStarted:
    """Принять свободный запрос, спланировать, запустить исполнение в фоне."""
    planner = ChatPlanner()
    plan = planner.plan(req.goal)

    run_id = BUS.new_run()
    executor = PipelineExecutor(BUS)
    asyncio.create_task(executor.run(run_id, plan))

    return RunStarted(run_id=run_id, plan={
        "goal": plan.goal,
        "tickers": plan.tickers,
        "timeframe": plan.timeframe,
        "hypothesis_families": plan.hypothesis_families,
        "n_hypotheses": plan.n_hypotheses,
        "rationale": plan.rationale,
    })


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    """Снимок всех накопленных событий."""
    history = BUS.history(run_id)
    if not history:
        return {"run_id": run_id, "events": [], "status": "unknown"}
    latest = history[-1]
    return {
        "run_id": run_id,
        "events": [
            {"kind": e.kind, "stage": e.stage, "message": e.message,
             "data": e.data, "ts": e.ts}
            for e in history
        ],
        "status": "done" if latest.kind == "done"
                  else "error" if latest.kind == "error"
                  else "running",
    }


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str):
    """SSE-стрим событий."""

    async def gen():
        async for ev in BUS.subscribe(run_id):
            yield f"event: {ev.kind}\ndata: {ev.to_json()}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
