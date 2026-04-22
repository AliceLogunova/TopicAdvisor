"""
data/indexer.py — индексация статей arXiv в PostgreSQL и FAISS

Принимает список статей от arxiv_client, сохраняет метаданные
в PostgreSQL и вычисляет эмбеддинги через Ollama (qwen3-embedding:0.6b)
для FAISS-индекса.

Порядок работы:
    1. Получить статьи от arxiv_client
    2. Сохранить метаданные в таблицу articles (пропустить дубликаты)
    3. Вычислить эмбеддинги title + abstract через Ollama
    4. Добавить векторы в FAISS-индекс
    5. Сохранить связь article_id <-> vector_id в таблицу article_embeddings
    6. Персистировать FAISS-индекс на диск

Используется в:
    - CLI: uv run python data.indexer.py --categories cs.AI --total 1000
    - core/retriever.py читает FAISS-индекс который создаёт этот файл
"""

import asyncio
import json
import logging
from pathlib import Path

import faiss
import numpy as np
import ollama
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from config import settings
from data.arxiv_client import fetch_batch, search_by_categories
from data.cache import cache
from db.models import Article, ArticleEmbedding
from db.session import get_session

logger = logging.getLogger(__name__)

# Модель (актуальная) эмбеддингов через Ollama
_EMBEDDING_MODEL_NAME = "qwen3-embedding:0.6b"

# Размерность векторов (максимальная для qwen3-embedding:0.6b)
_EMBEDDING_DIM = 1024


def _load_or_create_faiss_index() -> faiss.IndexFlatL2:
    """Загрузить существующий FAISS-индекс или создать новый.

    Индекс хранится на диске по пути из settings.faiss_index_path.
    """
    index_path = Path(settings.faiss_index_path)

    if index_path.exists():
        logger.info(f"Загружаем FAISS-индекс из {index_path}")
        index = faiss.read_index(str(index_path))
        logger.info(f"Индекс загружен, векторов: {index.ntotal}")
    else:
        logger.info("FAISS-индекс не найден, создаём новый")
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index = faiss.IndexFlatL2(_EMBEDDING_DIM)

    return index


def _save_faiss_index(index: faiss.IndexFlatL2) -> None:
    """Сохранить FAISS-индекс на диск."""
    index_path = Path(settings.faiss_index_path)
    faiss.write_index(index, str(index_path))
    logger.info(f"FAISS-индекс сохранён: {index.ntotal} векторов -> {index_path}")


def _make_text_for_embedding(article: dict) -> str:
    """Сформировать текст для вычисления эмбеддинга.

    Объединяем title и abstract — так вектор несёт больше смысла
    чем если бы мы кодировали только заголовок.
    """
    title = article.get("title", "")
    abstract = article.get("abstract", "")
    return f"{title}. {abstract}"


async def _get_embedding(text: str) -> np.ndarray:
    """Получить эмбеддинг текста через Ollama.

    Сначала проверяет кэш Redis — если вектор уже считался,
    возвращает его без обращения к Ollama.

    Args:
        text: Текст для кодирования

    Returns:
        numpy-вектор размерностью 1024 (float32)
    """
    # Проверяем кэш
    cached = await cache.get("embeddings", text)
    if cached is not None:
        return np.array(cached, dtype=np.float32)

    # Запрашиваем эмбеддинг у Ollama
    response = ollama.embed(
        model=_EMBEDDING_MODEL_NAME,
        input=text,
    )
    vector = np.array(response["embeddings"][0], dtype=np.float32)

    # Сохраняем в кэш на 24 часа
    await cache.set("embeddings", text, vector.tolist(), ttl=86400)

    return vector


async def _article_exists(session, arxiv_id: str) -> int | None:
    """Проверить существует ли статья в БД.

    Возвращает id статьи или None если не найдена.
    """
    result = await session.execute(
        select(Article.id).where(Article.arxiv_id == arxiv_id)
    )
    return result.scalar_one_or_none()


