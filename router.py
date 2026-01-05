from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton

from hooks.hooks import register_hook

from .keyboards import build_fox_den_menu
from .texts import FOX_DEN_BUTTON, FOX_DEN_WELCOME


router = Router(name="gamification")


# Хук для добавления кнопки в меню профиля
@register_hook("profile_menu")
async def add_fox_den_button(**kwargs):
    """Добавляет кнопку 'Логово Лисы' в меню профиля"""
    return {
        "button": InlineKeyboardButton(
            text=FOX_DEN_BUTTON,
            callback_data="fox:den"
        )
    }


@router.callback_query(F.data == "fox:den")
async def handle_fox_den(callback: CallbackQuery):
    """Главное меню Логова Лисы"""
    await callback.message.edit_text(
        text=FOX_DEN_WELCOME,
        reply_markup=build_fox_den_menu(),
    )
    await callback.answer()


@router.callback_query(F.data == "fox:try_luck")
async def handle_try_luck(callback: CallbackQuery):
    """Испытать удачу - заглушка"""
    await callback.answer("🎰 Скоро здесь будет игра!", show_alert=True)


@router.callback_query(F.data == "fox:quests")
async def handle_quests(callback: CallbackQuery):
    """Задания - заглушка"""
    await callback.answer("🧰 Задания скоро появятся!", show_alert=True)


@router.callback_query(F.data == "fox:my_prizes")
async def handle_my_prizes(callback: CallbackQuery):
    """Мои призы - заглушка"""
    await callback.answer("🎁 Призы скоро появятся!", show_alert=True)


@router.callback_query(F.data == "fox:balance")
async def handle_balance(callback: CallbackQuery):
    """Баланс - заглушка"""
    await callback.answer("🪙 Баланс скоро появится!", show_alert=True)


@router.callback_query(F.data == "fox:upgrades")
async def handle_upgrades(callback: CallbackQuery):
    """Улучшения - заглушка"""
    await callback.answer("⭐ Улучшения скоро появятся!", show_alert=True)
