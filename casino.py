"""
🦊 ЛИСЬЕ КАЗИНО — Психоэмоциональная игра на реальный баланс
⚠️ Ставки списываются с реального баланса пользователя!

Механики:
- Вход с напряжением (динамические предупреждения)
- Двухфазная ставка (забрать/рискнуть)
- Near Miss (почти выиграл)
- Серии побед/поражений
- FOMO (ночной режим, золотой час)
- Прогрессивный кулдаун
- Холодный тон Лисы
- Статистика сессии
"""
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.users import get_balance, update_balance
from logger import logger

from .models import FoxCasinoGame, FoxCasinoSession, FoxCasinoProfile


# ==================== НАСТРОЙКИ ====================

# 🧪 ТЕСТОВЫЙ РЕЖИМ — отключает кулдауны и лимиты!
# True = без ограничений, False = нормальная работа
CASINO_TEST_MODE = False

# Ставки (всегда целые рубли!)
MIN_BET = 10
MAX_BET = 500
FIXED_BETS = [10, 25, 50, 100]

# Дневные лимиты
DAILY_LOSS_LIMIT = 1000  # Макс проигрыш в день
DAILY_GAMES_LIMIT = 50   # Макс игр в день

# ==================== МАТЕМАТИКА (маржа ~40%) ====================
# Базовые шансы (сумма = 100%)
BASE_CHANCE_LOSE = 65.0      # ❌ Проигрыш
BASE_CHANCE_WIN_X15 = 22.0   # ✅ ×1.5 (промежуточный, можно рискнуть)
BASE_CHANCE_WIN_X2 = 9.0     # ✅ ×2
BASE_CHANCE_WIN_X3 = 3.0     # 🔥 ×3
BASE_CHANCE_WIN_X5 = 0.8     # 💎 ×5 (редкий)
BASE_CHANCE_JACKPOT = 0.2    # 🏆 Джекпот (только при проигрыше!)

# Шансы на второй фазе (если рискнул после ×1.5)
PHASE2_CHANCE_LOSE = 60
PHASE2_CHANCE_WIN_X2 = 30
PHASE2_CHANCE_WIN_X3 = 8
PHASE2_CHANCE_WIN_X5 = 2

# Near miss шанс (вероятность что проигрыш будет "почти выиграл")
NEAR_MISS_CHANCE = 35  # 35% проигрышей = near miss

# Джекпот
JACKPOT_CONTRIBUTION = 0.05  # 5% от каждой ставки идёт в джекпот
JACKPOT_MIN_POOL = 100       # Минимальный джекпот для выигрыша

# ==================== НОВАЯ СХЕМА КУЛДАУНОВ ====================
# 1-2 проигрыша подряд → без ограничений
# 3 проигрыша подряд → кулдаун 30-60 сек
# 5 проигрышей подряд → кулдаун 10-30 мин
# НИКАКИХ суточных кулдаунов!

COOLDOWN_THRESHOLD_SMALL = 3   # После 3 проигрышей подряд → маленький кулдаун
COOLDOWN_SMALL_MIN = 30        # 30-60 секунд
COOLDOWN_SMALL_MAX = 60

COOLDOWN_THRESHOLD_BIG = 5     # После 5 проигрышей подряд → большой кулдаун  
COOLDOWN_BIG_MIN = 600         # 10-30 минут (600-1800 секунд)
COOLDOWN_BIG_MAX = 1800

# Атмосферные фразы для кулдауна
COOLDOWN_PHRASES = [
    "🦊 Лиса протирает кости...",
    "🦊 Лиса раскладывает карты...",
    "🦊 Лиса считает выигрыш...",
    "🦊 Лиса готовит стол...",
    "🦊 Лиса перемешивает колоду...",
    "🦊 Лиса зажигает свечи...",
    "🦊 Лиса наводит порядок...",
]

# Самоблокировка
SELF_BLOCK_DAYS = 7

# Ночной режим (UTC)
NIGHT_MODE_START = 22  # 22:00
NIGHT_MODE_END = 6     # 06:00
NIGHT_MODE_X3_BONUS = 1  # +1% к шансу x3

# Золотой час
GOLDEN_HOUR_DURATION = 60  # минут
GOLDEN_HOUR_BONUS = 3      # +3% к шансу x2


# ==================== ФРАЗЫ ЛИСЫ ====================

# Приветствие в зависимости от истории
WELCOME_FIRST_TIME = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

Первый раз?
Лиса ждёт.

⚠️ Ставка списывается с <b>реального баланса</b>.
Проигрыш — без возврата.

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

WELCOME_AFTER_LOSS = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

Ты вернулся.
Лиса помнит: <b>{last_result:+.0f} ₽</b> в прошлый раз.

⚠️ Ставка с реального баланса. Без возврата.

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

WELCOME_AFTER_WIN = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

Снова здесь.
Удача не длится вечно.

⚠️ Ставка с реального баланса. Без возврата.

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

WELCOME_FREQUENT = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

Это твой <b>{visits}-й</b> визит.
Лиса считает.

⚠️ Ставка с реального баланса. Без возврата.

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

WELCOME_NIGHT = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

🌙 Лиса не спит.
Ночью шансы... другие.

⚠️ Ставка с реального баланса. Без возврата.

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

WELCOME_GOLDEN_HOUR = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

✨ <b>Золотой час</b>
Лиса благосклонна. Осталось <b>{minutes}</b> мин.

⚠️ Ставка с реального баланса. Без возврата.

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

