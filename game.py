"""
Игровая механика "Испытать удачу"
"""
import random
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from logger import logger

from .db import (
    add_game_history,
    add_prize,
    check_and_reset_daily_spin,
    get_active_boosts,
    get_or_create_player,
    update_player_coins,
    use_boost,
    use_free_spin,
)


# Типы игр (визуально разные, логика одна)
GAME_TYPES = ["wheel", "chest", "cards"]

# Эмодзи для игр
GAME_EMOJI = {
    "wheel": "🎡",
    "chest": "📦",
    "cards": "🃏",
}

GAME_NAMES = {
    "wheel": "Колесо удачи",
    "chest": "Сундук Лисы",
    "cards": "Карты судьбы",
}


@dataclass
class Prize:
    """Структура приза"""
    prize_type: str  # "vpn_days", "coins", "balance", "empty", "boost"
    value: int
    description: str
    rarity: str  # "common", "uncommon", "rare", "epic", "legendary"
    emoji: str


# Таблица призов с вероятностями
# Формат: (prize_type, value, description, rarity, emoji, weight)
PRIZE_TABLE = [
    # Пустышки (~15%)
    ("empty", 5, "Лиса убежала, но оставила 5 монет", "common", "🦊", 15),
    
    # Мелкие (~50%)
    ("coins", 10, "+10 Лискоинов", "common", "🪙", 20),
    ("coins", 15, "+15 Лискоинов", "common", "🪙", 15),
    ("coins", 25, "+25 Лискоинов", "common", "🪙", 10),
    ("vpn_days", 1, "+1 день VPN", "common", "📅", 5),
    
    # Средние (~25%)
    ("coins", 50, "+50 Лискоинов", "uncommon", "💰", 8),
    ("vpn_days", 3, "+3 дня VPN", "uncommon", "📅", 7),
    ("vpn_days", 5, "+5 дней VPN", "uncommon", "📅", 5),
    ("boost", 10, "Буст удачи +10%", "uncommon", "🍀", 5),
    
    # Редкие (~8%)
    ("coins", 100, "+100 Лискоинов", "rare", "💎", 3),
    ("vpn_days", 7, "+7 дней VPN", "rare", "🎁", 3),
    ("vpn_days", 14, "+14 дней VPN", "rare", "🎁", 2),
    
    # Эпические (~1.5%)
    ("coins", 200, "+200 Лискоинов", "epic", "👑", 0.8),
    ("vpn_days", 30, "+30 дней VPN", "epic", "🏆", 0.5),
    ("boost", 30, "Буст удачи +30%", "epic", "✨", 0.2),
    
    # Легендарные (~0.5%)
    ("balance", 50, "+25₽ на баланс", "legendary", "💸", 0.3),
    ("vpn_days", 60, "+60 дней VPN", "legendary", "👑", 0.2),
]

# Цвета редкости для отображения
RARITY_COLORS = {
    "common": "⚪",
    "uncommon": "🟢",
    "rare": "🔵",
    "epic": "🟣",
    "legendary": "🟡",
}

RARITY_NAMES = {
    "common": "Обычный",
    "uncommon": "Необычный",
    "rare": "Редкий",
    "epic": "Эпический",
    "legendary": "Легендарный",
}

# Стоимость попытки в Лискоинах
SPIN_COST_COINS = 30


def calculate_total_weight(boost_percent: int = 0) -> list[tuple]:
    """
    Рассчитывает веса с учётом буста.
    Буст увеличивает шанс редких призов.
    """
    adjusted_table = []
    
    for item in PRIZE_TABLE:
        prize_type, value, desc, rarity, emoji, weight = item
        
        # Буст увеличивает шанс редких+ призов
        if boost_percent > 0 and rarity in ("rare", "epic", "legendary"):
            weight = weight * (1 + boost_percent / 100)
        
        adjusted_table.append((prize_type, value, desc, rarity, emoji, weight))
    
    return adjusted_table


def roll_prize(boost_percent: int = 0) -> Prize:
    """Случайный выбор приза"""
    table = calculate_total_weight(boost_percent)
    
    total_weight = sum(item[5] for item in table)
    roll = random.uniform(0, total_weight)
    
    cumulative = 0
    for prize_type, value, desc, rarity, emoji, weight in table:
        cumulative += weight
        if roll <= cumulative:
            return Prize(
                prize_type=prize_type,
                value=value,
                description=desc,
                rarity=rarity,
                emoji=emoji,
            )
    
    # Fallback (не должен срабатывать)
    return Prize("coins", 10, "+10 Лискоинов", "common", "🪙")


