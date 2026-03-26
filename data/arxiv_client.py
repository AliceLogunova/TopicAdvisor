"""
data/arxiv_client.py — HTTP-клиент для arXiv API

Отвечает за получение метаданных статей с arXiv.org через REST API.
Парсит Atom/XML ответы через feedparser и возвращает нормализованные
словари готовые для записи в таблицу articles.

Используется в:
    - data/indexer.py — передаёт сюда поисковые запросы,
      получает списки статей для индексации

Rate limit arXiv API: не более 3 запросов в секунду.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import feedparser
import httpx

from config import settings

logger = logging.getLogger(__name__)

# Базовый URL arXiv API
_BASE_URL = "https://export.arxiv.org/api/query"

# Задержка между запросами чтобы не превысить rate limit (3 req/sec)
_REQUEST_DELAY = 0.4


def _parse_arxiv_id(entry_id: str) -> str:
    """Извлечь короткий arXiv ID из полного URL.

    Пример: "https://arxiv.org/abs/2401.12345v2" → "2401.12345"
    """
    short = entry_id.split("/abs/")[-1]
    # Убираем версию статьи (v1, v2, ...)
    short = short.split("v")[0]
    return short


def _parse_authors(entry: Any) -> str:
    """Получить список авторов как JSON-строку.

    feedparser возвращает authors как список объектов с полем .name.
    Сохраняем как JSON-список строк.
    """
    try:
        names = [a.name for a in entry.authors if hasattr(a, "name")]
        return json.dumps(names, ensure_ascii=False)
    except AttributeError:
        return json.dumps([])


def _parse_entry(entry: Any) -> dict | None:
    """Преобразовать feedparser-запись в словарь для таблицы articles.

    Возвращает None если запись не содержит обязательных полей.
    """
    # Обязательные поля
    entry_id = getattr(entry, "id", None)
    title = getattr(entry, "title", None)
    abstract = getattr(entry, "summary", None)

    if not entry_id or not title or not abstract:
        logger.warning(f"Пропускаем запись без обязательных полей: {entry_id}")
        return None

    # Дата публикации
    published_at: datetime | None = None
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            published_at = datetime(*entry.published_parsed[:6])
        except (TypeError, ValueError):
            pass

    # Категории
    primary_category: str | None = None
    if hasattr(entry, "arxiv_primary_category"):
        primary_category = entry.arxiv_primary_category.get("term")

    subjects_list = [
        tag.get("term") for tag in getattr(entry, "tags", []) if tag.get("term")
    ]
    subjects = json.dumps(subjects_list, ensure_ascii=False) if subjects_list else None

    return {
        "arxiv_id": _parse_arxiv_id(entry_id),
        "title": title.strip().replace("\n", " "),
        "abstract": abstract.strip().replace("\n", " "),
        "authors": _parse_authors(entry),
        "published_at": published_at,
        "url": f"https://arxiv.org/abs/{_parse_arxiv_id(entry_id)}",
        "primary_category": primary_category,
        "subjects": subjects,
    }


async def search(
    query: str,
    max_results: int | None = None,
    start: int = 0,
) -> list[dict]:
    """Поиск статей на arXiv по поисковому запросу.

    Args:
        query:       Поисковый запрос (например "cat:cs.AI AND all:RAG")
        max_results: Максимальное количество результатов
        start:       Смещение для пагинации

    Returns:
        Список словарей готовых для записи в таблицу articles
    """
    max_results = max_results or settings.arxiv_max_results

    params = urlencode({
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    })
    url = f"{_BASE_URL}?{params}"

    logger.info(f"arXiv API запрос: {query!r}, max={max_results}, start={start}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url)
        response.raise_for_status()

    feed = feedparser.parse(response.text)

    articles = []
    for entry in feed.entries:
        parsed = _parse_entry(entry)
        if parsed:
            articles.append(parsed)

    logger.info(f"arXiv вернул {len(articles)} статей")

    # Соблюдаем rate limit
    await asyncio.sleep(_REQUEST_DELAY)

    return articles


async def search_by_categories(
    categories: list[str],
    max_results: int | None = None,
) -> list[dict]:
    """Поиск статей по списку категорий arXiv.

    Пример: ["cs.AI", "cs.LG", "cs.CL"]
    Строит запрос вида: cat:cs.AI OR cat:cs.LG OR cat:cs.CL

    Args:
        categories:  Список категорий arXiv
        max_results: Максимальное количество результатов

    Returns:
        Список словарей готовых для записи в таблицу articles
    """
    query = " OR ".join(f"cat:{cat}" for cat in categories)
    return await search(query=query, max_results=max_results)


async def fetch_batch(
    query: str,
    total: int,
    batch_size: int = 100,
) -> list[dict]:
    """Загрузить большое количество статей батчами с пагинацией.

    arXiv API отдаёт не более 2000 результатов за один запрос.
    Этот метод делает несколько запросов с нарастающим start.

    Args:
        query:      Поисковый запрос
        total:      Общее количество статей которые нужно загрузить
        batch_size: Размер одного батча 

    Returns:
        Объединённый список всех статей
    """
    all_articles: list[dict] = []
    start = 0

    while start < total:
        current_batch = min(batch_size, total - start)
        batch = await search(query=query, max_results=current_batch, start=start)

        if not batch:
            logger.info("arXiv вернул пустой батч — останавливаем загрузку")
            break

        all_articles.extend(batch)
        start += len(batch)
        logger.info(f"Загружено {len(all_articles)} / {total} статей")

        # Пауза между батчами
        await asyncio.sleep(_REQUEST_DELAY)

    return all_articles