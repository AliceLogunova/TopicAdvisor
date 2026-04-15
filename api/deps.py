"""
api/deps.py — зависимости FastAPI (Depends)

Содержит переиспользуемые зависимости которые инжектируются
в эндпоинты через FastAPI Depends() механизм.

Используется в:
    - api/routers/topics.py — получение сессии БД
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость для получения сессии БД в эндпоинтах.

    Использование в роутере:
        async def endpoint(db: AsyncSession = Depends(get_db)):
            result = await db.execute(...)
    """
    async with get_session() as session:
        yield session