# Блокировки
BLOCKED_NO_BALANCE = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

Кошелёк пуст.
Мин. ставка: <b>{min_bet} ₽</b>
Баланс: <b>{balance:.0f} ₽</b>

<i>Лиса ждёт.</i>
"""

BLOCKED_DAILY_LIMIT = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

⛔ Достаточно.
Сегодня: <b>-{lost:.0f} ₽</b>
Лимит: <b>{limit} ₽</b>

<i>Вернись завтра.</i>
"""

BLOCKED_DAILY_GAMES = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

⛔ <b>{games}</b> игр сегодня.
Хватит.

<i>Вернись завтра.</i>
"""

BLOCKED_COOLDOWN = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

{phrase}

⏳ Подожди <b>{seconds}</b> сек.
"""

BLOCKED_FORCED_BREAK = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

⛔ <b>{streak}</b> проигрышей подряд.
Отдохни.

Вернуться через: <b>{time}</b>

<i>Лиса советует остыть.</i>
"""

BLOCKED_SELF = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

🔒 Ты заблокировал себе вход.
Осталось: <b>{days}</b> дн.

<i>Это было твоё решение.</i>
"""

# Подтверждение ставки
BET_CONFIRM = """🦊 Ставка: <b>{bet} ₽</b>

⚠️ Сумма спишется с <b>реального баланса</b>.
Проигрыш = потеря денег.

Продолжить?
"""

# Анимация
ROLLING_TEXTS = [
    "🎲 Лиса бросает кость...",
    "🎲 Кость катится...",
    "🎲 ...",
    "🎲 Лиса наблюдает...",
]

# Фаза 1 — промежуточный результат
PHASE1_WIN_X15 = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

🎲 Промежуточный результат

Ставка: <b>{bet} ₽</b>
Сейчас: <b>×1.5</b> → <b>{current} ₽</b>

<i>Забрать или рискнуть?</i>

🔸 <b>Забрать</b> — получишь {current} ₽
🔸 <b>Рискнуть</b> — шанс на ×2 или ×3, но можешь потерять всё
"""

# Результаты — ПРОИГРЫШ
RESULT_LOSE = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

❌ <b>ПРОИГРЫШ</b>

Ставка: {bet} ₽
Потеряно: <b>-{bet} ₽</b>

💬 <i>«{comment}»</i>

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

# Near miss — почти выиграл
RESULT_NEAR_MISS = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

❌ <b>ПРОИГРЫШ</b>

Ставка: {bet} ₽
Потеряно: <b>-{bet} ₽</b>

⚡ <i>«{near_miss_text}»</i>

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

# Выигрыши
RESULT_WIN_X15 = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

✅ <b>ВЫИГРЫШ ×1.5</b>

Ставка: {bet} ₽
Получено: <b>+{winnings:.0f} ₽</b>

💬 <i>«{comment}»</i>

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

RESULT_WIN_X2 = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

✅ <b>ВЫИГРЫШ ×2</b>

Ставка: {bet} ₽
Получено: <b>+{winnings:.0f} ₽</b>

💬 <i>«{comment}»</i>

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

RESULT_WIN_X3 = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

🔥 <b>КРУПНЫЙ ВЫИГРЫШ ×3</b>

Ставка: {bet} ₽
Получено: <b>+{winnings:.0f} ₽</b>

💬 <i>«{comment}»</i>

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

RESULT_WIN_X5 = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

💎 <b>ОГРОМНЫЙ ВЫИГРЫШ ×5!</b>

Ставка: {bet} ₽
Получено: <b>+{winnings:.0f} ₽</b>

💬 <i>«{comment}»</i>

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

RESULT_JACKPOT = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

🏆🏆🏆 <b>ДЖЕКПОТ!!!</b> 🏆🏆🏆

Ты проиграл ставку... НО СОРВАЛ ДЖЕКПОТ!

💰 Джекпот: <b>+{jackpot} ₽</b>

💬 <i>«{comment}»</i>

💰 Баланс: <b>{balance:.0f} ₽</b>

<i>Лиса в шоке. Такое бывает раз в жизни.</i>
"""

# Результат рискованной игры (фаза 2)
RESULT_RISK_LOSE = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

❌ <b>ПРОИГРЫШ</b>
<i>Риск не оправдался.</i>

Было: {had} ₽
Потеряно: <b>всё</b>

💬 <i>«{comment}»</i>

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

RESULT_RISK_WIN = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

🔥 <b>РИСК ОПРАВДАЛСЯ — ×{multiplier}!</b>

Ставка: {bet} ₽
Получено: <b>+{winnings:.0f} ₽</b>

💬 <i>«{comment}»</i>

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

# Статистика сессии при выходе
SESSION_EXIT = """🦊 <b>ЛИСЬЕ КАЗИНО</b> 🔞

━━━━━━━━━━━━━━━━━━
📊 <b>Итог сессии</b>

🎲 Игр: <b>{games}</b>
💰 Поставлено: <b>{wagered:.0f} ₽</b>
{result_line}

{streak_info}
━━━━━━━━━━━━━━━━━━

{fox_comment}
"""

# Фразы Лисы (холодные, наблюдающие)
FOX_COMMENTS_LOSE = [
    "Лиса забрала своё.",
    "Так бывает.",
    "Деньги любят тишину.",
    "Не повезло.",
    "Кость решила.",
    "Лиса сыта.",
]

FOX_COMMENTS_NEAR_MISS = [
    "Одно очко. Всего одно.",
    "Ты был близко.",
    "Почти...",
    "Редкий момент. Но нет.",
    "Следующий бросок был бы другим.",
    "Кость дрогнула на краю.",
]