async def _save_article(session, article_data: dict) -> int | None:
    """Сохранить метаданные статьи в PostgreSQL.

    Возвращает id новой записи или None если статья уже существует.
    """
    existing_id = await _article_exists(session, article_data["arxiv_id"])
    if existing_id is not None:
        logger.debug(f"Статья уже есть в БД: {article_data['arxiv_id']}")
        return None

    article = Article(
        arxiv_id=article_data["arxiv_id"],
        title=article_data["title"],
        abstract=article_data["abstract"],
        authors=article_data.get("authors"),
        published_at=article_data.get("published_at"),
        url=article_data["url"],
        primary_category=article_data.get("primary_category"),
        subjects=article_data.get("subjects"),
    )

    try:
        session.add(article)
        await session.flush()  # получаем id без финального коммита
        return article.id
    except IntegrityError:
        await session.rollback()
        logger.debug(f"Дубликат при вставке: {article_data['arxiv_id']}")
        return None


async def _save_embedding(session, article_id: int, vector_id: int) -> None:
    """Сохранить связь article_id <-> vector_id в таблицу article_embeddings."""
    embedding = ArticleEmbedding(
        article_id=article_id,
        vector_id=vector_id,
        model_version=_EMBEDDING_MODEL_NAME,
    )
    session.add(embedding)


async def index_articles(articles: list[dict]) -> dict:
    """Проиндексировать список статей в PostgreSQL и FAISS.

    Args:
        articles: Список словарей от arxiv_client.search()

    Returns:
        Словарь со статистикой: {"saved": int, "skipped": int, "total": int}
    """
    if not articles:
        logger.warning("Передан пустой список статей")
        return {"saved": 0, "skipped": 0, "total": 0}

    index = _load_or_create_faiss_index()

    saved_count = 0
    skipped_count = 0

    async with get_session() as session:
        for article in articles:
            # Сохраняем метаданные в PostgreSQL
            article_id = await _save_article(session, article)

            if article_id is None:
                skipped_count += 1
                continue

            # Вычисляем эмбеддинг через Ollama (с кэшированием)
            text = _make_text_for_embedding(article)
            vector = await _get_embedding(text)

            # Добавляем вектор в FAISS
            # FAISS требует shape (1, dim) — reshape добавляет измерение
            vector_id = index.ntotal
            index.add(vector.reshape(1, -1))

            # Сохраняем связь article_id <-> vector_id
            await _save_embedding(session, article_id, vector_id)

            saved_count += 1
            logger.debug(f"Проиндексирована статья: {article['arxiv_id']}")

        await session.commit()

    # Сохраняем обновлённый FAISS-индекс на диск
    _save_faiss_index(index)

    stats = {"saved": saved_count, "skipped": skipped_count, "total": len(articles)}
    logger.info(f"Индексация завершена: {stats}")
    return stats


async def run_indexing(
    query: str | None = None,
    categories: list[str] | None = None,
    total: int = 1000,
    batch_size: int = 100,
) -> dict:
    """Запустить полный цикл: скачать статьи и проиндексировать.

    Args:
        query:      Поисковый запрос (например "all:RAG AND cat:cs.AI")
        categories: Список категорий (например ["cs.AI", "cs.LG"])
        total:      Сколько статей загрузить
        batch_size: Размер батча при загрузке

    Returns:
        Статистика индексации
    """
    if query:
        articles = await fetch_batch(query=query, total=total, batch_size=batch_size)
    elif categories:
        articles = await search_by_categories(categories=categories, max_results=total)
    else:
        raise ValueError("Нужно передать query или categories")

    logger.info(f"Скачано статей: {len(articles)}, начинаем индексацию")
    return await index_articles(articles)




# CLI точка входа 

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Индексация статей arXiv")
    parser.add_argument("--query", type=str, help="Поисковый запрос arXiv")
    parser.add_argument(
        "--categories", type=str, nargs="+",
        help="Список категорий (например cs.AI cs.LG)",
    )
    parser.add_argument(
        "--total", type=int, default=500,
        help="Количество статей (по умолчанию 500)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=100,
        help="Размер батча (по умолчанию 100)",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Показать статистику FAISS-индекса",
    )

    args = parser.parse_args()

    if args.stats:
        index_path = Path(settings.faiss_index_path)
        if index_path.exists():
            idx = faiss.read_index(str(index_path))
            print(f"Векторов в индексе: {idx.ntotal}")
        else:
            print("FAISS-индекс не найден")
    else:
        stats = asyncio.run(
            run_indexing(
                query=args.query,
                categories=args.categories,
                total=args.total,
                batch_size=args.batch_size,
            )
        )
        print(f"Результат: {json.dumps(stats, ensure_ascii=False)}")