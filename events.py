"""
События и бонусы (Выходные, Счастливый час и т.д.)
"""
from datetime import datetime
from zoneinfo import ZoneInfo

# Московское время для событий
TIMEZONE = ZoneInfo("Europe/Moscow")


def get_moscow_now() -> datetime:
    """Текущее время по Москве"""
    return datetime.now(TIMEZONE)


def is_weekend() -> bool:
    """Сегодня выходной? (суббота=5, воскресенье=6)"""
    now = get_moscow_now()
    return now.weekday() >= 5


def is_happy_hour() -> bool:
    """Сейчас счастливый час? (18:00-19:00 МСК)"""
    now = get_moscow_now()
    return 18 <= now.hour < 19


def get_weekend_bonus_spins() -> int:
    """Бонусные попытки за выходной"""
    return 1 if is_weekend() else 0


def get_happy_hour_boost() -> int:
    """Бонус к шансам в счастливый час (%)"""
    return 20 if is_happy_hour() else 0


def get_active_events() -> list[dict]:
    """Получить список активных событий"""
    events = []
    
    if is_weekend():
        events.append({
            "type": "weekend",
            "icon": "🎉",
            "name": "Выходной бонус",
            "description": "+1 бесплатная попытка!",
        })
    
    if is_happy_hour():
        events.append({
            "type": "happy_hour",
            "icon": "⏰",
            "name": "Счастливый час",
            "description": "+20% к редким призам!",
        })
    
    return events


def format_events_text() -> str:
    """Форматированный текст активных событий"""
    events = get_active_events()
    
    if not events:
        return ""
    
    lines = ["🎪 <b>Активные события:</b>"]
    for event in events:
        lines.append(f"{event['icon']} {event['name']}: {event['description']}")
    
    return "\n".join(lines) + "\n"


def get_next_happy_hour() -> str:
    """Когда следующий счастливый час"""
    now = get_moscow_now()
    
    if now.hour < 18:
        return "сегодня в 18:00 МСК"
    elif now.hour >= 19:
        return "завтра в 18:00 МСК"
    else:
        return "СЕЙЧАС!"
