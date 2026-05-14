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
_MAX_RETRIES = 5
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
        max_abstract = 300 if len(articles) <= 5 else 200 if len(articles) <= 10 else 150
        abstract = article.get("abstract", "")[:max_abstract]
        facts = article.get("facts")

        part = f"PAPER\nTitle: {title}\nSOURCE URL (use this in sources field): {url}\nAbstract: {abstract}"
        
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


def _count_sentences(text: str) -> int:
    """Подсчёт предложений по знакам завершения."""
    if not text:
        return 0
    return len(re.findall(r'[.!?]+', text))


def _parse_topics(response_text: str) -> list[GeneratedTopic]:
    """Распарсить JSON-массив тем из ответа LLM."""
    text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()
    text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)

    start = text.find("[")
    end = text.rfind("]") + 1

    if start != -1 and end > 0:
        json_str = text[start:end]
    else:
        objects = re.findall(r'\{[^{}]*\}', text, re.DOTALL)
        if not objects:
            raise ValueError(f"JSON-массив не найден в ответе: {text[:200]}")
        json_str = "[" + ",".join(objects) + "]"

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Пробуем извлечь объекты по одному
        objects = re.findall(r'\{[^{}]+\}', json_str, re.DOTALL)
        data = []
        for obj in objects:
            try:
                data.append(json.loads(obj))
            except json.JSONDecodeError:
                continue
        if not data:
            raise ValueError(f"Не удалось распарсить ни одного объекта из ответа")

    if not isinstance(data, list):
        raise ValueError(f"Ожидался список тем, получено: {type(data)}")

    topics = [GeneratedTopic(**item) for item in data if isinstance(item, dict)]

    # Фильтруем темы без источников
    topics = [t for t in topics if t.sources]

    # Убираем дубликаты по заголовку (case-insensitive, первые 60 символов)
    seen_titles: set[str] = set()
    unique_topics = []
    for t in topics:
        title_key = t.title.strip().lower()[:60]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_topics.append(t)

    # Дедупликация источников в каждой теме
    for t in unique_topics:
        t.sources = list(dict.fromkeys(t.sources))
        if t.rationale:
            t.rationale = _clean_citations(t.rationale)
        if t.approach:
            t.approach = _clean_citations(t.approach)
        if t.title:
            t.title = _clean_citations(t.title)

    # Фильтруем темы с менее чем 2 источниками
    filtered = [t for t in unique_topics if len(t.sources) >= 2]

    # После фильтра по 2+ источникам добавь:
    filtered = [t for t in filtered if
        _count_sentences(t.rationale or '') >= 4 and
        _count_sentences(t.approach or '') >= 3
    ]

    logger.debug(f"Generator _parse_topics: после фильтра по длине={len(filtered)}")
    logger.debug(
        f"Generator _parse_topics: распарсено={len(topics)}, "
        f"уникальных={len(unique_topics)}, "
        f"с 2+ источниками={len(filtered)}"
    )

    # Если все отфильтровались — вернуть как есть (лучше 1 тема чем ничего)
    return filtered if filtered else unique_topics

import re

def _clean_citations(text: str) -> str:
    """Убирает артефакты цитирования вида [1], [2], (1), работа [3] и т.д."""
    if not text:
        return text
    # Убираем [1], [2], [3], [4] и т.д.
    text = re.sub(r'\[\d+\]', '', text)
    # Убираем (1), (2) и т.д.
    text = re.sub(r'\(\d+\)', '', text)
    # Убираем "в работе [N]", "paper [N]", "работа [N]"
    text = re.sub(r'\b(в работе|работа|paper|статья|источник)\s*\[\d+\]', '', text, flags=re.IGNORECASE)
    # Чистим двойные пробелы
    text = re.sub(r'  +', ' ', text).strip()
    return text

# Основная функция для генерации тем ВКР. Принимает список статей с фактами, параметры уровня и срока, желаемое количество тем.
# Формирует контекст и промпт, отправляет запрос в LLM, парсит и валидирует результат.
# Накапливает темы через несколько попыток пока не наберётся нужное количество.

async def generate_topics(
    articles: list[dict],
    level: str = "master",
    duration: int = 3,
    num_topics: int = _DEFAULT_NUM_TOPICS,
    locale: str = "ru",
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

    language_name = "Russian" if locale == "ru" else "English"

    system_message = (
        f"CRITICAL: Respond ONLY in {language_name}. "
        f"Every word of title, rationale, approach must be in {language_name}. "
        f"You are a strict JSON generator. "
        f"Keep only technical names, dataset names, model names and URLs unchanged."
    )

    # Накапливаем темы через несколько попыток
    accumulated: list[GeneratedTopic] = []
    seen_titles: set[str] = set()

    for attempt in range(1, _MAX_RETRIES + 1):
        # На каждой попытке просим столько тем сколько ещё не хватает (+ 2 про запас)
        remaining = num_topics - len(accumulated)
        effective_num = remaining + 2

        prompt = template.format(
            num_topics=effective_num,
            level=level,
            duration=duration,
            context=context,
            locale=locale,
        )

        prompt = (
            f"FINAL LANGUAGE REQUIREMENT: Write title, rationale, approach and dataset descriptions "
            f"strictly in {language_name}. Do not copy English wording from abstracts unless it is a technical term.\n\n"
            + prompt
        )

        try:
            response = ollama.chat(
                model=settings.ollama_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user",   "content": prompt},
                ],
                options={
                    "temperature": 0.5,
                    "num_predict": 8192,
                },
                think=False,
            )
            response_text = response["message"]["content"]
            new_topics = _parse_topics(response_text)

            # Добавляем только новые уникальные темы
            for t in new_topics:
                key = t.title.strip().lower()[:60]
                if key not in seen_titles:
                    seen_titles.add(key)
                    accumulated.append(t)

            logger.info(
                f"Generator: накоплено {len(accumulated)}/{num_topics} тем "
                f"(попытка {attempt}, новых в этой попытке: {len(new_topics)})"
            )

            # Достаточно тем — выходим
            if len(accumulated) >= num_topics:
                break

        except (ValueError, json.JSONDecodeError, Exception) as e:
            logger.warning(f"Generator: попытка {attempt}/{_MAX_RETRIES} failed: {e}")
            if attempt == _MAX_RETRIES and not accumulated:
                logger.error("Generator: все попытки исчерпаны, тем нет")
                return []

    result = accumulated[:num_topics]

    if not result:
        logger.error("Generator: не удалось сгенерировать ни одной темы")
        return []

    logger.info(f"Generator: итого сгенерировано {len(result)} тем")
    return [t.model_dump() for t in result]