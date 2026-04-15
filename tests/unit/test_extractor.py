"""
tests/unit/test_extractor.py — юнит-тесты core/extractor.py

Тестирует парсинг и валидацию без обращения к LLM.

Запуск:
    uv run pytest tests/unit/test_extractor.py -v
"""

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.extractor import ExtractedFacts, _parse_facts


# _parse_facts 

def test_parse_facts_valid_json():
    response = '''
    {
        "problem": "Text summarization is hard",
        "gap": "No multilingual datasets exist",
        "methods": ["BERT", "T5"],
        "datasets": ["CNN/DailyMail", "XSum"],
        "metrics": ["ROUGE-1", "ROUGE-2", "BERTScore"]
    }
    '''
    facts = _parse_facts(response)
    assert facts.problem == "Text summarization is hard"
    assert facts.gap == "No multilingual datasets exist"
    assert facts.methods == ["BERT", "T5"]
    assert facts.datasets == ["CNN/DailyMail", "XSum"]
    assert facts.metrics == ["ROUGE-1", "ROUGE-2", "BERTScore"]


def test_parse_facts_with_extra_text():
    """Парсер должен извлечь JSON даже если вокруг есть лишний текст."""
    response = """
    Here are the extracted facts:
    {
        "problem": "Long documents are hard to process",
        "gap": null,
        "methods": ["Transformer"],
        "datasets": [],
        "metrics": ["F1"]
    }
    Hope this helps!
    """
    facts = _parse_facts(response)
    assert facts.problem == "Long documents are hard to process"
    assert facts.gap is None
    assert facts.methods == ["Transformer"]
    assert facts.datasets == []


def test_parse_facts_with_think_blocks():
    """Парсер должен убирать <think> блоки qwen3."""
    response = """
    <think>
    Let me analyze this abstract carefully...
    The problem is about NLP.
    </think>
    {
        "problem": "NLP problem",
        "gap": "No solution exists",
        "methods": ["LSTM"],
        "datasets": ["GLUE"],
        "metrics": ["Accuracy"]
    }
    """
    facts = _parse_facts(response)
    assert facts.problem == "NLP problem"
    assert facts.methods == ["LSTM"]


def test_parse_facts_no_json_raises():
    with pytest.raises(ValueError, match="JSON-объект не найден"):
        _parse_facts("This response has no JSON at all.")


def test_parse_facts_invalid_json_raises():
    with pytest.raises(Exception):
        _parse_facts("{ invalid json }")


# ExtractedFacts validator 

def test_extracted_facts_string_to_list():
    """Если методы пришли строкой — должны конвертироваться в список."""
    facts = ExtractedFacts(
        problem="test",
        gap=None,
        methods="BERT",  # строка вместо списка
        datasets=[],
        metrics=[],
    )
    assert facts.methods == ["BERT"]


def test_extracted_facts_none_to_empty_list():
    facts = ExtractedFacts(
        problem="test",
        methods=None,
        datasets=None,
        metrics=None,
    )
    assert facts.methods == []
    assert facts.datasets == []
    assert facts.metrics == []


def test_extracted_facts_filters_empty_strings():
    facts = ExtractedFacts(
        problem="test",
        methods=["BERT", "", "  ", "T5"],
        datasets=["CNN", ""],
        metrics=[],
    )
    assert facts.methods == ["BERT", "T5"]
    assert facts.datasets == ["CNN"]


def test_extracted_facts_all_fields_optional():
    """Все поля кроме списков опциональны."""
    facts = ExtractedFacts()
    assert facts.problem is None
    assert facts.gap is None
    assert facts.methods == []