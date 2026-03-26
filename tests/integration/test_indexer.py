"""
tests/integration/test_indexer.py — интеграционные тесты data/indexer.py

Требования перед запуском:
    - docker compose up -d  (PostgreSQL + Redis)
    - ollama serve + ollama pull qwen3-embedding:0.6b

Запуск:
    uv run pytest tests/integration/test_indexer.py -v
"""

import sys
from pathlib import Path

import faiss
import numpy as np
import pytest
from sqlalchemy import select, func, delete
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import settings
from data.indexer import (
    _get_embedding,
    _article_exists,
    _save_article,
    _save_embedding,
    _load_or_create_faiss_index,
    _save_faiss_index,
    index_articles,
    run_indexing,
    _EMBEDDING_DIM,
    _EMBEDDING_MODEL_NAME,
)
from db.models import Article, ArticleEmbedding


# Фикстуры для настройки тестовой базы данных и сессий SQLAlchemy

@pytest.fixture
async def test_engine():
    engine = create_async_engine(
        settings.postgres_url,
        poolclass=NullPool,
        pool_pre_ping=True,
    )
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(test_engine):
    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

@pytest.fixture
async def session(session_factory):
    """Свежая сессия на каждый тест — автоматически откатывается после."""
    async with session_factory() as s:
        yield s
        await s.rollback()


@pytest.fixture
async def clean_session(session_factory):
    """Сессия с очищенными таблицами перед тестом."""
    async with session_factory() as s:
        await s.execute(delete(ArticleEmbedding))
        await s.execute(delete(Article))
        await s.commit()
    async with session_factory() as s:
        yield s
        await s.rollback()


def make_article(arxiv_id: str = "2401.00001", title: str = "Test Title") -> dict:
    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": "This is a test abstract about machine learning.",
        "authors": '["Alice", "Bob"]',
        "published_at": None,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "primary_category": "cs.AI",
        "subjects": '["cs.AI", "cs.LG"]',
    }


async def clean_db(session_factory):
    async with session_factory() as s:
        await s.execute(delete(ArticleEmbedding))
        await s.execute(delete(Article))
        await s.commit()


# Ollama Embedding 

async def test_get_embedding_shape():
    vector = await _get_embedding("machine learning")
    assert isinstance(vector, np.ndarray)
    assert vector.dtype == np.float32
    assert vector.shape == (_EMBEDDING_DIM,)


async def test_get_embedding_cache():
    text = "cache test sentence unique 12345"
    v1 = await _get_embedding(text)
    v2 = await _get_embedding(text)
    assert np.allclose(v1, v2)


async def test_get_embedding_different_texts():
    v1 = await _get_embedding("machine learning neural networks")
    v2 = await _get_embedding("quantum physics completely unrelated topic")
    assert not np.allclose(v1, v2)


# PostgreSQL 

async def test_article_exists_not_found(session):
    result = await _article_exists(session, "9999.99999")
    assert result is None


async def test_article_exists_found(session):
    article = Article(**make_article())
    session.add(article)
    await session.flush()
    result = await _article_exists(session, "2401.00001")
    assert result == article.id


async def test_save_article_new(session):
    article_id = await _save_article(session, make_article())
    assert article_id is not None
    assert isinstance(article_id, int)


async def test_save_article_duplicate(session):
    await _save_article(session, make_article())
    await session.flush()
    dup_id = await _save_article(session, make_article())
    assert dup_id is None


async def test_save_embedding_fields(session):
    article = Article(**make_article())
    session.add(article)
    await session.flush()

    await _save_embedding(session, article.id, vector_id=99)
    await session.flush()

    result = await session.execute(
        select(ArticleEmbedding).where(ArticleEmbedding.article_id == article.id)
    )
    emb = result.scalar_one_or_none()
    assert emb is not None
    assert emb.vector_id == 99
    assert emb.model_version == _EMBEDDING_MODEL_NAME


# FAISS 

async def test_faiss_create():
    index = _load_or_create_faiss_index()
    assert index.d == _EMBEDDING_DIM


async def test_faiss_save_and_reload():
    index = _load_or_create_faiss_index()
    before = index.ntotal
    vec = np.random.rand(1, _EMBEDDING_DIM).astype(np.float32)
    index.add(vec)
    _save_faiss_index(index)

    reloaded = faiss.read_index(str(settings.faiss_index_path))
    assert reloaded.ntotal == before + 1
    assert Path(settings.faiss_index_path).exists()


# index_articles 

async def test_index_articles_empty():
    stats = await index_articles([])
    assert stats == {"saved": 0, "skipped": 0, "total": 0}


async def test_index_articles_saves_to_postgres_and_faiss(session_factory):
    await clean_db(session_factory)
    articles = [
        make_article("2401.11111", "Deep Learning Survey"),
        make_article("2401.22222", "Transformer Architecture"),
    ]
    stats = await index_articles(articles)
    assert stats["saved"] == 2
    assert stats["skipped"] == 0
    assert stats["total"] == 2

    async with session_factory() as s:
        art_count = await s.scalar(select(func.count(Article.id)))
        emb_count = await s.scalar(select(func.count(ArticleEmbedding.id)))
    assert art_count == 2
    assert emb_count == 2

    idx = faiss.read_index(str(settings.faiss_index_path))
    assert idx.ntotal >= 2


async def test_index_articles_deduplication(session_factory):
    await clean_db(session_factory)
    article = make_article("2401.33333", "Duplicate Test")

    stats1 = await index_articles([article])
    assert stats1["saved"] == 1

    stats2 = await index_articles([article])
    assert stats2["saved"] == 0
    assert stats2["skipped"] == 1

    async with session_factory() as s:
        count = await s.scalar(select(func.count(Article.id)))
    assert count == 1


# run_indexing 

async def test_run_indexing_categories(session_factory):
    await clean_db(session_factory)
    stats = await run_indexing(categories=["cs.AI"], total=3, batch_size=3)
    assert stats["total"] == 3
    assert stats["saved"] + stats["skipped"] == 3


async def test_run_indexing_query(session_factory):
    await clean_db(session_factory)
    stats = await run_indexing(query="cat:cs.LG AND all:attention", total=2)
    assert stats["total"] >= 0


async def test_run_indexing_no_args_raises():
    with pytest.raises(ValueError):
        await run_indexing()