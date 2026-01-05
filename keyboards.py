from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .texts import (
    BTN_BACK,
    BTN_BALANCE,
    BTN_MY_PRIZES,
    BTN_QUESTS,
    BTN_TRY_LUCK,
    BTN_UPGRADES,
)


def build_fox_den_menu() -> InlineKeyboardMarkup:
    """Главное меню Логова Лисы"""
    builder = InlineKeyboardBuilder()
    
    builder.row(InlineKeyboardButton(text=BTN_TRY_LUCK, callback_data="fox_try_luck"))
    builder.row(InlineKeyboardButton(text="🦊 ЛИСЬЕ КАЗИНО 🔞", callback_data="fox_casino"))
    builder.row(InlineKeyboardButton(text=BTN_QUESTS, callback_data="fox_quests"))
    builder.row(
        InlineKeyboardButton(text=BTN_MY_PRIZES, callback_data="fox_my_prizes"),
        InlineKeyboardButton(text=BTN_BALANCE, callback_data="fox_balance"),
    )
    builder.row(InlineKeyboardButton(text=BTN_UPGRADES, callback_data="fox_upgrades"))
    builder.row(InlineKeyboardButton(text=BTN_BACK, callback_data="profile"))
    
    return builder.as_markup()
