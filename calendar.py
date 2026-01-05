"""
7-дневный календарь наград
"""
from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Награды за каждый день календаря
CALENDAR_REWARDS = {
    1: {"coins": 10, "text": "10 🪙"},
    2: {"coins": 15, "text": "15 🪙"},
    3: {"coins": 20, "spins": 1, "text": "20 🪙 + 🎫"},
    4: {"coins": 25, "text": "25 🪙"},
    5: {"coins": 30, "text": "30 🪙"},
    6: {"coins": 40, "spins": 1, "text": "40 🪙 + 🎫"},
    7: {"coins": 50, "light": 5, "spins": 2, "text": "50 🪙 + 5✨ + 2🎫"},  # Бонусный день!
}


def can_claim_today(last_claim: datetime | None) -> bool:
    """Можно ли забрать награду сегодня"""
    if last_claim is None:
        return True
    
    today = datetime.utcnow().date()
    last_claim_date = last_claim.date()
    
    return today > last_claim_date


def is_streak_broken(last_claim: datetime | None) -> bool:
    """Прервана ли серия (пропущен день)"""
    if last_claim is None:
        return False  # Новый игрок, серия не прервана
    
    today = datetime.utcnow().date()
    last_claim_date = last_claim.date()
    days_diff = (today - last_claim_date).days
    
    # Если пропустил больше 1 дня — серия прервана
    return days_diff > 1


def get_calendar_status(calendar_day: int, last_claim: datetime | None) -> dict:
    """
    Получить статус календаря.
    
    Returns:
        {
            "can_claim": bool,
            "current_day": int (1-7),
            "streak_broken": bool,
            "reward": dict,
            "is_completed": bool,
        }
    """
    streak_broken = is_streak_broken(last_claim)
    
    # Если серия прервана — сброс к дню 1
    if streak_broken:
        current_day = 1
    else:
        # Следующий день календаря
        current_day = min(calendar_day + 1, 7) if can_claim_today(last_claim) else calendar_day
    
    # Если уже собрал все 7 дней и сегодня уже забирал — календарь завершён
    is_completed = calendar_day >= 7 and not can_claim_today(last_claim)
    
    # Если завершил 7 дней и прошёл новый день — начинаем заново
    if calendar_day >= 7 and can_claim_today(last_claim):
        current_day = 1
        is_completed = False
    
    can_claim = can_claim_today(last_claim)
    reward = CALENDAR_REWARDS.get(current_day, CALENDAR_REWARDS[1])
    
    return {
        "can_claim": can_claim,
        "current_day": current_day,
        "streak_broken": streak_broken,
        "reward": reward,
        "is_completed": is_completed,
    }


def build_calendar_text(calendar_day: int, last_claim: datetime | None) -> str:
    """Построить текст календаря"""
    status = get_calendar_status(calendar_day, last_claim)
    
    lines = ["📅 <b>7-дневный календарь</b>\n"]
    
    if status["streak_broken"]:
        lines.append("⚠️ <i>Серия прервана! Начинаем заново.</i>\n")
    
    lines.append("Заходи каждый день и получай награды!\n")
    
    # Отображаем дни
    for day in range(1, 8):
        reward = CALENDAR_REWARDS[day]
        
        if day < status["current_day"] or (day == status["current_day"] and not status["can_claim"]):
            # Уже забран
            icon = "✅"
        elif day == status["current_day"] and status["can_claim"]:
            # Можно забрать сегодня
            icon = "🎁"
        else:
            # Будущий день
            icon = "🔒"
        
        day_text = f"День {day}" if day < 7 else "🌟 День 7"
        lines.append(f"{icon} {day_text}: {reward['text']}")
    
    if status["can_claim"]:
        lines.append(f"\n🎁 <b>Забери награду за день {status['current_day']}!</b>")
    elif status["is_completed"]:
        lines.append("\n🎉 <b>Календарь завершён! Завтра начнётся новый.</b>")
    else:
        lines.append("\n⏰ <i>Приходи завтра за наградой!</i>")
    
    return "\n".join(lines)


def build_calendar_kb(can_claim: bool) -> InlineKeyboardBuilder:
    """Клавиатура календаря"""
    builder = InlineKeyboardBuilder()
    
    if can_claim:
        builder.row(InlineKeyboardButton(
            text="🎁 Забрать награду!",
            callback_data="fox_calendar_claim"
        ))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="fox_den"))
    
    return builder
