"""
Игровая механика "Испытать удачу"
"""
import asyncio
import random
from dataclasses import dataclass

from aiogram.types import Message
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


# ==================== СИМВОЛЫ ДЛЯ СЛОТОВ ====================

SLOT_SYMBOLS = ["🦊", "💎", "🦊", "🔮", "⭐", "💰", "🎁", "❌"]

# Веса символов (чем меньше вес, тем реже выпадает)
SYMBOL_WEIGHTS = {
    "🦊": 5,   # Лиса - редкий (джекпот если 3)
    "💎": 8,   # Алмаз - редкий
    "🔮": 10,  # Клевер - необычный
    "⭐": 12,  # Звезда - необычный
    "💰": 15,  # Деньги - обычный
    "🦊": 18,  # Монета - обычный
    "🎁": 12,  # Подарок - необычный
    "❌": 20,  # Пусто - частый
}


@dataclass
class Prize:
    """Структура приза"""
    prize_type: str  # "vpn_days", "coins", "balance", "empty", "boost"
    value: int
    description: str
    rarity: str  # "common", "uncommon", "rare", "epic", "legendary"
    emoji: str


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


# ==================== ОПРЕДЕЛЕНИЕ ПРИЗА ПО КОМБИНАЦИИ ====================

def get_prize_for_combination(symbols: list[str], boost_percent: int = 0) -> Prize:
    """
    Определяет приз на основе выпавших символов.
    3 одинаковых = джекпот
    2 одинаковых = средний приз
    Все разные = маленький приз или ничего
    """
    s1, s2, s3 = symbols
    
    # Считаем одинаковые символы
    if s1 == s2 == s3:
        # ТРИ ОДИНАКОВЫХ - ДЖЕКПОТ!
        return get_jackpot_prize(s1, boost_percent)
    
    elif s1 == s2 or s2 == s3 or s1 == s3:
        # ДВА ОДИНАКОВЫХ - средний приз
        matching = s1 if s1 == s2 or s1 == s3 else s2
        return get_double_prize(matching, boost_percent)
    
    else:
        # ВСЕ РАЗНЫЕ
        # 70% - ничего, 30% - мелкий приз
        if random.random() < 0.70:
            return Prize("empty", 0, "Ничего не выпало", "common", "❌")
        else:
            return Prize("coins", random.choice([5, 10]), f"+{random.choice([5, 10])} Лискоинов", "common", "🦊")


def get_jackpot_prize(symbol: str, boost_percent: int = 0) -> Prize:
    """Приз за 3 одинаковых символа"""
    
    # Буст увеличивает ценность приза
    multiplier = 1 + (boost_percent / 100)
    
    if symbol == "🦊":
        # ТРИ ЛИСЫ - ЛЕГЕНДАРНЫЙ ДЖЕКПОТ!
        return Prize("vpn_days", 60, "+60 дней VPN!", "legendary", "🦊")
    
    elif symbol == "💎":
        # Три алмаза
        days = int(30 * multiplier)
        return Prize("vpn_days", days, f"+{days} дней VPN!", "epic", "💎")
    
    elif symbol == "🔮":
        # Три клевера - буст удачи
        return Prize("boost", 30, "Буст удачи +30%!", "epic", "🔮")
    
    elif symbol == "⭐":
        # Три звезды
        days = int(14 * multiplier)
        return Prize("vpn_days", days, f"+{days} дней VPN!", "rare", "⭐")
    
    elif symbol == "💰":
        # Три мешка денег - рубли на баланс
        return Prize("balance", 50, "+25₽ на баланс!", "legendary", "💰")
    
    elif symbol == "🦊":
        # Три монеты
        coins = int(100 * multiplier)
        return Prize("coins", coins, f"+{coins} Лискоинов!", "rare", "🦊")
    
    elif symbol == "🎁":
        # Три подарка
        days = int(7 * multiplier)
        return Prize("vpn_days", days, f"+{days} дней VPN!", "rare", "🎁")
    
    elif symbol == "❌":
        # Три креста - ничего, но даём утешительные монеты
        return Prize("coins", 15, "+15 Лискоинов (утешительный)", "common", "❌")
    
    return Prize("coins", 50, "+50 Лискоинов", "uncommon", "🦊")


