"""
Скрипт для начисления лискоинов игроку.
Запустить: python -m modules.gamification.add_coins
"""
import asyncio
import sys
import os

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import update
from database.db import get_session
from modules.gamification.models import FoxPlayer


async def add_coins_to_player(tg_id: int, coins: int):
    """Начислить лискоины игроку"""
    async with get_session() as session:
        # Проверяем существует ли игрок
        from sqlalchemy import select
        result = await session.execute(
            select(FoxPlayer).where(FoxPlayer.tg_id == tg_id)
        )
        player = result.scalar_one_or_none()
        
        if not player:
            # Создаём игрока если не существует
            player = FoxPlayer(tg_id=tg_id, coins=coins)
            session.add(player)
            await session.commit()
            print(f"✅ Создан новый игрок {tg_id} с {coins} лискоинами")
        else:
            # Обновляем баланс
            old_coins = player.coins
            await session.execute(
                update(FoxPlayer)
                .where(FoxPlayer.tg_id == tg_id)
                .values(coins=FoxPlayer.coins + coins)
            )
            await session.commit()
            print(f"✅ Игроку {tg_id} начислено {coins} лискоинов")
            print(f"   Было: {old_coins} → Стало: {old_coins + coins}")


if __name__ == "__main__":
    # Твой Telegram ID и количество лискоинов
    TG_ID = 1609908245
    COINS_TO_ADD = 8000
    
    print(f"🦊 Начисление {COINS_TO_ADD} лискоинов игроку {TG_ID}...")
    asyncio.run(add_coins_to_player(TG_ID, COINS_TO_ADD))
    print("✅ Готово!")

