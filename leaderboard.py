"""
Лидерборд — топ игроков
"""
from datetime import datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import FoxGameHistory, FoxPlayer


async def get_top_winners_week(session: AsyncSession, limit: int = 10) -> list[dict]:
    """Топ по выигрышам за последнюю неделю"""
    week_ago = datetime.utcnow() - timedelta(days=7)
    
    result = await session.execute(
        select(
            FoxGameHistory.tg_id,
            func.count(FoxGameHistory.id).label("wins_count")
        )
        .where(
            FoxGameHistory.created_at >= week_ago,
            FoxGameHistory.prize_type.isnot(None),
            FoxGameHistory.prize_type.notin_(["empty", "nothing", "lose"])
        )
        .group_by(FoxGameHistory.tg_id)
        .order_by(desc("wins_count"))
        .limit(limit)
    )
    
    return [{"tg_id": row.tg_id, "wins": row.wins_count} for row in result.fetchall()]


async def get_top_winners_month(session: AsyncSession, limit: int = 10) -> list[dict]:
    """Топ по выигрышам за последний месяц"""
    month_ago = datetime.utcnow() - timedelta(days=30)
    
    result = await session.execute(
        select(
            FoxGameHistory.tg_id,
            func.count(FoxGameHistory.id).label("wins_count")
        )
        .where(
            FoxGameHistory.created_at >= month_ago,
            FoxGameHistory.prize_type.isnot(None),
            FoxGameHistory.prize_type.notin_(["empty", "nothing", "lose"])
        )
        .group_by(FoxGameHistory.tg_id)
        .order_by(desc("wins_count"))
        .limit(limit)
    )
    
    return [{"tg_id": row.tg_id, "wins": row.wins_count} for row in result.fetchall()]


async def get_top_streak(session: AsyncSession, limit: int = 10) -> list[dict]:
    """Топ по серии входов"""
    result = await session.execute(
        select(FoxPlayer.tg_id, FoxPlayer.login_streak)
        .where(FoxPlayer.login_streak > 0)
        .order_by(desc(FoxPlayer.login_streak))
        .limit(limit)
    )
    
    return [{"tg_id": row.tg_id, "streak": row.login_streak} for row in result.fetchall()]


async def get_top_coins(session: AsyncSession, limit: int = 10) -> list[dict]:
    """Топ по количеству Лискоинов"""
    result = await session.execute(
        select(FoxPlayer.tg_id, FoxPlayer.coins)
        .where(FoxPlayer.coins > 0)
        .order_by(desc(FoxPlayer.coins))
        .limit(limit)
    )
    
    return [{"tg_id": row.tg_id, "coins": row.coins} for row in result.fetchall()]


async def get_top_games(session: AsyncSession, limit: int = 10) -> list[dict]:
    """Топ по количеству сыгранных игр"""
    result = await session.execute(
        select(FoxPlayer.tg_id, FoxPlayer.total_games)
        .where(FoxPlayer.total_games > 0)
        .order_by(desc(FoxPlayer.total_games))
        .limit(limit)
    )
    
    return [{"tg_id": row.tg_id, "games": row.total_games} for row in result.fetchall()]


def format_leaderboard(
    entries: list[dict], 
    value_key: str, 
    value_emoji: str,
    title: str,
) -> str:
    """Форматирует лидерборд в текст"""
    if not entries:
        return f"{title}\n\n<i>Пока нет данных</i>"
    
    lines = [title, ""]
    
    medals = ["🥇", "🥈", "🥉"]
    
    for i, entry in enumerate(entries):
        if i < 3:
            medal = medals[i]
        else:
            medal = f"{i + 1}."
        
        # Анонимизируем tg_id (показываем только последние 4 цифры)
        tg_id = entry["tg_id"]
        user_display = f"***{str(tg_id)[-4:]}"
        
        value = entry[value_key]
        lines.append(f"{medal} {user_display}: <b>{value}</b> {value_emoji}")
    
    return "\n".join(lines)
