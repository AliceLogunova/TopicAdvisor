"""
tests/integration/test_api.py — интеграционные e2e тесты FastAPI

Тестирует реальные HTTP-запросы к API через TestClient.
Не мокает пайплайн — проверяет что API корректно обрабатывает
запросы и возвращает правильную структуру ответов.

Требования:
    - docker compose up -d
    - ollama serve

Запуск:
    uv run pytest tests/integration/test_api.py -v
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from api.main import app

client = TestClient(app)


# Health check 

def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_root_returns_200():
    response = client.get("/")
    assert response.status_code == 200
    assert "TopicAdvisor" in response.json()["message"]


# POST /topics — валидация входных данных 

def test_topics_missing_query_returns_422():
    """Запрос без query должен вернуть 422 Unprocessable Entity."""
    response = client.post("/topics", json={"level": "master"})
    assert response.status_code == 422


def test_topics_query_too_short_returns_422():
    """Слишком короткий query (< 5 символов) должен вернуть 422."""
    response = client.post("/topics", json={"query": "NLP"})
    assert response.status_code == 422


def test_topics_invalid_num_topics_returns_422():
    """num_topics > 12 должен вернуть 422."""
    response = client.post("/topics", json={
        "query": "интересуюсь машинным обучением",
        "num_topics": 99,
    })
    assert response.status_code == 422


def test_topics_invalid_duration_returns_422():
    """duration < 1 должен вернуть 422."""
    response = client.post("/topics", json={
        "query": "интересуюсь машинным обучением",
        "duration": 0,
    })
    assert response.status_code == 422


# GET /topics/history 

def test_history_returns_list():
    response = client.get("/topics/history")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_history_limit_param():
    response = client.get("/topics/history?limit=2")
    assert response.status_code == 200
    assert len(response.json()) <= 2


# GET /topics/{query_id} 

def test_get_topics_nonexistent_id_returns_404():
    response = client.get("/topics/999999")
    assert response.status_code == 404


def test_get_topics_invalid_id_returns_422():
    response = client.get("/topics/abc")
    assert response.status_code == 422


# Docs доступны 

def test_swagger_docs_available():
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc_available():
    response = client.get("/redoc")
    assert response.status_code == 200