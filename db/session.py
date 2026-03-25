"""
db/session.py — настройка подключения к PostgreSQL (SQLAlchemy async)

Этот файл создаёт асинхронный движок и фабрику сессий для работы с БД.
Все операции с базой данных выполняются через get_session() —
асинхронный контекстный менеджер который открывает и закрывает сессию.

Зависимости:
    - config.py      — читает postgres_url из .env
    - db/models.py   — использует Base для создания таблиц

Используется в:
    - api/deps.py    — FastAPI зависимость get_db()
    - data/indexer.py — запись статей и фактов в БД
    - core/pipeline.py — запись запросов и тем в БД
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings
from db.models import Base

# Асинхронный движок — главное подключение к PostgreSQL
# echo=False — не выводить SQL-запросы в консоль (True для отладки)
engine = create_async_engine(
    settings.postgres_url,
    echo=False,
)

# Фабрика сессий — создаёт новые сессии для каждого запроса
# expire_on_commit=False — объекты остаются доступны после commit()
_AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Асинхронный генератор сессий для работы с БД.
    """
    async with _AsyncSessionFactory() as session:
        try:
            yield session
            # Сохранить все изменения если не было ошибок
            await session.commit()
        except Exception:
            # Откатить все изменения если произошла ошибка
            await session.rollback()
            raise


async def create_tables() -> None:
    """Создать все таблицы в БД если они не существуют.

    Используется только при первом запуске или в тестах.
    В продакшне таблицы создаются через Alembic-миграции.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)