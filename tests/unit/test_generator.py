"""
tests/unit/test_generator.py — юнит-тесты core/generator.py

Тестирует парсинг и валидацию без обращения к LLM.

Запуск:
    uv run pytest tests/unit/test_generator.py -v
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.generator import GeneratedTopic, _parse_topics, _build_context


# _parse_topics 

def test_parse_topics_valid_array():
    response = '''
    [
        {
            "title": "Topic 1",
            "rationale": "Because gap exists",
            "approach": "Use transformer",
            "datasets": ["GLUE", "SQuAD"],
            "sources": ["https://arxiv.org/abs/2401.00001", "https://arxiv.org/abs/2401.00002"]
        },
        {
            "title": "Topic 2",
            "rationale": "Another reason",
            "approach": "Fine-tune BERT",
            "datasets": ["CNN/DM"],
            "sources": ["https://arxiv.org/abs/2401.00003"]
        }
    ]
    '''
    topics = _parse_topics(response)
    assert len(topics) == 2
    assert topics[0].title == "Topic 1"
    assert topics[1].title == "Topic 2"
    assert len(topics[0].datasets) == 2
    assert len(topics[0].sources) == 2


def test_parse_topics_with_think_blocks():
    """Парсер убирает <think> блоки перед парсингом."""
    response = """
    <think>Let me generate topics...</think>
    [{"title": "Test Topic", "rationale": "reason", "approach": "method", "datasets": ["D1"], "sources": ["https://arxiv.org/abs/1"]}]
    """
    topics = _parse_topics(response)
    assert len(topics) == 1
    assert topics[0].title == "Test Topic"


def test_parse_topics_with_extra_text():
    """Парсер извлекает массив даже при наличии лишнего текста."""
    response = """
    Here are the topics:
    [{"title": "Topic A", "rationale": "R", "approach": "A", "datasets": [], "sources": []}]
    Done!
    """
    topics = _parse_topics(response)
    assert len(topics) == 1


def test_parse_topics_no_json_raises():
    with pytest.raises(ValueError):
        _parse_topics("No JSON here at all.")


def test_parse_topics_empty_array_returns_empty():
    topics = _parse_topics("[]")
    assert topics == []


def test_parse_topics_skips_non_dict_items():
    """Нестроковые элементы массива пропускаются."""
    response = '[{"title": "Valid", "rationale": "R", "approach": "A", "datasets": [], "sources": []}, "invalid", 123]'
    topics = _parse_topics(response)
    assert len(topics) == 1
    assert topics[0].title == "Valid"


# GeneratedTopic validator 

def test_generated_topic_string_to_list():
    topic = GeneratedTopic(
        title="Test",
        datasets="GLUE",  # строка вместо списка
        sources="https://arxiv.org/abs/1",
    )
    assert topic.datasets == ["GLUE"]
    assert topic.sources == ["https://arxiv.org/abs/1"]


def test_generated_topic_none_to_empty_list():
    topic = GeneratedTopic(title="Test", datasets=None, sources=None)
    assert topic.datasets == []
    assert topic.sources == []


def test_generated_topic_filters_empty_strings():
    topic = GeneratedTopic(
        title="Test",
        datasets=["GLUE", "", "  ", "SQuAD"],
        sources=["https://arxiv.org/abs/1", ""],
    )
    assert topic.datasets == ["GLUE", "SQuAD"]
    assert topic.sources == ["https://arxiv.org/abs/1"]


# _build_context 

def test_build_context_includes_title_and_url():
    articles = [
        {
            "title": "My Paper",
            "url": "https://arxiv.org/abs/2401.00001",
            "abstract": "This is about NLP.",
            "facts": None,
        }
    ]
    context = _build_context(articles)
    assert "My Paper" in context
    assert "https://arxiv.org/abs/2401.00001" in context
    assert "This is about NLP." in context


def test_build_context_includes_facts():
    articles = [
        {
            "title": "Paper",
            "url": "https://arxiv.org/abs/1",
            "abstract": "Abstract text.",
            "facts": {
                "problem": "Hard problem",
                "gap": "No solution",
                "methods": ["BERT", "T5"],
                "datasets": ["GLUE"],
                "metrics": ["F1"],
            },
        }
    ]
    context = _build_context(articles)
    assert "Hard problem" in context
    assert "No solution" in context
    assert "BERT" in context
    assert "GLUE" in context
    assert "F1" in context


def test_build_context_multiple_articles_separated():
    articles = [
        {"title": "Paper 1", "url": "url1", "abstract": "abs1", "facts": None},
        {"title": "Paper 2", "url": "url2", "abstract": "abs2", "facts": None},
    ]
    context = _build_context(articles)
    assert "Paper 1" in context
    assert "Paper 2" in context
    assert "---" in context  # разделитель между статьями


def test_build_context_truncates_abstract():
    long_abstract = "A" * 2000
    articles = [
        {"title": "Paper", "url": "url", "abstract": long_abstract, "facts": None}
    ]
    context = _build_context(articles)
    # Абстракт обрезается до 1000 символов
    assert len(context) < 2000 + 200  # 200 — запас на заголовок и url