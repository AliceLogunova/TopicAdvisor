"""
core/pipeline.py — оркестратор RAG-пайплайна

Собирает все шаги пайплайна в единый поток:
    Planner -> Retriever -> Reranker -> Extractor -> Generator

Сохраняет запрос и результаты в PostgreSQL.

Используется в:
    - run.py              — CLI точка входа
    - api/routers/topics.py — FastAPI эндпоинт POST /topics
"""

import json
import logging

from core.extractor import extract_facts
from core.generator import generate_topics
from core.planner import expand_query
from core.reranker import rerank
from core.retriever import retrieve
from db.models import GeneratedTopic, UserQuery
from db.session import get_session

logger = logging.getLogger(__name__)


async def run_pipeline(
    query: str,
    level: str = "master",
    duration: int = 3,
    num_topics: int = 6,
    retriever_top_k: int = 50,
    reranker_top_k: int = 10,
) -> dict:
    """Запустить полный RAG-пайплайн от запроса до тем.

    Args:
        query:          Исходный запрос пользователя
        level:          Степень обучения (bachelor/master/phd/postdoc)
        duration:       Желаемый срок работы в месяцах
        num_topics:     Желаемое количество тем на выходе
        retriever_top_k: Количество кандидатов после FAISS
        reranker_top_k:  Количество статей после Reranker

    Returns:
        Словарь с результатами:
        {
            "query_id": int,
            "subqueries": list[str],
            "articles": list[dict],
            "articles_with_facts": list[dict],
            "topics": list[dict],
        }
    """
    logger.info(f"Pipeline: запуск для запроса: {query!r}")

    # Шаг 1: Query Expansion через Planner
    logger.info("Pipeline: шаг 1 — Planner (Query Expansion)")
    subqueries = await expand_query(query=query, level=level, duration=duration)
    logger.info(f"Pipeline: получено {len(subqueries)} подзапросов")

    # Шаг 2: Semantic Retrieval через FAISS
    logger.info("Pipeline: шаг 2 — Retriever (FAISS)")
    candidates = await retrieve(subqueries=subqueries, top_k=retriever_top_k)
    logger.info(f"Pipeline: найдено {len(candidates)} кандидатов")

    if not candidates:
        logger.warning("Pipeline: Retriever вернул 0 статей — завершаем досрочно")
        return {"query_id": None, "subqueries": subqueries, "articles": [], "articles_with_facts": [], "topics": []}

    # Шаг 3: Reranking через Reranker
    logger.info("Pipeline: шаг 3 — Reranker (Cross-Encoder)")
    top_articles = rerank(query=query, articles=candidates, top_k=reranker_top_k)
    logger.info(f"Pipeline: после rerank осталось {len(top_articles)} статей")

    # Шаг 4: Fact Extraction через Extractor
    logger.info("Pipeline: шаг 4 — Extractor (LLM)")
    articles_with_facts = await extract_facts(top_articles)
    logger.info("Pipeline: факты извлечены")

    # Шаг 5: Topic Generation через Generator
    logger.info("Pipeline: шаг 5 — Generator (LLM)")
    topics = await generate_topics(
        articles=articles_with_facts,
        level=level,
        duration=duration,
        num_topics=num_topics,
    )
    logger.info(f"Pipeline: сгенерировано {len(topics)} тем")

    # Сохранение в PostgreSQL и получение query_id
    query_id = await _save_results(
        query_text=query,
        subqueries=subqueries,
        level=level,
        duration=duration,
        topics=topics,
    )

    logger.info(f"Pipeline: завершён, query_id={query_id}")
    return {
        "query_id": query_id,
        "subqueries": subqueries,
        "articles": top_articles,
        "articles_with_facts": articles_with_facts,
        "topics": topics,
    }


async def _save_results(
    query_text: str,
    subqueries: list[str],
    level: str,
    duration: int,
    topics: list[dict],
) -> int | None:
    """Сохранить запрос и темы в PostgreSQL.

    Returns:
        id созданного UserQuery или None при ошибке
    """
    try:
        async with get_session() as session:
            # Сохраняем запрос пользователя
            user_query = UserQuery(
                query_text=query_text,
                expanded_queries_json=json.dumps(subqueries, ensure_ascii=False),
                level=level,
                term=duration,
                locale="ru",
            )
            session.add(user_query)
            await session.flush()

            # Сохраняем каждую тему
            for rank, topic in enumerate(topics, 1):
                generated_topic = GeneratedTopic(
                    query_id=user_query.id,
                    title=topic.get("title", ""),
                    rationale=topic.get("rationale"),
                    approach=topic.get("approach"),
                    datasets=json.dumps(topic.get("datasets", []), ensure_ascii=False),
                    sources_json=json.dumps(topic.get("sources", []), ensure_ascii=False),
                    rank=rank,
                )
                session.add(generated_topic)

            await session.commit()
            return user_query.id

    except Exception as e:
        logger.error(f"Pipeline: ошибка сохранения в БД: {e}")
        return None