from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from handlers.utils import edit_or_send_message
from hooks.hooks import register_hook
from logger import logger

from .db import get_active_prizes, get_or_create_player, check_and_reset_daily_spin
from .game import SPIN_COST_COINS, format_prize_message, play_game
from .keyboards import build_fox_den_menu, build_try_luck_menu
from .texts import (
    BTN_BACK,
    FOX_DEN_BUTTON,
)

# Путь к картинке Логова Лисы
from pathlib import Path
FOX_DEN_IMAGE = str(Path(__file__).parent.parent.parent / "img" / "fox_den.jpg")


router = Router(name="gamification")

# Флаг инициализации БД
_db_initialized = False


async def ensure_db():
    """Ленивая инициализация таблиц БД"""
    global _db_initialized
    if not _db_initialized:
        from .init_db import init_gamification_db
        await init_gamification_db()
        _db_initialized = True


def build_back_to_den_kb() -> InlineKeyboardMarkup:
    """Кнопка назад в Логово"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    return builder.as_markup()


# === РЕЖИМ ТЕСТИРОВАНИЯ (True = бесконечные попытки) ===
TEST_MODE = False

# === РЕЖИМ ДОРАБОТКИ (True = только админы могут войти) ===
MAINTENANCE_MODE = True
ADMIN_IDS = [1609908245, 447153213, 8064244577]  # Telegram ID администраторов модуля


def build_game_select_kb() -> InlineKeyboardMarkup:
    """Клавиатура выбора игры"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="🎰 Слоты", callback_data="fox_play_slots"),
        InlineKeyboardButton(text="🎡 Колесо", callback_data="fox_play_wheel"),
    )
    builder.row(
        InlineKeyboardButton(text="🦊 Сделка с лисой", callback_data="fox_deal"),
    )
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    return builder.as_markup()


def build_after_game_kb(game_type: str = "slots") -> InlineKeyboardMarkup:
    """Клавиатура после игры"""
    builder = InlineKeyboardBuilder()
    
    # Кнопка повторить ту же игру
    game_buttons = {
        "slots": ("🎰 Ещё раз!", "fox_play_slots"),
        "wheel": ("🎡 Ещё раз!", "fox_play_wheel"),
    }
    btn_text, callback = game_buttons.get(game_type, ("🎰 Ещё раз!", "fox_play_slots"))
    builder.row(InlineKeyboardButton(text=btn_text, callback_data=callback))
    
    builder.row(InlineKeyboardButton(text="🎮 Выбрать игру", callback_data="fox_try_luck"))
    builder.row(InlineKeyboardButton(text="🎁 Мои призы", callback_data="fox_my_prizes"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    return builder.as_markup()


# Хук для добавления кнопки в меню профиля
@register_hook("profile_menu")
async def add_fox_den_button(**kwargs):
    """Добавляет кнопку 'Логово Лисы' в меню профиля"""
    return {
        "button": InlineKeyboardButton(
            text=FOX_DEN_BUTTON,
            callback_data="fox_den"
        )
    }


@router.callback_query(F.data == "fox_den")
async def handle_fox_den(callback: CallbackQuery, session: AsyncSession, admin: bool = False):
    """Главное меню Логова Лисы"""
    await ensure_db()
    
    # Проверка режима доработки
    user_id = callback.from_user.id
    is_allowed = admin or user_id in ADMIN_IDS
    
    if MAINTENANCE_MODE and not is_allowed:
        text = """🦊 <b>Логово Лисы на доработке!</b>

🔧 Лиса готовит что-то особенное...

<i>Скоро откроется! Следи за обновлениями.</i>
"""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="profile"))
        
        await edit_or_send_message(
            target_message=callback.message,
            text=text,
            reply_markup=builder.as_markup(),
        )
        await callback.answer()
        return
    
    logger.info(f"[Gamification] Открытие Логова Лисы для {user_id}")
    
    from .events import format_events_text
    from database.users import get_balance
    from .casino import get_current_jackpot
    
    player = await get_or_create_player(session, callback.from_user.id)
    await check_and_reset_daily_spin(session, callback.from_user.id)
    player = await get_or_create_player(session, callback.from_user.id)
    
    # Реальный баланс пользователя
    real_balance = int(await get_balance(session, callback.from_user.id))
    
    # Джекпот казино
    jackpot_pool = await get_current_jackpot(session)
    
    # Активные события
    events_text = format_events_text()
    
    text = f"""🦊 <b>Добро пожаловать в Логово Лисы!</b>

━━━━━━━━━━━━━━━━━━
💰 Баланс: <b>{real_balance} ₽</b> <i>(для VPN)</i>
🦊 Лискоины: <b>{player.coins}</b>
━━━━━━━━━━━━━━━━━━

🏆 Джекпот казино: <b>{jackpot_pool} ₽</b>
{events_text}
<i>Испытай удачу или рискни в казино!</i>
"""
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_fox_den_menu(),
        media_path=FOX_DEN_IMAGE,
    )
    await callback.answer()


@router.callback_query(F.data == "fox_try_luck")
async def handle_try_luck(callback: CallbackQuery, session: AsyncSession):
    """Подменю 'Испытать удачу' — игры и активности"""
    await ensure_db()
    logger.info(f"[Gamification] fox_try_luck от {callback.from_user.id}")
    
    await check_and_reset_daily_spin(session, callback.from_user.id)
    player = await get_or_create_player(session, callback.from_user.id)
    
    test_mode_text = "\n🔧 <b>ТЕСТОВЫЙ РЕЖИМ</b>\n" if TEST_MODE else ""
    
    # Формируем текст попыток
    spins_parts = []
    if player.free_spins > 0:
        spins_parts.append(f"🎫 {player.free_spins}")
    if player.paid_spins > 0:
        spins_parts.append(f"🛒 {player.paid_spins}")
    spins_text = " + ".join(spins_parts) if spins_parts else "❌ Нет"
    
    text = f"""🎰 <b>Испытать удачу</b>
{test_mode_text}
🎫 Попыток: <b>{spins_text}</b>
🦊 Лискоинов: <b>{player.coins}</b>

━━━━━━━━━━━━━━━━━━
<b>🎮 Игры:</b>
• 🎰 Слоты — крути барабаны
• 🎡 Колесо — испытай удачу
• 🦊 Сделка — рискни монетами

<b>📋 Активности:</b>
• Задания, календарь, рефералы
"""
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_try_luck_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_daily_bonus")
async def handle_daily_bonus(callback: CallbackQuery, session: AsyncSession):
    """Ежедневные бонусы — Задания + Календарь на одном экране"""
    await ensure_db()
    logger.info(f"[Gamification] fox_daily_bonus от {callback.from_user.id}")
    
    from .quests import (
        init_daily_quests, get_player_quests, 
        QUEST_DEFINITIONS, QuestType, update_quest_progress
    )
    from .calendar import get_calendar_status, CALENDAR_REWARDS
    
    player = await get_or_create_player(session, callback.from_user.id)
    
    # === КВЕСТЫ ===
    await init_daily_quests(session, callback.from_user.id)
    await update_quest_progress(session, callback.from_user.id, QuestType.DAILY_LOGIN)
    quests = await get_player_quests(session, callback.from_user.id)
    
    quests_text = ""
    claimable_quests = []
    
    for quest in quests:
        quest_info = QUEST_DEFINITIONS.get(QuestType(quest.quest_type))
        if not quest_info:
            continue
        
        if quest.is_claimed:
            status_icon = "✅"
            reward = f"<s>{quest_info.reward_description}</s>"
        elif quest.is_completed:
            status_icon = "🎁"
            reward = f"<b>{quest_info.reward_description}</b>"
            claimable_quests.append(quest)
        else:
            status_icon = "⬜"
            progress = f" ({quest.progress}/{quest.target})" if quest.target > 1 else ""
            reward = quest_info.reward_description
        
        progress_str = f" ({quest.progress}/{quest.target})" if not quest.is_completed and quest.target > 1 else ""
        quests_text += f"{status_icon} {quest_info.title}{progress_str} — {reward}\n"
    
    # === КАЛЕНДАРЬ ===
    cal_status = get_calendar_status(player.calendar_day, player.last_calendar_claim)
    current_day = player.calendar_day
    can_claim_calendar = cal_status["can_claim"]
    
    # Визуализация календаря
    calendar_line = ""
    for day in range(1, 8):
        if day < current_day or (day == current_day and not can_claim_calendar):
            calendar_line += "✅"
        elif day == current_day + 1 and can_claim_calendar:
            calendar_line += "🎁"
        elif day == 7:
            calendar_line += "🎁"
        else:
            calendar_line += "⬜"
        if day < 7:
            calendar_line += " "
    
    # Награда за следующий день
    next_day = (current_day + 1) if current_day < 7 else 1
    if can_claim_calendar:
        next_reward = CALENDAR_REWARDS.get(next_day if current_day < 7 else 1, {})
        reward_parts = []
        if next_reward.get("coins"):
            reward_parts.append(f"{next_reward['coins']} 🦊")
        if next_reward.get("spins"):
            reward_parts.append(f"{next_reward['spins']} 🎫")
        next_reward_text = " + ".join(reward_parts) if reward_parts else "???"
    else:
        next_reward_text = "Завтра!"
    
    text = f"""📋 <b>Ежедневные бонусы</b>

━━━━ 🗓 КАЛЕНДАРЬ ━━━━
{calendar_line}
День <b>{current_day}/7</b> | {next_reward_text}

━━━━ 📋 ЗАДАНИЯ ━━━━
{quests_text}
🔥 Серия входов: <b>{player.login_streak}</b> дней
"""
    
    builder = InlineKeyboardBuilder()
    
    # Кнопка забрать календарь
    if can_claim_calendar:
        builder.row(InlineKeyboardButton(
            text="🎁 Забрать награду календаря",
            callback_data="fox_calendar_claim_from_bonus"
        ))
    
    # Кнопка забрать квесты
    if claimable_quests:
        builder.row(InlineKeyboardButton(
            text=f"🎁 Забрать награды ({len(claimable_quests)})",
            callback_data="fox_claim_quests_from_bonus"
        ))
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_try_luck"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "fox_calendar_claim_from_bonus")
async def handle_calendar_claim_from_bonus(callback: CallbackQuery, session: AsyncSession):
    """Забрать награду календаря из объединённого меню"""
    await ensure_db()
    logger.info(f"[Gamification] fox_calendar_claim_from_bonus от {callback.from_user.id}")
    
    from .calendar import get_calendar_status, CALENDAR_REWARDS
    from .db import update_player_coins, add_paid_spin
    from datetime import datetime
    
    player = await get_or_create_player(session, callback.from_user.id)
    status = get_calendar_status(player.calendar_day, player.last_calendar_claim)
    
    if not status["can_claim"]:
        await callback.answer("⏰ Ты уже забрал награду сегодня!", show_alert=True)
        return
    
    # Определяем новый день
    if status["streak_broken"] or player.calendar_day >= 7:
        new_day = 1
    else:
        new_day = player.calendar_day + 1
    
    reward = CALENDAR_REWARDS[new_day]
    
    # Выдаём награды
    coins_added = reward.get("coins", 0)
    spins_added = reward.get("spins", 0)
    
    if coins_added > 0:
        await update_player_coins(session, callback.from_user.id, coins_added)
    if spins_added > 0:
        await add_paid_spin(session, callback.from_user.id, spins_added)
    
    # Обновляем календарь
    player.calendar_day = new_day
    player.last_calendar_claim = datetime.utcnow()
    await session.commit()
    
    # Формируем текст награды
    reward_parts = []
    if coins_added:
        reward_parts.append(f"+{coins_added} 🦊")
    if spins_added:
        reward_parts.append(f"+{spins_added} 🎫")
    
    await callback.answer(f"🎁 День {new_day}: {', '.join(reward_parts)}", show_alert=True)
    
    # Обновляем экран
    await handle_daily_bonus(callback, session)


