"""
core/reranker.py — переранжирование через Cross-Encoder

Берёт топ-50 кандидатов от Retriever и переранжирует их
через Cross-Encoder модель, которая оценивает релевантность
пары (запрос, статья) совместно.

Используется в:
    - core/pipeline.py — третий шаг пайплайна
"""

import logging

import numpy as np
from sentence_transformers import CrossEncoder
import torch

logger = logging.getLogger(__name__)

_RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"
_reranker: CrossEncoder | None = None


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Загружаем Cross-Encoder: {_RERANKER_MODEL_NAME} на {device}")
        _reranker = CrossEncoder(_RERANKER_MODEL_NAME, device=device)
    return _reranker


def rerank(
    query: str,
    articles: list[dict],
    top_k: int = 20,
) -> list[dict]:
    """Переранжировать статьи по релевантности к запросу.

    Cross-Encoder оценивает каждую пару (запрос, абстракт)
    и возвращает score — чем выше, тем релевантнее.

    Args:
        query:    Исходный запрос пользователя
        articles: Список статей от Retriever
        top_k:    Количество статей на выходе

    Returns:
        Топ-K статей отсортированных по релевантности (убывание)
    """
    if not articles:
        return []

    reranker = _get_reranker()

    # Формируем пары (запрос, текст статьи) для Cross-Encoder
    pairs = [
        (query, f"{article['title']}. {article['abstract']}")
        for article in articles
    ]

    # Получаем scores для всех пар
    scores = reranker.predict(pairs)
    # Нормализуем через sigmoid -> диапазон [0, 1]
    scores = 1 / (1 + np.exp(-scores))

    # Сортируем статьи по убыванию score
    scored = sorted(
        zip(scores, articles),
        key=lambda x: x[0],
        reverse=True,
    )

    top_articles = [article for _, article in scored[:top_k]]
    logger.info(
        f"Reranker: {len(articles)} → {len(top_articles)} статей "
        f"(top score: {scored[0][0]:.3f})"
    )
    return top_articles