"""
data/cache.py — кэш-слой поверх Redis и diskcache

Отвечает за сохранение и получение промежуточных результатов:
эмбеддингов, ответов LLM и результатов поиска.
Снижает время ответа при повторных похожих запросах.

Используется в:
    - data/indexer.py  — кэш эмбеддингов при индексации
    - core/retriever.py — кэш результатов поиска
    - core/extractor.py — кэш ответов LLM Extractor
    - core/generator.py — кэш ответов LLM Generator
"""

import hashlib
import json
import logging
from typing import Any

import redis.asyncio as aioredis

from config import settings

logger = logging.getLogger(__name__)


class Cache:
    """Асинхронный кэш поверх Redis.

    Все ключи хэшируются через MD5 чтобы избежать
    проблем со спецсимволами и длинными строками.
    """

    def __init__(self) -> None:
        # Создаём асинхронный Redis-клиент из URL в настройках
        self._redis = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )

    def _make_key(self, namespace: str, value: str) -> str:
        """Создать уникальный ключ для хранения в Redis.

        Формат: namespace:md5(value)
        Например: embeddings:a1b2c3d4...
        """
        hashed = hashlib.md5(value.encode()).hexdigest()
        return f"{namespace}:{hashed}"

    async def get(self, namespace: str, key: str) -> Any | None:
        """Получить значение из кэша.

        Возвращает десериализованный объект или None если ключ не найден.
        """
        try:
            redis_key = self._make_key(namespace, key)
            value = await self._redis.get(redis_key)
            if value is None:
                return None
            return json.loads(value)
        except Exception as e:
            logger.warning(f"Ошибка чтения из кэша: {e}")
            return None

    async def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: int = 3600,
    ) -> None:
        """Сохранить значение в кэш.

        Args:
            namespace: Пространство имён (например "embeddings", "llm")
            key:       Ключ для идентификации значения
            value:     Любой JSON-сериализуемый объект
            ttl:       Время жизни в секундах (по умолчанию 1 час)
        """
        try:
            redis_key = self._make_key(namespace, key)
            serialized = json.dumps(value, ensure_ascii=False)
            await self._redis.set(redis_key, serialized, ex=ttl)
        except Exception as e:
            logger.warning(f"Ошибка записи в кэш: {e}")

    async def delete(self, namespace: str, key: str) -> None:
        """Удалить значение из кэша."""
        try:
            redis_key = self._make_key(namespace, key)
            await self._redis.delete(redis_key)
        except Exception as e:
            logger.warning(f"Ошибка удаления из кэша: {e}")

    async def close(self) -> None:
        """Закрыть соединение с Redis."""
        await self._redis.aclose()


# Глобальный экземпляр кэша — импортируется во всех модулях
cache = Cache()