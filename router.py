from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from handlers.utils import edit_or_send_message
from hooks.hooks import register_hook
from logger import logger

from .db import get_active_prizes, get_or_create_player, check_and_reset_daily_spin
from .game import SPIN_COST_COINS, format_prize_message, play_game
from .keyboards import build_fox_den_menu
from .texts import (
    BTN_BACK,
    FOX_DEN_BUTTON,
)


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
TEST_MODE = True


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
async def handle_fox_den(callback: CallbackQuery, session: AsyncSession):
    """Главное меню Логова Лисы"""
    await ensure_db()
    logger.info(f"[Gamification] Открытие Логова Лисы для {callback.from_user.id}")
    
    player = await get_or_create_player(session, callback.from_user.id)
    await check_and_reset_daily_spin(session, callback.from_user.id)
    player = await get_or_create_player(session, callback.from_user.id)
    
    free_spin_text = "✅ Доступна" if player.free_spins > 0 else "❌ Использована"
    
    text = f"""🦊 <b>Добро пожаловать в Логово Лисы!</b>

🪙 Лискоины: <b>{player.coins}</b>
🎫 Бесплатная попытка: <b>{free_spin_text}</b>

🎮 Игр сыграно: <b>{player.total_games}</b>
🏆 Выигрышей: <b>{player.total_wins}</b>

<i>Испытай удачу, выполняй задания и получай призы!</i>
"""
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_fox_den_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_try_luck")
async def handle_try_luck(callback: CallbackQuery, session: AsyncSession):
    """Меню выбора игры"""
    await ensure_db()
    logger.info(f"[Gamification] fox_try_luck от {callback.from_user.id}")
    
    await check_and_reset_daily_spin(session, callback.from_user.id)
    player = await get_or_create_player(session, callback.from_user.id)
    
    test_mode_text = "\n🔧 <b>ТЕСТОВЫЙ РЕЖИМ: бесконечные попытки</b>\n" if TEST_MODE else ""
    
    text = f"""🎰 <b>Испытать удачу</b>

🦊 Выбери игру!
{test_mode_text}
🎫 Попыток: <b>{player.free_spins}</b>
🪙 Лискоинов: <b>{player.coins}</b>

<b>🎰 Слоты</b> — крути барабаны!
<b>🎡 Колесо</b> — испытай удачу!
<b>🦊 Сделка</b> — рискни своими монетами!

<i>3 одинаковых = ДЖЕКПОТ!</i>
"""
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_game_select_kb(),
    )
    await callback.answer()


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
Минимум: {MIN_COINS_STAKE} 🪙
Максимум: {MAX_COINS_STAKE} 🪙

<i>⚠️ Выиграешь — удвоишь (или утроишь)
Проиграешь — потеряешь всё</i>
"""
    
    # Кнопки выбора ставки
    builder = InlineKeyboardBuilder()
    stakes = [20, 50, 100, 200]
    row = []
    for stake in stakes:
        if player.coins >= stake:
            row.append(InlineKeyboardButton(text=f"{stake} 🪙", callback_data=f"fox_deal_stake_{stake}"))
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

Ты ставишь: <b>{stake}</b> 🪙

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
        f"Ставка: <b>{stake}</b> 🪙\n\n"
        "🤔 <i>Лиса думает...</i>"
    )
    
    await asyncio.sleep(1.5)
    
    await msg.edit_text(
        "🦊 <b>СДЕЛКА С ЛИСОЙ</b>\n\n"
        f"Ставка: <b>{stake}</b> 🪙\n\n"
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

Ставка: {stake} 🪙
Множитель: <b>×{result.multiplier:.0f}</b>
Выигрыш: <b>+{result.result_value - stake}</b> 🪙

💬 <i>"{result.fox_comment}"</i>

🪙 Баланс: <b>{player.coins}</b> Лискоинов
"""
    else:
        text = f"""🦊 <b>СДЕЛКА С ЛИСОЙ</b>

❌ <b>ПРОИГРЫШ</b>

Ставка: {stake} 🪙
Потеряно: <b>-{stake}</b> 🪙

💬 <i>"{result.fox_comment}"</i>

🪙 Баланс: <b>{player.coins}</b> Лискоинов
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
        f"❌ Недостаточно Лискоинов!\nНужно: {SPIN_COST_COINS} 🪙",
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
🪙 Получено: <b>+{total_reward} Лискоинов</b>

💰 Твой баланс: <b>{player.coins}</b> 🪙

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
    """Баланс"""
    await ensure_db()
    logger.info(f"[Gamification] fox_balance от {callback.from_user.id}")
    
    from database.users import get_balance
    
    player = await get_or_create_player(session, callback.from_user.id)
    real_balance = await get_balance(session, callback.from_user.id)
    
    # Курс: 50 Лискоинов = 25 рублей (2:1)
    rub_equivalent = player.coins / 2
    min_convert = 100  # Минимум для конвертации
    
    text = f"""🪙 <b>Баланс</b>

