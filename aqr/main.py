"""
Entry point: минимальный FastAPI-сервер вокруг сквозного пайплайна.

Запуск:
    uvicorn aqr.main:app --reload --port 8000

Endpoints:
    POST /pipeline/runs               — стартовать run по свободному запросу
    GET  /pipeline/runs/{run_id}      — снимок событий
    GET  /pipeline/runs/{run_id}/stream — SSE-лента событий
    GET  /health                      — health check
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aqr import __version__
from aqr.pipeline.api import router as pipeline_router

app = FastAPI(
    title="AQR",
    description="Thin pipeline: natural-language goal -> validated hypotheses on MOEX",
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev-режим; сузить в проде
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}
