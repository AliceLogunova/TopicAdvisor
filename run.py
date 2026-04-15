"""
run.py — CLI точка входа для запуска полного RAG-пайплайна

Запуск:
    uv run python run.py --query "интересуюсь NLP" --level bachelor --duration 5
    uv run python run.py --query "машинное обучение" --level master --duration 3 --topics 7
"""

import argparse
import asyncio
import json
import logging

# Настройка логирования — INFO по умолчанию, DEBUG если передан --verbose
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

from core.pipeline import run_pipeline

SEPARATOR = "=" * 70


def _print_results(result: dict) -> None:
    """Красиво вывести результаты пайплайна в терминал."""

    print(f"\n{SEPARATOR}")
    print("РЕЗУЛЬТАТЫ")
    print(SEPARATOR)
    print(f"Query ID: {result['query_id']}")
    print(f"Подзапросов сгенерировано: {len(result['subqueries'])}")
    print(f"Статей найдено: {len(result['articles'])}")
    print(f"Тем сгенерировано: {len(result['topics'])}")

    if not result["topics"]:
        print("\n  Темы не были сгенерированы. Попробуйте переформулировать запрос.")
        return

    print(f"\n{'─' * 70}")
    print("СГЕНЕРИРОВАННЫЕ ТЕМЫ")
    print(f"{'─' * 70}")

    for i, topic in enumerate(result["topics"], 1):
        print(f"\n{'─' * 70}")
        print(f"ТЕМА {i}: {topic['title']}")
        print(f"{'─' * 70}")

        if topic.get("rationale"):
            print(f"\n Почему сейчас:\n   {topic['rationale']}")

        if topic.get("approach"):
            print(f"\n Подход:\n   {topic['approach']}")

        if topic.get("datasets"):
            print(f"\n  Датасеты:")
            for ds in topic["datasets"]:
                print(f"   • {ds}")

        if topic.get("sources"):
            print(f"\n Источники:")
            for src in topic["sources"]:
                print(f"   • {src}")

    print(f"\n{SEPARATOR}\n")


async def main(args: argparse.Namespace) -> None:
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        # Приглушаем шум от сторонних библиотек
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
        logging.getLogger("transformers").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
        logging.getLogger("filelock").setLevel(logging.WARNING)
        logging.getLogger("huggingface_hub").setLevel(logging.WARNING)

    print(f"\n{SEPARATOR}")
    print("TopicAdvisor — RAG-пайплайн")
    print(SEPARATOR)
    print(f"Запрос:  {args.query}")
    print(f"Уровень: {args.level}")
    print(f"Срок:    {args.duration} месяцев")
    print(f"Тем:     {args.topics}")
    print(SEPARATOR)

    result = await run_pipeline(
        query=args.query,
        level=args.level,
        duration=args.duration,
        num_topics=args.topics,
    )

    # Вывод в терминал
    _print_results(result)

    # Сохранение в JSON если передан --output
    if args.output:
        output_data = {
            "query": args.query,
            "level": args.level,
            "duration": args.duration,
            "query_id": result["query_id"],
            "subqueries": result["subqueries"],
            "topics": result["topics"],
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f" Результаты сохранены в: {args.output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TopicAdvisor — генерация тем ВКР на основе arXiv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  uv run python run.py --query "интересуюсь NLP и трансформерами" --level bachelor --duration 5
  uv run python run.py --query "компьютерное зрение" --level master --duration 6 --topics 7
  uv run python run.py --query "reinforcement learning" --level phd --duration 12 --output results.json
        """,
    )

    parser.add_argument(
        "--query", "-q",
        type=str,
        required=True,
        help="Запрос пользователя (интересы, область, тематика)",
    )
    parser.add_argument(
        "--level", "-l",
        type=str,
        default="master",
        choices=["bachelor", "master", "phd", "postdoc"],
        help="Степень обучения (по умолчанию: master)",
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=3,
        help="Желаемый срок работы в месяцах (по умолчанию: 3)",
    )
    parser.add_argument(
        "--topics", "-t",
        type=int,
        default=6,
        help="Количество тем на выходе (по умолчанию: 6)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Путь для сохранения результатов в JSON (опционально)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Подробные логи всех шагов пайплайна",
    )

    args = parser.parse_args()
    asyncio.run(main(args))