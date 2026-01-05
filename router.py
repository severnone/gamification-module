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
        InlineKeyboardButton(text="📦 Сундук", callback_data="fox_play_chest"),
    )
    builder.row(
        InlineKeyboardButton(text="🎡 Колесо", callback_data="fox_play_wheel"),
    )
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    return builder.as_markup()


def build_chest_select_kb() -> InlineKeyboardMarkup:
    """Клавиатура выбора сундука"""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="📦 1", callback_data="fox_chest_1"),
        InlineKeyboardButton(text="📦 2", callback_data="fox_chest_2"),
        InlineKeyboardButton(text="📦 3", callback_data="fox_chest_3"),
    )
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_try_luck"))
    return builder.as_markup()


def build_after_game_kb(game_type: str = "slots") -> InlineKeyboardMarkup:
    """Клавиатура после игры"""
    builder = InlineKeyboardBuilder()
    
    # Кнопка повторить ту же игру
    game_buttons = {
        "slots": ("🎰 Ещё раз!", "fox_play_slots"),
        "chest": ("📦 Ещё раз!", "fox_play_chest"),
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

🦊 Выбери игру, в которую хочешь сыграть!
{test_mode_text}
🎫 Бесплатных попыток: <b>{player.free_spins}</b>
🪙 Лискоинов: <b>{player.coins}</b>

<b>🎰 Слоты</b> — крути барабаны, собирай комбинации!
<b>📦 Сундук</b> — открой сундук Лисы!
<b>🎡 Колесо</b> — крути колесо удачи!

<b>Призы:</b> 3 одинаковых = ДЖЕКПОТ 🦊
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


@router.callback_query(F.data == "fox_play_chest")
async def handle_play_chest(callback: CallbackQuery, session: AsyncSession):
    """Выбор сундука — интерактивный экран"""
    await ensure_db()
    logger.info(f"[Gamification] Выбор сундука от {callback.from_user.id}")
    await callback.answer()
    
    text = """📦 <b>СУНДУКИ ЛИСЫ</b>

🦊 Лиса спрятала приз в один из сундуков!

  📦      📦      📦
   1        2        3

<b>Выбери сундук, который хочешь открыть!</b>

<i>В одном из них — награда...</i>
"""
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_chest_select_kb(),
    )


@router.callback_query(F.data.startswith("fox_chest_"))
async def handle_chest_choice(callback: CallbackQuery, session: AsyncSession):
    """Открытие выбранного сундука"""
    await ensure_db()
    
    # Получаем номер выбранного сундука (1, 2, 3)
    chest_num = int(callback.data.split("_")[-1])
    chosen_chest = chest_num - 1  # Индекс 0, 1, 2
    
    logger.info(f"[Gamification] Открытие сундука {chest_num} от {callback.from_user.id}")
    await callback.answer()
    
    # Удаляем старое сообщение
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    # Начальное сообщение
    msg = await callback.message.answer(
        "📦 <b>СУНДУКИ ЛИСЫ</b>\n\n"
        f"🎯 Ты выбрал сундук <b>№{chest_num}</b>!\n\n"
        "<i>Открываем...</i>"
    )
    
    # Запускаем игру с выбранным сундуком
    result = await play_game(
        session, 
        callback.from_user.id, 
        use_coins=False,
        message=msg,
        game_type="chest",
        test_mode=TEST_MODE,
        chosen_chest=chosen_chest,
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
    
    await msg.edit_text(text, reply_markup=build_after_game_kb("chest"))


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