async def play_game(
    session: AsyncSession,
    tg_id: int,
    use_coins: bool = False,
) -> dict:
    """
    Основная функция игры.
    
    Returns:
        dict с полями:
        - success: bool
        - error: str | None
        - game_type: str
        - prize: Prize | None
        - coins_spent: int
        - new_balance: int
    """
    player = await get_or_create_player(session, tg_id)
    
    # Проверяем и сбрасываем ежедневную попытку
    await check_and_reset_daily_spin(session, tg_id)
    
    # Обновляем данные игрока
    player = await get_or_create_player(session, tg_id)
    
    coins_spent = 0
    
    # Проверяем, есть ли попытка
    if player.free_spins > 0:
        # Используем бесплатную попытку
        success = await use_free_spin(session, tg_id)
        if not success:
            return {
                "success": False,
                "error": "Не удалось использовать попытку. Попробуйте снова.",
                "game_type": None,
                "prize": None,
                "coins_spent": 0,
                "new_balance": player.coins,
            }
    elif use_coins:
        # Платим Лискоинами
        if player.coins < SPIN_COST_COINS:
            return {
                "success": False,
                "error": f"Недостаточно Лискоинов. Нужно {SPIN_COST_COINS}, у вас {player.coins}.",
                "game_type": None,
                "prize": None,
                "coins_spent": 0,
                "new_balance": player.coins,
            }
        
        new_balance = await update_player_coins(session, tg_id, -SPIN_COST_COINS)
        coins_spent = SPIN_COST_COINS
    else:
        return {
            "success": False,
            "error": "no_spins",  # Специальный код - нет попыток
            "game_type": None,
            "prize": None,
            "coins_spent": 0,
            "new_balance": player.coins,
        }
    
    # Проверяем активные бусты
    boost_percent = 0
    boosts = await get_active_boosts(session, tg_id)
    for boost in boosts:
        if boost.boost_type.startswith("luck_"):
            try:
                boost_percent += int(boost.boost_type.split("_")[1])
                await use_boost(session, boost.id)
            except (ValueError, IndexError):
                pass
    
    # Выбираем случайный тип игры
    game_type = random.choice(GAME_TYPES)
    
    # Крутим приз
    prize = roll_prize(boost_percent)
    
    # Применяем приз
    if prize.prize_type == "coins" or prize.prize_type == "empty":
        # Монеты начисляем сразу
        new_balance = await update_player_coins(session, tg_id, prize.value)
    elif prize.prize_type == "boost":
        # Бусты тоже применяем сразу
        from .db import add_boost
        await add_boost(session, tg_id, f"luck_{prize.value}", uses=1)
        player = await get_or_create_player(session, tg_id)
        new_balance = player.coins
    else:
        # VPN дни и баланс сохраняем как призы
        await add_prize(
            session=session,
            tg_id=tg_id,
            prize_type=prize.prize_type,
            value=prize.value,
            description=prize.description,
        )
        player = await get_or_create_player(session, tg_id)
        new_balance = player.coins
    
    # Записываем в историю
    await add_game_history(
        session=session,
        tg_id=tg_id,
        game_type=game_type,
        prize_type=prize.prize_type,
        prize_value=prize.value,
        prize_description=prize.description,
        boost_used=boost_percent > 0,
    )
    
    logger.info(
        f"[Gamification] Игра {tg_id}: {game_type} -> {prize.rarity} {prize.prize_type}:{prize.value}"
    )
    
    return {
        "success": True,
        "error": None,
        "game_type": game_type,
        "prize": prize,
        "coins_spent": coins_spent,
        "new_balance": new_balance,
    }


def format_prize_message(game_type: str, prize: Prize, coins_spent: int, new_balance: int) -> str:
    """Форматирует сообщение о выигрыше"""
    game_emoji = GAME_EMOJI.get(game_type, "🎰")
    game_name = GAME_NAMES.get(game_type, "Игра")
    rarity_color = RARITY_COLORS.get(prize.rarity, "⚪")
    rarity_name = RARITY_NAMES.get(prize.rarity, "Обычный")
    
    # Анимация в зависимости от редкости
    if prize.rarity == "legendary":
        header = "🌟✨🌟 ЛЕГЕНДАРНЫЙ ВЫИГРЫШ! 🌟✨🌟"
    elif prize.rarity == "epic":
        header = "🎊 ЭПИЧЕСКИЙ ВЫИГРЫШ! 🎊"
    elif prize.rarity == "rare":
        header = "🎉 Редкий выигрыш!"
    else:
        header = f"{game_emoji} {game_name}"
    
    message = f"""<b>{header}</b>

{rarity_color} <b>{rarity_name}</b>

{prize.emoji} <b>{prize.description}</b>

"""
    
    if prize.prize_type in ("vpn_days", "balance"):
        message += "📦 <i>Приз сохранён в «Мои призы»</i>\n\n"
    
    if coins_spent > 0:
        message += f"💸 Потрачено: {coins_spent} Лискоинов\n"
    
    message += f"🪙 Баланс: <b>{new_balance}</b> Лискоинов"
    
    return message
