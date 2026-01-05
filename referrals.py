"""
Реферальная система
- Пригласи друга → получи Лискоины когда он сыграет первую игру
- Друг тоже получает бонус
"""
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import FoxPlayer


# Награды
REFERRER_BONUS = 50  # Лискоины пригласившему
REFERRED_BONUS = 25  # Лискоины приглашённому


async def set_referrer(session: AsyncSession, tg_id: int, referrer_id: int) -> bool:
    """
    Установить пригласившего для игрока.
    Возвращает True если успешно (ещё не было пригласившего).
    """
    from .db import get_or_create_player
    
    player = await get_or_create_player(session, tg_id)
    
    # Нельзя пригласить себя
    if tg_id == referrer_id:
        return False
    
    # Уже есть пригласивший
    if player.invited_by is not None:
        return False
    
    # Проверяем что referrer существует
    referrer = await get_or_create_player(session, referrer_id)
    if not referrer:
        return False
    
    # Устанавливаем связь
    player.invited_by = referrer_id
    await session.commit()
    
    return True


async def give_referral_bonus(session: AsyncSession, tg_id: int) -> dict | None:
    """
    Выдать реферальный бонус при первой игре.
    Возвращает {"referrer_id": ..., "referrer_bonus": ..., "referred_bonus": ...}
    или None если бонус уже выдан или нет реферера.
    """
    from .db import get_or_create_player, update_player_coins
    
    player = await get_or_create_player(session, tg_id)
    
    # Бонус уже выдан или нет реферера
    if player.referral_bonus_given or player.invited_by is None:
        return None
    
    referrer_id = player.invited_by
    
    # Выдаём бонус пригласившему
    await update_player_coins(session, referrer_id, REFERRER_BONUS)
    
    # Выдаём бонус приглашённому
    await update_player_coins(session, tg_id, REFERRED_BONUS)
    
    # Увеличиваем счётчик рефералов у пригласившего
    await session.execute(
        update(FoxPlayer)
        .where(FoxPlayer.tg_id == referrer_id)
        .values(total_referrals=FoxPlayer.total_referrals + 1)
    )
    
    # Помечаем что бонус выдан
    player.referral_bonus_given = True
    await session.commit()
    
    return {
        "referrer_id": referrer_id,
        "referrer_bonus": REFERRER_BONUS,
        "referred_bonus": REFERRED_BONUS,
    }


def generate_referral_link(bot_username: str, tg_id: int) -> str:
    """Сгенерировать реферальную ссылку"""
    return f"https://t.me/{bot_username}?start=ref_{tg_id}"


def parse_referral_code(start_param: str) -> int | None:
    """Извлечь tg_id из реферального кода"""
    if start_param and start_param.startswith("ref_"):
        try:
            return int(start_param[4:])
        except ValueError:
            pass
    return None
