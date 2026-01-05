"""
🦊 ЛИСЬЕ КАЗИНО — игра на реальный баланс
⚠️ Ставки списываются с реального баланса пользователя!
"""
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.users import get_balance, update_balance
from logger import logger

from .models import FoxCasinoGame


# ==================== НАСТРОЙКИ ====================

# Минимальная/максимальная ставка
MIN_BET = 10  # рублей
MAX_BET = 500  # рублей

# Дневной лимит проигрыша
DAILY_LOSS_LIMIT = 1000  # рублей

# Фиксированные ставки
FIXED_BETS = [10, 25, 50, 100]

# Шансы (сумма = 100%)
CHANCE_LOSE = 60      # Проигрыш
CHANCE_WIN_X2 = 35    # Выигрыш ×2
CHANCE_WIN_X3 = 5     # Выигрыш ×3


# ==================== ФРАЗЫ ====================

CASINO_INTRO = """🦊 <b>ЛИСЬЕ КАЗИНО</b>

⚠️ <b>ВНИМАНИЕ!</b>
Ставка списывается с <b>реального баланса</b>.
Проигрыш — без возврата.

💰 Твой баланс: <b>{balance:.0f} ₽</b>

<i>Лиса не уговаривает. Она принимает ставки.</i>
"""

CASINO_BLOCKED_NO_BALANCE = """🦊 <b>ЛИСЬЕ КАЗИНО</b>

❌ Недостаточно средств.
Минимальная ставка: <b>{min_bet} ₽</b>
Твой баланс: <b>{balance:.0f} ₽</b>

<i>Лиса ждёт, когда у тебя появятся деньги.</i>
"""

CASINO_BLOCKED_LIMIT = """🦊 <b>ЛИСЬЕ КАЗИНО</b>

⛔ Дневной лимит исчерпан.
Ты уже потерял <b>{lost:.0f} ₽</b> сегодня.
Лимит: <b>{limit} ₽</b>

<i>Лиса советует остыть.</i>
"""

BET_CONFIRM = """🦊 <b>ЛИСЬЕ КАЗИНО</b>

Ты ставишь: <b>{bet} ₽</b>

⚠️ Эта сумма будет списана с твоего <b>реального баланса</b>.
Проигрыш = потеря денег.

<b>Продолжить?</b>
"""

ROLLING = """🦊 <b>ЛИСЬЕ КАЗИНО</b>

Ставка: <b>{bet} ₽</b>

🎲 <i>Лиса бросает кость...</i>
"""

RESULT_LOSE = """🦊 <b>ЛИСЬЕ КАЗИНО</b>

❌ <b>ПРОИГРЫШ</b>

Ставка: {bet} ₽
Потеряно: <b>-{bet} ₽</b>

💬 <i>«Лиса забрала своё.»</i>

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

RESULT_WIN_X2 = """🦊 <b>ЛИСЬЕ КАЗИНО</b>

✅ <b>ВЫИГРЫШ ×2</b>

Ставка: {bet} ₽
Выигрыш: <b>+{winnings} ₽</b>

💬 <i>«Лиса недовольна. Ты забрал своё.»</i>

💰 Баланс: <b>{balance:.0f} ₽</b>
"""

RESULT_WIN_X3 = """🦊 <b>ЛИСЬЕ КАЗИНО</b>

🔥 <b>КРУПНЫЙ ВЫИГРЫШ ×3!</b>

Ставка: {bet} ₽
Выигрыш: <b>+{winnings} ₽</b>

💬 <i>«Лиса ошиблась. Больше так не будет.»</i>

💰 Баланс: <b>{balance:.0f} ₽</b>
"""


@dataclass
class CasinoResult:
    """Результат игры в казино"""
    outcome: str  # "lose", "win_x2", "win_x3"
    bet: float
    multiplier: float
    winnings: float  # чистый выигрыш (может быть отрицательным)
    new_balance: float


async def get_daily_losses(session: AsyncSession, tg_id: int) -> float:
    """Получить сумму проигрышей за сегодня."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    result = await session.execute(
        select(func.sum(FoxCasinoGame.bet))
        .where(
            FoxCasinoGame.tg_id == tg_id,
            FoxCasinoGame.won == False,
            FoxCasinoGame.created_at >= today_start,
        )
    )
    total = result.scalar_one_or_none()
    return float(total) if total else 0.0


async def can_play_casino(session: AsyncSession, tg_id: int, bet: float) -> tuple[bool, str | None]:
    """Проверить, может ли игрок играть."""
    # Проверяем баланс
    balance = await get_balance(session, tg_id)
    if balance < bet:
        return False, "no_balance"
    
    if bet < MIN_BET:
        return False, "min_bet"
    
    if bet > MAX_BET:
        return False, "max_bet"
    
    # Проверяем дневной лимит
    daily_losses = await get_daily_losses(session, tg_id)
    if daily_losses >= DAILY_LOSS_LIMIT:
        return False, "daily_limit"
    
    return True, None


async def play_casino(session: AsyncSession, tg_id: int, bet: float) -> CasinoResult:
    """
    Сыграть в казино.
    СТАВКА СПИСЫВАЕТСЯ С РЕАЛЬНОГО БАЛАНСА!
    """
    # Списываем ставку сразу
    await update_balance(session, tg_id, -bet)
    
    # Бросаем кости
    roll = random.randint(1, 100)
    
    if roll <= CHANCE_LOSE:
        # Проигрыш (60%)
        outcome = "lose"
        multiplier = 0.0
        winnings = -bet
        # Ставка уже списана, ничего не возвращаем
    elif roll <= CHANCE_LOSE + CHANCE_WIN_X2:
        # Выигрыш ×2 (35%)
        outcome = "win_x2"
        multiplier = 2.0
        payout = bet * multiplier
        winnings = payout - bet  # Чистый выигрыш
        # Возвращаем выигрыш
        await update_balance(session, tg_id, payout)
    else:
        # Выигрыш ×3 (5%)
        outcome = "win_x3"
        multiplier = 3.0
        payout = bet * multiplier
        winnings = payout - bet  # Чистый выигрыш
        # Возвращаем выигрыш
        await update_balance(session, tg_id, payout)
    
    # Получаем новый баланс
    new_balance = await get_balance(session, tg_id)
    
    # Сохраняем в историю
    game = FoxCasinoGame(
        tg_id=tg_id,
        bet=bet,
        multiplier=multiplier,
        won=outcome != "lose",
        payout=bet * multiplier if outcome != "lose" else 0,
    )
    session.add(game)
    await session.commit()
    
    logger.info(
        f"[Casino] {tg_id}: ставка {bet}₽, исход {outcome}, "
        f"множитель ×{multiplier}, баланс {new_balance}₽"
    )
    
    return CasinoResult(
        outcome=outcome,
        bet=bet,
        multiplier=multiplier,
        winnings=winnings,
        new_balance=new_balance,
    )