def get_double_prize(symbol: str, boost_percent: int = 0) -> Prize:
    """Приз за 2 одинаковых символа"""
    
    multiplier = 1 + (boost_percent / 100)
    
    if symbol == "🦊":
        days = int(7 * multiplier)
        return Prize("vpn_days", days, f"+{days} дней VPN", "rare", "🦊")
    
    elif symbol == "💎":
        days = int(5 * multiplier)
        return Prize("vpn_days", days, f"+{days} дней VPN", "uncommon", "💎")
    
    elif symbol == "🔮":
        return Prize("boost", 10, "Буст удачи +10%", "uncommon", "🔮")
    
    elif symbol == "⭐":
        days = int(3 * multiplier)
        return Prize("vpn_days", days, f"+{days} дней VPN", "uncommon", "⭐")
    
    elif symbol == "💰":
        coins = int(50 * multiplier)
        return Prize("coins", coins, f"+{coins} Лискоинов", "uncommon", "💰")
    
    elif symbol == "🦊":
        coins = int(25 * multiplier)
        return Prize("coins", coins, f"+{coins} Лискоинов", "common", "🦊")
    
    elif symbol == "🎁":
        return Prize("vpn_days", 1, "+1 день VPN", "common", "🎁")
    
    elif symbol == "❌":
        return Prize("empty", 0, "Почти повезло...", "common", "❌")
    
    return Prize("coins", 15, "+15 Лискоинов", "common", "🦊")


def roll_symbol() -> str:
    """Случайный выбор символа с учётом весов"""
    symbols = list(SYMBOL_WEIGHTS.keys())
    weights = list(SYMBOL_WEIGHTS.values())
    return random.choices(symbols, weights=weights, k=1)[0]


def roll_slots() -> list[str]:
    """Крутим 3 барабана"""
    return [roll_symbol() for _ in range(3)]


# ==================== АНИМАЦИЯ ====================

async def animate_slots(message: Message, final_symbols: list[str]) -> None:
    """Анимация слотов — простая и красивая"""
    
    random_symbols = list(SYMBOL_WEIGHTS.keys())
    
    # Фаза 1: Все крутятся
    await message.edit_text(
        "🎰 <b>СЛОТЫ</b>\n\n"
        "[ ❓ ] [ ❓ ] [ ❓ ]\n\n"
        "🔥 <i>Барабаны раскручиваются...</i>"
    )
    await asyncio.sleep(1.0)
    
    # Фаза 2: Мелькают случайные символы
    for _ in range(4):
        s1, s2, s3 = random.choices(random_symbols, k=3)
        await message.edit_text(
            "🎰 <b>СЛОТЫ</b>\n\n"
            f"[ {s1} ] [ {s2} ] [ {s3} ]\n\n"
            "🎲 <i>Крутятся...</i>"
        )
        await asyncio.sleep(0.35)
    
    # Фаза 3: Первый остановился
    await message.edit_text(
        "🎰 <b>СЛОТЫ</b>\n\n"
        f"[ {final_symbols[0]} ] [ ❓ ] [ ❓ ]\n\n"
        "⏳ <i>Первый...</i>"
    )
    await asyncio.sleep(0.9)
    
    # Фаза 4: Второй остановился
    await message.edit_text(
        "🎰 <b>СЛОТЫ</b>\n\n"
        f"[ {final_symbols[0]} ] [ {final_symbols[1]} ] [ ❓ ]\n\n"
        "⏳ <i>Второй...</i>"
    )
    await asyncio.sleep(1.0)
    
    # Фаза 5: Последний
    await message.edit_text(
        "🎰 <b>СЛОТЫ</b>\n\n"
        f"[ {final_symbols[0]} ] [ {final_symbols[1]} ] [ ❓ ]\n\n"
        "🤞 <i>Последний...</i>"
    )
    await asyncio.sleep(1.2)


async def animate_chest_opening(message: Message, chosen_chest: int) -> None:
    """Анимация открытия выбранного сундука — простая"""
    
    chest_num = chosen_chest + 1
    
    # Фаза 1: Выбор сделан
    await message.edit_text(
        f"📦 <b>СУНДУКИ ЛИСЫ</b>\n\n"
        f"Ты выбрал сундук <b>№{chest_num}</b>!\n\n"
        f"🔒 Сундук закрыт...\n\n"
        "<i>Открываем...</i>"
    )
    await asyncio.sleep(1.0)
    
    # Фаза 2: Открывается
    await message.edit_text(
        f"📦 <b>СУНДУКИ ЛИСЫ</b>\n\n"
        f"Сундук <b>№{chest_num}</b>\n\n"
        f"🔓 Замок щёлкает...\n\n"
        "<i>Что внутри?</i>"
    )
    await asyncio.sleep(0.8)
    
    # Фаза 3: Сияние
    await message.edit_text(
        f"📦 <b>СУНДУКИ ЛИСЫ</b>\n\n"
        f"Сундук <b>№{chest_num}</b>\n\n"
        f"✨ Сияние изнутри! ✨\n\n"
        "<i>Смотрим приз...</i>"
    )
    await asyncio.sleep(1.0)