FOX_COMMENTS_WIN_SMALL = [
    "Забирай.",
    "Небольшая удача.",
    "Это случается.",
    "Лиса отпустила.",
]

FOX_COMMENTS_WIN_X2 = [
    "Лиса недовольна.",
    "Ты забрал своё.",
    "Удача на твоей стороне. Пока.",
    "Интересно.",
]

FOX_COMMENTS_WIN_X3 = [
    "Лиса ошиблась. Больше так не будет.",
    "Редкость.",
    "Запомни этот момент.",
    "Такого не было давно.",
]

FOX_COMMENTS_WIN_X5 = [
    "Невероятно.",
    "Лиса в замешательстве.",
    "Это... неожиданно.",
    "Больше такого не повторится.",
    "Уходи, пока можешь.",
]

FOX_COMMENTS_JACKPOT = [
    "Лиса... потеряла дар речи.",
    "Это было... невозможно.",
    "Ты только что сделал невозможное.",
    "Легенда.",
]

FOX_COMMENTS_RISK_LOSE = [
    "Жадность.",
    "Надо было забрать.",
    "Риск — это выбор.",
    "Ты знал, на что шёл.",
]

FOX_COMMENTS_RISK_WIN = [
    "Смелость.",
    "Лиса уважает.",
    "Редкое решение, редкий исход.",
]

FOX_COMMENTS_EXIT_PLUS = [
    "🦊 Уходишь в плюсе. Умно.",
    "🦊 Лиса запомнила.",
    "🦊 До встречи.",
]

FOX_COMMENTS_EXIT_MINUS = [
    "🦊 Вернёшься закрыть?",
    "🦊 Лиса подождёт.",
    "🦊 Минус остаётся.",
]

FOX_COMMENTS_EXIT_ZERO = [
    "🦊 Ни туда, ни сюда.",
    "🦊 Ничья?",
]

# Комментарии к сериям
STREAK_WIN_2 = "🔥 Серия: 2 победы"
STREAK_WIN_3 = "🔥 Серия: 3 победы — редкость"
STREAK_WIN_4 = "🔥 Серия: 4+ — Лиса напряглась"
STREAK_LOSE_3 = "❄️ 3 проигрыша подряд"
STREAK_LOSE_5 = "❄️ 5 проигрышей — достаточно"


# ==================== ВСПОМОГАТЕЛЬНЫЕ КЛАССЫ ====================

@dataclass
class CasinoResult:
    """Результат игры в казино"""
    outcome: str  # "lose", "near_miss", "win_x15", "win_x2", "win_x3", "win_x5", "jackpot"
    bet: int  # Целые рубли!
    multiplier: float
    winnings: int  # чистый выигрыш (может быть отрицательным), целые рубли
    new_balance: int  # Целые рубли
    comment: str
    near_miss_text: Optional[str] = None
    phase: int = 1
    was_risk: bool = False
    jackpot_amount: int = 0  # Сумма джекпота если выиграл


@dataclass 
class Phase1Result:
    """Результат первой фазы (для двухфазной игры)"""
    can_risk: bool  # Может ли рискнуть
    current_multiplier: float  # 1.5 или сразу финал
    current_value: float  # Текущая сумма
    bet: float
    balance: float


# ==================== ФУНКЦИИ ПРОФИЛЯ ====================

async def get_or_create_casino_profile(session: AsyncSession, tg_id: int) -> FoxCasinoProfile:
    """Получить или создать профиль казино."""
    result = await session.execute(
        select(FoxCasinoProfile).where(FoxCasinoProfile.tg_id == tg_id)
    )
    profile = result.scalar_one_or_none()
    
    if not profile:
        profile = FoxCasinoProfile(tg_id=tg_id)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
    
    return profile


async def reset_daily_stats_if_needed(session: AsyncSession, profile: FoxCasinoProfile):
    """Сбросить дневную статистику если нужно."""
    today = datetime.utcnow().date()
    
    if profile.daily_reset_date is None or profile.daily_reset_date.date() < today:
        profile.daily_games = 0
        profile.daily_lost = 0
        profile.daily_won = 0
        profile.daily_reset_date = datetime.utcnow()
        profile.games_in_row = 0
        await session.commit()


# ==================== ПРОВЕРКИ ДОСТУПА ====================

async def can_enter_casino(session: AsyncSession, tg_id: int) -> tuple[bool, str, dict]:
    """
    Проверить, может ли игрок войти в казино.
    Возвращает (можно ли, причина блокировки, данные для шаблона).
    """
    profile = await get_or_create_casino_profile(session, tg_id)
    await reset_daily_stats_if_needed(session, profile)
    
    balance = await get_balance(session, tg_id)
    now = datetime.utcnow()
    
    # В тестовом режиме пропускаем все ограничения кроме баланса
    if not CASINO_TEST_MODE:
        # Самоблокировка
        if profile.blocked_until and profile.blocked_until > now:
            days_left = (profile.blocked_until - now).days + 1
            return False, "self_blocked", {"days": days_left}
        
        # Принудительный перерыв
        if profile.forced_break_until and profile.forced_break_until > now:
            remaining = profile.forced_break_until - now
            time_str = format_timedelta(remaining)
            return False, "forced_break", {
                "streak": FORCED_BREAK_AFTER_LOSSES,
                "time": time_str
            }
        
        # Кулдаун между играми (только после проигрыша)
        if profile.cooldown_until and profile.cooldown_until > now:
            remaining = (profile.cooldown_until - now).total_seconds()
            phrase = random.choice(COOLDOWN_PHRASES)
            return False, "cooldown", {"seconds": int(remaining), "phrase": phrase}
        
        # Дневной лимит проигрыша
        if profile.daily_lost >= DAILY_LOSS_LIMIT:
            return False, "daily_limit", {"lost": profile.daily_lost, "limit": DAILY_LOSS_LIMIT}
        
        # Дневной лимит игр
        if profile.daily_games >= DAILY_GAMES_LIMIT:
            return False, "daily_games", {"games": profile.daily_games}
    
    # Баланс всегда проверяем (даже в тестовом режиме)
    if balance < MIN_BET:
        return False, "no_balance", {"min_bet": MIN_BET, "balance": balance}
    
    return True, "ok", {"balance": balance}


