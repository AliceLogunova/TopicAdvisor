"""
core/extractor.py — извлечение фактов из абстрактов через LLM

Принимает список статей, для каждой прогоняет абстракт через LLM
и извлекает структурированные факты: problem, gap, methods, datasets, metrics.
Результаты валидируются через Pydantic. При невалидном JSON — авто-повтор до 3 раз.

Используется в:
    - core/pipeline.py — четвёртый шаг пайплайна
"""

import json
import logging
import re
from pathlib import Path

import ollama
from pydantic import BaseModel, field_validator

from config import settings

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path("prompts/extractor.txt")
_MAX_RETRIES = 3


# Pydantic-схема для структурированных фактов извлечённых из абстракта статьи.

class ExtractedFacts(BaseModel):
    """Структурированные факты извлечённые из абстракта статьи."""

    problem: str | None = None
    gap: str | None = None
    methods: list[str] = []
    datasets: list[str] = []
    metrics: list[str] = []

    @field_validator("methods", "datasets", "metrics", mode="before")
    @classmethod
    def ensure_list_of_strings(cls, v):
        """Убедиться что поле — список строк, а не одна строка."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        # Фильтруем пустые строки и нестроковые элементы
        return [str(item).strip() for item in v if item and str(item).strip()]


# Вспомогательные функции для загрузки промпта, построения запроса и парсинга ответа от LLM.

def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_prompt(abstract: str) -> str:
    return _load_prompt().format(abstract=abstract)


def _parse_facts(response_text: str) -> ExtractedFacts:
    """Распарсить JSON-ответ LLM в объект ExtractedFacts.

    Пытается извлечь JSON даже если модель добавила лишний текст.
    """
    # Убираем think-блоки qwen3
    text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()
    
    # Ищем JSON-объект в тексте
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"JSON-объект не найден в ответе: {text[:200]}")

    json_str = text[start:end]
    data = json.loads(json_str)
    return ExtractedFacts(**data)


# Основная функция для извлечения фактов из списка статей. Для каждой статьи запускает синхронное извлечение фактов и добавляет их в словарь статьи.

def _extract_facts_sync(abstract: str) -> ExtractedFacts | None:
    """Извлечь факты из одного абстракта через LLM (синхронно).

    Делает до _MAX_RETRIES попыток при невалидном JSON.
    Возвращает None при исчерпании попыток.
    """
    prompt = _build_prompt(abstract)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = ollama.chat(
                model=settings.ollama_model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": 0.1,  # низкая температура для точного JSON
                    "num_predict": 512,  
                    },
                think=False,
            )
            response_text = response["message"]["content"]
            facts = _parse_facts(response_text)
            logger.debug(f"Extractor: факты извлечены (попытка {attempt})")
            return facts

        except (ValueError, json.JSONDecodeError, Exception) as e:
            logger.warning(f"Extractor: попытка {attempt}/{_MAX_RETRIES} failed: {e}")
            if attempt == _MAX_RETRIES:
                logger.error(f"Extractor: все попытки исчерпаны для абстракта: {abstract[:80]}...")
                return None

    return None


async def extract_facts(articles: list[dict]) -> list[dict]:
    """Извлечь факты из абстрактов списка статей.

    Для каждой статьи запускает LLM-извлечение и добавляет
    поле 'facts' в словарь статьи. Статьи без фактов — тоже
    включаются в результат (с facts=None).

    Args:
        articles: Список словарей статей от Reranker

    Returns:
        Тот же список с добавленным полем 'facts' в каждой статье
    """
    if not articles:
        return []

    result = []
    for i, article in enumerate(articles):
        abstract = article.get("abstract", "")
        if not abstract:
            logger.warning(f"Extractor: статья без абстракта: {article.get('arxiv_id')}")
            result.append({**article, "facts": None})
            continue

        facts = _extract_facts_sync(abstract)
        result.append({**article, "facts": facts.model_dump() if facts else None})
        logger.info(f"Extractor: обработано {i + 1}/{len(articles)}")

    return result