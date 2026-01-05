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


@router.callback_query(F.data == "fox_try_luck")
async def handle_try_luck(callback: CallbackQuery):
    """Испытать удачу"""
    logger.info(f"[Gamification] fox_try_luck от {callback.from_user.id}")
    try:
        await callback.answer("🎰 Скоро здесь будет игра!", show_alert=True)
    except Exception as e:
        logger.error(f"[Gamification] Ошибка answer: {e}")


@router.callback_query(F.data == "fox_quests")
async def handle_quests(callback: CallbackQuery):
    """Задания"""
    logger.info(f"[Gamification] fox_quests от {callback.from_user.id}")
    try:
        await callback.answer("🧰 Задания скоро появятся!", show_alert=True)
    except Exception as e:
        logger.error(f"[Gamification] Ошибка answer: {e}")


@router.callback_query(F.data == "fox_my_prizes")
async def handle_my_prizes(callback: CallbackQuery):
    """Мои призы"""
    logger.info(f"[Gamification] fox_my_prizes от {callback.from_user.id}")
    try:
        await callback.answer("🎁 Призы скоро появятся!", show_alert=True)
    except Exception as e:
        logger.error(f"[Gamification] Ошибка answer: {e}")


@router.callback_query(F.data == "fox_balance")
async def handle_balance(callback: CallbackQuery):
    """Баланс"""
    logger.info(f"[Gamification] fox_balance от {callback.from_user.id}")
    try:
        await callback.answer("🪙 Баланс скоро появится!", show_alert=True)
    except Exception as e:
        logger.error(f"[Gamification] Ошибка answer: {e}")


@router.callback_query(F.data == "fox_upgrades")
async def handle_upgrades(callback: CallbackQuery):
    """Улучшения"""
    logger.info(f"[Gamification] fox_upgrades от {callback.from_user.id}")
    try:
        await callback.answer("⭐ Улучшения скоро появятся!", show_alert=True)
    except Exception as e:
        logger.error(f"[Gamification] Ошибка answer: {e}")
