import asyncio
import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Добавляем корень проекта в sys.path чтобы импортировать модули
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from config import settings
from db.models import Base

# Конфиг Alembic
config = context.config

# Подставляем URL из нашего settings вместо alembic.ini
config.set_main_option("sqlalchemy.url", settings.postgres_url)

# Настройка логирования
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные моделей — Alembic смотрит сюда чтобы найти таблицы
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Режим offline — генерирует SQL без подключения к БД."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Режим online — подключается к БД и применяет миграции."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    import asyncio
    # Фикс для Windows — asyncpg не работает с ProactorEventLoop
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()