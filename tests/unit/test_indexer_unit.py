"""
tests/unit/test_indexer_unit.py — юнит-тесты вспомогательных функций data/indexer.py

Тестирует чистые функции без внешних зависимостей (без БД, Ollama, FAISS).

Запуск:
    uv run python tests/unit/test_indexer_unit.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data.indexer import _make_text_for_embedding

PASSED = 0
FAILED = 0


def ok(name: str):
    global PASSED
    PASSED += 1
    print(f"  ✓ {name}")


def fail(name: str, error: Exception):
    global FAILED
    FAILED += 1
    print(f"  ✗ {name}: {error}")


def test_make_text_combines_title_and_abstract():
    article = {
        "title": "RAG Systems",
        "abstract": "This paper proposes a new retrieval method.",
    }
    text = _make_text_for_embedding(article)
    assert "RAG Systems" in text
    assert "retrieval method" in text
    assert text.startswith("RAG Systems")
    ok("объединяет title и abstract")


def test_make_text_empty_dict():
    text = _make_text_for_embedding({})
    assert isinstance(text, str)
    ok("работает с пустым словарём")


def test_make_text_missing_abstract():
    article = {"title": "Only Title"}
    text = _make_text_for_embedding(article)
    assert "Only Title" in text
    ok("работает без abstract")


def test_make_text_missing_title():
    article = {"abstract": "Only abstract text here."}
    text = _make_text_for_embedding(article)
    assert "Only abstract text here." in text
    ok("работает без title")


def test_make_text_separator():
    article = {"title": "Title", "abstract": "Abstract"}
    text = _make_text_for_embedding(article)
    assert "Title. Abstract" == text
    ok("разделитель между title и abstract — точка с пробелом")


def main():
    print("\n" + "=" * 50)
    print("ЮНИТ-ТЕСТЫ: data/indexer.py — _make_text_for_embedding")
    print("=" * 50)

    tests = [
        test_make_text_combines_title_and_abstract,
        test_make_text_empty_dict,
        test_make_text_missing_abstract,
        test_make_text_missing_title,
        test_make_text_separator,
    ]

    for test_fn in tests:
        try:
            test_fn()
        except Exception as e:
            fail(test_fn.__name__, e)

    print("\n" + "=" * 50)
    print(f"Результат: {PASSED} passed, {FAILED} failed")
    print("=" * 50 + "\n")

    if FAILED > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()