🪙 Лискоины: <b>{player.coins}</b>
💰 Эквивалент: <b>~{rub_equivalent:.0f} ₽</b>

✨ Свет Лисы: <b>{player.light}</b>

💳 Реальный баланс: <b>{real_balance:.0f} ₽</b>

<i>Курс обмена: 50 🪙 = 25 ₽</i>
<i>Минимум для обмена: {min_convert} 🪙</i>
"""
    
    builder = InlineKeyboardBuilder()
    
    if player.coins >= min_convert:
        builder.row(InlineKeyboardButton(
            text=f"💱 Обменять {player.coins} 🪙 → {rub_equivalent:.0f} ₽",
            callback_data="fox_convert_coins"
        ))
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_convert_coins")
async def handle_convert_coins(callback: CallbackQuery, session: AsyncSession):
    """Конвертация Лискоинов в рубли"""
    await ensure_db()
    logger.info(f"[Gamification] Конвертация монет от {callback.from_user.id}")
    await callback.answer()
    
    from database.users import update_balance, get_balance
    from .db import update_player_coins
    
    player = await get_or_create_player(session, callback.from_user.id)
    
    min_convert = 100
    if player.coins < min_convert:
        await callback.answer(f"❌ Минимум для обмена: {min_convert} 🪙", show_alert=True)
        return
    
    # Считаем сумму
    coins_to_convert = player.coins
    rub_amount = coins_to_convert / 2  # 50 монет = 25 рублей
    
    # Списываем монеты
    await update_player_coins(session, callback.from_user.id, -coins_to_convert)
    
    # Добавляем на баланс
    await update_balance(session, callback.from_user.id, rub_amount)
    
    new_balance = await get_balance(session, callback.from_user.id)
    
    text = f"""💱 <b>Обмен завершён!</b>

✅ Обменяно: <b>{coins_to_convert}</b> 🪙
💰 Получено: <b>+{rub_amount:.0f} ₽</b>

💳 Баланс: <b>{new_balance:.0f} ₽</b>

🦊 <i>Используй с умом!</i>
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🪙 Баланс", callback_data="fox_balance"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data == "fox_upgrades")
async def handle_upgrades(callback: CallbackQuery, session: AsyncSession):
    """Магазин улучшений"""
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
                active_boosts_text += f"🍀 Буст удачи +{percent}% ({boost.uses_left} исп.)\n"
    else:
        active_boosts_text = "<i>Нет активных бустов</i>\n"
    
    text = f"""⭐ <b>Улучшения</b>

🪙 Лискоины: <b>{player.coins}</b>

<b>Активные бусты:</b>
{active_boosts_text}
<b>Магазин:</b>

🍀 <b>Буст удачи +10%</b> — 50 🪙
<i>Увеличивает шанс редких призов</i>

🍀 <b>Буст удачи +20%</b> — 100 🪙
<i>Увеличивает шанс редких призов</i>

🎫 <b>Доп. попытка</b> — 30 🪙
<i>+1 бесплатная игра</i>
"""
    
    builder = InlineKeyboardBuilder()
    
    # Кнопки покупки
    if player.coins >= 50:
        builder.row(InlineKeyboardButton(text="🍀 +10% (50 🪙)", callback_data="fox_buy_boost_10"))
    if player.coins >= 100:
        builder.row(InlineKeyboardButton(text="🍀 +20% (100 🪙)", callback_data="fox_buy_boost_20"))
    if player.coins >= 30:
        builder.row(InlineKeyboardButton(text="🎫 Попытка (30 🪙)", callback_data="fox_buy_spin"))
    
    if player.coins < 30:
        builder.row(InlineKeyboardButton(text="❌ Недостаточно монет", callback_data="fox_no_coins_shop"))
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_no_coins_shop")
async def handle_no_coins_shop(callback: CallbackQuery):
    """Недостаточно монет для магазина"""
    await callback.answer("❌ Недостаточно Лискоинов! Играй и выполняй задания.", show_alert=True)


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
    
    from .db import update_player_coins
    
    player = await get_or_create_player(session, callback.from_user.id)
    
    if player.coins < cost:
        await callback.answer("❌ Недостаточно Лискоинов!", show_alert=True)
        return
    
    # Списываем монеты и добавляем попытку
    await update_player_coins(session, callback.from_user.id, -cost)
    player.free_spins += 1
    await session.commit()
    
    await callback.answer("✅ +1 бесплатная попытка!", show_alert=True)
    
    # Обновляем экран
    await handle_upgrades(callback, session)


