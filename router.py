from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from handlers.utils import edit_or_send_message
from hooks.hooks import register_hook
from logger import logger

from .keyboards import build_fox_den_menu
from .texts import (
    BTN_BACK,
    FOX_DEN_BUTTON,
    FOX_DEN_WELCOME,
)


router = Router(name="gamification")


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
async def handle_fox_den(callback: CallbackQuery):
    """Главное меню Логова Лисы"""
    logger.info(f"[Gamification] Открытие Логова Лисы для {callback.from_user.id}")
    await edit_or_send_message(
        target_message=callback.message,
        text=FOX_DEN_WELCOME,
        reply_markup=build_fox_den_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_try_luck")
async def handle_try_luck(callback: CallbackQuery):
    """Испытать удачу"""
    logger.info(f"[Gamification] fox_try_luck от {callback.from_user.id}")
    text = """🎰 <b>Испытать удачу</b>

🦊 Лиса готовит для тебя испытание...

<i>Эта функция скоро будет доступна!</i>
"""
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_back_to_den_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_quests")
async def handle_quests(callback: CallbackQuery):
    """Задания"""
    logger.info(f"[Gamification] fox_quests от {callback.from_user.id}")
    text = """🧰 <b>Задания</b>

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
async def handle_my_prizes(callback: CallbackQuery):
    """Мои призы"""
    logger.info(f"[Gamification] fox_my_prizes от {callback.from_user.id}")
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
async def handle_balance(callback: CallbackQuery):
    """Баланс"""
    logger.info(f"[Gamification] fox_balance от {callback.from_user.id}")
    text = """🪙 <b>Баланс</b>

🦊 Твои Лискоины: <b>0</b>

<i>Выполняй задания и играй, чтобы заработать!</i>
"""
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_back_to_den_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox_upgrades")
async def handle_upgrades(callback: CallbackQuery):
    """Улучшения"""
    logger.info(f"[Gamification] fox_upgrades от {callback.from_user.id}")
    text = """⭐ <b>Улучшения</b>

🦊 Лиса готовит для тебя улучшения...

<i>Эта функция скоро будет доступна!</i>
"""
    await edit_or_send_message(
        target_message=callback.message,
        text=text,
        reply_markup=build_back_to_den_kb(),
    )
    await callback.answer()
