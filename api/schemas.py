"""
api/schemas.py — Pydantic-схемы для FastAPI эндпоинтов

Описывает структуру входящих запросов (Request) и исходящих
ответов (Response) для всех эндпоинтов API.

Используется в:
    - api/routers/topics.py — валидация запросов и ответов
    - api/main.py           — подключение роутеров
"""

from datetime import datetime
from pydantic import BaseModel, Field


# Входящие запросы 

class TopicsRequest(BaseModel):
    """Запрос на генерацию тем ВКР."""

    query: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Текст запроса пользователя — интересы, область, тематика",
        example="интересуюсь NLP и трансформерами, хочу исследовать суммаризацию текста",
    )
    level: str = Field(
        default="master",
        description="Степень обучения",
        example="bachelor",
    )
    duration: int = Field(
        default=3,
        ge=1,
        le=60,
        description="Желаемый срок работы в месяцах",
        example=5,
    )
    num_topics: int = Field(
        default=6,
        ge=1,
        le=12,
        description="Желаемое количество тем на выходе",
        example=6,
    )
    locale: str = "ru"


# Исходящие ответы 

class TopicResponse(BaseModel):
    """Одна сгенерированная тема ВКР."""

    title: str = Field(description="Формулировка темы")
    rationale: str | None = Field(default=None, description="Обоснование актуальности")
    approach: str | None = Field(default=None, description="Предлагаемый подход и методы")
    datasets: list[str] = Field(default=[], description="Релевантные датасеты")
    sources: list[str] = Field(default=[], description="Ссылки на arXiv-статьи")


class ArticleResponse(BaseModel):
    """Краткие метаданные статьи arXiv."""

    arxiv_id: str
    title: str
    url: str
    primary_category: str | None = None


class TopicsResponse(BaseModel):
    """Полный ответ пайплайна на запрос генерации тем."""

    query_id: int | None = Field(description="ID запроса в БД")
    query: str = Field(description="Исходный запрос пользователя")
    subqueries: list[str] = Field(description="Подзапросы от Planner")
    articles: list[ArticleResponse] = Field(description="Статьи после Reranker")
    topics: list[TopicResponse] = Field(description="Сгенерированные темы")
    duration_seconds: float = Field(description="Время выполнения пайплайна")


class HealthResponse(BaseModel):
    """Ответ health-check эндпоинта."""

    status: str = "ok"
    timestamp: datetime