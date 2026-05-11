"""
data/reindex_cs.py — очистка FAISS и перекачка статей по всем CS категориям arXiv

Запуск:
    uv run python data/reindex_cs.py

Что делает:
    1. Удаляет существующий FAISS-индекс с диска
    2. Очищает таблицы articles и article_embeddings в PostgreSQL
    3. Скачивает по ARTICLES_PER_CATEGORY статей из каждой CS категории
    4. Строит новый FAISS-индекс и сохраняет на диск
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

import urllib

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

import arxiv
import faiss
import feedparser
import numpy as np
import ollama
from sqlalchemy import delete, text

from config import settings
from db.models import Article, ArticleEmbedding
from db.session import get_session

import urllib.request
import urllib.error

# User-Agent для arXiv API
HEADERS = {
    "User-Agent": "TopicAdvisor/1.0 (research project; mailto:alice@example.com)"
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Настройки 

ARTICLES_PER_CATEGORY = 80  # статей на категорию 

CS_CATEGORIES = [
    "cs.AI", "cs.AR", "cs.CC", "cs.CE", "cs.CG", "cs.CL", "cs.CR",
    "cs.CV", "cs.CY", "cs.DB", "cs.DC", "cs.DL", "cs.DM", "cs.DS",
    "cs.ET", "cs.FL", "cs.GL", "cs.GR", "cs.HC", "cs.IR", "cs.IT",
    "cs.LG", "cs.LO", "cs.MA", "cs.MM", "cs.MS", "cs.NA", "cs.NE",
    "cs.NI", "cs.OH", "cs.OS", "cs.PF", "cs.PL", "cs.RO", "cs.SC",
    "cs.SD", "cs.SE", "cs.SI", "cs.SY",
]

ARXIV_API = "http://export.arxiv.org/api/query"
EMBEDDING_MODEL = settings.ollama_embedding_model  # qwen3-embedding:0.6b
FAISS_INDEX_PATH = Path(settings.faiss_index_path) if hasattr(settings, "faiss_index_path") else Path("data/faiss_index.bin")
FAISS_IDS_PATH   = FAISS_INDEX_PATH.with_suffix(".ids.npy")
EMBED_DIM = 1024  # размерность qwen3-embedding:0.6b

# Шаг 1: Очистка 

async def clear_database():
    """Очистить таблицы articles и article_embeddings."""
    logger.info("Очищаем таблицы articles и article_embeddings...")
    async with get_session() as session:
        await session.execute(delete(ArticleEmbedding))
        await session.execute(delete(Article))
        await session.execute(text("ALTER SEQUENCE articles_id_seq RESTART WITH 1"))
        await session.execute(text("ALTER SEQUENCE article_embeddings_id_seq RESTART WITH 1"))
        await session.commit()
    logger.info("Таблицы очищены.")


def clear_faiss():
    """Удалить FAISS-индекс с диска."""
    for path in [FAISS_INDEX_PATH, FAISS_IDS_PATH]:
        if path.exists():
            path.unlink()
            logger.info(f"Удалён файл: {path}")
    logger.info("FAISS-индекс очищен.")


# Шаг 2: Скачивание статей 

def fetch_articles(category: str, max_results: int = ARTICLES_PER_CATEGORY) -> list[dict]:
    client = arxiv.Client(
        page_size=max_results,
        delay_seconds=5,      # пауза между запросами
        num_retries=5,        # повторы при ошибках
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
            "authors":          ", ".join(a.name for a in result.authors),
            "published_at":     result.published.isoformat(),
            "primary_category": result.primary_category,
            "subjects":         ", ".join(result.categories),
        })
    return articles

# def fetch_articles(category: str, max_results: int = ARTICLES_PER_CATEGORY) -> list[dict]:
#     articles = []
#     batch_size = 100
#     start = 0
#     retries = 0

#     while len(articles) < max_results:
#         fetch_n = min(batch_size, max_results - len(articles))
#         url = (
#             f"{ARXIV_API}?search_query=cat:{category}"
#             f"&start={start}&max_results={fetch_n}"
#             f"&sortBy=submittedDate&sortOrder=descending"
#         )
#         try:
#             req = urllib.request.Request(url, headers=HEADERS)
#             with urllib.request.urlopen(req, timeout=30) as response:
#                 content = response.read()
#             feed = feedparser.parse(content)
#             entries = feed.get("entries", [])
#             logger.info(f"    API ответил: {len(entries)} записей")
#             if not entries:
#                 break

#             for entry in entries:
#                 arxiv_id = entry.get("id", "").split("/abs/")[-1].split("v")[0]
#                 title    = entry.get("title", "").replace("\n", " ").strip()
#                 abstract = entry.get("summary", "").replace("\n", " ").strip()
#                 url_link = entry.get("link", "")
#                 authors  = ", ".join(a.get("name", "") for a in entry.get("authors", []))
#                 published = entry.get("published", "")
#                 tags     = [t.get("term", "") for t in entry.get("tags", [])]
#                 primary  = tags[0] if tags else category

#                 if not arxiv_id or not title or not abstract:
#                     continue

#                 articles.append({
#                     "arxiv_id":        arxiv_id,
#                     "title":           title,
#                     "abstract":        abstract,
#                     "url":             url_link,
#                     "authors":         authors,
#                     "published_at":    published,
#                     "primary_category": primary,
#                     "subjects":        ", ".join(tags),
#                 })

#             start += len(entries)
#             retries = 0
#             time.sleep(3)  # обычная пауза

#         except urllib.error.HTTPError as e:
#             if e.code == 429:
#                 wait = 60 * (retries + 1)  # 60с, 120с, 180с...
#                 logger.warning(f"Rate limit (429), ждём {wait}с...")
#                 time.sleep(wait)
#                 retries += 1
#                 if retries > 3:
#                     logger.error(f"Слишком много 429 для {category}, пропускаем")
#                     break
#             else:
#                 logger.warning(f"HTTP ошибка {e.code} для {category}: {e}")
#                 time.sleep(5)
#                 break
#         except Exception as e:
#             logger.warning(f"Ошибка при запросе {category}: {e}")
#             time.sleep(5)
#             break

#     return articles[:max_results]

# Шаг 3: Эмбеддинги 

def embed_texts(texts: list[str]) -> np.ndarray:
    """Получить эмбеддинги для списка текстов через Ollama."""
    response = ollama.embed(model=EMBEDDING_MODEL, input=texts)
    vectors = response["embeddings"]
    return np.array(vectors, dtype=np.float32)


# Шаг 4: Сохранение в БД и FAISS 

async def save_articles_and_build_index(all_articles: list[dict]):
    """Сохранить статьи в PostgreSQL и построить FAISS-индекс."""
    logger.info(f"Сохраняем {len(all_articles)} статей в БД и строим FAISS...")

    # Создаём пустой FAISS индекс
    index = faiss.IndexFlatIP(EMBED_DIM)  # Inner Product (косинусное сходство)
    vector_ids = []  # article_id → vector_id

    # Обрабатываем батчами
    BATCH = 20
    saved_count = 0
    skipped_count = 0

    async with get_session() as session:
        for i in range(0, len(all_articles), BATCH):
            batch = all_articles[i:i + BATCH]

            # Проверяем дубликаты по arxiv_id
            new_batch = []
            for art in batch:
                from sqlalchemy import select
                result = await session.execute(
                    select(Article.id).where(Article.arxiv_id == art["arxiv_id"])
                )
                if result.scalar_one_or_none() is None:
                    new_batch.append(art)
                else:
                    skipped_count += 1

            if not new_batch:
                continue

            # Тексты для эмбеддинга: title + abstract
            texts = [f"{a['title']}. {a['abstract'][:300]}" for a in new_batch]

            try:
                vectors = embed_texts(texts)
            except Exception as e:
                logger.warning(f"Ошибка эмбеддинга батча {i}: {e}")
                continue

            # Нормализация для косинусного сходства
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)
            vectors = vectors / norms

            # Сохраняем статьи в БД
            for j, art in enumerate(new_batch):
                from datetime import datetime
                published_at = None
                if art.get("published_at"):
                    try:
                        published_at = datetime.fromisoformat(art["published_at"].replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass

                db_article = Article(
                    arxiv_id=art["arxiv_id"],
                    title=art["title"],
                    abstract=art["abstract"],
                    url=art["url"],
                    authors=art["authors"],
                    published_at=published_at,
                    primary_category=art["primary_category"],
                    subjects=art["subjects"],
                )
                session.add(db_article)
                await session.flush()

                # Добавляем вектор в FAISS
                vector_id = index.ntotal
                index.add(vectors[j:j+1])

                # Сохраняем связь article_id → vector_id
                embedding = ArticleEmbedding(
                    article_id=db_article.id,
                    vector_id=vector_id,
                    model_version=EMBEDDING_MODEL,
                )
                session.add(embedding)
                vector_ids.append(db_article.id)

            await session.commit()
            saved_count += len(new_batch)

            if (i // BATCH) % 5 == 0:
                logger.info(f"  Сохранено: {saved_count} | Пропущено дублей: {skipped_count} | Векторов в FAISS: {index.ntotal}")

    # Сохраняем FAISS на диск
    FAISS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(FAISS_INDEX_PATH))
    np.save(str(FAISS_IDS_PATH), np.array(vector_ids, dtype=np.int64))

    logger.info(f"FAISS-индекс сохранён: {FAISS_INDEX_PATH} ({index.ntotal} векторов)")
    logger.info(f"Итого сохранено: {saved_count} статей, пропущено дублей: {skipped_count}")


# Главная функция

async def main():
    logger.info("=" * 60)
    logger.info("Начинаем переиндексацию arXiv CS категорий")
    logger.info(f"Категорий: {len(CS_CATEGORIES)} × {ARTICLES_PER_CATEGORY} статей = ~{len(CS_CATEGORIES) * ARTICLES_PER_CATEGORY}")
    logger.info("=" * 60)

    # Шаг 1: Очистка
    clear_faiss()
    await clear_database()

    # Шаг 2: Скачивание статей
    all_articles = []
    for idx, category in enumerate(CS_CATEGORIES, 1):
        logger.info(f"[{idx}/{len(CS_CATEGORIES)}] Скачиваем {category}...")
        articles = fetch_articles(category, ARTICLES_PER_CATEGORY)
        all_articles.extend(articles)
        logger.info(f"  Получено: {len(articles)} статей (всего: {len(all_articles)})")
        time.sleep(15)  # пауза между категориями

    logger.info(f"Всего скачано: {len(all_articles)} статей")

    # Шаг 3: Сохранение и индексация
    await save_articles_and_build_index(all_articles)

    logger.info("=" * 60)
    logger.info("Переиндексация завершена!")
    logger.info("=" * 60)


if __name__ == "__main__":
    # Windows-специфичная настройка event loop
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
