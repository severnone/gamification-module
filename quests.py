"""
🧰 Система заданий (квесты)
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from logger import logger

from .models import FoxPlayer, FoxQuest
from .db import get_or_create_player, update_player_coins


class QuestType(str, Enum):
    """Типы заданий"""
    DAILY_LOGIN = "daily_login"        # Зайти в бот
    LOGIN_STREAK_3 = "login_streak_3"  # Серия входов 3 дня
    LOGIN_STREAK_7 = "login_streak_7"  # Серия входов 7 дней
    PLAY_GAME = "play_game"            # Сыграть в игру
    PLAY_3_GAMES = "play_3_games"      # Сыграть 3 игры
    WIN_GAME = "win_game"              # Выиграть в игре
    VISIT_CASINO = "visit_casino"      # Посетить казино
    MAKE_DEAL = "make_deal"            # Заключить сделку


@dataclass
class QuestInfo:
    """Информация о задании"""
    quest_type: QuestType
    title: str
    description: str
    reward_coins: int
    reward_description: str
    emoji: str
    is_daily: bool = True


# Определения всех заданий
QUEST_DEFINITIONS = {
    QuestType.DAILY_LOGIN: QuestInfo(
        quest_type=QuestType.DAILY_LOGIN,
        title="Ежедневный визит",
        description="Зайди в Логово Лисы",
        reward_coins=10,
        reward_description="+10 🪙",
        emoji="📅",
        is_daily=True,
    ),
    QuestType.LOGIN_STREAK_3: QuestInfo(
        quest_type=QuestType.LOGIN_STREAK_3,
        title="Постоянство",
        description="Заходи 3 дня подряд",
        reward_coins=30,
        reward_description="+30 🪙",
        emoji="🔥",
        is_daily=False,
    ),
    QuestType.LOGIN_STREAK_7: QuestInfo(
        quest_type=QuestType.LOGIN_STREAK_7,
        title="Верность",
        description="Заходи 7 дней подряд",
        reward_coins=100,
        reward_description="+100 🪙",
        emoji="⭐",
        is_daily=False,
    ),
    QuestType.PLAY_GAME: QuestInfo(
        quest_type=QuestType.PLAY_GAME,
        title="Игрок",
        description="Сыграй в любую игру",
        reward_coins=5,
        reward_description="+5 🪙",
        emoji="🎮",
        is_daily=True,
    ),
    QuestType.PLAY_3_GAMES: QuestInfo(
        quest_type=QuestType.PLAY_3_GAMES,
        title="Азартный",
        description="Сыграй 3 игры за день",
        reward_coins=20,
        reward_description="+20 🪙",
        emoji="🎰",
        is_daily=True,
    ),
    QuestType.WIN_GAME: QuestInfo(
        quest_type=QuestType.WIN_GAME,
        title="Победитель",
        description="Выиграй в любой игре",
        reward_coins=15,
        reward_description="+15 🪙",
        emoji="🏆",
        is_daily=True,
    ),
}


async def get_player_quests(session: AsyncSession, tg_id: int) -> list[FoxQuest]:
    """Получить все активные квесты игрока"""
    today = datetime.utcnow().date()
    
    result = await session.execute(
        select(FoxQuest)
        .where(
            FoxQuest.tg_id == tg_id,
            func.date(FoxQuest.created_at) == today,
        )
    )
    return list(result.scalars().all())


async def init_daily_quests(session: AsyncSession, tg_id: int) -> list[FoxQuest]:
    """Инициализировать ежедневные квесты для игрока"""
    today = datetime.utcnow().date()
    
    # Проверяем, есть ли уже квесты на сегодня
    existing = await get_player_quests(session, tg_id)
    if existing:
        return existing
    
    # Создаём ежедневные квесты
    quests = []
    daily_quest_types = [
        QuestType.DAILY_LOGIN,
        QuestType.PLAY_GAME,
        QuestType.PLAY_3_GAMES,
        QuestType.WIN_GAME,
    ]
    
    for quest_type in daily_quest_types:
        quest = FoxQuest(
            tg_id=tg_id,
            quest_type=quest_type.value,
            progress=0,
            target=3 if quest_type == QuestType.PLAY_3_GAMES else 1,
            is_completed=False,
            is_claimed=False,
        )
        session.add(quest)
        quests.append(quest)
    
    await session.commit()
    logger.info(f"[Quests] Созданы ежедневные квесты для {tg_id}")
    
    return quests


async def update_quest_progress(
    session: AsyncSession, 
    tg_id: int, 
    quest_type: QuestType, 
    increment: int = 1
) -> FoxQuest | None:
    """Обновить прогресс квеста. Возвращает квест если он был завершён."""
    today = datetime.utcnow().date()
    
    result = await session.execute(
        select(FoxQuest)
        .where(
            FoxQuest.tg_id == tg_id,
            FoxQuest.quest_type == quest_type.value,
            func.date(FoxQuest.created_at) == today,
            FoxQuest.is_completed == False,
        )
    )
    quest = result.scalar_one_or_none()
    
    if not quest:
        return None
    
    quest.progress += increment
    
    if quest.progress >= quest.target:
        quest.is_completed = True
        quest.completed_at = datetime.utcnow()
        logger.info(f"[Quests] Квест {quest_type.value} выполнен игроком {tg_id}")
    
    await session.commit()
    
    return quest if quest.is_completed else None


async def claim_quest_reward(session: AsyncSession, tg_id: int, quest_id: int) -> int | None:
    """Забрать награду за выполненный квест. Возвращает количество монет."""
    result = await session.execute(
        select(FoxQuest)
        .where(
            FoxQuest.id == quest_id,
            FoxQuest.tg_id == tg_id,
            FoxQuest.is_completed == True,
            FoxQuest.is_claimed == False,
        )
    )
    quest = result.scalar_one_or_none()
    
    if not quest:
        return None
    
    # Получаем награду
    quest_info = QUEST_DEFINITIONS.get(QuestType(quest.quest_type))
    if not quest_info:
        return None
    
    reward = quest_info.reward_coins
    
    # Помечаем как забранную
    quest.is_claimed = True
    quest.claimed_at = datetime.utcnow()
    
    # Начисляем монеты
    await update_player_coins(session, tg_id, reward)
    
    await session.commit()
    logger.info(f"[Quests] Игрок {tg_id} забрал награду {reward} за квест {quest.quest_type}")
    
    return reward


async def check_login_streak_quests(session: AsyncSession, tg_id: int) -> list[str]:
    """Проверить и выполнить квесты на серию входов. Возвращает список выполненных."""
    player = await get_or_create_player(session, tg_id)
    completed = []
    
    # Проверяем серию 3 дня
    if player.login_streak >= 3:
        quest = await update_quest_progress(session, tg_id, QuestType.LOGIN_STREAK_3)
        if quest:
            completed.append("LOGIN_STREAK_3")
    
    # Проверяем серию 7 дней
    if player.login_streak >= 7:
        quest = await update_quest_progress(session, tg_id, QuestType.LOGIN_STREAK_7)
        if quest:
            completed.append("LOGIN_STREAK_7")
    
    return completed


def format_quest_status(quest: FoxQuest) -> str:
    """Форматировать статус квеста для отображения"""
    quest_info = QUEST_DEFINITIONS.get(QuestType(quest.quest_type))
    if not quest_info:
        return ""
    
    if quest.is_claimed:
        return f"✅ {quest_info.emoji} {quest_info.title} — получено!"
    elif quest.is_completed:
        return f"🎁 {quest_info.emoji} <b>{quest_info.title}</b> — забери награду!"
    else:
        progress = f"({quest.progress}/{quest.target})" if quest.target > 1 else ""
        return f"⏳ {quest_info.emoji} {quest_info.title} {progress}"
