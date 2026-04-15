"""
api/routers/topics.py — роутер для работы с темами ВКР

Эндпоинты:
    POST /topics  — запустить пайплайн и получить темы
    GET  /topics  — получить историю запросов из БД

Используется в:
    - api/main.py — подключается как роутер
"""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db
from api.schemas import (
    ArticleResponse,
    TopicResponse,
    TopicsRequest,
    TopicsResponse,
)
from core.pipeline import run_pipeline
from db.models import GeneratedTopic, UserQuery

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/topics", tags=["topics"])


@router.post(
    "",
    response_model=TopicsResponse,
    summary="Сгенерировать темы ВКР",
    description="Запускает полный RAG-пайплайн и возвращает список тем с обоснованием",
)
async def generate_topics(request: TopicsRequest) -> TopicsResponse:
    """Основной эндпоинт — запускает пайплайн от запроса до тем."""
    logger.info(f"POST /topics: query={request.query!r}, level={request.level}")

    start_time = time.time()

    try:
        result = await run_pipeline(
            query=request.query,
            level=request.level,
            duration=request.duration,
            num_topics=request.num_topics,
        )
    except Exception as e:
        logger.error(f"POST /topics: пайплайн завершился с ошибкой: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ошибка пайплайна: {str(e)}",
        )

    duration_seconds = time.time() - start_time

    # Формируем ответ
    articles = [
        ArticleResponse(
            arxiv_id=a.get("arxiv_id", ""),
            title=a.get("title", ""),
            url=a.get("url", ""),
            primary_category=a.get("primary_category"),
        )
        for a in result.get("articles", [])
    ]

    topics = [
        TopicResponse(
            title=t.get("title", ""),
            rationale=t.get("rationale"),
            approach=t.get("approach"),
            datasets=t.get("datasets", []),
            sources=t.get("sources", []),
        )
        for t in result.get("topics", [])
    ]

    return TopicsResponse(
        query_id=result.get("query_id"),
        query=request.query,
        subqueries=result.get("subqueries", []),
        articles=articles,
        topics=topics,
        duration_seconds=round(duration_seconds, 2),
    )


@router.get(
    "/history",
    summary="История запросов",
    description="Возвращает список последних запросов из БД",
)
async def get_history(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Получить историю запросов пользователей из PostgreSQL."""
    result = await db.execute(
        select(UserQuery)
        .order_by(UserQuery.created_at.desc())
        .limit(limit)
    )
    queries = result.scalars().all()

    return [
        {
            "id": q.id,
            "query_text": q.query_text,
            "level": q.level,
            "term": q.term,
            "created_at": str(q.created_at),
        }
        for q in queries
    ]


@router.get(
    "/{query_id}",
    summary="Темы по ID запроса",
    description="Возвращает сохранённые темы для конкретного запроса",
)
async def get_topics_by_query(
    query_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Получить сохранённые темы по query_id из PostgreSQL."""
    # Проверяем что запрос существует
    query_result = await db.execute(
        select(UserQuery).where(UserQuery.id == query_id)
    )
    user_query = query_result.scalar_one_or_none()

    if not user_query:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Запрос с id={query_id} не найден",
        )

    # Получаем темы
    topics_result = await db.execute(
        select(GeneratedTopic)
        .where(GeneratedTopic.query_id == query_id)
        .order_by(GeneratedTopic.rank)
    )
    topics = topics_result.scalars().all()

    return {
        "query_id": query_id,
        "query_text": user_query.query_text,
        "level": user_query.level,
        "term": user_query.term,
        "created_at": str(user_query.created_at),
        "topics": [
            {
                "id": t.id,
                "title": t.title,
                "rationale": t.rationale,
                "approach": t.approach,
                "sources": t.sources_json,
                "rank": t.rank,
            }
            for t in topics
        ],
    }