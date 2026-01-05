"""
🦊 Сделка с лисой — рискованная игра на жадность
"""
import random
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from logger import logger

from .db import (
    can_make_deal,
    create_deal,
    get_deal_stats,
    get_or_create_player,
    update_player_coins,
    get_active_prizes,
)


# ==================== ФРАЗЫ ЛИСЫ ====================

# Приветственные фразы (зависят от истории)
GREETINGS = {
    "first_time": [
        "🦊 Впервые пришёл к Лисе за сделкой?\n\n<i>Рискни, если не боишься...</i>",
        "🦊 Новенький? Интересно...\n\n<i>Лиса любит смельчаков.</i>",
    ],
    "winner_returns": [
        "🦊 Снова пришёл за лёгким выигрышем?\n\n<i>Удача не вечна...</i>",
        "🦊 Победитель возвращается...\n\n<i>Жадность — грех, знаешь?</i>",
    ],
    "loser_returns": [
        "🦊 Хочешь отыграться?\n\n<i>Лиса это уважает.</i>",
        "🦊 Вернулся после поражения?\n\n<i>Храбрый выбор.</i>",
    ],
    "long_absence": [
        "🦊 Давно не виделись...\n\n<i>Соскучился по риску?</i>",
        "🦊 Ты пропал надолго.\n\n<i>Лиса ждала.</i>",
    ],
    "greedy": [
        "🦊 Опять ты?\n\n<i>Сколько можно испытывать судьбу?</i>",
        "🦊 Жадность затуманила разум?\n\n<i>Ладно, давай.</i>",
    ],
}

# Комментарии при выигрыше
WIN_COMMENTS = [
    "Ты рискнул вовремя.",
    "Лиса была в хорошем настроении.",
    "Удача на твоей стороне... пока.",
    "Смелость города берёт.",
    "Ты заслужил это.",
    "Лиса уважает смелых.",
]

# Комментарии при проигрыше
LOSE_COMMENTS = [
    "Лиса была не в настроении.",
    "Жадность наказуема.",
    "Не всегда везёт...",
    "Риск — это риск.",
    "Лиса забрала своё.",
    "В следующий раз подумай дважды.",
]

# При отказе от сделки
DECLINE_COMMENTS = [
    "🦊 Струсил? Мудрое решение.\n\n<i>Или трусливое?</i>",
    "🦊 Уходишь? Лиса запомнит.\n\n<i>Возвращайся, когда осмелеешь.</i>",
    "🦊 Благоразумие... или страх?\n\n<i>Лиса подождёт.</i>",
]


@dataclass
class DealResult:
    """Результат сделки"""
    won: bool
    stake_type: str
    stake_value: int
    multiplier: float
    result_value: int
    chance_percent: int
    fox_comment: str


def calculate_dynamic_chance(stats: dict) -> int:
    """
    Рассчитывает динамический шанс победы.
    Базовый шанс: 45%
    """
    base_chance = 45
    
    # Давно не играл → +15%
    if stats["days_since_last"] is not None and stats["days_since_last"] >= 3:
        base_chance += 15
    
    # Серия побед → обязательный откат
    if stats["win_streak"] >= 2:
        base_chance -= 20
    if stats["win_streak"] >= 3:
        base_chance -= 15  # Ещё больше
    
    # Серия поражений → жалость лисы
    if stats["loss_streak"] >= 2:
        base_chance += 10
    if stats["loss_streak"] >= 3:
        base_chance += 10  # Ещё больше
    
    # Ограничиваем от 15% до 65%
    return max(15, min(65, base_chance))


def get_multiplier() -> float:
    """Случайный множитель: x2 (85%) или x3 (15%)"""
    return 3.0 if random.random() < 0.15 else 2.0


def get_greeting(stats: dict) -> str:
    """Получить приветствие в зависимости от истории"""
    if stats["total"] == 0:
        return random.choice(GREETINGS["first_time"])
    
    if stats["days_since_last"] is not None and stats["days_since_last"] >= 7:
        return random.choice(GREETINGS["long_absence"])
    
    if stats["win_streak"] >= 2:
        return random.choice(GREETINGS["greedy"])
    
    if stats["win_streak"] >= 1:
        return random.choice(GREETINGS["winner_returns"])
    
    if stats["loss_streak"] >= 1:
        return random.choice(GREETINGS["loser_returns"])
    
    return random.choice(GREETINGS["first_time"])


async def execute_deal(
    session: AsyncSession,
    tg_id: int,
    stake_type: str,
    stake_value: int,
) -> DealResult:
    """
    Выполнить сделку с лисой.
    
    stake_type: "coins" | "vpn_days" | "spin"
    stake_value: количество
    """
    # Получаем статистику для расчёта шанса
    stats = await get_deal_stats(session, tg_id)
    
    # Рассчитываем шанс
    chance = calculate_dynamic_chance(stats)
    
    # Бросаем кости
    roll = random.randint(1, 100)
    won = roll <= chance
    
    # Множитель
    multiplier = get_multiplier() if won else 0.0
    
    # Результат
    if won:
        result_value = int(stake_value * multiplier)
        fox_comment = random.choice(WIN_COMMENTS)
    else:
        result_value = 0
        fox_comment = random.choice(LOSE_COMMENTS)
    
    # Применяем результат
    if stake_type == "coins":
        if won:
            # Выигрыш — добавляем разницу (stake уже у игрока, добавляем выигрыш)
            winnings = result_value - stake_value
            await update_player_coins(session, tg_id, winnings)
        else:
            # Проигрыш — забираем ставку
            await update_player_coins(session, tg_id, -stake_value)
    
    # Сохраняем историю сделки
    await create_deal(
        session=session,
        tg_id=tg_id,
        stake_type=stake_type,
        stake_value=stake_value,
        won=won,
        multiplier=multiplier,
        result_value=result_value,
        chance_percent=chance,
        fox_comment=fox_comment,
    )
    
    logger.info(
        f"[Deal] {tg_id}: ставка {stake_type}:{stake_value}, "
        f"шанс {chance}%, выигрыш: {won}, x{multiplier}, результат: {result_value}"
    )
    
    return DealResult(
        won=won,
        stake_type=stake_type,
        stake_value=stake_value,
        multiplier=multiplier,
        result_value=result_value,
        chance_percent=chance,
        fox_comment=fox_comment,
    )


# Минимальная ставка в Лискоинах
MIN_COINS_STAKE = 20
MAX_COINS_STAKE = 500
