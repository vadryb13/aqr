"""
Сквозной пайплайн: цель на естественном языке → результат с нарративом.

Модуль спроектирован как минимально работающий вертикальный срез:
- не требует Redis
- не требует DuckDB
- LLM опционален (fallback на детерминистский планировщик)
- все шаги эмитят события в общую очередь для живой ленты
"""
from .events import EventBus, Event
from .planner import ChatPlanner, ResearchPlan
from .executor import PipelineExecutor, PipelineResult
from .narrator import Narrator

__all__ = [
    "EventBus", "Event",
    "ChatPlanner", "ResearchPlan",
    "PipelineExecutor", "PipelineResult",
    "Narrator",
]