async def can_play_bet(session: AsyncSession, tg_id: int, bet: float) -> tuple[bool, str]:
    """Проверить конкретную ставку."""
    balance = await get_balance(session, tg_id)
    
    if balance < bet:
        return False, "no_balance"
    if bet < MIN_BET:
        return False, "min_bet"
    if bet > MAX_BET:
        return False, "max_bet"
    
    return True, "ok"


# ==================== ПРИВЕТСТВЕННЫЕ СООБЩЕНИЯ ====================

def is_night_mode() -> bool:
    """Проверить, ночной ли режим."""
    hour = datetime.utcnow().hour
    return hour >= NIGHT_MODE_START or hour < NIGHT_MODE_END


async def get_welcome_message(session: AsyncSession, tg_id: int, balance: float) -> str:
    """Получить приветственное сообщение в зависимости от истории."""
    profile = await get_or_create_casino_profile(session, tg_id)
    
    # Золотой час
    if profile.golden_hour_start:
        remaining = profile.golden_hour_start + timedelta(minutes=GOLDEN_HOUR_DURATION) - datetime.utcnow()
        if remaining.total_seconds() > 0:
            return WELCOME_GOLDEN_HOUR.format(
                balance=balance,
                minutes=int(remaining.total_seconds() / 60)
            )
    
    # Ночной режим
    if is_night_mode():
        return WELCOME_NIGHT.format(balance=balance)
    
    # Первый визит
    if profile.total_visits == 0:
        return WELCOME_FIRST_TIME.format(balance=balance)
    
    # После проигрыша
    if profile.last_session_result < 0:
        return WELCOME_AFTER_LOSS.format(
            balance=balance,
            last_result=profile.last_session_result
        )
    
    # После выигрыша
    if profile.last_session_result > 0:
        return WELCOME_AFTER_WIN.format(balance=balance)
    
    # Частый посетитель
    if profile.total_visits >= 5:
        return WELCOME_FREQUENT.format(
            balance=balance,
            visits=profile.total_visits + 1
        )
    
    # По умолчанию
    return WELCOME_FIRST_TIME.format(balance=balance)


# ==================== СЕССИИ ====================

async def start_session(session: AsyncSession, tg_id: int) -> FoxCasinoSession:
    """Начать новую сессию казино."""
    profile = await get_or_create_casino_profile(session, tg_id)
    
    # Инкрементируем визиты
    profile.total_visits += 1
    
    # Создаём сессию
    casino_session = FoxCasinoSession(tg_id=tg_id)
    session.add(casino_session)
    await session.commit()
    await session.refresh(casino_session)
    
    # Привязываем к профилю
    profile.current_session_id = casino_session.id
    await session.commit()
    
    logger.info(f"[Casino] Начата сессия #{casino_session.id} для {tg_id}")
    return casino_session


async def get_current_session(session: AsyncSession, tg_id: int) -> Optional[FoxCasinoSession]:
    """Получить текущую активную сессию."""
    profile = await get_or_create_casino_profile(session, tg_id)
    
    if not profile.current_session_id:
        return None
    
    result = await session.execute(
        select(FoxCasinoSession)
        .where(FoxCasinoSession.id == profile.current_session_id)
        .where(FoxCasinoSession.is_active == True)
    )
    return result.scalar_one_or_none()


async def end_session(session: AsyncSession, tg_id: int) -> Optional[str]:
    """Завершить сессию и вернуть текст статистики."""
    profile = await get_or_create_casino_profile(session, tg_id)
    casino_session = await get_current_session(session, tg_id)
    
    if not casino_session:
        return None
    
    # Закрываем сессию
    casino_session.is_active = False
    casino_session.ended_at = datetime.utcnow()
    
    # Сохраняем результат в профиль
    profile.last_session_result = casino_session.net_result
    profile.last_session_games = casino_session.games_played
    profile.current_session_id = None
    profile.games_in_row = 0
    
    await session.commit()
    
    # Формируем текст
    if casino_session.games_played == 0:
        return None
    
    # Результат
    if casino_session.net_result > 0:
        result_line = f"📈 Итог: <b>+{casino_session.net_result:.0f} ₽</b>"
        fox_comment = random.choice(FOX_COMMENTS_EXIT_PLUS)
    elif casino_session.net_result < 0:
        result_line = f"📉 Итог: <b>{casino_session.net_result:.0f} ₽</b>"
        fox_comment = random.choice(FOX_COMMENTS_EXIT_MINUS)
    else:
        result_line = "📊 Итог: <b>0 ₽</b>"
        fox_comment = random.choice(FOX_COMMENTS_EXIT_ZERO)
    
    # Серии
    streak_info = ""
    if casino_session.max_win_streak >= 2:
        streak_info = f"🔥 Лучшая серия: {casino_session.max_win_streak} побед\n"
    if casino_session.max_lose_streak >= 3:
        streak_info += f"❄️ Худшая серия: {casino_session.max_lose_streak} проигрышей"
    
    return SESSION_EXIT.format(
        games=casino_session.games_played,
        wagered=casino_session.total_bet,
        result_line=result_line,
        streak_info=streak_info.strip(),
        fox_comment=fox_comment,
    )


