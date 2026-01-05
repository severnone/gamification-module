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
    
    player = await get_or_create_player(session, callback.from_user.id)
    
    text = f"""🧰 <b>Задания</b>

🔥 Серия входов: <b>{player.login_streak} дней</b>

🦊 Лиса готовит для тебя задания...

<i>Эта функция скоро будет доступна!</i>
"""
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_back_to_den_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_my_prizes")
async def handle_my_prizes(callback: CallbackQuery, session: AsyncSession):
    """Мои призы"""
    await ensure_db()
    logger.info(f"[Gamification] fox_my_prizes от {callback.from_user.id}")
    
    prizes = await get_active_prizes(session, callback.from_user.id)
    
    if prizes:
        prizes_text = ""
        for prize in prizes:
            days_left = (prize.expires_at - prize.created_at).days
            expires_info = f"(истекает через {days_left}д)"
            prizes_text += f"• {prize.description or f'{prize.prize_type}: {prize.value}'} {expires_info}\n"
        
        text = f"""🎁 <b>Мои призы</b>

{prizes_text}
<i>Призы с днями VPN можно применить к подписке.</i>
<i>Призы истекают через 14 дней!</i>
"""
        # TODO: Добавить кнопки для применения призов
    else:
        text = """🎁 <b>Мои призы</b>

🦊 У тебя пока нет призов.

<i>Испытай удачу, чтобы получить награды!</i>
"""
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_back_to_den_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_balance")
async def handle_balance(callback: CallbackQuery, session: AsyncSession):
    """Баланс"""
    await ensure_db()
    logger.info(f"[Gamification] fox_balance от {callback.from_user.id}")
    
    player = await get_or_create_player(session, callback.from_user.id)
    
    # Курс: 50 Лискоинов = 25 рублей (2:1)
    rub_equivalent = player.coins / 2
    
    text = f"""🪙 <b>Баланс</b>

🪙 Лискоины: <b>{player.coins}</b>
💰 Эквивалент: <b>~{rub_equivalent:.0f} ₽</b>

✨ Свет Лисы: <b>{player.light}</b>

<i>Курс: 50 Лискоинов = 25 ₽</i>

<i>Выполняй задания и играй, чтобы заработать!</i>
"""
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_back_to_den_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_upgrades")
async def handle_upgrades(callback: CallbackQuery, session: AsyncSession):
    """Улучшения"""
    await ensure_db()
    logger.info(f"[Gamification] fox_upgrades от {callback.from_user.id}")
    text = """⭐ <b>Улучшения</b>

🦊 Лиса готовит для тебя улучшения...

<b>Скоро здесь появятся:</b>
• 🍀 Бусты удачи (+10-30% к редким призам)
• 🎫 Дополнительные попытки
• ✨ Особые возможности

<i>Эта функция скоро будет доступна!</i>
"""
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_back_to_den_kb(),
    )
    await callback.answer()


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
    
    await ensure_db()
    
    bet = int(callback.data.split("_")[-1])
    logger.info(f"[Casino] ИГРА! Ставка {bet}₽ от {callback.from_user.id}")
    await callback.answer()
    
    from .casino import (
        play_casino, can_play_casino,
        ROLLING, RESULT_LOSE, RESULT_WIN_X2, RESULT_WIN_X3
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
    
    # Анимация
    msg = await callback.message.answer(ROLLING.format(bet=bet))
    
    # Пауза 2-3 секунды для напряжения
    await asyncio.sleep(2.0)
    
    await msg.edit_text(
        f"🦊 <b>ЛИСЬЕ КАЗИНО</b>\n\n"
        f"Ставка: <b>{bet} ₽</b>\n\n"
        f"🎲 <i>Кость катится...</i>"
    )
    
    await asyncio.sleep(1.5)
    
    await msg.edit_text(
        f"🦊 <b>ЛИСЬЕ КАЗИНО</b>\n\n"
        f"Ставка: <b>{bet} ₽</b>\n\n"
        f"🦊 <i>Лиса смотрит на результат...</i>"
    )
    
    await asyncio.sleep(1.0)
    
    # ИГРА!
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