@router.callback_query(F.data == "fox_claim_quests_from_bonus")
async def handle_claim_quests_from_bonus(callback: CallbackQuery, session: AsyncSession):
    """Забрать награды за квесты из объединённого меню"""
    await ensure_db()
    logger.info(f"[Gamification] fox_claim_quests_from_bonus от {callback.from_user.id}")
    
    from .quests import get_player_quests, QUEST_DEFINITIONS, QuestType
    from .db import update_player_coins
    
    quests = await get_player_quests(session, callback.from_user.id)
    
    total_coins = 0
    claimed_count = 0
    
    for quest in quests:
        if quest.is_completed and not quest.is_claimed:
            quest_info = QUEST_DEFINITIONS.get(QuestType(quest.quest_type))
            if quest_info:
                total_coins += quest_info.reward_coins
                quest.is_claimed = True
                claimed_count += 1
    
    if claimed_count == 0:
        await callback.answer("Нет наград для получения!", show_alert=True)
        return
    
    # Начисляем монеты
    await update_player_coins(session, callback.from_user.id, total_coins)
    await session.commit()
    
    await callback.answer(f"🎁 Получено: +{total_coins} 🦊", show_alert=True)
    
    # Обновляем экран
    await handle_daily_bonus(callback, session)


async def run_game(callback: CallbackQuery, session: AsyncSession, game_type: str):
    """Общая функция запуска игры"""
    await ensure_db()
    logger.info(f"[Gamification] Игра {game_type} от {callback.from_user.id}")
    await callback.answer()
    
    # Удаляем старое сообщение (может содержать фото)
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    # Начальное сообщение в зависимости от типа игры
    if game_type == "slots":
        init_text = "🎰 <b>Крутим барабаны...</b>\n\n┃ 🔄 ┃ 🔄 ┃ 🔄 ┃\n\n<i>Удачи!</i>"
    elif game_type == "chest":
        init_text = "📦 <b>Открываем сундук...</b>\n\n🔒 Сундук закрыт...\n\n<i>Что внутри?</i>"
    else:  # wheel
        init_text = "🎡 <b>Крутим колесо...</b>\n\n⚪🔴🟠🟡🟢🔵🟣⚫\n      ⬆️\n\n<i>Удачи!</i>"
    
    msg = await callback.message.answer(init_text)
    
    # В тестовом режиме не тратим попытки
    result = await play_game(
        session, 
        callback.from_user.id, 
        use_coins=False,
        message=msg,
        game_type=game_type,
        test_mode=TEST_MODE,
    )
    
    if not result["success"]:
        # Понятное сообщение если попытки закончились
        if result["error"] == "no_spins":
            error_text = """❌ <b>Попытки закончились!</b>

🎫 У тебя нет бесплатных попыток.

<b>Как получить:</b>
• ⏰ Бесплатная попытка каждый день
• 🧰 Выполняй задания
• ⭐ Купи в улучшениях (30 🦊)
"""
            builder = InlineKeyboardBuilder()
            builder.row(InlineKeyboardButton(text="⭐ Купить попытку", callback_data="fox_upgrades"))
            builder.row(InlineKeyboardButton(text="🧰 Задания", callback_data="fox_quests"))
            builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
            await msg.edit_text(error_text, reply_markup=builder.as_markup())
        else:
            await msg.edit_text(
                f"❌ <b>Ошибка:</b> {result['error']}",
                reply_markup=build_game_select_kb()
            )
        return
    
    text = format_prize_message(
        result["game_type"],
        result["prize"],
        result["symbols"],
        result["coins_spent"],
        result["new_balance"],
    )
    
    # Если выиграли джекпот — добавляем к сообщению
    if result.get("jackpot_win"):
        jackpot_text = f"""

🎰🎰🎰 <b>ДЖЕКПОТ!!!</b> 🎰🎰🎰

🦊 Лиса в шоке! Ты сорвал банк!

💰 <b>+{result['jackpot_win']}</b> 🦊

🎉🎉🎉"""
        text = jackpot_text + "\n\n" + text
    
    await msg.edit_text(text, reply_markup=build_after_game_kb(game_type))


@router.callback_query(F.data == "fox_play_slots")
async def handle_play_slots(callback: CallbackQuery, session: AsyncSession):
    """Игра в слоты"""
    await run_game(callback, session, "slots")