# ==================== ИГРОВАЯ ЛОГИКА ====================

async def add_to_jackpot(session: AsyncSession, amount: int):
    """Добавить в джекпот."""
    from .jackpot import get_or_create_jackpot
    jackpot = await get_or_create_jackpot(session)
    jackpot.pool += amount
    await session.commit()


async def win_jackpot(session: AsyncSession, tg_id: int) -> int:
    """Выиграть джекпот. Возвращает сумму."""
    from .jackpot import get_or_create_jackpot, FoxJackpotWin, JACKPOT_START_POOL
    jackpot = await get_or_create_jackpot(session)
    
    amount = jackpot.pool
    
    # Сбрасываем джекпот
    jackpot.pool = JACKPOT_START_POOL
    jackpot.last_winner_id = tg_id
    jackpot.last_win_amount = amount
    jackpot.last_win_date = datetime.utcnow()
    jackpot.total_won += amount
    
    # Записываем выигрыш
    win_record = FoxJackpotWin(tg_id=tg_id, amount=amount)
    session.add(win_record)
    
    await session.commit()
    return amount


async def get_current_jackpot(session: AsyncSession) -> int:
    """Получить текущий размер джекпота."""
    from .jackpot import get_or_create_jackpot
    jackpot = await get_or_create_jackpot(session)
    return jackpot.pool


async def play_casino_phase1(session: AsyncSession, tg_id: int, bet: int) -> tuple[CasinoResult | Phase1Result, str]:
    """
    Первая фаза игры.
    Возвращает либо финальный результат, либо промежуточный (для риска).
    
    Математика (маржа ~40%):
    - 65% проигрыш (с шансом 0.2% на джекпот!)
    - 22% ×1.5 (промежуточный)
    - 9% ×2
    - 3% ×3
    - 0.8% ×5
    """
    bet = int(bet)  # Гарантируем целые рубли
    
    profile = await get_or_create_casino_profile(session, tg_id)
    casino_session = await get_current_session(session, tg_id)
    
    # Списываем ставку
    await update_balance(session, tg_id, -bet)
    
    # 5% от ставки идёт в джекпот
    jackpot_contribution = max(1, int(bet * JACKPOT_CONTRIBUTION))
    await add_to_jackpot(session, jackpot_contribution)
    
    balance = int(await get_balance(session, tg_id))
    
    # Модификаторы шансов
    bonus_x2 = 0.0
    bonus_x3 = 0.0
    
    if is_night_mode():
        bonus_x3 += NIGHT_MODE_X3_BONUS
    
    # Проверяем золотой час
    if profile.golden_hour_start:
        remaining = profile.golden_hour_start + timedelta(minutes=GOLDEN_HOUR_DURATION) - datetime.utcnow()
        if remaining.total_seconds() > 0:
            bonus_x2 += GOLDEN_HOUR_BONUS
    
    # Бросаем кость (используем float для точности)
    roll = random.uniform(0, 100)
    
    # Расчёт шансов с бонусами
    chance_lose = BASE_CHANCE_LOSE
    chance_win_x15 = BASE_CHANCE_WIN_X15
    chance_win_x2 = BASE_CHANCE_WIN_X2 + bonus_x2
    chance_win_x3 = BASE_CHANCE_WIN_X3 + bonus_x3
    chance_win_x5 = BASE_CHANCE_WIN_X5
    
    # Корректируем проигрыш чтобы сумма была 100
    total_wins = chance_win_x15 + chance_win_x2 + chance_win_x3 + chance_win_x5
    chance_lose = 100.0 - total_wins
    
    # Пороги
    threshold_lose = chance_lose
    threshold_x15 = threshold_lose + chance_win_x15
    threshold_x2 = threshold_x15 + chance_win_x2
    threshold_x3 = threshold_x2 + chance_win_x3
    # threshold_x5 = 100 (всё что осталось)
    
    if roll < threshold_lose:
        # ПРОИГРЫШ — но проверяем джекпот!
        jackpot_roll = random.uniform(0, 100)
        current_jackpot = await get_current_jackpot(session)
        
        if jackpot_roll < BASE_CHANCE_JACKPOT and current_jackpot >= JACKPOT_MIN_POOL:
            # 🏆 ДЖЕКПОТ!!!
            jackpot_amount = await win_jackpot(session, tg_id)
            await update_balance(session, tg_id, jackpot_amount)
            balance = int(await get_balance(session, tg_id))
            
            # Обновляем статистику как выигрыш
            await update_game_stats(session, profile, casino_session, bet, True, jackpot_amount)
            
            result = CasinoResult(
                outcome="jackpot",
                bet=bet,
                multiplier=0,  # Джекпот не зависит от ставки
                winnings=jackpot_amount - bet,
                new_balance=balance,
                comment=random.choice(FOX_COMMENTS_JACKPOT),
                jackpot_amount=jackpot_amount,
            )
            
            await save_game(session, tg_id, casino_session, result)
            logger.info(f"[Casino] 🏆 JACKPOT! {tg_id} выиграл {jackpot_amount}₽!")
            return result, "final"
        
        # Обычный проигрыш
        is_near_miss = random.randint(1, 100) <= NEAR_MISS_CHANCE
        
        if is_near_miss:
            near_miss_text = random.choice(FOX_COMMENTS_NEAR_MISS)
            outcome = "near_miss"
            comment = near_miss_text
        else:
            outcome = "lose"
            comment = random.choice(FOX_COMMENTS_LOSE)
            near_miss_text = None
        
        await update_game_stats(session, profile, casino_session, bet, False, 0)
        
        result = CasinoResult(
            outcome=outcome,
            bet=bet,
            multiplier=0,
            winnings=-bet,
            new_balance=balance,
            comment=comment,
            near_miss_text=near_miss_text,
        )
        
        await save_game(session, tg_id, casino_session, result)
        return result, "final"
    
    elif roll < threshold_x15:
        # ПРОМЕЖУТОЧНЫЙ ВЫИГРЫШ ×1.5 — можно рискнуть
        current_value = int(bet * 1.5)
        
        return Phase1Result(
            can_risk=True,
            current_multiplier=1.5,
            current_value=current_value,
            bet=bet,
            balance=balance,
        ), "phase1"
    
    elif roll < threshold_x2:
        # ВЫИГРЫШ ×2
        payout = bet * 2
        await update_balance(session, tg_id, payout)
        balance = int(await get_balance(session, tg_id))
        
        await update_game_stats(session, profile, casino_session, bet, True, payout)
        
        result = CasinoResult(
            outcome="win_x2",
            bet=bet,
            multiplier=2,
            winnings=payout - bet,
            new_balance=balance,
            comment=random.choice(FOX_COMMENTS_WIN_X2),
        )
        
        await save_game(session, tg_id, casino_session, result)
        return result, "final"
    
    elif roll < threshold_x3:
        # ВЫИГРЫШ ×3
        payout = bet * 3
        await update_balance(session, tg_id, payout)
        balance = int(await get_balance(session, tg_id))
        
        await update_game_stats(session, profile, casino_session, bet, True, payout)
        
        result = CasinoResult(
            outcome="win_x3",
            bet=bet,
            multiplier=3,
            winnings=payout - bet,
            new_balance=balance,
            comment=random.choice(FOX_COMMENTS_WIN_X3),
        )
        
        await save_game(session, tg_id, casino_session, result)
        return result, "final"
    
    else:
        # 💎 ВЫИГРЫШ ×5 (редкий!)
        payout = bet * 5
        await update_balance(session, tg_id, payout)
        balance = int(await get_balance(session, tg_id))
        
        await update_game_stats(session, profile, casino_session, bet, True, payout)
        
        result = CasinoResult(
            outcome="win_x5",
            bet=bet,
            multiplier=5,
            winnings=payout - bet,
            new_balance=balance,
            comment=random.choice(FOX_COMMENTS_WIN_X5),
        )
        
        await save_game(session, tg_id, casino_session, result)
        return result, "final"


