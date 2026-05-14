"""
eval_runner.py — Прогон пайплайна по 27 тестовым запросам для оценки качества

Запускает все запросы, замеряет Time-to-Result, вычисляет машинные метрики
и сохраняет результаты в eval_results.json для последующей экспертной оценки.

Запуск:
    uv run python eval_runner.py

Требования:
    - docker compose up -d
    - ollama serve + модели qwen3.5:2b, qwen3-embedding:0.6b
    - проиндексированные статьи (uv run python data/reindex_cs.py)

────────────────────────────────────────────────────────────────────────────────
МЕТРИКИ И УСЛОВИЯ ИХ ТЕСТИРОВАНИЯ
────────────────────────────────────────────────────────────────────────────────

1. TIME-TO-RESULT
   Что измеряет: полное время работы пайплайна от запроса до тем (секунды).
   Данные: все 27 прогонов (3 домена × 3 запроса × 3 значения top_k).
   Условия: измеряется по top_k = 5, 10, 15 — показывает зависимость времени от
   размера выборки. По доменам — показывает есть ли разница между CS/Math/Physics.
   Агрегация: mean, median, min, max. Median устойчивее к выбросам.

2. JSON PARSE RATE (Planner / Extractor / Generator)
   Что измеряет: долю запросов где LLM вернул валидный JSON с первой попытки.
   Данные: все 27 прогонов.
   Условия: Planner — 1 если subqueries непустой список; Extractor — 1 если хотя
   бы одна статья имеет непустые факты; Generator — 1 если topics непустой список.
   Важно: Generator использует накопление через несколько попыток — метрика
   показывает итоговый успех, а не успех с первой попытки.

3. COVERAGE RATE (Retriever / Planner)
   Что измеряет: насколько разнообразно Planner расширяет запрос —
   покрывает ли он ключевые аспекты предметной области.
   Данные: подзапросы от Planner по каждому домену.
   Условия: проверяется по regex-паттернам характерным для домена.
   Считается отдельно для CS, Math, Physics по всем подзапросам домена вместе.
   Ограничение: метрика измеряет лексическое покрытие, не семантическое.

4. TOPIC COHERENCE
   Что измеряет: семантическую связность сгенерированной темы с источниками.
   Данные: только темы у которых найдены источники-статьи по URL.
   Условия: косинусное сходство между эмбеддингом (title + rationale) темы и
   средним эмбеддингом статей-источников. Используется qwen3-embedding:0.6b.
   Диапазон: [−1, 1], чем выше тем лучше. Обычно >0.5 — хорошо.
   Важно: темы без найденных источников пропускаются, чтобы не занижать метрику
   через fallback на нерелевантные статьи.

5. PRECISION@K / NDCG@K (экспертная, Retriever + Reranker)
   Что измеряет: долю релевантных статей среди top-k выданных Retriever/Reranker.
   Данные: эксперт оценивает каждую статью (✓ Да / ~ Частично / ✗ Нет).
   Условия: считается отдельно для top_k = 5, 10, 15. delta-Precision@K показывает
   изменение качества при увеличении top_k — позволяет выбрать оптимальный параметр.
   NDCG учитывает порядок (релевантные статьи должны быть выше).

6. FIELD ACCURACY (экспертная, Extractor)
   Что измеряет: точность извлечения структурированных фактов из абстракта.
   Данные: только статьи где Extractor нашёл ХОТЯ БЫ ОДНО непустое поле.
   Статьи без фактов исключаются — они не показывают качество Extractor,
   а только сигнализируют о пропуске (отдельная метрика — Extractor JSON Parse Rate).
   Условия: эксперт сравнивает извлечённые поля (problem, gap, methods, datasets,
   metrics) с оригинальным абстрактом и ставит ✓ Верно / ~ Частично / ✗ Неверно.
   Accuracy = (верно + 0.5×частично) / всего оценённых.

7. RELEVANCE@K + ЭКСПЕРТНЫЕ ОЦЕНКИ (экспертная, Generator)
   Что измеряет: долю релевантных тем и качество по 5 критериям (1–5).
   Данные: все темы из прогонов с top_k=10 (основной режим работы системы).
   Критерии: научная новизна, корректность формулировки, обоснованность/актуальность,
   практическая реализуемость, качество источников.
────────────────────────────────────────────────────────────────────────────────
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

# ── Тестовые запросы ──────────────────────────────────────────────────────────
# Запросы на русском языке → пайплайн автоматически определяет locale=ru
# и генерирует темы на русском через _detect_query_locale()
#
# Каждая область содержит:
#   - 2 коротких запроса (ключевые слова, 2–5 слов) — проверяет работу с
#     неполным контекстом, когда Planner должен самостоятельно расширить тему
#   - 1 длинный запрос (20+ слов) — проверяет работу с детальным контекстом
#     и способность системы сохранить фокус на конкретной теме

QUERIES = {
    "cs_ai": [
        # cs.AI — короткий запрос
        "планирование и принятие решений в автономных интеллектуальных системах",
    ],

    "cs_cv": [
        # cs.CV — средний запрос
        "обнаружение дипфейков в видео с использованием пространственно-временных признаков",
    ],

    "cs_cl": [
        # cs.CL — длинный сложный запрос
        "меня интересует применение больших языковых моделей для автоматической суммаризации "
        "научных текстов с учетом сохранения фактической достоверности и обнаружения галлюцинаций",
    ],

    "cs_cr": [
        # cs.CR — короткий технический запрос
        "обнаружение уязвимостей в программном коде с помощью llm",
    ],

    "cs_ir": [
        # cs.IR — запрос средней сложности
        "retrieval augmented generation для поиска научной информации и ранжирования документов",
    ],

    "cs_sd": [
        # cs.SD — длинный инженерный запрос
        "исследование нейросетевых систем синтеза речи для английского языка "
        "с акцентом на выразительность, управление эмоциями и оценку качества tts-моделей",
    ],

    "cs_ro": [
    # cs.RO — robotics / autonomous agents
    "планирование траекторий и координация автономных роботов в динамической среде",
    ],

    "cs_lg": [
        # cs.LG — machine learning / optimization
        "адаптивное обучение агентов с подкреплением в условиях ограниченных вычислительных ресурсов",
    ],
}

TOP_K_VALUES = [5, 8, 11]


# ── Машинные метрики ──────────────────────────────────────────────────────────

def compute_coverage_rate(subqueries: list[str], domain: str) -> float:
    domain_patterns = {
        "cs_ai": [r"\bplan\b|\bdecision\b|\bagent\b", r"\bauton\b|\bintellig\b", r"\blearn\b|\btrain\b", r"\bmodel\b|\boptim\b", r"\bneural\b|\bdeep\b"],
        "cs_cv": [r"\bvideo\b|\bimage\b|\bvisual\b", r"\bdetect\b|\brecogn\b", r"\btemporal\b|\bspatial\b", r"\bdeep\b|\bneural\b", r"\bbenchmark\b|\bdataset\b"],
        "cs_cl": [r"\blanguage\b|\bllm\b|\btransform\b", r"\bsummar\b|\btext\b", r"\bhallucin\b|\bfact\b", r"\bgenerat\b|\bmodel\b", r"\bevaluat\b|\bbenchmark\b"],
        "cs_cr": [r"\bvulnerab\b|\bsecur\b|\battack\b", r"\bcode\b|\bmalware\b", r"\bllm\b|\bmodel\b", r"\bdetect\b|\banalys\b", r"\bbenchmark\b|\bdataset\b"],
        "cs_ir": [r"\bretrieval\b|\brag\b", r"\bgenerat\b|\bsearch\b", r"\bdocument\b|\branking\b", r"\bembedding\b|\bvector\b", r"\bfactual\b|\bgrounding\b"],
        "cs_sd": [r"\bspeech\b|\btts\b|\baudio\b", r"\bsynthes\b|\bvoice\b", r"\bemotion\b|\bexpressiv\b", r"\baccent\b|\bphoneme\b", r"\bevaluat\b|\bquality\b"],
        "cs_ro": [r"\brobot\b|\bswarm\b", r"\bpath\b|\btrajectory\b|\bnavig\b", r"\bplan\b|\bcontrol\b", r"\bautonomous\b|\bagent\b", r"\bdynamic\b|\buncertain\b"],
        "cs_lg": [r"\breinforcement\b|\brl\b", r"\blearn\b|\btrain\b", r"\bresource\b|\befficient\b", r"\badapt\b|\boptim\b", r"\bagent\b|\bpolic\b"],
    }
    patterns = domain_patterns.get(domain, [])
    if not patterns:
        return 0.0
    all_text = " ".join(subqueries).lower()
    covered = sum(1 for p in patterns if re.search(p, all_text))
    return round(covered / len(patterns), 4)

def compute_coverage_rate_for_domain(all_results: list[dict], domain: str) -> float:
    all_subqueries = []
    for r in all_results:
        if r.get("domain") == domain:
            all_subqueries.extend(r.get("subqueries", []))
    return compute_coverage_rate(all_subqueries, domain)


def compute_json_parse_rate(results: list[dict], field: str) -> float:
    """
    JSON Parse Rate: доля прогонов с успешным итоговым результатом.
    - planner: subqueries — непустой список
    - extractor: articles_with_facts — хотя бы одна статья с непустыми фактами
    - generator: topics — непустой список (учитывает накопление через попытки)
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
            # Считаем успешным только если есть статьи с НЕПУСТЫМИ фактами
            if any(
                a.get("facts") is not None and
                any(v for v in a["facts"].values() if v)
                for a in facts_list
            ):
                success += 1

    return round(success / total, 4)


