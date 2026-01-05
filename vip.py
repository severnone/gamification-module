"""
VIP-статус
- +1 бесплатная попытка в день
- +10% к шансам на редкие призы
- Покупка за Свет Лисы или реальные деньги
"""
from datetime import datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from .models import FoxPlayer


# Цены VIP
VIP_PRICE_LIGHT = 50  # Свет Лисы за 7 дней
VIP_PRICE_RUB = 99  # Рублей за 7 дней

# Бонусы VIP
VIP_EXTRA_SPINS = 1  # Доп. попыток в день
VIP_LUCK_BOOST = 10  # % к шансам


async def is_vip(session: AsyncSession, tg_id: int) -> bool:
    """Проверить активен ли VIP"""
    from .db import get_or_create_player
    
    player = await get_or_create_player(session, tg_id)
    
    if not player.is_vip:
        return False
    
    # Проверяем срок
    if player.vip_expires_at and player.vip_expires_at < datetime.utcnow():
        # VIP истёк
        await session.execute(
            update(FoxPlayer)
            .where(FoxPlayer.tg_id == tg_id)
            .values(is_vip=False)
        )
        await session.commit()
        return False
    
    return True


async def get_vip_days_left(session: AsyncSession, tg_id: int) -> int:
    """Сколько дней осталось VIP"""
    from .db import get_or_create_player
    
    player = await get_or_create_player(session, tg_id)
    
    if not player.is_vip or not player.vip_expires_at:
        return 0
    
    delta = player.vip_expires_at - datetime.utcnow()
    return max(0, delta.days + 1)


async def activate_vip(session: AsyncSession, tg_id: int, days: int = 7) -> datetime:
    """Активировать VIP на N дней. Возвращает дату окончания."""
    from .db import get_or_create_player
    
    player = await get_or_create_player(session, tg_id)
    
    # Если уже есть VIP — продлеваем
    if player.is_vip and player.vip_expires_at and player.vip_expires_at > datetime.utcnow():
        new_expires = player.vip_expires_at + timedelta(days=days)
    else:
        new_expires = datetime.utcnow() + timedelta(days=days)
    
    await session.execute(
        update(FoxPlayer)
        .where(FoxPlayer.tg_id == tg_id)
        .values(is_vip=True, vip_expires_at=new_expires)
    )
    await session.commit()
    
    return new_expires


async def buy_vip_with_light(session: AsyncSession, tg_id: int) -> dict | None:
    """Купить VIP за Свет Лисы. Возвращает результат или None если не хватает."""
    from .db import get_or_create_player
    
    player = await get_or_create_player(session, tg_id)
    
    if player.light < VIP_PRICE_LIGHT:
        return None
    
    # Списываем Свет Лисы
    player.light -= VIP_PRICE_LIGHT
    await session.commit()
    
    # Активируем VIP
    expires = await activate_vip(session, tg_id, days=7)
    
    return {
        "spent": VIP_PRICE_LIGHT,
        "currency": "light",
        "days": 7,
        "expires": expires,
    }


async def buy_vip_with_balance(session: AsyncSession, tg_id: int) -> dict | None:
    """Купить VIP за реальный баланс. Возвращает результат или None."""
    from database.users import get_balance, update_balance
    
    balance = await get_balance(session, tg_id)
    
    if balance < VIP_PRICE_RUB:
        return None
    
    # Списываем с баланса
    await update_balance(session, tg_id, -VIP_PRICE_RUB)
    
    # Активируем VIP
    expires = await activate_vip(session, tg_id, days=7)
    
    return {
        "spent": VIP_PRICE_RUB,
        "currency": "rub",
        "days": 7,
        "expires": expires,
    }


def get_vip_benefits_text() -> str:
    """Текст с преимуществами VIP"""
    return f"""💎 <b>VIP-статус</b>

<b>Преимущества:</b>
• +{VIP_EXTRA_SPINS} бесплатная попытка в день
• +{VIP_LUCK_BOOST}% к шансам на редкие призы
• 🌟 Эксклюзивный статус в профиле

<b>Цена (7 дней):</b>
• {VIP_PRICE_LIGHT} ✨ Свет Лисы
• {VIP_PRICE_RUB} ₽ с баланса
"""