async def play_casino_phase2_take(session: AsyncSession, tg_id: int, bet: int, current_value: int) -> CasinoResult:
    """Игрок решил забрать ×1.5."""
    bet = int(bet)
    current_value = int(current_value)
    
    profile = await get_or_create_casino_profile(session, tg_id)
    casino_session = await get_current_session(session, tg_id)
    
    # Выплачиваем ×1.5
    await update_balance(session, tg_id, current_value)
    balance = int(await get_balance(session, tg_id))
    
    await update_game_stats(session, profile, casino_session, bet, True, current_value)
    
    result = CasinoResult(
        outcome="win_x15",
        bet=bet,
        multiplier=1.5,
        winnings=current_value - bet,
        new_balance=balance,
        comment=random.choice(FOX_COMMENTS_WIN_SMALL),
    )
    
    await save_game(session, tg_id, casino_session, result)
    return result


async def play_casino_phase2_risk(session: AsyncSession, tg_id: int, bet: int) -> CasinoResult:
    """Игрок решил рискнуть — вторая фаза."""
    bet = int(bet)  # Гарантируем целые рубли
    
    profile = await get_or_create_casino_profile(session, tg_id)
    casino_session = await get_current_session(session, tg_id)
    
    # Шансы на второй фазе (60% проигрыш, 30% x2, 8% x3, 2% x5)
    roll = random.randint(1, 100)
    balance = int(await get_balance(session, tg_id))
    
    if roll <= PHASE2_CHANCE_LOSE:
        # ПРОИГРЫШ — теряет всё
        await update_game_stats(session, profile, casino_session, bet, False, 0)
        
        result = CasinoResult(
            outcome="lose",
            bet=bet,
            multiplier=0,
            winnings=-bet,
            new_balance=balance,
            comment=random.choice(FOX_COMMENTS_RISK_LOSE),
            phase=2,
            was_risk=True,
        )
    
    elif roll <= PHASE2_CHANCE_LOSE + PHASE2_CHANCE_WIN_X2:
        # ВЫИГРЫШ ×2
        payout = bet * 2
        await update_balance(session, tg_id, payout)
        balance = int(await get_balance(session, tg_id))
        
        await update_game_stats(session, profile, casino_session, bet, True, payout)
        
        result = CasinoResult(
            outcome="win_x2",
            bet=bet,
            multiplier=2,
            winnings=payout - bet,
            new_balance=balance,
            comment=random.choice(FOX_COMMENTS_RISK_WIN),
            phase=2,
            was_risk=True,
        )
    
    elif roll <= PHASE2_CHANCE_LOSE + PHASE2_CHANCE_WIN_X2 + PHASE2_CHANCE_WIN_X3:
        # ВЫИГРЫШ ×3
        payout = bet * 3
        await update_balance(session, tg_id, payout)
        balance = int(await get_balance(session, tg_id))
        
        await update_game_stats(session, profile, casino_session, bet, True, payout)
        
        result = CasinoResult(
            outcome="win_x3",
            bet=bet,
            multiplier=3,
            winnings=payout - bet,
            new_balance=balance,
            comment=random.choice(FOX_COMMENTS_RISK_WIN),
            phase=2,
            was_risk=True,
        )
    
    else:
        # 💎 ВЫИГРЫШ ×5 (редкий при риске!)
        payout = bet * 5
        await update_balance(session, tg_id, payout)
        balance = int(await get_balance(session, tg_id))
        
        await update_game_stats(session, profile, casino_session, bet, True, payout)
        
        result = CasinoResult(
            outcome="win_x5",
            bet=bet,
            multiplier=5,
            winnings=payout - bet,
            new_balance=balance,
            comment=random.choice(FOX_COMMENTS_WIN_X5),
            phase=2,
            was_risk=True,
        )
    
    await save_game(session, tg_id, casino_session, result)
    return result


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

