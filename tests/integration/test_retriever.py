"""
tests/integration/test_retriever.py — интеграционные тесты core/retriever.py

Требования:
    - docker compose up -d
    - FAISS-индекс должен существовать (uv run python data/indexer.py --categories cs.AI --total 10)
    - ollama pull qwen3-embedding:0.6b

Запуск:
    uv run pytest tests/integration/test_retriever.py -v
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.retriever import retrieve, _embed_query, _load_faiss_index
from config import settings


# _load_faiss_index 

async def test_faiss_index_loads():
    index = _load_faiss_index()
    assert index is not None
    assert index.ntotal > 0
    assert index.d == 1024  # размерность qwen3-embedding:0.6b


async def test_faiss_index_not_found_raises(tmp_path, monkeypatch):
    """Если индекс не найден — должен бросить FileNotFoundError."""
    monkeypatch.setattr(settings, "faiss_index_path", tmp_path / "nonexistent.faiss")
    from core.retriever import _load_faiss_index as load
    with pytest.raises(FileNotFoundError):
        load()


# _embed_query 

async def test_embed_query_returns_correct_shape():
    import numpy as np
    vector = _embed_query("machine learning transformers")
    assert vector.shape == (1, 1024)
    assert vector.dtype == np.float32


async def test_embed_query_different_texts_different_vectors():
    import numpy as np
    v1 = _embed_query("natural language processing")
    v2 = _embed_query("quantum physics unrelated")
    assert not np.allclose(v1, v2)


# retrieve 

async def test_retrieve_returns_list():
    results = await retrieve(["transformer models NLP"])
    assert isinstance(results, list)


async def test_retrieve_empty_subqueries_returns_empty():
    results = await retrieve([])
    assert results == []


async def test_retrieve_returns_correct_fields():
    results = await retrieve(["deep learning"], top_k=5)
    if results:
        article = results[0]
        assert "arxiv_id" in article
        assert "title" in article
        assert "abstract" in article
        assert "url" in article


async def test_retrieve_deduplicates_results():
    """Один и тот же подзапрос дважды не должен давать дубликаты."""
    results = await retrieve(["NLP", "NLP"], top_k=10)
    arxiv_ids = [r["arxiv_id"] for r in results]
    assert len(arxiv_ids) == len(set(arxiv_ids))


async def test_retrieve_respects_top_k():
    results = await retrieve(["machine learning", "deep learning", "NLP"], top_k=5)
    assert len(results) <= 5


async def test_retrieve_multiple_subqueries_more_results():
    """Несколько подзапросов должны давать больше результатов чем один."""
    r1 = await retrieve(["NLP"], top_k=50)
    r2 = await retrieve(["NLP", "transformers", "BERT", "text classification"], top_k=50)
    assert len(r2) >= len(r1)