"""
Функции работы с БД для модуля геймификации
"""
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from logger import logger

from .models import FoxBoost, FoxGameHistory, FoxPlayer, FoxPrize


# ==================== FoxPlayer ====================

async def get_or_create_player(session: AsyncSession, tg_id: int) -> FoxPlayer:
    """Получить или создать игрока"""
    result = await session.execute(
        select(FoxPlayer).where(FoxPlayer.tg_id == tg_id)
    )
    player = result.scalar_one_or_none()
    
    if not player:
        player = FoxPlayer(tg_id=tg_id)
        session.add(player)
        await session.commit()
        await session.refresh(player)
        logger.info(f"[Gamification] Создан игрок: {tg_id}")
    
    return player


async def get_player(session: AsyncSession, tg_id: int) -> FoxPlayer | None:
    """Получить игрока"""
    result = await session.execute(
        select(FoxPlayer).where(FoxPlayer.tg_id == tg_id)
    )
    return result.scalar_one_or_none()


async def update_player_coins(session: AsyncSession, tg_id: int, amount: int) -> int:
    """Изменить баланс Лискоинов (может быть отрицательным)"""
    result = await session.execute(
        update(FoxPlayer)
        .where(FoxPlayer.tg_id == tg_id)
        .values(coins=FoxPlayer.coins + amount, updated_at=datetime.utcnow())
        .returning(FoxPlayer.coins)
    )
    new_balance = result.scalar_one_or_none()
    await session.commit()
    return new_balance or 0


async def check_and_reset_daily_spin(session: AsyncSession, tg_id: int) -> bool:
    """
    Проверить и сбросить ежедневную попытку.
    Возвращает True, если попытка доступна.
    """
    player = await get_or_create_player(session, tg_id)
    today = datetime.utcnow().date()
    
    # Если последняя попытка была не сегодня — сбрасываем
    if player.last_free_spin_date is None or player.last_free_spin_date.date() < today:
        await session.execute(
            update(FoxPlayer)
            .where(FoxPlayer.tg_id == tg_id)
            .values(free_spins=1, last_free_spin_date=datetime.utcnow())
        )
        await session.commit()
        return True
    
    return player.free_spins > 0


async def use_free_spin(session: AsyncSession, tg_id: int) -> bool:
    """Использовать бесплатную попытку. Возвращает True если успешно."""
    result = await session.execute(
        update(FoxPlayer)
        .where(FoxPlayer.tg_id == tg_id, FoxPlayer.free_spins > 0)
        .values(free_spins=FoxPlayer.free_spins - 1)
        .returning(FoxPlayer.free_spins)
    )
    success = result.scalar_one_or_none() is not None
    await session.commit()
    return success


async def update_login_streak(session: AsyncSession, tg_id: int) -> int:
    """Обновить серию входов. Возвращает текущую серию."""
    player = await get_or_create_player(session, tg_id)
    today = datetime.utcnow().date()
    
    if player.last_login_date is None:
        new_streak = 1
    elif player.last_login_date.date() == today:
        # Уже заходил сегодня
        return player.login_streak
    elif player.last_login_date.date() == today - timedelta(days=1):
        # Вчера заходил — продолжаем серию
        new_streak = player.login_streak + 1
    else:
        # Пропустил день — серия сбрасывается
        new_streak = 1
    
    await session.execute(
        update(FoxPlayer)
        .where(FoxPlayer.tg_id == tg_id)
        .values(login_streak=new_streak, last_login_date=datetime.utcnow())
    )
    await session.commit()
    return new_streak


# ==================== FoxPrize ====================

async def add_prize(
    session: AsyncSession,
    tg_id: int,
    prize_type: str,
    value: int,
    description: str | None = None,
    expires_in_days: int = 14,
) -> FoxPrize:
    """Добавить приз пользователю"""
    # Убедимся, что игрок существует
    await get_or_create_player(session, tg_id)
    
    prize = FoxPrize(
        tg_id=tg_id,
        prize_type=prize_type,
        value=value,
        description=description,
        expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
    )
    session.add(prize)
    await session.commit()
    await session.refresh(prize)
    logger.info(f"[Gamification] Приз добавлен: {tg_id} - {prize_type}:{value}")
    return prize


