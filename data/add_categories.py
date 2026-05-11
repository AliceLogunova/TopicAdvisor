"""
data/add_categories.py — добавить статьи из конкретных категорий в существующий FAISS-индекс

Запуск:
    uv run python data/add_categories.py

Не трогает существующие статьи — только добавляет новые.
"""

import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import arxiv
import faiss
import numpy as np
import ollama
from sqlalchemy import select

from config import settings
from db.models import Article, ArticleEmbedding
from db.session import get_session

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Настройки 

CATEGORIES_TO_ADD = ["cs.NA", "cs.SY"]
ARTICLES_PER_CATEGORY = 80

EMBEDDING_MODEL = settings.ollama_embedding_model
FAISS_INDEX_PATH = Path(settings.faiss_index_path)
FAISS_IDS_PATH   = FAISS_INDEX_PATH.with_suffix(".ids.npy")
EMBED_DIM = 1024


# Скачивание статей

def fetch_articles(category: str, max_results: int = ARTICLES_PER_CATEGORY) -> list[dict]:
    """Скачать статьи из arXiv для одной категории через официальный клиент."""
    client = arxiv.Client(
        page_size=max_results,
        delay_seconds=5,
        num_retries=5,
    )
    search = arxiv.Search(
        query=f"cat:{category}",
        max_results=max_results,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )
    articles = []
    for result in client.results(search):
        articles.append({
            "arxiv_id":         result.entry_id.split("/abs/")[-1].split("v")[0],
            "title":            result.title.replace("\n", " ").strip(),
            "abstract":         result.summary.replace("\n", " ").strip(),
            "url":              result.entry_id,
            "authors":         ", ".join(a.name for a in result.authors),
            "published_at":    result.published.replace(tzinfo=None),  # убираем timezone
            "primary_category": result.primary_category,
            "subjects":        ", ".join(result.categories),
        })
    return articles


# Эмбеддинги 

def embed_texts(texts: list[str]) -> np.ndarray:
    response = ollama.embed(model=EMBEDDING_MODEL, input=texts)
    vectors = np.array(response["embeddings"], dtype=np.float32)
    # Нормализация для косинусного сходства (IndexFlatIP)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    return vectors / norms


# Добавление в существующий индекс 

async def add_articles_to_index(articles: list[dict]):
    """Добавить статьи в существующий FAISS-индекс и БД."""

    # Загружаем существующий индекс
    if not FAISS_INDEX_PATH.exists():
        logger.error(f"FAISS-индекс не найден: {FAISS_INDEX_PATH}")
        return

    index = faiss.read_index(str(FAISS_INDEX_PATH))
    logger.info(f"Загружен индекс: {index.ntotal} существующих векторов")

    # Загружаем существующие vector_ids
    if FAISS_IDS_PATH.exists():
        existing_ids = np.load(str(FAISS_IDS_PATH)).tolist()
    else:
        existing_ids = list(range(index.ntotal))
    logger.info(f"Существующих article_id в маппинге: {len(existing_ids)}")

    BATCH = 20
    saved_count = 0
    skipped_count = 0
    new_ids = list(existing_ids)  # копируем существующие

    async with get_session() as session:
        for i in range(0, len(articles), BATCH):
            batch = articles[i:i + BATCH]

            # Пропускаем дубликаты
            new_batch = []
            for art in batch:
                result = await session.execute(
                    select(Article.id).where(Article.arxiv_id == art["arxiv_id"])
                )
                if result.scalar_one_or_none() is None:
                    new_batch.append(art)
                else:
                    skipped_count += 1

            if not new_batch:
                continue

            texts = [f"{a['title']}. {a['abstract'][:300]}" for a in new_batch]
            try:
                vectors = embed_texts(texts)
            except Exception as e:
                logger.warning(f"Ошибка эмбеддинга батча {i}: {e}")
                continue

            for j, art in enumerate(new_batch):
                db_article = Article(
                    arxiv_id=art["arxiv_id"],
                    title=art["title"],
                    abstract=art["abstract"],
                    url=art["url"],
                    authors=art["authors"],
                    published_at=art["published_at"],
                    primary_category=art["primary_category"],
                    subjects=art["subjects"],
                )
                session.add(db_article)
                await session.flush()

                # Добавляем вектор в FAISS
                vector_id = index.ntotal
                index.add(vectors[j:j+1])

                embedding = ArticleEmbedding(
                    article_id=db_article.id,
                    vector_id=vector_id,
                    model_version=EMBEDDING_MODEL,
                )
                session.add(embedding)
                new_ids.append(db_article.id)

            await session.commit()
            saved_count += len(new_batch)
            logger.info(f"  Добавлено: {saved_count} | Пропущено: {skipped_count} | Всего в индексе: {index.ntotal}")

    # Сохраняем обновлённый индекс
    faiss.write_index(index, str(FAISS_INDEX_PATH))
    np.save(str(FAISS_IDS_PATH), np.array(new_ids, dtype=np.int64))
    logger.info(f"Индекс обновлён: {index.ntotal} векторов")
    logger.info(f"Итого добавлено: {saved_count}, пропущено дублей: {skipped_count}")


# Главная функция 

async def main():
    logger.info(f"Добавляем категории: {CATEGORIES_TO_ADD}")

    all_articles = []
    for cat in CATEGORIES_TO_ADD:
        logger.info(f"Скачиваем {cat}...")
        articles = fetch_articles(cat, ARTICLES_PER_CATEGORY)
        logger.info(f"  Получено: {len(articles)} статей")
        all_articles.extend(articles)
        time.sleep(5)

    logger.info(f"Всего скачано: {len(all_articles)} статей")

    if all_articles:
        await add_articles_to_index(all_articles)
    else:
        logger.warning("Нет статей для добавления")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())