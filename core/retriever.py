"""
core/retriever.py — семантический поиск статей через FAISS

Кодирует подзапросы от Planner в векторы через Ollama,
выполняет ANN-поиск по FAISS-индексу и возвращает
метаданные топ-N статей из PostgreSQL.

Используется в:
    - core/pipeline.py — второй шаг пайплайна
"""

import logging
from pathlib import Path

import faiss
import numpy as np
import ollama
from sqlalchemy import select

from config import settings
from db.models import Article, ArticleEmbedding
from db.session import get_session

logger = logging.getLogger(__name__)

_EMBEDDING_MODEL_NAME = "qwen3-embedding:0.6b"


def _load_faiss_index() -> faiss.IndexFlatL2:
    """Загрузить FAISS-индекс с диска"""
    index_path = Path(settings.faiss_index_path)
    if not index_path.exists():
        raise FileNotFoundError(
            f"FAISS-индекс не найден: {index_path}. "
            "Запустите индексацию: uv run python data/indexer.py"
        )
    index = faiss.read_index(str(index_path))
    logger.info(f"FAISS-индекс загружен: {index.ntotal} векторов")
    return index


def _embed_query(text: str) -> np.ndarray:
    """Вычислить эмбеддинг текста через Ollama"""
    response = ollama.embed(model=_EMBEDDING_MODEL_NAME, input=text)
    vector = np.array(response["embeddings"][0], dtype=np.float32)
    return vector.reshape(1, -1)  # FAISS требует shape (1, dim)


async def _get_articles_by_vector_ids(
    vector_ids: list[int],
) -> list[dict]:
    """Получить метаданные статей из PostgreSQL по vector_id из FAISS"""
    async with get_session() as session:
        result = await session.execute(
            select(Article, ArticleEmbedding.vector_id)
            .join(ArticleEmbedding, Article.id == ArticleEmbedding.article_id)
            .where(ArticleEmbedding.vector_id.in_(vector_ids))
        )
        rows = result.all()

    # Возвращаем в порядке vector_ids (по релевантности от FAISS)
    id_to_article = {
        row.vector_id: {
            "arxiv_id": row.Article.arxiv_id,
            "title": row.Article.title,
            "abstract": row.Article.abstract,
            "authors": row.Article.authors,
            "url": row.Article.url,
            "primary_category": row.Article.primary_category,
            "subjects": row.Article.subjects,
            "published_at": str(row.Article.published_at) if row.Article.published_at else None,
            "vector_id": row.vector_id,
        }
        for row in rows
    }

    # Сохраняем порядок релевантности
    return [id_to_article[vid] for vid in vector_ids if vid in id_to_article]


async def retrieve(
    subqueries: list[str],
    top_k: int = 50,
) -> list[dict]:
    """Семантический поиск статей по списку подзапросов.

    Для каждого подзапроса вычисляет эмбеддинг, ищет в FAISS
    и объединяет результаты с дедупликацией.

    Args:
        subqueries: Список подзапросов от Planner
        top_k:      Количество кандидатов на выходе

    Returns:
        Список словарей с метаданными статей (до top_k уникальных)
    """
    if not subqueries:
        logger.warning("Retriever: передан пустой список подзапросов")
        return []

    index = _load_faiss_index()

    # Собираем vector_id кандидатов по всем подзапросам
    seen_ids: set[int] = set()
    ordered_ids: list[int] = []

    for subquery in subqueries:
        try:
            vector = _embed_query(subquery)
            # k на подзапрос — берём больше чтобы после дедупликации осталось top_k
            k_per_query = min(top_k, index.ntotal)
            if k_per_query == 0:
                continue

            distances, indices = index.search(vector, k=k_per_query)

            for vid in indices[0]:
                if vid == -1:  # FAISS возвращает -1 если результатов меньше k
                    continue
                vid = int(vid)
                if vid not in seen_ids:
                    seen_ids.add(vid)
                    ordered_ids.append(vid)

        except Exception as e:
            logger.warning(f"Retriever: ошибка при обработке подзапроса '{subquery}': {e}")
            continue

    if not ordered_ids:
        logger.warning("Retriever: не найдено ни одного кандидата")
        return []

    # Берём топ-K уникальных по порядку появления (приоритет — первые подзапросы)
    top_ids = ordered_ids[:top_k]

    articles = await _get_articles_by_vector_ids(top_ids)
    logger.info(f"Retriever: найдено {len(articles)} уникальных статей")
    return articles