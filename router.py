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


def build_try_luck_kb(has_free_spin: bool, coins: int) -> InlineKeyboardMarkup:
    """Клавиатура для игры"""
    builder = InlineKeyboardBuilder()
    
    if has_free_spin:
        builder.row(InlineKeyboardButton(
            text="🎰 Испытать удачу (бесплатно)",
            callback_data="fox_spin_free"
        ))
    else:
        can_afford = coins >= SPIN_COST_COINS
        btn_text = f"🎰 Испытать удачу ({SPIN_COST_COINS} 🪙)"
        if can_afford:
            builder.row(InlineKeyboardButton(text=btn_text, callback_data="fox_spin_coins"))
        else:
            builder.row(InlineKeyboardButton(text=f"❌ {btn_text}", callback_data="fox_no_coins"))
    
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="fox_den"))
    return builder.as_markup()


def build_after_game_kb() -> InlineKeyboardMarkup:
    """Клавиатура после игры"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎰 Ещё раз!", callback_data="fox_try_luck"))
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
    """Меню испытания удачи"""
    await ensure_db()
    logger.info(f"[Gamification] fox_try_luck от {callback.from_user.id}")
    
    await check_and_reset_daily_spin(session, callback.from_user.id)
    player = await get_or_create_player(session, callback.from_user.id)
    
    has_free = player.free_spins > 0
    
    text = f"""🎰 <b>Испытать удачу</b>

🦊 Лиса приготовила для тебя испытание!

🎫 Бесплатных попыток: <b>{player.free_spins}</b>
🪙 Лискоинов: <b>{player.coins}</b>

<b>Возможные призы:</b>
• 📅 Дни VPN (1-60 дней)
• 🪙 Лискоины (10-200)
• 💸 Рубли на баланс
• 🍀 Бусты удачи

<i>Стоимость попытки: {SPIN_COST_COINS} Лискоинов</i>
"""
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_try_luck_kb(has_free, player.coins),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_spin_free")
async def handle_spin_free(callback: CallbackQuery, session: AsyncSession):
    """Бесплатная попытка"""
    await ensure_db()
    logger.info(f"[Gamification] fox_spin_free от {callback.from_user.id}")
    await callback.answer()
    
    # Удаляем старое сообщение (может содержать фото)
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    # Отправляем новое текстовое сообщение для анимации
    msg = await callback.message.answer(
        "🎰 <b>Крутим барабаны...</b>\n\n"
        "┃ 🔄 ┃ 🔄 ┃ 🔄 ┃\n\n"
        "<i>Удачи!</i>"
    )
    
    result = await play_game(
        session, 
        callback.from_user.id, 
        use_coins=False,
        message=msg,
    )
    
    if not result["success"]:
        if result["error"] == "no_spins":
            await msg.edit_text(
                "❌ <b>Нет бесплатных попыток!</b>\n\n"
                "Попробуйте завтра или сыграйте за Лискоины.",
                reply_markup=build_try_luck_kb(False, 0)
            )
            return
        await msg.edit_text(f"❌ {result['error']}", reply_markup=build_back_to_den_kb())
        return
    
    text = format_prize_message(
        result["game_type"],
        result["prize"],
        result["symbols"],
        result["coins_spent"],
        result["new_balance"],
    )
    
    await msg.edit_text(text, reply_markup=build_after_game_kb())


@router.callback_query(F.data == "fox_spin_coins")
async def handle_spin_coins(callback: CallbackQuery, session: AsyncSession):
    """Попытка за Лискоины"""
    await ensure_db()
    logger.info(f"[Gamification] fox_spin_coins от {callback.from_user.id}")
    await callback.answer()
    
    # Удаляем старое сообщение (может содержать фото)
    try:
        await callback.message.delete()
    except Exception:
        pass
    
    # Отправляем новое текстовое сообщение для анимации
    msg = await callback.message.answer(
        "🎰 <b>Крутим барабаны...</b>\n\n"
        "┃ 🔄 ┃ 🔄 ┃ 🔄 ┃\n\n"
        "<i>Удачи!</i>"
    )
    
    result = await play_game(
        session, 
        callback.from_user.id, 
        use_coins=True,
        message=msg,
    )
    
    if not result["success"]:
        player = await get_or_create_player(session, callback.from_user.id)
        await msg.edit_text(
            f"❌ <b>Ошибка:</b> {result['error']}",
            reply_markup=build_try_luck_kb(player.free_spins > 0, player.coins)
        )
        return
    
    text = format_prize_message(
        result["game_type"],
        result["prize"],
        result["symbols"],
        result["coins_spent"],
        result["new_balance"],
    )
    
    await msg.edit_text(text, reply_markup=build_after_game_kb())


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