async def update_game_stats(
    session: AsyncSession,
    profile: FoxCasinoProfile,
    casino_session: Optional[FoxCasinoSession],
    bet: float,
    won: bool,
    payout: float
):
    """Обновить статистику после игры."""
    now = datetime.utcnow()
    
    # Профиль
    profile.total_games += 1
    profile.total_wagered += bet
    profile.daily_games += 1
    profile.games_in_row += 1
    profile.last_game_at = now
    
    if won:
        winnings = payout - bet
        profile.total_won += winnings
        profile.daily_won += winnings
        profile.current_win_streak += 1
        profile.current_lose_streak = 0
        
        if profile.current_win_streak > profile.best_win_streak:
            profile.best_win_streak = profile.current_win_streak
        
        if winnings > profile.biggest_win:
            profile.biggest_win = winnings
    else:
        profile.total_lost += bet
        profile.daily_lost += bet
        profile.current_lose_streak += 1
        profile.current_win_streak = 0
        
        if profile.current_lose_streak > profile.worst_lose_streak:
            profile.worst_lose_streak = profile.current_lose_streak
    
    # Кулдаун ТОЛЬКО при проигрыше! При выигрыше можно играть сразу.
    if not won:
        profile.cooldown_until = now + timedelta(seconds=COOLDOWN_AFTER_LOSE)
    else:
        profile.cooldown_until = None  # Сбрасываем кулдаун при выигрыше
        profile.games_in_row = 0  # Сбрасываем счётчик игр подряд
    
    # Принудительный перерыв после серии проигрышей
    if profile.current_lose_streak >= FORCED_BREAK_AFTER_LOSSES:
        profile.forced_break_until = now + timedelta(seconds=FORCED_BREAK_DURATION)
        profile.current_lose_streak = 0
        logger.info(f"[Casino] {profile.tg_id}: принудительный перерыв после {FORCED_BREAK_AFTER_LOSSES} проигрышей")
    
    # Сессия
    if casino_session:
        casino_session.games_played += 1
        casino_session.total_bet += bet
        
        if won:
            casino_session.total_won += payout - bet
            casino_session.net_result += payout - bet
            
            # Текущая серия побед в сессии
            win_streak = profile.current_win_streak
            if win_streak > casino_session.max_win_streak:
                casino_session.max_win_streak = win_streak
        else:
            casino_session.net_result -= bet
            
            # Текущая серия проигрышей в сессии
            lose_streak = profile.current_lose_streak
            if lose_streak > casino_session.max_lose_streak:
                casino_session.max_lose_streak = lose_streak
    
    await session.commit()


async def save_game(
    session: AsyncSession,
    tg_id: int,
    casino_session: Optional[FoxCasinoSession],
    result: CasinoResult
):
    """Сохранить игру в историю."""
    game = FoxCasinoGame(
        tg_id=tg_id,
        bet=result.bet,
        won=result.outcome not in ("lose", "near_miss"),
        multiplier=result.multiplier,
        payout=result.bet * result.multiplier if result.multiplier > 0 else 0,
        phase=result.phase,
        was_doubled=result.was_risk,
        near_miss=result.outcome == "near_miss",
        near_miss_text=result.near_miss_text,
        session_id=casino_session.id if casino_session else None,
    )
    session.add(game)
    await session.commit()
    
    logger.info(
        f"[Casino] {tg_id}: ставка {result.bet}₽, исход {result.outcome}, "
        f"×{result.multiplier}, баланс {result.new_balance}₽"
    )


