"""
Прогрессивный джекпот
- Часть от каждой игры идёт в общий банк
- Очень редкий шанс выиграть весь банк
- Банк отображается в меню
"""
import json
import os
import random
from datetime import datetime
from pathlib import Path

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Base


# Настройки джекпота
JACKPOT_CONTRIBUTION = 5  # Лискоинов с каждой игры в банк
JACKPOT_WIN_CHANCE = 0.001  # 0.1% шанс на джекпот (1 из 1000)
JACKPOT_MIN_POOL = 100  # Минимальный банк для розыгрыша
JACKPOT_START_POOL = 500  # Начальный банк


class FoxJackpot(Base):
    """Джекпот"""
    __tablename__ = "fox_jackpot"
    
    id = Column(Integer, primary_key=True, default=1)
    pool = Column(Integer, default=JACKPOT_START_POOL, nullable=False)  # Текущий банк
    last_winner_id = Column(BigInteger, nullable=True)  # Последний победитель
    last_win_amount = Column(Integer, nullable=True)  # Последний выигрыш
    last_win_date = Column(DateTime, nullable=True)  # Когда был выигран
    total_won = Column(Integer, default=0, nullable=False)  # Всего выиграно за всё время


class FoxJackpotWin(Base):
    """История выигрышей джекпота"""
    __tablename__ = "fox_jackpot_wins"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, nullable=False, index=True)
    amount = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


async def get_or_create_jackpot(session: AsyncSession) -> FoxJackpot:
    """Получить или создать запись джекпота"""
    from sqlalchemy import select
    
    result = await session.execute(select(FoxJackpot).where(FoxJackpot.id == 1))
    jackpot = result.scalar_one_or_none()
    
    if not jackpot:
        jackpot = FoxJackpot(id=1, pool=JACKPOT_START_POOL)
        session.add(jackpot)
        await session.commit()
    
    return jackpot


async def get_jackpot_pool(session: AsyncSession) -> int:
    """Получить текущий размер джекпота"""
    jackpot = await get_or_create_jackpot(session)
    return jackpot.pool


async def add_to_jackpot(session: AsyncSession, amount: int = JACKPOT_CONTRIBUTION) -> int:
    """Добавить в банк джекпота. Возвращает новый размер."""
    jackpot = await get_or_create_jackpot(session)
    jackpot.pool += amount
    await session.commit()
    return jackpot.pool


async def try_win_jackpot(session: AsyncSession, tg_id: int) -> int | None:
    """
    Попытаться выиграть джекпот.
    Возвращает сумму выигрыша или None.
    """
    jackpot = await get_or_create_jackpot(session)
    
    # Проверяем минимальный банк
    if jackpot.pool < JACKPOT_MIN_POOL:
        return None
    
    # Проверяем шанс
    if random.random() > JACKPOT_WIN_CHANCE:
        return None
    
    # ДЖЕКПОТ!
    win_amount = jackpot.pool
    
    # Записываем историю
    win = FoxJackpotWin(tg_id=tg_id, amount=win_amount)
    session.add(win)
    
    # Обновляем джекпот
    jackpot.pool = JACKPOT_START_POOL  # Сбрасываем банк
    jackpot.last_winner_id = tg_id
    jackpot.last_win_amount = win_amount
    jackpot.last_win_date = datetime.utcnow()
    jackpot.total_won += win_amount
    
    await session.commit()
    
    return win_amount


async def get_jackpot_info(session: AsyncSession) -> dict:
    """Получить информацию о джекпоте"""
    jackpot = await get_or_create_jackpot(session)
    
    return {
        "pool": jackpot.pool,
        "last_winner_id": jackpot.last_winner_id,
        "last_win_amount": jackpot.last_win_amount,
        "last_win_date": jackpot.last_win_date,
        "total_won": jackpot.total_won,
    }


def format_jackpot_display(pool: int) -> str:
    """Форматированное отображение джекпота для меню"""
    return f"🎰 Джекпот: <b>{pool}</b> 🦊"