@router.callback_query(F.data == "fox_deal")
async def handle_deal_menu(callback: CallbackQuery, session: AsyncSession):
    """Меню сделки с лисой"""
    await ensure_db()
    logger.info(f"[Gamification] Сделка с лисой от {callback.from_user.id}")
    await callback.answer()
    
    from .deal import get_greeting, MIN_COINS_STAKE, MAX_COINS_STAKE
    from .db import get_deal_stats, can_make_deal
    
    player = await get_or_create_player(session, callback.from_user.id)
    stats = await get_deal_stats(session, callback.from_user.id)
    can_deal, reason = await can_make_deal(session, callback.from_user.id)
    
    greeting = get_greeting(stats)
    
    # Проверяем, есть ли что ставить
    has_coins = player.coins >= MIN_COINS_STAKE
    
    if not can_deal:
        text = f"""🦊 <b>СДЕЛКА С ЛИСОЙ</b>

⏰ {reason}

<i>Лиса отдыхает. Приходи позже.</i>
"""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_try_luck"))
        await edit_or_send_message(callback.message, text, builder.as_markup())
        return
    
    if not has_coins:
        text = f"""🦊 <b>СДЕЛКА С ЛИСОЙ</b>

{greeting}

❌ У тебя нет ничего для ставки.
Минимум: <b>{MIN_COINS_STAKE}</b> Лискоинов

<i>Сначала заработай, потом рискуй.</i>
"""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_try_luck"))
        await edit_or_send_message(callback.message, text, builder.as_markup())
        return
    
    text = f"""🦊 <b>СДЕЛКА С ЛИСОЙ</b>

{greeting}

💰 Твои Лискоины: <b>{player.coins}</b>

<b>Выбери ставку:</b>
Минимум: {MIN_COINS_STAKE} 🦊
Максимум: {MAX_COINS_STAKE} 🦊

<i>⚠️ Выиграешь — удвоишь (или утроишь)
Проиграешь — потеряешь всё</i>
"""
    
    # Кнопки выбора ставки
    builder = InlineKeyboardBuilder()
    stakes = [20, 50, 100, 200]
    row = []
    for stake in stakes:
        if player.coins >= stake:
            row.append(InlineKeyboardButton(text=f"{stake} 🦊", callback_data=f"fox_deal_stake_{stake}"))
    if row:
        builder.row(*row[:2])
        if len(row) > 2:
            builder.row(*row[2:])
    
    builder.row(InlineKeyboardButton(text="🚪 Уйти", callback_data="fox_deal_decline"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_try_luck"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data == "fox_deal_decline")
async def handle_deal_decline(callback: CallbackQuery, session: AsyncSession):
    """Отказ от сделки"""
    import random
    from .deal import DECLINE_COMMENTS
    
    await callback.answer()
    comment = random.choice(DECLINE_COMMENTS)
    
    text = f"""{comment}"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎮 К играм", callback_data="fox_try_luck"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data.startswith("fox_deal_stake_"))
async def handle_deal_confirm(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение ставки и сделка"""
    await ensure_db()
    
    stake = int(callback.data.split("_")[-1])
    logger.info(f"[Gamification] Сделка: ставка {stake} от {callback.from_user.id}")
    await callback.answer()
    
    player = await get_or_create_player(session, callback.from_user.id)
    
    # Проверяем, хватает ли монет
    if player.coins < stake:
        await callback.answer("❌ Недостаточно Лискоинов!", show_alert=True)
        return
    
    # Показываем экран подтверждения
    text = f"""🦊 <b>СДЕЛКА С ЛИСОЙ</b>

Ты ставишь: <b>{stake}</b> 🦊

<b>Заключить сделку?</b>

⚠️ <i>Это решение необратимо.</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🤝 Заключить сделку", callback_data=f"fox_deal_confirm_{stake}"))
    builder.row(InlineKeyboardButton(text="🚪 Передумал", callback_data="fox_deal"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data.startswith("fox_deal_confirm_"))
async def handle_deal_execute(callback: CallbackQuery, session: AsyncSession):
    """Выполнение сделки"""
    import asyncio
    from .deal import execute_deal
    
    await ensure_db()
    
    stake = int(callback.data.split("_")[-1])
    logger.info(f"[Gamification] Выполнение сделки: {stake} от {callback.from_user.id}")
    await callback.answer()
    
    # Удаляем старое сообщение
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    # Анимация: Лиса думает
    msg = await callback.message.answer(
        "🦊 <b>СДЕЛКА С ЛИСОЙ</b>\n\n"
        f"Ставка: <b>{stake}</b> 🦊\n\n"
        "🤔 <i>Лиса думает...</i>"
    )
    
    await asyncio.sleep(1.5)
    
    await msg.edit_text(
        "🦊 <b>СДЕЛКА С ЛИСОЙ</b>\n\n"
        f"Ставка: <b>{stake}</b> 🦊\n\n"
        "🦊 <i>Лиса смотрит тебе в глаза...</i>"
    )
    
    await asyncio.sleep(1.0)
    
    # Выполняем сделку
    result = await execute_deal(session, callback.from_user.id, "coins", stake)
    
    await asyncio.sleep(0.5)
    
    # Показываем результат
    player = await get_or_create_player(session, callback.from_user.id)
    
    if result.won:
        text = f"""🦊 <b>СДЕЛКА С ЛИСОЙ</b>

✅ <b>ВЫИГРЫШ!</b>

Ставка: {stake} 🦊
Множитель: <b>×{result.multiplier:.0f}</b>
Выигрыш: <b>+{result.result_value - stake}</b> 🦊

💬 <i>"{result.fox_comment}"</i>

🦊 Баланс: <b>{player.coins}</b> Лискоинов
"""
    else:
        text = f"""🦊 <b>СДЕЛКА С ЛИСОЙ</b>

❌ <b>ПРОИГРЫШ</b>

Ставка: {stake} 🦊
Потеряно: <b>-{stake}</b> 🦊

💬 <i>"{result.fox_comment}"</i>

🦊 Баланс: <b>{player.coins}</b> Лискоинов
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎮 К играм", callback_data="fox_try_luck"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await msg.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "fox_play_wheel")
async def handle_play_wheel(callback: CallbackQuery, session: AsyncSession):
    """Игра с колесом"""
    await run_game(callback, session, "wheel")


@router.callback_query(F.data == "fox_no_coins")
async def handle_no_coins(callback: CallbackQuery):
    """Недостаточно монет"""
    await callback.answer(
        f"❌ Недостаточно Лискоинов!\nНужно: {SPIN_COST_COINS} 🦊",
        show_alert=True
    )


@router.callback_query(F.data == "fox_quests")
async def handle_quests(callback: CallbackQuery, session: AsyncSession):
    """Задания"""
    await ensure_db()
    logger.info(f"[Gamification] fox_quests от {callback.from_user.id}")
    
    from .quests import (
        init_daily_quests, get_player_quests, format_quest_status,
        QUEST_DEFINITIONS, QuestType, update_quest_progress
    )
    
    player = await get_or_create_player(session, callback.from_user.id)
    
    # Инициализируем ежедневные квесты (если ещё нет)
    await init_daily_quests(session, callback.from_user.id)
    
    # Отмечаем ежедневный вход
    await update_quest_progress(session, callback.from_user.id, QuestType.DAILY_LOGIN)
    
    # Получаем квесты
    quests = await get_player_quests(session, callback.from_user.id)
    
    # Формируем список
    quests_text = ""
    claimable_quests = []
    
    for quest in quests:
        quest_info = QUEST_DEFINITIONS.get(QuestType(quest.quest_type))
        if not quest_info:
            continue
        
        if quest.is_claimed:
            status = "✅"
            reward = "<s>" + quest_info.reward_description + "</s>"
        elif quest.is_completed:
            status = "🎁"
            reward = f"<b>{quest_info.reward_description}</b>"
            claimable_quests.append(quest)
        else:
            status = "⏳"
            progress = f" ({quest.progress}/{quest.target})" if quest.target > 1 else ""
            reward = quest_info.reward_description
        
        quests_text += f"{status} {quest_info.emoji} {quest_info.title}{progress if not quest.is_completed else ''} — {reward}\n"
    
    text = f"""🧰 <b>Ежедневные задания</b>

🔥 Серия входов: <b>{player.login_streak} дней</b>

{quests_text}
<i>Задания обновляются каждый день!</i>
"""
    
    builder = InlineKeyboardBuilder()
    
    # Кнопки для получения наград
    if claimable_quests:
        builder.row(InlineKeyboardButton(
            text=f"🎁 Забрать награды ({len(claimable_quests)})",
            callback_data="fox_claim_quests"
        ))
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_claim_quests")
async def handle_claim_quests(callback: CallbackQuery, session: AsyncSession):
    """Забрать награды за выполненные квесты"""
    await ensure_db()
    logger.info(f"[Gamification] Забор наград от {callback.from_user.id}")
    await callback.answer()
    
    from .quests import get_player_quests, claim_quest_reward, QUEST_DEFINITIONS, QuestType
    
    quests = await get_player_quests(session, callback.from_user.id)
    
    total_reward = 0
    claimed_count = 0
    
    for quest in quests:
        if quest.is_completed and not quest.is_claimed:
            reward = await claim_quest_reward(session, callback.from_user.id, quest.id)
            if reward:
                total_reward += reward
                claimed_count += 1
    
    if claimed_count > 0:
        player = await get_or_create_player(session, callback.from_user.id)
        text = f"""🎁 <b>Награды получены!</b>

✅ Выполнено заданий: <b>{claimed_count}</b>
🦊 Получено: <b>+{total_reward} Лискоинов</b>

💰 Твой баланс: <b>{player.coins}</b> 🦊

🦊 <i>Возвращайся завтра за новыми заданиями!</i>
"""
    else:
        text = """🧰 <b>Задания</b>

❌ Нет наград для получения.

<i>Выполни задания, чтобы получить награды!</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🧰 К заданиям", callback_data="fox_quests"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data == "fox_my_prizes")
async def handle_my_prizes(callback: CallbackQuery, session: AsyncSession):
    """Мои призы"""
    await ensure_db()
    logger.info(f"[Gamification] fox_my_prizes от {callback.from_user.id}")
    
    from datetime import datetime
    
    prizes = await get_active_prizes(session, callback.from_user.id)
    
    builder = InlineKeyboardBuilder()
    
    if prizes:
        prizes_text = ""
        vpn_prizes = []
        balance_prizes = []
        
        for prize in prizes:
            # Считаем дни до истечения
            days_left = (prize.expires_at - datetime.utcnow()).days
            expires_info = f"(осталось {days_left}д)" if days_left > 0 else "(истекает сегодня!)"
            
            if prize.prize_type == "vpn_days":
                prizes_text += f"📅 <b>+{prize.value} дней VPN</b> {expires_info}\n"
                vpn_prizes.append(prize)
            elif prize.prize_type == "balance":
                rub_value = prize.value / 2  # 50 монет = 25 рублей
                prizes_text += f"💰 <b>+{rub_value:.0f}₽ на баланс</b> {expires_info}\n"
                balance_prizes.append(prize)
            else:
                prizes_text += f"🎁 {prize.description or prize.prize_type}: {prize.value} {expires_info}\n"
        
        text = f"""🎁 <b>Мои призы</b>

{prizes_text}
<i>Выбери приз для применения:</i>
"""
        
        # Кнопки для VPN призов
        if vpn_prizes:
            # Суммируем все дни VPN
            total_vpn_days = sum(p.value for p in vpn_prizes)
            builder.row(InlineKeyboardButton(
                text=f"📅 Применить {total_vpn_days} дней VPN",
                callback_data="fox_apply_vpn"
            ))
        
        # Кнопки для баланса
        if balance_prizes:
            total_balance = sum(p.value / 2 for p in balance_prizes)
            builder.row(InlineKeyboardButton(
                text=f"💰 Получить {total_balance:.0f}₽ на баланс",
                callback_data="fox_apply_balance"
            ))
        
    else:
        text = """🎁 <b>Мои призы</b>

🦊 У тебя пока нет призов.

<i>Испытай удачу, чтобы получить награды!</i>
"""
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_apply_vpn")
async def handle_apply_vpn(callback: CallbackQuery, session: AsyncSession):
    """Применить призовые дни VPN к подписке"""
    await ensure_db()
    logger.info(f"[Gamification] Применение VPN призов от {callback.from_user.id}")
    await callback.answer()
    
    from database.keys import get_keys
    from datetime import datetime
    
    # Получаем ключи пользователя
    keys = await get_keys(session, callback.from_user.id)
    
    if not keys:
        text = """🎁 <b>Применить приз</b>

❌ У тебя нет активных подписок VPN.

<i>Сначала купи подписку, потом применяй призы.</i>
"""
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_my_prizes"))
        await edit_or_send_message(callback.message, text, builder.as_markup())
        return
    
    # Получаем VPN призы
    prizes = await get_active_prizes(session, callback.from_user.id)
    vpn_prizes = [p for p in prizes if p.prize_type == "vpn_days"]
    
    if not vpn_prizes:
        await callback.answer("❌ Нет призов для применения!", show_alert=True)
        return
    
    total_days = sum(p.value for p in vpn_prizes)
    
    # Показываем выбор подписки
    text = f"""🎁 <b>Применить {total_days} дней VPN</b>

Выбери подписку, к которой применить приз:
"""
    
    builder = InlineKeyboardBuilder()
    now = datetime.utcnow().timestamp() * 1000
    
    for key in keys:
        # Определяем статус
        if key.expiry_time > now:
            days_left = int((key.expiry_time - now) / 1000 / 60 / 60 / 24)
            status = f"✅ {days_left}д"
        else:
            status = "❌ истекла"
        
        name = key.alias or key.email or key.client_id[:8]
        builder.row(InlineKeyboardButton(
            text=f"{name} ({status})",
            callback_data=f"fox_apply_vpn_to_{key.client_id}"
        ))
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_my_prizes"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data.startswith("fox_apply_vpn_to_"))
async def handle_apply_vpn_to_key(callback: CallbackQuery, session: AsyncSession):
    """Применить VPN дни к конкретной подписке"""
    await ensure_db()
    
    client_id = callback.data.replace("fox_apply_vpn_to_", "")
    logger.info(f"[Gamification] Применение VPN к {client_id} от {callback.from_user.id}")
    await callback.answer()
    
    from database.keys import get_key_by_server, update_key_expiry
    from .db import mark_prize_used
    from datetime import datetime
    
    # Получаем ключ
    key = await get_key_by_server(session, callback.from_user.id, client_id)
    
    if not key:
        await callback.answer("❌ Подписка не найдена!", show_alert=True)
        return
    
    # Получаем VPN призы
    prizes = await get_active_prizes(session, callback.from_user.id)
    vpn_prizes = [p for p in prizes if p.prize_type == "vpn_days"]
    
    if not vpn_prizes:
        await callback.answer("❌ Нет призов для применения!", show_alert=True)
        return
    
    total_days = sum(p.value for p in vpn_prizes)
    total_ms = total_days * 24 * 60 * 60 * 1000
    
    # Вычисляем новый срок
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    current_expiry = max(key.expiry_time, now_ms)  # Если истёк, считаем от сейчас
    new_expiry = current_expiry + total_ms
    
    # Применяем
    await update_key_expiry(session, client_id, new_expiry)
    
    # Помечаем призы как использованные
    for prize in vpn_prizes:
        await mark_prize_used(session, prize.id)
    
    new_days = int((new_expiry - now_ms) / 1000 / 60 / 60 / 24)
    
    text = f"""🎁 <b>Приз применён!</b>

✅ Добавлено: <b>+{total_days} дней</b>
📅 Подписка теперь активна: <b>{new_days} дней</b>

🦊 <i>Лиса довольна твоим выбором!</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎁 Мои призы", callback_data="fox_my_prizes"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data == "fox_apply_balance")
async def handle_apply_balance(callback: CallbackQuery, session: AsyncSession):
    """Применить баланс на счёт"""
    await ensure_db()
    logger.info(f"[Gamification] Применение баланса от {callback.from_user.id}")
    await callback.answer()
    
    from database.users import update_balance, get_balance
    from .db import mark_prize_used
    
    # Получаем призы баланса
    prizes = await get_active_prizes(session, callback.from_user.id)
    balance_prizes = [p for p in prizes if p.prize_type == "balance"]
    
    if not balance_prizes:
        await callback.answer("❌ Нет призов для применения!", show_alert=True)
        return
    
    # Считаем сумму (50 лискоинов = 25 рублей, т.е. value/2)
    total_rub = sum(p.value / 2 for p in balance_prizes)
    
    # Добавляем на баланс
    await update_balance(session, callback.from_user.id, total_rub)
    
    # Помечаем призы как использованные
    for prize in balance_prizes:
        await mark_prize_used(session, prize.id)
    
    new_balance = await get_balance(session, callback.from_user.id)
    
    text = f"""🎁 <b>Приз применён!</b>

✅ Добавлено на баланс: <b>+{total_rub:.0f}₽</b>
💰 Твой баланс: <b>{new_balance:.0f}₽</b>

🦊 <i>Используй с умом!</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎁 Мои призы", callback_data="fox_my_prizes"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data == "fox_balance")
async def handle_balance(callback: CallbackQuery, session: AsyncSession):
    """Баланс — информационная страница"""
    await ensure_db()
    logger.info(f"[Gamification] fox_balance от {callback.from_user.id}")
    
    from database.users import get_balance
    
    player = await get_or_create_player(session, callback.from_user.id)
    real_balance = int(await get_balance(session, callback.from_user.id))
    
    text = f"""🦊 <b>Баланс</b>

━━━━━━━━━━━━━━━━━━
💳 <b>Баланс бота: {real_balance} ₽</b>
<i>Это реальные деньги для покупки VPN</i>
━━━━━━━━━━━━━━━━━━

🦊 Лискоины: <b>{player.coins}</b>

<b>Что можно купить за Лискоины:</b>
• Дополнительные попытки
• Бусты удачи

<i>Лискоины — игровая валюта Логова Лисы</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛒 Магазин", callback_data="fox_upgrades"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data == "fox_upgrades")
async def handle_upgrades(callback: CallbackQuery, session: AsyncSession):
    """Магазин бустов"""
    await ensure_db()
    logger.info(f"[Gamification] fox_upgrades от {callback.from_user.id}")
    
    from .db import get_active_boosts
    
    player = await get_or_create_player(session, callback.from_user.id)
    boosts = await get_active_boosts(session, callback.from_user.id)
    
    # Форматируем активные бусты
    active_boosts_text = ""
    if boosts:
        for boost in boosts:
            if boost.boost_type.startswith("luck_"):
                percent = boost.boost_type.replace("luck_", "")
                active_boosts_text += f"🔮 Буст удачи +{percent}% ({boost.uses_left} исп.)\n"
    
    if not active_boosts_text:
        active_boosts_text = "<i>Нет активных бустов</i>\n"
    
    # Формируем текст с доступностью
    coins_status = f"🦊 Лискоины: <b>{player.coins}</b>"
    
    text = f"""🛒 <b>Магазин бустов</b>

{coins_status}

<b>Активные бусты:</b>
{active_boosts_text}
<b>Товары:</b>

🔮 Буст удачи +10% — 50 🦊
🔮 Буст удачи +20% — 100 🦊
🎫 Доп. попытка — 30 🦊
"""
    
    builder = InlineKeyboardBuilder()
    
    # Кнопки покупки (всегда показываем, но с 🔒 если не хватает)
    if player.coins >= 50:
        builder.row(InlineKeyboardButton(text="✅ +10% удачи (50 🦊)", callback_data="fox_buy_boost_10"))
    else:
        builder.row(InlineKeyboardButton(text="🔒 +10% удачи (50 🦊)", callback_data="fox_no_coins_50"))
    
    if player.coins >= 100:
        builder.row(InlineKeyboardButton(text="✅ +20% удачи (100 🦊)", callback_data="fox_buy_boost_20"))
    else:
        builder.row(InlineKeyboardButton(text="🔒 +20% удачи (100 🦊)", callback_data="fox_no_coins_100"))
    
    if player.coins >= 30:
        builder.row(InlineKeyboardButton(text="✅ Попытка (30 🦊)", callback_data="fox_buy_spin"))
    else:
        builder.row(InlineKeyboardButton(text="🔒 Попытка (30 🦊)", callback_data="fox_no_coins_30"))
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("fox_no_coins_"))
async def handle_no_coins(callback: CallbackQuery):
    """Недостаточно монет для покупки"""
    needed = callback.data.split("_")[-1]
    await callback.answer(
        f"🔒 Нужно {needed} Лискоинов!\n\n"
        f"🎰 Играй в игры\n"
        f"🧰 Выполняй задания\n"
        f"📅 Заходи каждый день",
        show_alert=True
    )


@router.callback_query(F.data.startswith("fox_buy_boost_"))
async def handle_buy_boost(callback: CallbackQuery, session: AsyncSession):
    """Покупка буста удачи"""
    await ensure_db()
    
    boost_percent = int(callback.data.split("_")[-1])
    cost = 50 if boost_percent == 10 else 100
    
    logger.info(f"[Gamification] Покупка буста +{boost_percent}% от {callback.from_user.id}")
    
    from .db import update_player_coins, add_boost
    
    player = await get_or_create_player(session, callback.from_user.id)
    
    if player.coins < cost:
        await callback.answer("❌ Недостаточно Лискоинов!", show_alert=True)
        return
    
    # Списываем монеты
    await update_player_coins(session, callback.from_user.id, -cost)
    
    # Добавляем буст
    await add_boost(session, callback.from_user.id, f"luck_{boost_percent}", uses=1)
    
    await callback.answer(f"✅ Буст +{boost_percent}% активирован!", show_alert=True)
    
    # Обновляем экран
    await handle_upgrades(callback, session)


@router.callback_query(F.data == "fox_buy_spin")
async def handle_buy_spin(callback: CallbackQuery, session: AsyncSession):
    """Покупка дополнительной попытки"""
    await ensure_db()
    
    cost = 30
    logger.info(f"[Gamification] Покупка попытки от {callback.from_user.id}")
    await callback.answer()
    
    from .db import update_player_coins
    
    player = await get_or_create_player(session, callback.from_user.id)
    
    if player.coins < cost:
        await callback.answer("❌ Недостаточно Лискоинов!", show_alert=True)
        return
    
    # Списываем монеты и добавляем КУПЛЕННУЮ попытку
    from .db import add_paid_spin
    await update_player_coins(session, callback.from_user.id, -cost)
    new_paid_spins = await add_paid_spin(session, callback.from_user.id, 1)
    
    # Показываем экран подтверждения
    text = f"""✅ <b>Попытка куплена!</b>

🎫 Списано: <b>-{cost}</b> 🦊
🛒 Купленных попыток: <b>{new_paid_spins}</b>
🦊 Осталось монет: <b>{player.coins - cost}</b> 🦊

<i>Иди и испытай удачу!</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 Играть!", callback_data="fox_try_luck"))
    builder.row(InlineKeyboardButton(text="⭐ Улучшения", callback_data="fox_upgrades"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


# ==================== ЛИСЬЕ КАЗИНО (реальные ставки!) ====================

# Временное хранилище для двухфазных игр (bet для риска)
_casino_pending_bets: dict[int, tuple[float, float]] = {}  # tg_id -> (bet, current_value)


@router.callback_query(F.data == "fox_casino")
async def handle_casino_menu(callback: CallbackQuery, session: AsyncSession):
    """Вход в казино — с напряжением"""
    await ensure_db()
    logger.info(f"[Casino] Вход в казино от {callback.from_user.id}")
    await callback.answer()
    
    from database.users import get_balance
    from .casino import (
        can_enter_casino, get_welcome_message, start_session,
        MIN_BET, FIXED_BETS,
        BLOCKED_NO_BALANCE, BLOCKED_DAILY_LIMIT, BLOCKED_DAILY_GAMES,
        BLOCKED_COOLDOWN, BLOCKED_FORCED_BREAK, BLOCKED_SELF
    )
    
    tg_id = callback.from_user.id
    can_enter, reason, data = await can_enter_casino(session, tg_id)
    
    builder = InlineKeyboardBuilder()
    
    if not can_enter:
        # Показываем блокировку
        if reason == "self_blocked":
            text = BLOCKED_SELF.format(**data)
        elif reason == "forced_break":
            text = BLOCKED_FORCED_BREAK.format(**data)
        elif reason == "cooldown":
            text = BLOCKED_COOLDOWN.format(**data)
        elif reason == "no_balance":
            text = BLOCKED_NO_BALANCE.format(**data)
        elif reason == "daily_limit":
            text = BLOCKED_DAILY_LIMIT.format(**data)
        elif reason == "daily_games":
            text = BLOCKED_DAILY_GAMES.format(**data)
        else:
            text = "❌ Вход заблокирован."
        
        builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
        await edit_or_send_message(callback.message, text, builder.as_markup())
        return
    
    # Получаем приветствие на основе истории
    balance = data["balance"]
    text = await get_welcome_message(session, tg_id, balance)
    
    # Кнопки: Войти / Не сейчас
    builder.row(InlineKeyboardButton(text="🎰 Войти в казино", callback_data="fox_casino_enter"))
    builder.row(InlineKeyboardButton(text="🚪 Не сейчас", callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data == "fox_casino_enter")
async def handle_casino_enter(callback: CallbackQuery, session: AsyncSession):
    """Вход подтверждён — показываем ставки"""
    await ensure_db()
    logger.info(f"[Casino] Подтверждённый вход от {callback.from_user.id}")
    await callback.answer()
    
    from database.users import get_balance
    from .casino import (
        can_enter_casino, start_session, FIXED_BETS, get_or_create_casino_profile, 
        get_streak_text, get_current_jackpot, MIN_BET,
        BLOCKED_NO_BALANCE, BLOCKED_DAILY_LIMIT, BLOCKED_DAILY_GAMES,
        BLOCKED_COOLDOWN, BLOCKED_FORCED_BREAK, BLOCKED_SELF
    )
    
    tg_id = callback.from_user.id
    can_enter, reason, data = await can_enter_casino(session, tg_id)
    
    builder = InlineKeyboardBuilder()
    
    if not can_enter:
        # Показываем причину блокировки
        if reason == "self_blocked":
            text = BLOCKED_SELF.format(**data)
        elif reason == "forced_break":
            text = BLOCKED_FORCED_BREAK.format(**data)
        elif reason == "cooldown":
            text = BLOCKED_COOLDOWN.format(**data)
        elif reason == "no_balance":
            text = BLOCKED_NO_BALANCE.format(**data)
        elif reason == "daily_limit":
            text = BLOCKED_DAILY_LIMIT.format(**data)
        elif reason == "daily_games":
            text = BLOCKED_DAILY_GAMES.format(**data)
        else:
            text = "❌ Вход заблокирован."
        
        builder.row(InlineKeyboardButton(text="🚪 Выйти", callback_data="fox_casino_exit"))
        await edit_or_send_message(callback.message, text, builder.as_markup())
        return
    
    # Начинаем сессию
    await start_session(session, tg_id)
    
    balance = int(data["balance"])
    profile = await get_or_create_casino_profile(session, tg_id)
    jackpot = await get_current_jackpot(session)
    
    # Информация о серии
    streak_text = get_streak_text(profile)
    streak_line = f"\n{streak_text}\n" if streak_text else ""
    
    text = f"""🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

💰 Баланс: <b>{balance} ₽</b>
🏆 Джекпот: <b>{jackpot} ₽</b>
{streak_line}
Выбери ставку:
"""
    
    row = []
    for bet in FIXED_BETS:
        if balance >= bet:
            row.append(InlineKeyboardButton(text=f"{bet} ₽", callback_data=f"fox_casino_bet_{bet}"))
    
    if row:
        builder.row(*row[:2])
        if len(row) > 2:
            builder.row(*row[2:])
    
    # Дополнительные кнопки
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="fox_casino_stats"),
        InlineKeyboardButton(text="🔒 Заблокировать", callback_data="fox_casino_self_block"),
    )
    builder.row(InlineKeyboardButton(text="🚪 Выйти", callback_data="fox_casino_exit"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data.startswith("fox_casino_bet_"))
async def handle_casino_bet_select(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение ставки"""
    await ensure_db()
    
    bet = int(callback.data.split("_")[-1])
    logger.info(f"[Casino] Выбор ставки {bet}₽ от {callback.from_user.id}")
    await callback.answer()
    
    from .casino import BET_CONFIRM, can_play_bet
    
    can_play, error = await can_play_bet(session, callback.from_user.id, bet)
    
    if not can_play:
        await callback.answer(f"❌ {error}", show_alert=True)
        return
    
    text = BET_CONFIRM.format(bet=bet)
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 Бросить кость", callback_data=f"fox_casino_play_{bet}"))
    builder.row(InlineKeyboardButton(text="🚪 Передумал", callback_data="fox_casino_enter"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data.startswith("fox_casino_play_"))
async def handle_casino_play(callback: CallbackQuery, session: AsyncSession):
    """Игра в казино — СПИСАНИЕ РЕАЛЬНЫХ ДЕНЕГ! Фаза 1"""
    import asyncio
    import random
    
    await ensure_db()
    
    bet = int(callback.data.split("_")[-1])
    tg_id = callback.from_user.id
    logger.info(f"[Casino] ИГРА! Ставка {bet}₽ от {tg_id}")
    await callback.answer()
    
    from .casino import (
        play_casino_phase1, can_play_bet, format_result_message,
        ROLLING_TEXTS, PHASE1_WIN_X15, get_or_create_casino_profile, get_streak_text
    )
    
    # Финальная проверка
    can_play, error = await can_play_bet(session, tg_id, bet)
    if not can_play:
        await callback.answer(f"❌ {error}", show_alert=True)
        return
    
    # Удаляем старое сообщение
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    # === ДРАМАТИЧНАЯ АНИМАЦИЯ ===
    
    # Фаза 1: Ставка принята
    msg = await callback.message.answer(
        f"🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞\n\n"
        f"💰 Ставка: <b>{bet} ₽</b>\n\n"
        f"🎲 <i>Лиса берёт кость...</i>"
    )
    await asyncio.sleep(1.5)
    
    # Фаза 2: Бросок
    await msg.edit_text(
        f"🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞\n\n"
        f"💰 Ставка: <b>{bet} ₽</b>\n\n"
        f"🎲 <i>Лиса бросает!</i>\n\n"
        f"⚀ ⚁ ⚂ ⚃ ⚄ ⚅"
    )
    await asyncio.sleep(1.2)
    
    # Фаза 3: Кость катится
    dice_faces = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    for i in range(5):
        random.shuffle(dice_faces)
        try:
            dots = "." * ((i % 3) + 1)
            await msg.edit_text(
                f"🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞\n\n"
                f"💰 Ставка: <b>{bet} ₽</b>\n\n"
                f"🎲 Кость катится{dots}\n\n"
                f"   [ {dice_faces[0]} ]"
            )
        except Exception:
            pass
        await asyncio.sleep(0.5)
    
    # Фаза 4: Замедление
    await msg.edit_text(
        f"🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞\n\n"
        f"💰 Ставка: <b>{bet} ₽</b>\n\n"
        f"🎲 <i>Кость останавливается...</i>\n\n"
        f"   [ ❓ ]"
    )
    await asyncio.sleep(1.5)
    
    # Фаза 5: Лиса смотрит
    await msg.edit_text(
        f"🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞\n\n"
        f"💰 Ставка: <b>{bet} ₽</b>\n\n"
        f"🦊 <i>Лиса смотрит на кость...</i>"
    )
    await asyncio.sleep(1.2)
    
    # Фаза 6: Напряжение
    await msg.edit_text(
        f"🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞\n\n"
        f"💰 Ставка: <b>{bet} ₽</b>\n\n"
        f"🦊 <i>...</i>"
    )
    await asyncio.sleep(1.0)
    
    # === ИГРА! ===
    result, result_type = await play_casino_phase1(session, tg_id, bet)
    
    builder = InlineKeyboardBuilder()
    
    if result_type == "phase1":
        # Промежуточный результат — можно рискнуть
        _casino_pending_bets[tg_id] = (bet, result.current_value)
        
        text = PHASE1_WIN_X15.format(
            bet=bet,
            current=int(result.current_value)
        )
        
        builder.row(
            InlineKeyboardButton(text=f"💰 Забрать {int(result.current_value)} ₽", callback_data="fox_casino_take"),
        )
        builder.row(
            InlineKeyboardButton(text="🔥 Рискнуть!", callback_data="fox_casino_risk"),
        )
    else:
        # Финальный результат
        text = format_result_message(result)
        
        # Показать серию
        profile = await get_or_create_casino_profile(session, tg_id)
        streak_text = get_streak_text(profile)
        if streak_text:
            text += f"\n\n{streak_text}"
        
        builder.row(InlineKeyboardButton(text="🎲 Ещё раз", callback_data="fox_casino_again"))
        builder.row(InlineKeyboardButton(text="🚪 Выйти", callback_data="fox_casino_exit"))
    
    await msg.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "fox_casino_take")
async def handle_casino_take(callback: CallbackQuery, session: AsyncSession):
    """Забрать ×1.5"""
    await ensure_db()
    tg_id = callback.from_user.id
    logger.info(f"[Casino] Забрать от {tg_id}")
    await callback.answer()
    
    from .casino import play_casino_phase2_take, format_result_message, get_or_create_casino_profile, get_streak_text
    
    if tg_id not in _casino_pending_bets:
        await callback.answer("❌ Ставка не найдена", show_alert=True)
        return
    
    bet, current_value = _casino_pending_bets.pop(tg_id)
    
    result = await play_casino_phase2_take(session, tg_id, bet, current_value)
    
    text = format_result_message(result)
    
    # Показать серию
    profile = await get_or_create_casino_profile(session, tg_id)
    streak_text = get_streak_text(profile)
    if streak_text:
        text += f"\n\n{streak_text}"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 Ещё раз", callback_data="fox_casino_enter"))
    builder.row(InlineKeyboardButton(text="🚪 Выйти", callback_data="fox_casino_exit"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data == "fox_casino_risk")
async def handle_casino_risk(callback: CallbackQuery, session: AsyncSession):
    """Рискнуть — вторая фаза"""
    import asyncio
    import random
    
    await ensure_db()
    tg_id = callback.from_user.id
    logger.info(f"[Casino] РИСК от {tg_id}")
    await callback.answer()
    
    from .casino import play_casino_phase2_risk, format_result_message, get_or_create_casino_profile, get_streak_text
    
    if tg_id not in _casino_pending_bets:
        await callback.answer("❌ Ставка не найдена", show_alert=True)
        return
    
    bet, current_value = _casino_pending_bets.pop(tg_id)
    
    # Удаляем сообщение
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    # Анимация риска
    msg = await callback.message.answer(
        f"🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞\n\n"
        f"🔥 <b>РИСК!</b>\n\n"
        f"💰 На кону: <b>{int(current_value)} ₽</b>\n\n"
        f"🎲 <i>Лиса бросает снова...</i>"
    )
    await asyncio.sleep(2.0)
    
    dice_faces = ["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]
    for i in range(4):
        random.shuffle(dice_faces)
        try:
            await msg.edit_text(
                f"🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞\n\n"
                f"🔥 <b>РИСК!</b>\n\n"
                f"💰 На кону: <b>{int(current_value)} ₽</b>\n\n"
                f"🎲 [ {dice_faces[0]} ] {'.' * (i + 1)}"
            )
        except Exception:
            pass
        await asyncio.sleep(0.6)
    
    await msg.edit_text(
        f"🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞\n\n"
        f"🔥 <b>РИСК!</b>\n\n"
        f"💰 На кону: <b>{int(current_value)} ₽</b>\n\n"
        f"🦊 <i>...</i>"
    )
    await asyncio.sleep(1.5)
    
    # Результат
    result = await play_casino_phase2_risk(session, tg_id, bet)
    
    text = format_result_message(result)
    
    # Показать серию
    profile = await get_or_create_casino_profile(session, tg_id)
    streak_text = get_streak_text(profile)
    if streak_text:
        text += f"\n\n{streak_text}"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 Ещё раз", callback_data="fox_casino_enter"))
    builder.row(InlineKeyboardButton(text="🚪 Выйти", callback_data="fox_casino_exit"))
    
    await msg.edit_text(text, reply_markup=builder.as_markup())


@router.callback_query(F.data == "fox_casino_again")
async def handle_casino_again(callback: CallbackQuery, session: AsyncSession):
    """Ещё раз — показываем ставки в том же сообщении"""
    await ensure_db()
    tg_id = callback.from_user.id
    logger.info(f"[Casino] Ещё раз от {tg_id}")
    await callback.answer()
    
    from database.users import get_balance
    from .casino import (
        can_enter_casino, FIXED_BETS, get_or_create_casino_profile, 
        get_streak_text, get_current_jackpot,
        BLOCKED_NO_BALANCE, BLOCKED_DAILY_LIMIT, BLOCKED_DAILY_GAMES,
        BLOCKED_COOLDOWN, BLOCKED_FORCED_BREAK, BLOCKED_SELF
    )
    
    can_enter, reason, data = await can_enter_casino(session, tg_id)
    
    builder = InlineKeyboardBuilder()
    
    if not can_enter:
        # Показываем причину блокировки со ставками
        if reason == "self_blocked":
            text = BLOCKED_SELF.format(**data)
        elif reason == "forced_break":
            text = BLOCKED_FORCED_BREAK.format(**data)
        elif reason == "cooldown":
            text = BLOCKED_COOLDOWN.format(**data)
        elif reason == "no_balance":
            text = BLOCKED_NO_BALANCE.format(**data)
        elif reason == "daily_limit":
            text = BLOCKED_DAILY_LIMIT.format(**data)
        elif reason == "daily_games":
            text = BLOCKED_DAILY_GAMES.format(**data)
        else:
            text = "❌ Вход заблокирован."
        
        builder.row(InlineKeyboardButton(text="🚪 Выйти", callback_data="fox_casino_exit"))
        await edit_or_send_message(callback.message, text, builder.as_markup())
        return
    
    # Показываем ставки
    balance = int(data["balance"])
    profile = await get_or_create_casino_profile(session, tg_id)
    jackpot = await get_current_jackpot(session)
    
    streak_text = get_streak_text(profile)
    streak_line = f"\n{streak_text}\n" if streak_text else ""
    
    text = f"""🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

💰 Баланс: <b>{balance} ₽</b>
🏆 Джекпот: <b>{jackpot} ₽</b>
{streak_line}
Выбери ставку:
"""
    
    row = []
    for bet in FIXED_BETS:
        if balance >= bet:
            row.append(InlineKeyboardButton(text=f"{bet} ₽", callback_data=f"fox_casino_bet_{bet}"))
    
    if row:
        builder.row(*row[:2])
        if len(row) > 2:
            builder.row(*row[2:])
    
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="fox_casino_stats"),
        InlineKeyboardButton(text="🔒 Заблокировать", callback_data="fox_casino_self_block"),
    )
    builder.row(InlineKeyboardButton(text="🚪 Выйти", callback_data="fox_casino_exit"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data == "fox_casino_exit")
async def handle_casino_exit(callback: CallbackQuery, session: AsyncSession):
    """Выход из казино — показ статистики сессии"""
    await ensure_db()
    tg_id = callback.from_user.id
    logger.info(f"[Casino] Выход от {tg_id}")
    await callback.answer()
    
    from .casino import end_session
    
    # Получаем статистику сессии
    session_text = await end_session(session, tg_id)
    
    if session_text:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🦊 В Логово", callback_data="fox_den"))
        await edit_or_send_message(callback.message, session_text, builder.as_markup())
    else:
        # Нет игр — просто выходим
        await handle_fox_den(callback, session)


@router.callback_query(F.data == "fox_casino_stats")
async def handle_casino_stats(callback: CallbackQuery, session: AsyncSession):
    """Статистика игрока в казино"""
    await ensure_db()
    tg_id = callback.from_user.id
    await callback.answer()
    
    from .casino import get_or_create_casino_profile
    
    profile = await get_or_create_casino_profile(session, tg_id)
    
    net = profile.total_won - profile.total_lost
    net_sign = "+" if net >= 0 else ""
    
    text = f"""🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

📊 <b>Твоя статистика</b>

🎲 Всего игр: <b>{profile.total_games}</b>
💰 Поставлено: <b>{profile.total_wagered:.0f} ₽</b>
📈 Выиграно: <b>+{profile.total_won:.0f} ₽</b>
📉 Проиграно: <b>-{profile.total_lost:.0f} ₽</b>
━━━━━━━━━━━━━━━━
💵 Итого: <b>{net_sign}{net:.0f} ₽</b>

🔥 Лучшая серия побед: <b>{profile.best_win_streak}</b>
❄️ Худшая серия проигрышей: <b>{profile.worst_lose_streak}</b>
🏆 Макс. выигрыш: <b>+{profile.biggest_win:.0f} ₽</b>

👁 Визитов: <b>{profile.total_visits}</b>
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="fox_casino_enter"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data == "fox_casino_self_block")
async def handle_casino_self_block(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение самоблокировки"""
    await ensure_db()
    await callback.answer()
    
    from .casino import SELF_BLOCK_DAYS
    
    text = f"""🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

🔒 <b>Самоблокировка</b>

Ты уверен, что хочешь заблокировать себе вход в казино на <b>{SELF_BLOCK_DAYS} дней</b>?

⚠️ Это действие <b>нельзя отменить</b>.
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔒 Да, заблокировать", callback_data="fox_casino_self_block_confirm"))
    builder.row(InlineKeyboardButton(text="🔙 Отмена", callback_data="fox_casino_enter"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data == "fox_casino_self_block_confirm")
async def handle_casino_self_block_confirm(callback: CallbackQuery, session: AsyncSession):
    """Подтверждённая самоблокировка"""
    await ensure_db()
    tg_id = callback.from_user.id
    logger.info(f"[Casino] Самоблокировка от {tg_id}")
    await callback.answer()
    
    from .casino import self_block_casino, SELF_BLOCK_DAYS
    
    await self_block_casino(session, tg_id)
    
    text = f"""🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

🔒 <b>Казино заблокировано</b>

Ты не сможешь войти в казино <b>{SELF_BLOCK_DAYS} дней</b>.

<i>Это было твоё решение.</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🦊 В Логово", callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


# ==================== КАЛЕНДАРЬ 7 ДНЕЙ ====================

@router.callback_query(F.data == "fox_calendar")
async def handle_calendar(callback: CallbackQuery, session: AsyncSession):
    """Показать 7-дневный календарь"""
    await ensure_db()
    logger.info(f"[Gamification] fox_calendar от {callback.from_user.id}")
    
    from .calendar import build_calendar_text, build_calendar_kb, get_calendar_status
    
    player = await get_or_create_player(session, callback.from_user.id)
    
    status = get_calendar_status(player.calendar_day, player.last_calendar_claim)
    text = build_calendar_text(player.calendar_day, player.last_calendar_claim)
    kb = build_calendar_kb(status["can_claim"])
    
    await edit_or_send_message(callback.message, text, kb.as_markup())
    await callback.answer()


@router.callback_query(F.data == "fox_calendar_claim")
async def handle_calendar_claim(callback: CallbackQuery, session: AsyncSession):
    """Забрать награду из календаря"""
    await ensure_db()
    logger.info(f"[Gamification] fox_calendar_claim от {callback.from_user.id}")
    await callback.answer()
    
    from .calendar import get_calendar_status, CALENDAR_REWARDS, build_calendar_kb
    from .db import update_player_coins, add_paid_spin
    from datetime import datetime
    
    player = await get_or_create_player(session, callback.from_user.id)
    status = get_calendar_status(player.calendar_day, player.last_calendar_claim)
    
    if not status["can_claim"]:
        await callback.answer("⏰ Ты уже забрал награду сегодня!", show_alert=True)
        return
    
    # Определяем новый день
    if status["streak_broken"] or player.calendar_day >= 7:
        new_day = 1
    else:
        new_day = player.calendar_day + 1
    
    reward = CALENDAR_REWARDS[new_day]
    
    # Выдаём награды
    coins_added = reward.get("coins", 0)
    spins_added = reward.get("spins", 0)
    
    if coins_added > 0:
        await update_player_coins(session, callback.from_user.id, coins_added)
    
    if spins_added > 0:
        await add_paid_spin(session, callback.from_user.id, spins_added)
    
    # Обновляем календарь
    player.calendar_day = new_day
    player.last_calendar_claim = datetime.utcnow()
    await session.commit()
    
    # Текст результата
    reward_parts = []
    if coins_added:
        reward_parts.append(f"+{coins_added} 🦊")
    if spins_added:
        reward_parts.append(f"+{spins_added} 🎫")
    
    reward_text = ", ".join(reward_parts)
    
    if new_day == 7:
        text = f"""🎉 <b>ДЕНЬ 7 — БОНУСНЫЙ!</b>

🌟 Ты получил максимальную награду!

{reward_text}

<i>Завтра начнётся новый календарь!</i>
"""
    else:
        text = f"""✅ <b>День {new_day} — награда получена!</b>

{reward_text}

📅 До бонуса: {7 - new_day} дней

<i>Приходи завтра!</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📅 Календарь", callback_data="fox_calendar"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


# ==================== ЛИДЕРБОРД ====================

@router.callback_query(F.data == "fox_leaderboard")
async def handle_leaderboard(callback: CallbackQuery, session: AsyncSession):
    """Показать лидерборд — топ за неделю по умолчанию"""
    await ensure_db()
    logger.info(f"[Gamification] fox_leaderboard от {callback.from_user.id}")
    
    from .leaderboard import get_top_winners_week, format_leaderboard
    
    top = await get_top_winners_week(session, limit=10)
    text = format_leaderboard(top, "wins", "🏆", "📊 <b>Топ-10 за неделю</b>")
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Неделя", callback_data="fox_lb_week"),
        InlineKeyboardButton(text="📆 Месяц", callback_data="fox_lb_month"),
    )
    builder.row(
        InlineKeyboardButton(text="🔥 Серия", callback_data="fox_lb_streak"),
        InlineKeyboardButton(text="🦊 Монеты", callback_data="fox_lb_coins"),
    )
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "fox_lb_week")
async def handle_lb_week(callback: CallbackQuery, session: AsyncSession):
    """Топ за неделю"""
    await ensure_db()
    from .leaderboard import get_top_winners_week, format_leaderboard
    
    top = await get_top_winners_week(session, limit=10)
    text = format_leaderboard(top, "wins", "🏆", "📊 <b>Топ-10 выигрышей за неделю</b>")
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Неделя", callback_data="fox_lb_week"),
        InlineKeyboardButton(text="📆 Месяц", callback_data="fox_lb_month"),
    )
    builder.row(
        InlineKeyboardButton(text="🔥 Серия", callback_data="fox_lb_streak"),
        InlineKeyboardButton(text="🦊 Монеты", callback_data="fox_lb_coins"),
    )
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "fox_lb_month")
async def handle_lb_month(callback: CallbackQuery, session: AsyncSession):
    """Топ за месяц"""
    await ensure_db()
    from .leaderboard import get_top_winners_month, format_leaderboard
    
    top = await get_top_winners_month(session, limit=10)
    text = format_leaderboard(top, "wins", "🏆", "📊 <b>Топ-10 выигрышей за месяц</b>")
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Неделя", callback_data="fox_lb_week"),
        InlineKeyboardButton(text="✅ Месяц", callback_data="fox_lb_month"),
    )
    builder.row(
        InlineKeyboardButton(text="🔥 Серия", callback_data="fox_lb_streak"),
        InlineKeyboardButton(text="🦊 Монеты", callback_data="fox_lb_coins"),
    )
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "fox_lb_streak")
async def handle_lb_streak(callback: CallbackQuery, session: AsyncSession):
    """Топ по серии входов"""
    await ensure_db()
    from .leaderboard import get_top_streak, format_leaderboard
    
    top = await get_top_streak(session, limit=10)
    text = format_leaderboard(top, "streak", "дней 🔥", "📊 <b>Топ-10 по серии входов</b>")
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Неделя", callback_data="fox_lb_week"),
        InlineKeyboardButton(text="📆 Месяц", callback_data="fox_lb_month"),
    )
    builder.row(
        InlineKeyboardButton(text="✅ Серия", callback_data="fox_lb_streak"),
        InlineKeyboardButton(text="🦊 Монеты", callback_data="fox_lb_coins"),
    )
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "fox_lb_coins")
async def handle_lb_coins(callback: CallbackQuery, session: AsyncSession):
    """Топ по Лискоинам"""
    await ensure_db()
    from .leaderboard import get_top_coins, format_leaderboard
    
    top = await get_top_coins(session, limit=10)
    text = format_leaderboard(top, "coins", "🦊", "📊 <b>Топ-10 по Лискоинам</b>")
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Неделя", callback_data="fox_lb_week"),
        InlineKeyboardButton(text="📆 Месяц", callback_data="fox_lb_month"),
    )
    builder.row(
        InlineKeyboardButton(text="🔥 Серия", callback_data="fox_lb_streak"),
        InlineKeyboardButton(text="✅ Монеты", callback_data="fox_lb_coins"),
    )
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())
    await callback.answer()


# ==================== АДМИНСКИЕ КОМАНДЫ ====================

@router.message(Command("fox_notify"))
async def cmd_fox_notify(message: Message, session: AsyncSession):
    """Отправить уведомления неактивным игрокам (админ)"""
    from config import ADMIN_TG_IDS
    if message.from_user.id not in ADMIN_TG_IDS:
        return
    
    await ensure_db()
    logger.info(f"[Gamification] Запуск уведомлений админом {message.from_user.id}")
    
    await message.answer("📤 Отправляю уведомления...")
    
    from .notifications import send_inactive_notifications
    
    result = await send_inactive_notifications(message.bot, session)
    
    await message.answer(
        f"✅ <b>Уведомления отправлены!</b>\n\n"
        f"📬 3 дня неактивности: {result['3d']} чел.\n"
        f"📬 7 дней неактивности: {result['7d']} чел."
    )


@router.message(Command("fox_daily_notify"))
async def cmd_fox_daily_notify(message: Message, session: AsyncSession):
    """Отправить ежедневные уведомления (админ)"""
    from config import ADMIN_TG_IDS
    if message.from_user.id not in ADMIN_TG_IDS:
        return
    
    await ensure_db()
    logger.info(f"[Gamification] Запуск daily уведомлений админом {message.from_user.id}")
    
    await message.answer("📤 Отправляю ежедневные уведомления...")
    
    from .notifications import send_daily_notifications
    
    sent = await send_daily_notifications(message.bot, session)
    
    await message.answer(f"✅ <b>Отправлено:</b> {sent} уведомлений")


# ==================== РЕФЕРАЛЫ ====================

@router.callback_query(F.data == "fox_referrals")
async def handle_referrals(callback: CallbackQuery, session: AsyncSession):
    """Страница рефералов"""
    await ensure_db()
    logger.info(f"[Gamification] fox_referrals от {callback.from_user.id}")
    
    from .referrals import generate_referral_link, REFERRER_BONUS, REFERRED_BONUS
    
    player = await get_or_create_player(session, callback.from_user.id)
    
    # Получаем username бота
    bot_info = await callback.bot.get_me()
    ref_link = generate_referral_link(bot_info.username, callback.from_user.id)
    
    text = f"""🎁 <b>Реферальная программа</b>

Пригласи друга и получи бонус!

<b>Твоя ссылка:</b>
<code>{ref_link}</code>

<b>Награды:</b>
• Ты получишь: <b>{REFERRER_BONUS}</b> 🦊
• Друг получит: <b>{REFERRED_BONUS}</b> 🦊

<i>Бонус начисляется когда друг сыграет первую игру!</i>

📊 <b>Твоя статистика:</b>
👥 Приглашено: <b>{player.total_referrals}</b> чел.
💰 Заработано: <b>{player.total_referrals * REFERRER_BONUS}</b> 🦊
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📤 Поделиться ссылкой",
        switch_inline_query=f"Заходи в Логово Лисы! 🦊 Испытай удачу и получи бонусы: {ref_link}"
    ))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())
    await callback.answer()