# ==================== ЛИСЬЕ КАЗИНО (реальные ставки!) ====================

@router.callback_query(F.data == "fox_casino")
async def handle_casino_menu(callback: CallbackQuery, session: AsyncSession):
    """Главное меню казино"""
    await ensure_db()
    logger.info(f"[Casino] Открытие казино от {callback.from_user.id}")
    await callback.answer()
    
    from database.users import get_balance
    from .casino import (
        CASINO_INTRO, CASINO_BLOCKED_NO_BALANCE, CASINO_BLOCKED_LIMIT,
        MIN_BET, FIXED_BETS, DAILY_LOSS_LIMIT, get_daily_losses
    )
    
    balance = await get_balance(session, callback.from_user.id)
    daily_losses = await get_daily_losses(session, callback.from_user.id)
    
    # Проверяем лимит
    if daily_losses >= DAILY_LOSS_LIMIT:
        text = CASINO_BLOCKED_LIMIT.format(lost=daily_losses, limit=DAILY_LOSS_LIMIT)
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
        await edit_or_send_message(callback.message, text, builder.as_markup())
        return
    
    # Проверяем баланс
    if balance < MIN_BET:
        text = CASINO_BLOCKED_NO_BALANCE.format(min_bet=MIN_BET, balance=balance)
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
        await edit_or_send_message(callback.message, text, builder.as_markup())
        return
    
    text = CASINO_INTRO.format(balance=balance)
    
    # Кнопки ставок
    builder = InlineKeyboardBuilder()
    row = []
    for bet in FIXED_BETS:
        if balance >= bet:
            row.append(InlineKeyboardButton(text=f"{bet} ₽", callback_data=f"fox_casino_bet_{bet}"))
    
    if row:
        builder.row(*row[:2])
        if len(row) > 2:
            builder.row(*row[2:])
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data.startswith("fox_casino_bet_"))
async def handle_casino_bet_select(callback: CallbackQuery, session: AsyncSession):
    """Подтверждение ставки"""
    await ensure_db()
    
    bet = int(callback.data.split("_")[-1])
    logger.info(f"[Casino] Выбор ставки {bet}₽ от {callback.from_user.id}")
    await callback.answer()
    
    from database.users import get_balance
    from .casino import BET_CONFIRM, can_play_casino
    
    can_play, error = await can_play_casino(session, callback.from_user.id, bet)
    
    if not can_play:
        await callback.answer(f"❌ Ошибка: {error}", show_alert=True)
        return
    
    text = BET_CONFIRM.format(bet=bet)
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 Бросить кость", callback_data=f"fox_casino_play_{bet}"))
    builder.row(InlineKeyboardButton(text="🚪 Передумал", callback_data="fox_casino"))
    
    await edit_or_send_message(callback.message, text, builder.as_markup())


@router.callback_query(F.data.startswith("fox_casino_play_"))
async def handle_casino_play(callback: CallbackQuery, session: AsyncSession):
    """Игра в казино — СПИСАНИЕ РЕАЛЬНЫХ ДЕНЕГ!"""
    import asyncio
    import random
    
    await ensure_db()
    
    bet = int(callback.data.split("_")[-1])
    logger.info(f"[Casino] ИГРА! Ставка {bet}₽ от {callback.from_user.id}")
    await callback.answer()
    
    from .casino import (
        play_casino, can_play_casino,
        RESULT_LOSE, RESULT_WIN_X2, RESULT_WIN_X3
    )
    
    # Финальная проверка
    can_play, error = await can_play_casino(session, callback.from_user.id, bet)
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
    for i in range(4):
        dice = random.choice(dice_faces)
        await msg.edit_text(
            f"🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞\n\n"
            f"💰 Ставка: <b>{bet} ₽</b>\n\n"
            f"🎲 Кость катится...\n\n"
            f"   [ {dice} ]"
        )
        await asyncio.sleep(0.4)
    
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
    result = await play_casino(session, callback.from_user.id, bet)
    
    # Показываем результат
    if result.outcome == "lose":
        text = RESULT_LOSE.format(bet=bet, balance=result.new_balance)
    elif result.outcome == "win_x2":
        winnings = int(result.bet * result.multiplier - result.bet)
        text = RESULT_WIN_X2.format(bet=bet, winnings=winnings, balance=result.new_balance)
    else:  # win_x3
        winnings = int(result.bet * result.multiplier - result.bet)
        text = RESULT_WIN_X3.format(bet=bet, winnings=winnings, balance=result.new_balance)
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎲 Ещё раз", callback_data="fox_casino"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    
    await msg.edit_text(text, reply_markup=builder.as_markup())