def compute_topic_coherence(results: list[dict]) -> float:
    """
    Topic Coherence через эмбеддинги qwen3-embedding:0.6b.
    Косинусное сходство между вектором темы и средним вектором статей-источников.

    Важно: темы без найденных источников пропускаются.
    Это не занижает метрику через fallback на нерелевантные статьи.
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
        # Строим маппинг url → статья для быстрого поиска источников
        article_map = {a.get("url", ""): a for a in articles}

        for topic in topics:
            topic_text = " ".join(filter(None, [
                topic.get("title", ""),
                topic.get("rationale", ""),
            ]))
            if not topic_text.strip():
                continue

            source_urls = topic.get("sources", [])
            source_texts = []
            for url in source_urls:
                art = article_map.get(url)
                if art:
                    source_texts.append(
                        art.get("title", "") + " " + art.get("abstract", "")[:300]
                    )

            # Пропускаем тему если источники не найдены — не делаем fallback
            # чтобы не завышать метрику для тем с плохими/выдуманными источниками
            if not source_texts:
                logger.debug(f"Topic Coherence: пропущена тема без найденных источников: {topic.get('title','')[:50]}")
                continue

            try:
                topic_vec = get_embedding(topic_text)
                source_vecs = [get_embedding(t) for t in source_texts]
                mean_source_vec = np.mean(source_vecs, axis=0)
                scores.append(cosine(topic_vec, mean_source_vec))
            except Exception as e:
                logger.warning(f"Topic Coherence: ошибка эмбеддинга: {e}")
                continue

    if not scores:
        logger.warning("Topic Coherence: нет тем с найденными источниками")
        return 0.0

    return round(float(np.mean(scores)), 4)


# ── Основной прогон ───────────────────────────────────────────────────────────

async def run_single_query(query: str, domain: str, top_k: int) -> dict:
    """
    Запустить пайплайн для одного запроса и вернуть результат с метриками.
    locale определяется автоматически в pipeline.py по кириллице в запросе.
    """
    from core.pipeline import run_pipeline

    start = time.time()
    try:
        result = await run_pipeline(
            query=query,
            level="master",
            duration=6,
            num_topics=3,
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

    articles_with_facts = result.get("articles_with_facts", [])

    # Считаем Extractor JSON Parse Rate только для статей с непустыми фактами
    extractor_success = int(
        any(
            a.get("facts") is not None and
            any(v for v in a["facts"].values() if v)
            for a in articles_with_facts
        )
    )

    return {
        "query": query,
        "domain": domain,
        "top_k": top_k,
        "time_seconds": elapsed,
        "success": success,
        "error": error,
        "query_id": result.get("query_id"),
        "subqueries": result.get("subqueries", []),
        # Для Precision@K в eval_expert.html — статьи после Reranker
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
        # Для Field Accuracy в eval_expert.html — статьи с фактами
        # Фильтруем: только статьи где Extractor нашёл хотя бы одно непустое поле
        # Статьи без фактов не оцениваются по Field Accuracy — они не показывают
        # качество Extractor, а лишь сигнализируют о пропуске (см. JSON Parse Rate)
        "articles_with_facts": [
            {
                "arxiv_id": a.get("arxiv_id", ""),
                "title": a.get("title", ""),
                "abstract": a.get("abstract", "")[:500],
                "url": a.get("url", ""),
                "facts": a.get("facts"),
                # Флаг: статья имеет хотя бы одно непустое поле фактов
                "has_facts": (
                    a.get("facts") is not None and
                    any(v for v in a["facts"].values() if v)
                ),
            }
            for a in articles_with_facts
        ],
        "topics": result.get("topics", []),
        "metrics": {
            "coverage_rate": compute_coverage_rate(result.get("subqueries", []), domain),            "generator_json_parse": 1 if result.get("topics") else 0,
            "planner_json_parse": 1 if result.get("subqueries") else 0,   # ← добавить
            "generator_json_parse": 1 if result.get("topics") else 0,
            "extractor_json_parse": extractor_success,
            # Дополнительно: сколько статей имеют факты vs всего статей
            "articles_with_facts_count": sum(
                1 for a in articles_with_facts
                if a.get("facts") is not None and any(v for v in a["facts"].values() if v)
            ),
            "articles_total_count": len(articles_with_facts),
        },
    }


async def main():
    logger.info("=" * 70)
    logger.info("TopicAdvisor — Оценочный прогон пайплайна")
    total_runs = sum(len(qs) for qs in QUERIES.values()) * len(TOP_K_VALUES)
    logger.info(f"Запросов: {sum(len(qs) for qs in QUERIES.values())} × top_k: {TOP_K_VALUES} = {total_runs} прогонов")
    logger.info("Язык запросов: русский → ответы генерируются на русском")
    logger.info("=" * 70)

    all_results = []
    done = 0

    for domain, queries in QUERIES.items():
        for top_k in TOP_K_VALUES:
            for query in queries:
                done += 1
                logger.info(f"\n[{done}/{total_runs}] domain={domain} top_k={top_k}")
                logger.info(f"Запрос: {query[:80]}...")
                result = await run_single_query(query, domain, top_k)
                all_results.append(result)

                # Красивый вывод тем
                topics = result.get("topics", [])
                sep = "─" * 70
                print(f"\n{'=' * 70}")
                print(f"[{done}/{total_runs}] domain={domain.upper()} top_k={top_k}")
                print(f"Запрос: {query}")
                m = result.get("metrics", {})
                print(
                    f"Время: {result['time_seconds']}с | "
                    f"Подзапросов: {len(result.get('subqueries', []))} | "
                    f"Статей: {m.get('articles_total_count', 0)} "
                    f"(с фактами: {m.get('articles_with_facts_count', 0)}) | "
                    f"Тем: {len(topics)}"
                )

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
                    print("  ⚠ Темы не сгенерированы")
                print()

                # Сохраняем после каждого запроса (на случай прерывания)
                with open("eval_results.json", "w", encoding="utf-8") as f:
                    json.dump(all_results, f, ensure_ascii=False, indent=2)

    # ── Агрегированные метрики ────────────────────────────────────────────────
    logger.info("\nВычисляем агрегированные метрики...")

    # Topic Coherence — самая долгая операция (эмбеддинги)
    logger.info("Вычисляем Topic Coherence (эмбеддинги)...")
    topic_coherence_overall = compute_topic_coherence(all_results)
    topic_coherence_by_domain = {
        d: compute_topic_coherence([r for r in all_results if r["domain"] == d])
        for d in QUERIES
    }

    summary = {
        "generated_at": datetime.now().isoformat(),
        "total_queries": len(all_results),
        "successful_queries": sum(1 for r in all_results if r["success"]),

        # 1. Time-to-Result
        "time_to_result": {
            "mean":   round(float(np.mean([r["time_seconds"] for r in all_results])), 2),
            "median": round(float(np.median([r["time_seconds"] for r in all_results])), 2),
            "min":    round(float(np.min([r["time_seconds"] for r in all_results])), 2),
            "max":    round(float(np.max([r["time_seconds"] for r in all_results])), 2),
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

        # 2. JSON Parse Rates
        "json_parse_rates": {
            "planner":   round(float(np.mean([r["metrics"]["planner_json_parse"]   for r in all_results])), 4),
            "extractor": round(float(np.mean([r["metrics"]["extractor_json_parse"] for r in all_results])), 4),
            "generator": round(float(np.mean([r["metrics"]["generator_json_parse"] for r in all_results])), 4),
        },

        # Дополнительно: среднее покрытие фактами
        "extractor_coverage": {
            "mean_articles_with_facts": round(float(np.mean([
                r["metrics"]["articles_with_facts_count"] for r in all_results
            ])), 2),
            "mean_articles_total": round(float(np.mean([
                r["metrics"]["articles_total_count"] for r in all_results
            ])), 2),
        },

        # 3. Coverage Rate по доменам
        "coverage_rate": {
            d: compute_coverage_rate_for_domain(all_results, d)
            for d in QUERIES
        },

        # 4. Topic Coherence
        "topic_coherence": {
            "overall":   topic_coherence_overall,
            "by_domain": topic_coherence_by_domain,
        },
    }

    # Финальный файл
    output = {
        "summary": summary,
        "results": all_results,
    }

    with open("eval_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # ── Итоговый вывод ────────────────────────────────────────────────────────
    logger.info("\n" + "=" * 70)
    logger.info("МАШИННЫЕ МЕТРИКИ (итог)")
    logger.info("=" * 70)
    logger.info(f"Всего прогонов:              {summary['total_queries']}")
    logger.info(f"Успешных:                    {summary['successful_queries']}")
    logger.info(f"Time-to-result (среднее):    {summary['time_to_result']['mean']}с")
    logger.info(f"Time-to-result (медиана):    {summary['time_to_result']['median']}с")
    logger.info(f"Planner JSON Parse Rate:     {summary['json_parse_rates']['planner'] * 100:.1f}%")
    logger.info(f"Extractor JSON Parse Rate:   {summary['json_parse_rates']['extractor'] * 100:.1f}%")
    logger.info(f"  (статей с фактами в среднем: {summary['extractor_coverage']['mean_articles_with_facts']:.1f} / {summary['extractor_coverage']['mean_articles_total']:.1f})")
    logger.info(f"Generator JSON Parse Rate:   {summary['json_parse_rates']['generator'] * 100:.1f}%")
    for d, v in summary["coverage_rate"].items():
        logger.info(f"Coverage Rate ({d}):         {v * 100:.1f}%")
    logger.info(f"Topic Coherence (overall):   {summary['topic_coherence']['overall']:.4f}")
    for d, v in summary['topic_coherence']['by_domain'].items():
        logger.info(f"  Topic Coherence ({d}):      {v:.4f}")
    logger.info("=" * 70)
    logger.info("Результаты сохранены в eval_results.json")
    logger.info("Запустите eval_expert.html для экспертной оценки.")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())