"""
core/planner.py — Query Expansion через LLM (Planner)

Принимает запрос пользователя и расширяет его в 10-15 тематических
подзапросов для более широкого покрытия области в arXiv.

Используется в:
    - core/pipeline.py — первый шаг пайплайна
"""

import json
import logging
import re
from pathlib import Path

import ollama

from config import settings

logger = logging.getLogger(__name__)

# Путь к промпту
_PROMPT_PATH = Path("prompts/planner.txt")

# Количество попыток при невалидном ответе LLM
_MAX_RETRIES = 3


def _load_prompt() -> str:
    """Загрузить промпт из файла."""
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_prompt(query: str, level: str, duration: int) -> str:
    """Подставить параметры в шаблон промпта."""
    template = _load_prompt()
    return template.format(query=query, level=level, duration=duration)


def _parse_subqueries(response_text: str) -> list[str]:
    """Распарсить JSON-список подзапросов из ответа LLM.

    Пытается извлечь JSON даже если модель добавила лишний текст.
    """
    # Убираем think-блоки qwen3
    text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()
    
    # Ищем JSON-массив в тексте
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"JSON-массив не найден в ответе: {text[:200]}")

    json_str = text[start:end]
    result = json.loads(json_str)

    if not isinstance(result, list):
        raise ValueError(f"Ожидался список, получено: {type(result)}")

    # Фильтруем пустые строки
    subqueries = [q.strip() for q in result if isinstance(q, str) and q.strip()]
    subqueries = subqueries[:15]  # Ограничиваем максимум 15 подзапросами
    return subqueries


async def expand_query(
    query: str,
    level: str = "master",
    duration: int = 3,
) -> list[str]:
    """Расширить запрос пользователя в список подзапросов через LLM.

    Args:
        query:    Исходный запрос пользователя
        level:    Степень обучения (bachelor/master/phd/postdoc)
        duration: Желаемый срок работы в месяцах

    Returns:
        Список из 10-15 поисковых подзапросов для arXiv
    """
    prompt = _build_prompt(query=query, level=level, duration=duration)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = ollama.chat(
                model=settings.ollama_model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": 0.3,
                    "num_predict": 512,  
                    },
                    think=False,
            )
            response_text = response["message"]["content"]
            subqueries = _parse_subqueries(response_text)

            if not subqueries:
                raise ValueError("Получен пустой список подзапросов")

            logger.info(
                f"Planner сгенерировал {len(subqueries)} подзапросов "
                f"(попытка {attempt})"
            )
            return subqueries

        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"Planner: попытка {attempt}/{_MAX_RETRIES} failed: {e}")
            if attempt == _MAX_RETRIES:
                # Fallback — возвращаем исходный запрос как единственный подзапрос
                logger.error("Planner: все попытки исчерпаны, используем fallback")
                return [query]

    return [query]