import asyncio

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from handlers.utils import edit_or_send_message
from hooks.hooks import register_hook
from logger import logger

from .db import get_active_prizes, get_or_create_player
from .init_db import init_gamification_db
from .keyboards import build_fox_den_menu
from .texts import (
    BTN_BACK,
    FOX_DEN_BUTTON,
    FOX_DEN_WELCOME,
)


router = Router(name="gamification")


# Инициализация БД при загрузке модуля
asyncio.get_event_loop().run_until_complete(init_gamification_db())


def build_back_to_den_kb() -> InlineKeyboardMarkup:
    """Кнопка назад в Логово"""
    builder = InlineKeyboardBuilder()
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
    logger.info(f"[Gamification] Открытие Логова Лисы для {callback.from_user.id}")
    
    # Получаем или создаём игрока
    player = await get_or_create_player(session, callback.from_user.id)
    
    text = f"""🦊 <b>Добро пожаловать в Логово Лисы!</b>

🪙 Лискоины: <b>{player.coins}</b>
🎮 Игр сыграно: <b>{player.total_games}</b>
🏆 Выигрышей: <b>{player.total_wins}</b>

Испытай удачу, выполняй задания и получай призы!
"""
    
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_fox_den_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_try_luck")
async def handle_try_luck(callback: CallbackQuery, session: AsyncSession):
    """Испытать удачу"""
    logger.info(f"[Gamification] fox_try_luck от {callback.from_user.id}")
    
    player = await get_or_create_player(session, callback.from_user.id)
    
    text = f"""🎰 <b>Испытать удачу</b>

🦊 Лиса готовит для тебя испытание...

🎫 Бесплатных попыток: <b>{player.free_spins}</b>
🪙 Лискоинов: <b>{player.coins}</b>

<i>Игровая механика скоро будет доступна!</i>
"""
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_back_to_den_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_quests")
async def handle_quests(callback: CallbackQuery, session: AsyncSession):
    """Задания"""
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
    logger.info(f"[Gamification] fox_my_prizes от {callback.from_user.id}")
    
    prizes = await get_active_prizes(session, callback.from_user.id)
    
    if prizes:
        prizes_text = ""
        for prize in prizes:
            expires_in = (prize.expires_at - prize.created_at).days
            prizes_text += f"• {prize.description or f'{prize.prize_type}: {prize.value}'}\n"
        
        text = f"""🎁 <b>Мои призы</b>

{prizes_text}
<i>Нажмите на приз, чтобы использовать</i>
"""
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