async def get_active_prizes(session: AsyncSession, tg_id: int) -> list[FoxPrize]:
    """Получить активные (неиспользованные, не истёкшие) призы"""
    now = datetime.utcnow()
    result = await session.execute(
        select(FoxPrize)
        .where(
            FoxPrize.tg_id == tg_id,
            FoxPrize.is_used == False,
            FoxPrize.expires_at > now,
        )
        .order_by(FoxPrize.expires_at)
    )
    return list(result.scalars().all())


async def use_prize(session: AsyncSession, prize_id: int, tg_id: int) -> FoxPrize | None:
    """Использовать приз. Возвращает приз если успешно."""
    result = await session.execute(
        select(FoxPrize)
        .where(
            FoxPrize.id == prize_id,
            FoxPrize.tg_id == tg_id,
            FoxPrize.is_used == False,
            FoxPrize.expires_at > datetime.utcnow(),
        )
    )
    prize = result.scalar_one_or_none()
    
    if prize:
        prize.is_used = True
        prize.used_at = datetime.utcnow()
        await session.commit()
        logger.info(f"[Gamification] Приз использован: {prize_id} пользователем {tg_id}")
    
    return prize


# ==================== FoxGameHistory ====================

async def add_game_history(
    session: AsyncSession,
    tg_id: int,
    game_type: str,
    prize_type: str | None = None,
    prize_value: int | None = None,
    prize_description: str | None = None,
    boost_used: bool = False,
) -> FoxGameHistory:
    """Записать игру в историю"""
    # Обновляем статистику игрока
    await session.execute(
        update(FoxPlayer)
        .where(FoxPlayer.tg_id == tg_id)
        .values(
            total_games=FoxPlayer.total_games + 1,
            total_wins=FoxPlayer.total_wins + (1 if prize_type else 0),
        )
    )
    
    game = FoxGameHistory(
        tg_id=tg_id,
        game_type=game_type,
        prize_type=prize_type,
        prize_value=prize_value,
        prize_description=prize_description,
        boost_used=boost_used,
    )
    session.add(game)
    await session.commit()
    return game


# ==================== FoxBoost ====================

async def add_boost(
    session: AsyncSession,
    tg_id: int,
    boost_type: str,
    uses: int = 1,
    expires_in_hours: int | None = None,
) -> FoxBoost:
    """Добавить буст пользователю"""
    await get_or_create_player(session, tg_id)
    
    expires_at = None
    if expires_in_hours:
        expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
    
    boost = FoxBoost(
        tg_id=tg_id,
        boost_type=boost_type,
        uses_left=uses,
        expires_at=expires_at,
    )
    session.add(boost)
    await session.commit()
    return boost


async def get_active_boosts(session: AsyncSession, tg_id: int) -> list[FoxBoost]:
    """Получить активные бусты"""
    now = datetime.utcnow()
    result = await session.execute(
        select(FoxBoost)
        .where(
            FoxBoost.tg_id == tg_id,
            FoxBoost.uses_left > 0,
            (FoxBoost.expires_at.is_(None)) | (FoxBoost.expires_at > now),
        )
    )
    return list(result.scalars().all())


async def use_boost(session: AsyncSession, boost_id: int) -> bool:
    """Использовать буст. Возвращает True если успешно."""
    result = await session.execute(
        update(FoxBoost)
        .where(FoxBoost.id == boost_id, FoxBoost.uses_left > 0)
        .values(uses_left=FoxBoost.uses_left - 1)
        .returning(FoxBoost.uses_left)
    )
    success = result.scalar_one_or_none() is not None
    await session.commit()
    return success
