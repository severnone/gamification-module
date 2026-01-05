"""
Уведомления для игроков
- Ежедневная попытка восстановилась
- Напоминание неактивным
- Бонус за возвращение
"""
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import FoxPlayer

if TYPE_CHECKING:
    from aiogram import Bot


# Тексты уведомлений
NOTIFY_DAILY_SPIN = """🦊 <b>Твоя ежедневная попытка восстановилась!</b>

🎰 Заходи в Логово Лисы и испытай удачу!

/start → Профиль → 🦊 Логово Лисы
"""

NOTIFY_INACTIVE_3_DAYS = """🦊 <b>Лиса скучает по тебе!</b>

Ты не заходил {days} дней. Вот тебе подарок — <b>+20 Лискоинов</b>! 🦊

Заходи и забери награду!

/start → Профиль → 🦊 Логово Лисы
"""

NOTIFY_INACTIVE_7_DAYS = """🦊 <b>Лиса очень скучает!</b>

Прошла целая неделя! Специально для тебя — <b>+50 Лискоинов и бесплатная попытка</b>! 🎁

/start → Профиль → 🦊 Логово Лисы
"""


async def get_inactive_players(
    session: AsyncSession, 
    days: int = 3,
    limit: int = 100,
) -> list[FoxPlayer]:
    """Получить игроков, которые не заходили N дней"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    result = await session.execute(
        select(FoxPlayer)
        .where(
            FoxPlayer.last_login_date < cutoff,
            FoxPlayer.last_login_date.isnot(None),
        )
        .limit(limit)
    )
    
    return list(result.scalars().all())


async def get_players_for_daily_notify(
    session: AsyncSession,
    limit: int = 100,
) -> list[FoxPlayer]:
    """
    Получить игроков, которым нужно отправить уведомление о восстановлении попытки.
    (Заходили вчера, но ещё не сегодня)
    """
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    
    result = await session.execute(
        select(FoxPlayer)
        .where(
            FoxPlayer.last_login_date >= datetime.combine(yesterday, datetime.min.time()),
            FoxPlayer.last_login_date < datetime.combine(today, datetime.min.time()),
        )
        .limit(limit)
    )
    
    return list(result.scalars().all())


async def send_notification(bot: "Bot", tg_id: int, text: str) -> bool:
    """Отправить уведомление пользователю"""
    try:
        await bot.send_message(tg_id, text)
        return True
    except Exception:
        return False


async def send_daily_notifications(bot: "Bot", session: AsyncSession):
    """Отправить уведомления о восстановлении попытки"""
    players = await get_players_for_daily_notify(session)
    
    sent = 0
    for player in players:
        if await send_notification(bot, player.tg_id, NOTIFY_DAILY_SPIN):
            sent += 1
    
    return sent


async def send_inactive_notifications(bot: "Bot", session: AsyncSession):
    """Отправить уведомления неактивным игрокам"""
    from .db import update_player_coins, add_paid_spin
    
    # 3 дня неактивности
    players_3d = await get_inactive_players(session, days=3, limit=50)
    sent_3d = 0
    for player in players_3d:
        text = NOTIFY_INACTIVE_3_DAYS.format(days=3)
        if await send_notification(bot, player.tg_id, text):
            # Даём бонус
            await update_player_coins(session, player.tg_id, 20)
            sent_3d += 1
    
    # 7 дней неактивности
    players_7d = await get_inactive_players(session, days=7, limit=50)
    sent_7d = 0
    for player in players_7d:
        text = NOTIFY_INACTIVE_7_DAYS
        if await send_notification(bot, player.tg_id, text):
            # Даём бонус
            await update_player_coins(session, player.tg_id, 50)
            await add_paid_spin(session, player.tg_id, 1)
            sent_7d += 1
    
    return {"3d": sent_3d, "7d": sent_7d}
