"""
core/generator.py — генерация тем ВКР через LLM

Принимает статьи с извлечёнными фактами и ограничения пользователя,
генерирует 5-12 тем с обоснованием, подходом, датасетами и ссылками.
Результаты валидируются через Pydantic.

Используется в:
    - core/pipeline.py — пятый шаг пайплайна
"""

import json
import logging
import re
from pathlib import Path

import ollama
from pydantic import BaseModel, field_validator

from config import settings

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path("prompts/generator.txt")
_MAX_RETRIES = 3
_DEFAULT_NUM_TOPICS = 6

# Pydantic-схема для одной сгенерированной темы ВКР, которая включает в себя название, обоснование, подход, датасеты и источники.

class GeneratedTopic(BaseModel):
    """Одна сгенерированная тема ВКР."""

    title: str
    rationale: str | None = None
    approach: str | None = None
    datasets: list[str] = []
    sources: list[str] = []

    @field_validator("datasets", "sources", mode="before")
    @classmethod
    def ensure_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [str(item).strip() for item in v if item and str(item).strip()]


# Вспомогательные функции для загрузки промпта, построения контекста из статей и парсинга ответа от LLM.

def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _build_context(articles: list[dict]) -> str:
    """Сформировать контекст из статей и фактов для промпта Generator."""
    parts = []
    for i, article in enumerate(articles, 1):
        title = article.get("title", "")
        url = article.get("url", "")
        abstract = article.get("abstract", "")[:1000] # ограничиваем длину абстракта
        facts = article.get("facts")

        part = f"[{i}] {title}\nSOURCE URL (use this in sources field): {url}\nAbstract: {abstract}"

        if facts:
            if facts.get("problem"):
                part += f"\nProblem: {facts['problem']}"
            if facts.get("gap"):
                part += f"\nGap: {facts['gap']}"
            if facts.get("methods"):
                part += f"\nMethods: {', '.join(facts['methods'])}"
            if facts.get("datasets"):
                part += f"\nDatasets: {', '.join(facts['datasets'])}"
            if facts.get("metrics"):
                part += f"\nMetrics: {', '.join(facts['metrics'])}"

        parts.append(part)

    return "\n\n---\n\n".join(parts)


def _parse_topics(response_text: str) -> list[GeneratedTopic]:
    """Распарсить JSON-массив тем из ответа LLM."""
    text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()

    # Попытка 1 — ищем массив [...] 
    start = text.find("[")
    end = text.rfind("]") + 1
    
    if start != -1 and end > 0:
        json_str = text[start:end]
    else:
        # Попытка 2 — модель вернула объекты подряд, оборачиваем в массив
        objects = re.findall(r'\{[^{}]*\}', text, re.DOTALL)
        if not objects:
            raise ValueError(f"JSON-массив не найден в ответе: {text[:200]}")
        json_str = "[" + ",".join(objects) + "]"

    data = json.loads(json_str)
    if not isinstance(data, list):
        raise ValueError(f"Ожидался список тем, получено: {type(data)}")

    topics = [GeneratedTopic(**item) for item in data if isinstance(item, dict)]
    return topics


# Основная функция для генерации тем ВКР. Принимает список статей с фактами, параметры уровня и срока, желаемое количество тем. 
# Формирует контекст и промпт, отправляет запрос в LLM, парсит и валидирует результат. Делает несколько попыток при невалидном ответе.

async def generate_topics(
    articles: list[dict],
    level: str = "master",
    duration: int = 3,
    num_topics: int = _DEFAULT_NUM_TOPICS,
) -> list[dict]:
    """Сгенерировать темы ВКР на основе статей и извлечённых фактов.

    Args:
        articles:   Список статей с полем 'facts' от Extractor
        level:      Степень обучения (bachelor/master/phd/postdoc)
        duration:   Желаемый срок работы в месяцах
        num_topics: Желаемое количество тем

    Returns:
        Список словарей с темами (title, rationale, approach, datasets, sources)
    """
    if not articles:
        logger.warning("Generator: передан пустой список статей")
        return []

    context = _build_context(articles)
    template = _load_prompt()
    prompt = template.format(
        num_topics=num_topics,
        level=level,
        duration=duration,
        context=context,
    )

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = ollama.chat(
                model=settings.ollama_model,
                messages=[{"role": "user", "content": prompt}],
                options={
                    "temperature": 0.5,
                    "num_predict": 4096,  
                    },
                think=False,
            )
            response_text = response["message"]["content"]
            topics = _parse_topics(response_text)

            if not topics:
                raise ValueError("Получен пустой список тем")

            logger.info(
                f"Generator: сгенерировано {len(topics)} тем "
                f"(попытка {attempt})"
            )
            return [t.model_dump() for t in topics]

        except (ValueError, json.JSONDecodeError, Exception) as e:
            logger.warning(f"Generator: попытка {attempt}/{_MAX_RETRIES} failed: {e}")
            if attempt == _MAX_RETRIES:
                logger.error("Generator: все попытки исчерпаны")
                return []

    return []