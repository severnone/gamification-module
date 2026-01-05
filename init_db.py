"""
Инициализация таблиц БД для модуля геймификации
"""
from database.db import engine
from logger import logger

from .models import Base, FoxBoost, FoxGameHistory, FoxPlayer, FoxPrize


async def init_gamification_db():
    """Создать таблицы модуля геймификации"""
    async with engine.begin() as conn:
        # Создаём только таблицы этого модуля
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                FoxPlayer.__table__,
                FoxPrize.__table__,
                FoxGameHistory.__table__,
                FoxBoost.__table__,
            ]
        )
    logger.info("[Gamification] Таблицы БД созданы/проверены")
