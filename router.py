from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton

from handlers.utils import edit_or_send_message
from hooks.hooks import register_hook
from logger import logger

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


@router.callback_query(F.data.startswith("fox_"))
async def handle_fox_actions(callback: CallbackQuery):
    """Обработчик всех действий в Логове Лисы"""
    action = callback.data
    logger.info(f"[Gamification] Действие: {action} от {callback.from_user.id}")
    
    if action == "fox_den":
        return  # Уже обработано выше
    
    if action == "fox_try_luck":
        await callback.answer("🎰 Скоро здесь будет игра!", show_alert=True)
    elif action == "fox_quests":
        await callback.answer("🧰 Задания скоро появятся!", show_alert=True)
    elif action == "fox_my_prizes":
        await callback.answer("🎁 Призы скоро появятся!", show_alert=True)
    elif action == "fox_balance":
        await callback.answer("🪙 Баланс скоро появится!", show_alert=True)
    elif action == "fox_upgrades":
        await callback.answer("⭐ Улучшения скоро появятся!", show_alert=True)
    else:
        await callback.answer("Неизвестное действие", show_alert=True)
