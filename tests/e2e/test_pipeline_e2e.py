"""
tests/test_pipeline_e2e.py — end-to-end тест полного RAG-пайплайна

Запускает полный цикл от запроса пользователя до генерации тем.
Выводит подробные логи каждого шага.

Запуск:
    uv run python tests/test_pipeline_e2e.py
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Настраиваем подробное логирование для всех модулей core
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
    datefmt="%H:%M:%S",
)

# Снижаем шум от сторонних библиотек
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logging.getLogger("faiss").setLevel(logging.WARNING)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

from core.pipeline import run_pipeline

SEPARATOR = "=" * 70


async def main():
    query = "я студент магистр, меня интересует CV и Speech processing. Проект на 5 месяцев"
    level = "master"
    duration = 5

    print(f"\n{SEPARATOR}")
    print("E2E ТЕСТ: ПОЛНЫЙ RAG-ПАЙПЛАЙН")
    print(SEPARATOR)
    print(f"Запрос:  {query}")
    print(f"Уровень: {level}")
    print(f"Срок:    {duration} месяцев")
    print(SEPARATOR + "\n")

    result = await run_pipeline(
        query=query,
        level=level,
        duration=duration,
        num_topics=5,
    )

    # Вывод результатов 

    print(f"\n{SEPARATOR}")
    print("РЕЗУЛЬТАТЫ ПАЙПЛАЙНА")
    print(SEPARATOR)

    print(f"\n Query ID в БД: {result['query_id']}")

    print(f"\n ПОДЗАПРОСЫ от Planner ({len(result['subqueries'])} шт.):")
    for i, sq in enumerate(result['subqueries'], 1):
        print(f"   {i:2}. {sq}")

    print(f"\n СТАТЬИ после Reranker ({len(result['articles'])} шт.):")
    for i, art in enumerate(result['articles'], 1):
        print(f"   {i:2}. [{art.get('primary_category', '?')}] {art['title'][:70]}")
        print(f"       URL: {art['url']}")

    print(f"\n СГЕНЕРИРОВАННЫЕ ТЕМЫ ({len(result['topics'])} шт.):")
    print(SEPARATOR)

    for i, topic in enumerate(result['topics'], 1):
        print(f"\n{'─' * 70}")
        print(f"ТЕМА {i}: {topic['title']}")
        print(f"{'─' * 70}")

        if topic.get('rationale'):
            print(f"\n Обоснование:\n   {topic['rationale']}")

        if topic.get('approach'):
            print(f"\n Подход:\n   {topic['approach']}")

        if topic.get('datasets'):
            print(f"\n  Датасеты:")
            for ds in topic['datasets']:
                print(f"   • {ds}")

        if topic.get('sources'):
            print(f"\n Источники:")
            for src in topic['sources']:
                print(f"   • {src}")

    print(f"\n{SEPARATOR}")
    print("ТЕСТ ЗАВЕРШЁН УСПЕШНО")
    print(SEPARATOR + "\n")


if __name__ == "__main__":
    asyncio.run(main())