async def record_casino_game(
    session: AsyncSession,
    tg_id: int,
    bet: int,
    won: bool,
    multiplier: float,
    payout: int
):
    """Универсальная функция записи игры для всех игр казино."""
    from database.users import update_balance, get_balance
    
    profile = await get_or_create_casino_profile(session, tg_id)
    casino_session = await get_current_session(session, tg_id)
    
    # Списываем ставку
    await update_balance(session, tg_id, -bet)
    
    # Если выиграл — начисляем выигрыш (payout уже передан с учётом ставки)
    if won and payout > 0:
        await update_balance(session, tg_id, payout)
    
    # Джекпот — часть ставки идёт в пул
    jackpot_contribution = max(1, int(bet * JACKPOT_CONTRIBUTION))
    await add_to_jackpot(session, jackpot_contribution)
    
    # Обновляем статистику (БЕЗ forced_break для мини-игр, только для основной игры в кости)
    # Для новых игр обновляем только базовую статистику
    now = datetime.utcnow()
    
    profile.total_games += 1
    profile.total_wagered += bet
    profile.daily_games += 1
    profile.last_game_at = now
    
    if won:
        winnings = payout - bet
        profile.total_won += winnings
        profile.daily_won += winnings
        profile.current_win_streak += 1
        profile.current_lose_streak = 0
        
        if profile.current_win_streak > profile.best_win_streak:
            profile.best_win_streak = profile.current_win_streak
    else:
        profile.total_lost += bet
        profile.daily_lost += bet
        profile.current_lose_streak += 1
        profile.current_win_streak = 0
        
        if profile.current_lose_streak > profile.worst_lose_streak:
            profile.worst_lose_streak = profile.current_lose_streak
    
    # Кулдауны теперь управляются отдельно для каждой игры в router.py
    
    # Обновляем сессию если есть
    if casino_session:
        casino_session.games_played += 1
        casino_session.total_bet += bet
        
        if won:
            casino_session.total_won += payout - bet
            casino_session.net_result += payout - bet
        else:
            casino_session.net_result -= bet
    
    # Сохраняем игру
    game = FoxCasinoGame(
        tg_id=tg_id,
        bet=bet,
        won=won,
        multiplier=multiplier,
        payout=payout if won else 0,
        phase=1,
        was_doubled=False,
        near_miss=False,
        session_id=casino_session.id if casino_session else None,
    )
    session.add(game)
    await session.commit()
    
    logger.info(f"[Casino] {tg_id}: игра bet={bet}, won={won}, multiplier={multiplier}, payout={payout}")


async def self_block_casino(session: AsyncSession, tg_id: int) -> str:
    """Заблокировать себе вход в казино."""
    profile = await get_or_create_casino_profile(session, tg_id)
    profile.blocked_until = datetime.utcnow() + timedelta(days=SELF_BLOCK_DAYS)
    await session.commit()
    
    return f"🔒 Казино заблокировано на {SELF_BLOCK_DAYS} дней."


async def trigger_golden_hour(session: AsyncSession, tg_id: int):
    """Активировать золотой час для игрока."""
    profile = await get_or_create_casino_profile(session, tg_id)
    profile.golden_hour_start = datetime.utcnow()
    profile.golden_hour_notified = False
    await session.commit()


def format_timedelta(td: timedelta) -> str:
    """Форматировать timedelta в читаемый вид."""
    total_seconds = int(td.total_seconds())
    
    if total_seconds < 60:
        return f"{total_seconds} сек"
    
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} мин"
    
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours} ч {minutes} мин"


def get_streak_text(profile: FoxCasinoProfile) -> str:
    """Получить текст о текущей серии."""
    if profile.current_win_streak >= 4:
        return STREAK_WIN_4
    elif profile.current_win_streak == 3:
        return STREAK_WIN_3
    elif profile.current_win_streak == 2:
        return STREAK_WIN_2
    elif profile.current_lose_streak >= 5:
        return STREAK_LOSE_5
    elif profile.current_lose_streak >= 3:
        return STREAK_LOSE_3
    return ""


# ==================== ФОРМАТИРОВАНИЕ РЕЗУЛЬТАТОВ ====================

def format_result_message(result: CasinoResult) -> str:
    """Форматировать сообщение с результатом."""
    # Джекпот — особый случай!
    if result.outcome == "jackpot":
        return RESULT_JACKPOT.format(
            jackpot=result.jackpot_amount,
            comment=result.comment,
            balance=result.new_balance,
        )
    
    if result.was_risk:
        # Результат рискованной игры
        if result.outcome == "lose":
            return RESULT_RISK_LOSE.format(
                had=int(result.bet * 1.5),
                comment=result.comment,
                balance=result.new_balance,
            )
        else:
            return RESULT_RISK_WIN.format(
                bet=result.bet,
                multiplier=int(result.multiplier),
                winnings=result.winnings,
                comment=result.comment,
                balance=result.new_balance,
            )
    
    if result.outcome == "near_miss":
        return RESULT_NEAR_MISS.format(
            bet=result.bet,
            near_miss_text=result.near_miss_text,
            balance=result.new_balance,
        )
    
    if result.outcome == "lose":
        return RESULT_LOSE.format(
            bet=result.bet,
            comment=result.comment,
            balance=result.new_balance,
        )
    
    if result.outcome == "win_x15":
        return RESULT_WIN_X15.format(
            bet=result.bet,
            winnings=result.winnings,
            comment=result.comment,
            balance=result.new_balance,
        )
    
    if result.outcome == "win_x2":
        return RESULT_WIN_X2.format(
            bet=result.bet,
            winnings=result.winnings,
            comment=result.comment,
            balance=result.new_balance,
        )
    
    if result.outcome == "win_x3":
        return RESULT_WIN_X3.format(
            bet=result.bet,
            winnings=result.winnings,
            comment=result.comment,
            balance=result.new_balance,
        )
    
    if result.outcome == "win_x5":
        return RESULT_WIN_X5.format(
            bet=result.bet,
            winnings=result.winnings,
            comment=result.comment,
            balance=result.new_balance,
        )
    
    return "Ошибка"
