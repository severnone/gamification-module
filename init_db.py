"""
Инициализация таблиц БД для модуля геймификации
"""
from database.db import engine
from logger import logger

from .models import (
    Base, FoxBoost, FoxGameHistory, FoxPlayer, FoxPrize,
    FoxDeal, FoxQuest, FoxCasinoSession, FoxCasinoGame, FoxCasinoProfile
)


async def init_gamification_db():
    """Создать таблицы модуля геймификации"""
    async with engine.begin() as conn:
        # Создаём только таблицы этого модуля
        # ВАЖНО: FoxCasinoSession должна быть создана ДО FoxCasinoGame из-за FK
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[
                FoxPlayer.__table__,
                FoxPrize.__table__,
                FoxGameHistory.__table__,
                FoxBoost.__table__,
                FoxDeal.__table__,
                FoxQuest.__table__,
                FoxCasinoSession.__table__,
                FoxCasinoGame.__table__,
                FoxCasinoProfile.__table__,
            ]
        )
    logger.info("[Gamification] Таблицы БД созданы/проверены")
