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


async def mark_prize_used(session: AsyncSession, prize_id: int) -> bool:
    """Пометить приз как использованный."""
    result = await session.execute(
        update(FoxPrize)
        .where(FoxPrize.id == prize_id)
        .values(is_used=True, used_at=datetime.utcnow())
        .returning(FoxPrize.id)
    )
    success = result.scalar_one_or_none() is not None
    await session.commit()
    if success:
        logger.info(f"[Gamification] Приз {prize_id} помечен как использованный")
    return success


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


# ==================== СДЕЛКИ С ЛИСОЙ ====================

from .models import FoxDeal


async def get_last_deal(session: AsyncSession, tg_id: int) -> FoxDeal | None:
    """Получить последнюю сделку пользователя."""
    result = await session.execute(
        select(FoxDeal)
        .where(FoxDeal.tg_id == tg_id)
        .order_by(FoxDeal.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_deal_stats(session: AsyncSession, tg_id: int) -> dict:
    """Получить статистику сделок: количество, серия побед/поражений."""
    result = await session.execute(
        select(FoxDeal)
        .where(FoxDeal.tg_id == tg_id)
        .order_by(FoxDeal.created_at.desc())
        .limit(10)  # Последние 10 сделок
    )
    deals = list(result.scalars().all())
    
    if not deals:
        return {
            "total": 0,
            "wins": 0,
            "losses": 0,
            "win_streak": 0,
            "loss_streak": 0,
            "days_since_last": None,
        }
    
    wins = sum(1 for d in deals if d.won)
    losses = len(deals) - wins
    
    # Считаем текущую серию
    win_streak = 0
    loss_streak = 0
    for d in deals:
        if d.won:
            if loss_streak == 0:
                win_streak += 1
            else:
                break
        else:
            if win_streak == 0:
                loss_streak += 1
            else:
                break
    
    # Дней с последней сделки
    last_deal = deals[0]
    days_since = (datetime.utcnow() - last_deal.created_at).days
    
    return {
        "total": len(deals),
        "wins": wins,
        "losses": losses,
        "win_streak": win_streak,
        "loss_streak": loss_streak,
        "days_since_last": days_since,
    }


async def can_make_deal(session: AsyncSession, tg_id: int) -> tuple[bool, str | None]:
    """Проверить, может ли игрок заключить сделку (1 раз в 24 часа)."""
    last_deal = await get_last_deal(session, tg_id)
    
    if last_deal is None:
        return True, None
    
    hours_since = (datetime.utcnow() - last_deal.created_at).total_seconds() / 3600
    
    if hours_since < 24:
        hours_left = int(24 - hours_since)
        return False, f"Следующая сделка через {hours_left}ч"
    
    return True, None


async def create_deal(
    session: AsyncSession,
    tg_id: int,
    stake_type: str,
    stake_value: int,
    won: bool,
    multiplier: float,
    result_value: int,
    chance_percent: int,
    fox_comment: str,
) -> FoxDeal:
    """Создать запись о сделке."""
    deal = FoxDeal(
        tg_id=tg_id,
        stake_type=stake_type,
        stake_value=stake_value,
        won=won,
        multiplier=multiplier,
        result_value=result_value,
        chance_percent=chance_percent,
        fox_comment=fox_comment,
    )
    session.add(deal)
    await session.commit()
    await session.refresh(deal)
    return deal