async def animate_wheel(message: Message, final_sector: int) -> None:
    """Анимация колеса удачи — простая"""
    
    # Секторы колеса
    sectors = ["🦊", "💎", "🦊", "🔮", "⭐", "💰", "🎁", "❌"]
    
    # Фаза 1: Начало
    await message.edit_text(
        "🎡 <b>КОЛЕСО УДАЧИ</b>\n\n"
        "🦊 Лиса крутит колесо...\n\n"
        "⏳ <i>Раскручивается...</i>"
    )
    await asyncio.sleep(1.0)
    
    # Фаза 2: Крутится — показываем мелькающие символы
    spin_count = 8 + random.randint(0, 4)
    
    for i in range(spin_count):
        current = sectors[i % len(sectors)]
        
        if i < 3:
            status = "🔥 Быстро!"
            delay = 0.25
        elif i < 6:
            status = "💨 Крутится..."
            delay = 0.4
        else:
            status = "⏳ Замедляется..."
            delay = 0.5 + (i - 6) * 0.2
        
        await message.edit_text(
            "🎡 <b>КОЛЕСО УДАЧИ</b>\n\n"
            f"➤ {current} ◀\n\n"
            f"<i>{status}</i>"
        )
        await asyncio.sleep(min(delay, 0.9))
    
    # Фаза 3: Останавливается
    final_symbol = sectors[final_sector % len(sectors)]
    await message.edit_text(
        "🎡 <b>КОЛЕСО УДАЧИ</b>\n\n"
        f"🎯 ➤ {final_symbol} ◀ 🎯\n\n"
        "<i>Колесо остановилось!</i>"
    )
    await asyncio.sleep(1.0)


# ==================== ОСНОВНАЯ ИГРА ====================

