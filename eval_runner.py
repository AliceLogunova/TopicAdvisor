"""
eval_runner.py — Прогон пайплайна по 180 тестовым запросам для оценки качества

Запускает все запросы, замеряет Time-to-Result, вычисляет машинные метрики
(Coverage Rate, JSON Parse Rate, Topic Coherence)
и сохраняет результаты в eval_results.json для последующей экспертной оценки.

Запуск:
    uv run python eval_runner.py

Требования:
    - docker compose up -d
    - ollama serve + модели qwen3.5:2b, qwen3-embedding:0.6b
    - проиндексированные статьи (см. инструкции ниже)
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
import re

import numpy as np

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Тестовые запросы 
# 3 запроса × 3 предметных области × 3 значения top_k = 27 прогонов
# Каждая область содержит короткие (1-5 слов) и длинные (20+ слов) запросы

QUERIES = {
    "cs": [
        # Короткие
        "adversarial robustness attacks",
        "recommendation systems embeddings",
        # Длинный
        "Interested in multimodal learning combining vision and language for video understanding tasks, "
        "specifically temporal reasoning and cross-modal alignment in long video sequences",
    ],
    "math": [
        # Короткие
        "number theory primes",
        "game theory equilibria",
        # Длинный
        "I would like to research categorical approaches to homotopy theory and their applications "
        "in modern algebraic topology, focusing on infinity-categories and derived algebraic geometry",
    ],
    "physics": [
        # Короткие
        "dark matter detection",
        "atomic physics laser cooling",
        # Длинный
        "I want to explore experimental and theoretical aspects of quantum sensing and metrology, "
        "including atom interferometry, optical clocks, and their applications to tests of "
        "fundamental physics and gravitational wave detection",
    ],
}

TOP_K_VALUES = [5, 10, 15]


# Машинные метрики — автоматические оценки качества по результатам прогонов

def compute_coverage_rate(subqueries: list[str], domain: str) -> float:
    """Coverage Rate через regex — для одного прогона."""
    domain_patterns = {
        "cs": [
            r"\bneural\b|\bdeep\b|\blearn\b|\bnetwork\b",
            r"\bmodel\b|\btrain\b|\boptim\b",
            r"\bdata\b|\bdataset\b|\bbenchmark\b",
            r"\bmethod\b|\bapproach\b|\balgorithm\b",
            r"\bperform\b|\bevaluat\b|\bmetric\b",
            r"\bembed\b|\brepresent\b|\bvector\b",
            r"\bgraph\b|\bnode\b|\bedge\b|\bknowledge\b",
            r"\blanguage\b|\btext\b|\bnlp\b|\bsemantic\b",
            r"\bclassif\b|\bpredict\b|\bdetect\b",
            r"\btransform\b|\battention\b|\bbert\b|\bgpt\b",
        ],
        "math": [
            r"\btheor\b|\bproof\b|\btheorem\b",
            r"\bfunction\b|\bequation\b|\boperator\b",
            r"\balgebra\b|\bgeometr\b|\btopolog\b",
            r"\bnumber\b|\bprime\b|\binteger\b",
            r"\bprobabilit\b|\bstochast\b|\brandom\b",
            r"\boptim\b|\bconvex\b|\bgradient\b",
            r"\bmatrix\b|\blinear\b|\bdimension\b",
            r"\banalys\b|\bcalculus\b|\bintegral\b",
            r"\bspace\b|\bmanifold\b|\bconvergence\b",
            r"\bstatistic\b|\bdistribut\b|\bestimат\b",
        ],
        "physics": [
            r"\bquantum\b|\bqubit\b|\bentangl\b",
            r"\benergy\b|\bstate\b|\bsystem\b",
            r"\bparticle\b|\bfield\b|\bwave\b",
            r"\bmatter\b|\bmaterial\b|\bphase\b",
            r"\bmagnetic\b|\bspin\b|\belectron\b",
            r"\boptical\b|\bphoton\b|\blaser\b",
            r"\bthermodynam\b|\bentropy\b|\btemper\b",
            r"\bgravitati\b|\bspacetime\b|\brelativ\b",
            r"\bnuclear\b|\batom\b|\bmolecul\b",
            r"\bexperiment\b|\bmeasur\b|\bdetect\b",
        ],
    }
    patterns = domain_patterns.get(domain, [])
    if not patterns:
        return 0.0
    all_text = " ".join(subqueries).lower()
    covered = sum(1 for p in patterns if re.search(p, all_text))
    return round(covered / len(patterns), 4)


def compute_coverage_rate_for_domain(all_results: list[dict], domain: str) -> float:
    """Coverage Rate идеальный — по всем подзапросам домена вместе."""
    all_subqueries = []
    for r in all_results:
        if r.get("domain") == domain:
            all_subqueries.extend(r.get("subqueries", []))
    return compute_coverage_rate(all_subqueries, domain)


def compute_json_parse_rate(results: list[dict], field: str) -> float:
    """
    JSON Parse Rate: доля успешно распарсенных JSON-ответов
    для planner (subqueries), extractor (facts), generator (topics).
    """
    total = len(results)
    if total == 0:
        return 0.0

    success = 0
    for r in results:
        val = r.get(field)
        if field == "subqueries":
            if isinstance(val, list) and len(val) > 0:
                success += 1
        elif field == "topics":
            if isinstance(val, list) and len(val) > 0:
                success += 1
        elif field == "articles_with_facts":
            facts_list = val or []
            if any(a.get("facts") is not None for a in facts_list):
                success += 1

    return round(success / total, 4)


def compute_topic_coherence(results: list[dict]) -> float:
    """
    Topic Coherence через реальные эмбеддинги qwen3-embedding:0.6b.
    Косинусное сходство между вектором темы и средним вектором источников.
    """
    import ollama
    import numpy as np

    _EMBED_MODEL = "qwen3-embedding:0.6b"

    def get_embedding(text: str) -> np.ndarray:
        resp = ollama.embed(model=_EMBED_MODEL, input=text[:500])
        return np.array(resp["embeddings"][0], dtype=np.float32)

    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    scores = []
    for r in results:
        topics = r.get("topics", [])
        articles = r.get("articles_with_facts", r.get("articles", []))
        article_map = {a.get("url", ""): a for a in articles}

        for topic in topics:
            # Текст темы
            topic_text = " ".join(filter(None, [
                topic.get("title", ""),
                topic.get("rationale", ""),
            ]))
            if not topic_text.strip():
                continue

            # Тексты источников
            source_urls = topic.get("sources", [])
            source_texts = []
            for url in source_urls:
                art = article_map.get(url)
                if art:
                    source_texts.append(
                        art.get("title", "") + " " + art.get("abstract", "")[:300]
                    )

            # Если источники не найдены по URL — берём первые 3 статьи
            if not source_texts:
                source_texts = [
                    a.get("title", "") + " " + a.get("abstract", "")[:200]
                    for a in articles[:3]
                ]

            if not source_texts:
                continue

            try:
                topic_vec = get_embedding(topic_text)
                source_vecs = [get_embedding(t) for t in source_texts]
                mean_source_vec = np.mean(source_vecs, axis=0)
                scores.append(cosine(topic_vec, mean_source_vec))
            except Exception as e:
                logger.warning(f"Topic Coherence: ошибка эмбеддинга: {e}")
                continue

    return round(float(np.mean(scores)) if scores else 0.0, 4)


# Основной прогон — запускаем пайплайн для каждого запроса и собираем результаты с метриками

async def run_single_query(query: str, domain: str, top_k: int) -> dict:
    """Запустить пайплайн для одного запроса и вернуть результат с метриками."""
    from core.pipeline import run_pipeline

    start = time.time()
    try:
        result = await run_pipeline(
            query=query,
            level="master",
            duration=6,
            num_topics=5,
            retriever_top_k=top_k * 3,
            reranker_top_k=top_k,
        )
        elapsed = round(time.time() - start, 2)
        success = True
        error = None
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        result = {"subqueries": [], "articles": [], "topics": [], "query_id": None}
        success = False
        error = str(e)
        logger.error(f"Ошибка для запроса '{query[:50]}': {e}")

    # Сохраняем articles_with_facts если есть
    articles_with_facts = result.get("articles_with_facts", [])

    return {
        "query": query,
        "domain": domain,
        "top_k": top_k,
        "time_seconds": elapsed,
        "success": success,
        "error": error,
        "query_id": result.get("query_id"),
        "subqueries": result.get("subqueries", []),
        "articles": [
            {
                "arxiv_id": a.get("arxiv_id", ""),
                "title": a.get("title", ""),
                "abstract": a.get("abstract", "")[:500],
                "url": a.get("url", ""),
                "primary_category": a.get("primary_category", ""),
            }
            for a in articles_with_facts
        ],
        "articles_with_facts": [
            {
                "arxiv_id": a.get("arxiv_id", ""),
                "title": a.get("title", ""),
                "abstract": a.get("abstract", "")[:500],
                "url": a.get("url", ""),
                "facts": a.get("facts"),
            }
            for a in articles_with_facts
        ],
        "topics": result.get("topics", []),
        # Машинные метрики для этого запроса
        "metrics": {
            "coverage_rate": compute_coverage_rate(result.get("subqueries", []), domain),
            "planner_json_parse": 1 if result.get("subqueries") else 0,
            "generator_json_parse": 1 if result.get("topics") else 0,
            "extractor_json_parse": (
                1 if any(a.get("facts") for a in articles_with_facts) else 0
            ),
        },
    }


async def main():
    logger.info("=" * 6)
    logger.info("TopicAdvisor — Оценочный прогон пайплайна (27 запросов)")
    logger.info("=" * 6)

    all_results = []
    total = sum(len(qs) for qs in QUERIES.values()) * len(TOP_K_VALUES)
    done = 0

    for domain, queries in QUERIES.items():
        for top_k in TOP_K_VALUES:
            for query in queries:
                done += 1
                logger.info(f"[{done}/{total}] domain={domain} top_k={top_k} | {query[:6]}...")
                result = await run_single_query(query, domain, top_k)
                all_results.append(result)

                # Красивый вывод тем в консоль для быстрой оценки результатов
                topics = result.get("topics", [])
                sep = "─" * 70
                print(f"\n{'=' * 70}")
                print(f"[{done}/{total}] domain={domain.upper()} top_k={top_k}")
                print(f"Запрос: {query}")
                print(f"Время: {result['time_seconds']}с | Подзапросов: {len(result.get('subqueries', []))} | Статей: {len(result.get('articles', []))} | Тем: {len(topics)}")
                if topics:
                    for i, t in enumerate(topics, 1):
                        print(f"\n{sep}")
                        print(f"ТЕМА {i}: {t.get('title', '—')}")
                        print(sep)
                        if t.get("rationale"):
                            print(f"\n  Обоснование:\n    {t['rationale']}")
                        if t.get("approach"):
                            print(f"\n  Подход:\n    {t['approach']}")
                        if t.get("datasets"):
                            print(f"\n  Датасеты:")
                            for ds in t["datasets"]:
                                print(f"    • {ds}")
                        if t.get("sources"):
                            print(f"\n  Источники:")
                            for src in t["sources"]:
                                print(f"    • {src}")
                else:
                    print(" Темы не сгенерированы")
                print()

                # Сохраняем после каждого запроса (на случай прерывания)
                with open("eval_results.json", "w", encoding="utf-8") as f:
                    json.dump(all_results, f, ensure_ascii=False, indent=2)

    # Агрегированные машинные метрики 
    logger.info("\nВычисляем агрегированные метрики...")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "total_queries": len(all_results),
        "successful_queries": sum(1 for r in all_results if r["success"]),

        # Time-to-Result
        "time_to_result": {
            "mean": round(float(np.mean([r["time_seconds"] for r in all_results])), 2),
            "median": round(float(np.median([r["time_seconds"] for r in all_results])), 2),
            "min": round(float(np.min([r["time_seconds"] for r in all_results])), 2),
            "max": round(float(np.max([r["time_seconds"] for r in all_results])), 2),
            "by_top_k": {
                str(k): round(float(np.mean([
                    r["time_seconds"] for r in all_results if r["top_k"] == k
                ])), 2)
                for k in TOP_K_VALUES
            },
            "by_domain": {
                d: round(float(np.mean([
                    r["time_seconds"] for r in all_results if r["domain"] == d
                ])), 2)
                for d in QUERIES
            },
        },

        # JSON Parse Rates
        "json_parse_rates": {
            "planner": round(float(np.mean([r["metrics"]["planner_json_parse"] for r in all_results])), 4),
            "extractor": round(float(np.mean([r["metrics"]["extractor_json_parse"] for r in all_results])), 4),
            "generator": round(float(np.mean([r["metrics"]["generator_json_parse"] for r in all_results])), 4),
        },

        # Coverage Rate по доменам
        "coverage_rate": {
            d: compute_coverage_rate_for_domain(all_results, d)
            for d in QUERIES
        },

        # Topic Coherence
        "topic_coherence": {
            "overall": compute_topic_coherence(all_results),
            "by_domain": {
                d: compute_topic_coherence([r for r in all_results if r["domain"] == d])
                for d in QUERIES
            },
        },
    }

    # Сохраняем итоговый файл с результатами и метриками
    output = {
        "summary": summary,
        "results": all_results,
    }

    with open("eval_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info("\n" + "=" * 6)
    logger.info("МАШИННЫЕ МЕТРИКИ (итог)")
    logger.info("=" * 6)
    logger.info(f"Всего запросов:       {summary['total_queries']}")
    logger.info(f"Успешных:             {summary['successful_queries']}")
    logger.info(f"Time-to-result (ср.): {summary['time_to_result']['mean']}с")
    logger.info(f"Time-to-result (мед.): {summary['time_to_result']['median']}с")
    logger.info(f"Planner JSON Parse:   {summary['json_parse_rates']['planner'] * 100:.1f}%")
    logger.info(f"Extractor JSON Parse: {summary['json_parse_rates']['extractor'] * 100:.1f}%")
    logger.info(f"Generator JSON Parse: {summary['json_parse_rates']['generator'] * 100:.1f}%")
    logger.info(f"Coverage Rate (CS):   {summary['coverage_rate'].get('cs', 0) * 100:.1f}%")
    logger.info(f"Coverage Rate (Math): {summary['coverage_rate'].get('math', 0) * 100:.1f}%")
    logger.info(f"Coverage Rate (Phys): {summary['coverage_rate'].get('physics', 0) * 100:.1f}%")
    logger.info(f"Topic Coherence:      {summary['topic_coherence']['overall']:.4f}")
    logger.info("=" * 6)
    logger.info(f"\nРезультаты сохранены в eval_results.json")
    logger.info("Запустите eval_expert.html для экспертной оценки.")


if __name__ == "__main__":
    asyncio.run(main())