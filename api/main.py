"""
api/main.py — FastAPI приложение

Точка входа для веб-сервера. Подключает роутеры,
настраивает CORS, middleware и документацию.

Запуск:
    uv run uvicorn api.main:app --reload --port 8000

Документация доступна по адресу:
    http://localhost:8000/docs     — Swagger UI
    http://localhost:8000/redoc   — ReDoc
"""

import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import topics
from api.schemas import HealthResponse

from api.routers import auth, topics

logger = logging.getLogger(__name__)

# Создание приложения FastAPI

app = FastAPI(
    title="TopicAdvisor API",
    description="Интеллектуальная система поддержки выбора тем ВКР на основе arXiv",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — разрешаем запросы от фронтенда 

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev-сервер
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Роутеры — подключаем эндпоинты из разных модулей

app.include_router(topics.router)
app.include_router(auth.router)

# Системные эндпоинты — корневой и health check

@app.get("/", include_in_schema=False)
async def root() -> dict:
    """Редирект на документацию."""
    return {"message": "TopicAdvisor API", "docs": "/docs"}


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Health check",
)
async def health() -> HealthResponse:
    """Проверка работоспособности сервера."""
    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc),
    )