async def play_game(
    session: AsyncSession,
    tg_id: int,
    use_coins: bool = False,
    message: Message = None,
    game_type: str = None,
    test_mode: bool = False,
    chosen_chest: int = None,
) -> dict:
    """
    Основная функция игры.
    
    game_type: "slots", "chest", "wheel" или None (случайный)
    test_mode: если True - бесконечные попытки для тестирования
    chosen_chest: индекс выбранного сундука (0, 1, 2) для игры с сундуками
    """
    player = await get_or_create_player(session, tg_id)
    
    # Проверяем и сбрасываем ежедневную попытку
    await check_and_reset_daily_spin(session, tg_id)
    
    # Обновляем данные игрока
    player = await get_or_create_player(session, tg_id)
    
    coins_spent = 0
    
    # В тестовом режиме пропускаем проверку попыток
    if test_mode:
        pass  # Бесконечные попытки
    elif player.free_spins > 0 or player.paid_spins > 0:
        # Используем попытку (сначала бесплатные, потом купленные)
        from .db import use_spin
        success, spin_type = await use_spin(session, tg_id)
        if not success:
            return {
                "success": False,
                "error": "Не удалось использовать попытку.",
                "game_type": None,
                "prize": None,
                "symbols": None,
                "coins_spent": 0,
                "new_balance": player.coins,
            }
    elif use_coins:
        if player.coins < SPIN_COST_COINS:
            return {
                "success": False,
                "error": f"Недостаточно Лискоинов. Нужно {SPIN_COST_COINS}, у вас {player.coins}.",
                "game_type": None,
                "prize": None,
                "symbols": None,
                "coins_spent": 0,
                "new_balance": player.coins,
            }
        
        new_balance = await update_player_coins(session, tg_id, -SPIN_COST_COINS)
        coins_spent = SPIN_COST_COINS
    else:
        return {
            "success": False,
            "error": "no_spins",
            "game_type": None,
            "prize": None,
            "symbols": None,
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
    
    # Бонус счастливого часа
    from .events import get_happy_hour_boost
    boost_percent += get_happy_hour_boost()
    
    # Выбираем тип игры
    if game_type is None:
        game_type = random.choice(["slots", "chest", "wheel"])
    
    # Крутим символы
    symbols = roll_slots()
    
    # Параметры для анимаций
    chest_index = chosen_chest if chosen_chest is not None else random.randint(0, 2)
    wheel_sector = random.randint(0, 7)
    
    # Анимация (если есть сообщение)
    if message:
        try:
            if game_type == "slots":
                await animate_slots(message, symbols)
            elif game_type == "chest":
                await animate_chest_opening(message, chest_index)
            elif game_type == "wheel":
                await animate_wheel(message, wheel_sector)
        except Exception as e:
            logger.warning(f"[Gamification] Ошибка анимации: {e}")
    
    # Определяем приз
    prize = get_prize_for_combination(symbols, boost_percent)
    
    # Применяем приз
    if prize.prize_type == "coins":
        new_balance = await update_player_coins(session, tg_id, prize.value)
    elif prize.prize_type == "empty":
        player = await get_or_create_player(session, tg_id)
        new_balance = player.coins
    elif prize.prize_type == "boost":
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
    
    # Обновляем квесты
    try:
        from .quests import update_quest_progress, QuestType
        
        # Квест "сыграть игру"
        await update_quest_progress(session, tg_id, QuestType.PLAY_GAME)
        
        # Квест "сыграть 3 игры"
        await update_quest_progress(session, tg_id, QuestType.PLAY_3_GAMES)
        
        # Квест "выиграть" (если не пустышка)
        if prize.prize_type != "empty":
            await update_quest_progress(session, tg_id, QuestType.WIN_GAME)
    except Exception as e:
        logger.warning(f"[Gamification] Ошибка обновления квестов: {e}")
    
    # Реферальный бонус при первой игре
    try:
        from .referrals import give_referral_bonus
        ref_result = await give_referral_bonus(session, tg_id)
        if ref_result:
            logger.info(f"[Gamification] Реф бонус: {tg_id} от {ref_result['referrer_id']}")
    except Exception as e:
        logger.warning(f"[Gamification] Ошибка реферального бонуса: {e}")
    
    # Прогрессивный джекпот
    jackpot_win = None
    try:
        from .jackpot import add_to_jackpot, try_win_jackpot
        
        # Добавляем в банк
        await add_to_jackpot(session)
        
        # Проверяем на выигрыш джекпота
        jackpot_win = await try_win_jackpot(session, tg_id)
        if jackpot_win:
            # Выдаём джекпот
            await update_player_coins(session, tg_id, jackpot_win)
            player = await get_or_create_player(session, tg_id)
            new_balance = player.coins
            logger.info(f"[Gamification] 🎰 ДЖЕКПОТ! {tg_id} выиграл {jackpot_win} 🦊")
    except Exception as e:
        logger.warning(f"[Gamification] Ошибка джекпота: {e}")
    
    logger.info(
        f"[Gamification] Игра {tg_id}: {game_type} [{symbols}] -> {prize.rarity} {prize.prize_type}:{prize.value}"
    )
    
    return {
        "success": True,
        "error": None,
        "game_type": game_type,
        "prize": prize,
        "symbols": symbols,
        "coins_spent": coins_spent,
        "new_balance": new_balance,
        "jackpot_win": jackpot_win,
    }


def format_prize_message(game_type: str, prize: Prize, symbols: list[str], coins_spent: int, new_balance: int) -> str:
    """Форматирует сообщение о выигрыше — уникальный стиль для каждой игры"""
    
    rarity_color = RARITY_COLORS.get(prize.rarity, "⚪")
    rarity_name = RARITY_NAMES.get(prize.rarity, "Обычный")
    
    # Заголовок в зависимости от редкости
    if prize.rarity == "legendary":
        header = "🌟✨🌟 ЛЕГЕНДАРНЫЙ ДЖЕКПОТ! 🌟✨🌟"
    elif prize.rarity == "epic":
        header = "🎊 ЭПИЧЕСКИЙ ВЫИГРЫШ! 🎊"
    elif prize.rarity == "rare":
        header = "🎉 Редкий выигрыш!"
    elif prize.rarity == "uncommon":
        header = "✨ Неплохо!"
    else:
        if prize.prize_type == "empty":
            header = "😔 Не повезло..."
        else:
            header = "👍 Результат"
    
    # УНИКАЛЬНОЕ отображение для каждой игры (простое, без ASCII-арта)
    if game_type == "slots":
        s1, s2, s3 = symbols
        game_display = (
            f"🎰 <b>СЛОТЫ</b>\n\n"
            f"[ {s1} ] [ {s2} ] [ {s3} ]"
        )
    elif game_type == "chest":
        game_display = (
            f"📦 <b>СУНДУКИ ЛИСЫ</b>\n\n"
            f"🎁 Открыт сундук → {prize.emoji}"
        )
    elif game_type == "wheel":
        game_display = (
            f"🎡 <b>КОЛЕСО УДАЧИ</b>\n\n"
            f"🎯 Выпало → {prize.emoji}"
        )
    else:
        game_display = f"🎮 Игра"
    
    message = f"<b>{header}</b>\n\n{game_display}\n\n"
    
    # Информация о призе
    if prize.prize_type != "empty" or prize.value > 0:
        message += f"{rarity_color} <b>{rarity_name}</b>\n"
        message += f"{prize.emoji} <b>{prize.description}</b>\n\n"
    else:
        message += "🦊 <i>Лиса ушла с пустыми лапами...</i>\n\n"
    
    if prize.prize_type in ("vpn_days", "balance"):
        message += "📦 <i>Приз сохранён в «Мои призы»</i>\n\n"
    
    if coins_spent > 0:
        message += f"💸 Потрачено: {coins_spent} Лискоинов\n"
    
    message += f"🦊 Баланс: <b>{new_balance}</b> Лискоинов"
    
    return message
