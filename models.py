"""
Модели БД для модуля геймификации "Логово Лисы"
"""
from datetime import datetime, timedelta

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database.models import Base


class FoxPlayer(Base):
    """Игровой профиль пользователя в Логове Лисы"""
    __tablename__ = "fox_players"

    tg_id = Column(BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"), primary_key=True)
    
    # Валюты
    coins = Column(Integer, default=0, nullable=False)  # Лискоины
    light = Column(Integer, default=0, nullable=False)  # Свет Лисы (редкая валюта)
    
    # Попытки
    free_spins = Column(Integer, default=1, nullable=False)  # Бесплатные ежедневные попытки
    paid_spins = Column(Integer, default=0, nullable=False)  # Купленные попытки
    last_free_spin_date = Column(DateTime, nullable=True)  # Дата последней бесплатной попытки
    
    # Статистика
    total_games = Column(Integer, default=0, nullable=False)  # Всего игр
    total_wins = Column(Integer, default=0, nullable=False)  # Всего выигрышей
    
    # Серия входов
    login_streak = Column(Integer, default=0, nullable=False)  # Дней подряд
    last_login_date = Column(DateTime, nullable=True)  # Последний вход
    
    # 7-дневный календарь наград
    calendar_day = Column(Integer, default=0, nullable=False)  # Текущий день (0-7)
    last_calendar_claim = Column(DateTime, nullable=True)  # Когда забрал последнюю награду
    
    # Рефералы
    invited_by = Column(BigInteger, nullable=True)  # Кто пригласил (tg_id)
    referral_bonus_given = Column(Boolean, default=False, nullable=False)  # Бонус за реферала выдан
    total_referrals = Column(Integer, default=0, nullable=False)  # Сколько пригласил
    
    # VIP статус
    is_vip = Column(Boolean, default=False, nullable=False)
    vip_expires_at = Column(DateTime, nullable=True)  # Когда истекает VIP
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    prizes = relationship("FoxPrize", back_populates="player", cascade="all, delete-orphan")
    games = relationship("FoxGameHistory", back_populates="player", cascade="all, delete-orphan")


class FoxPrize(Base):
    """Призы пользователя"""
    __tablename__ = "fox_prizes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, ForeignKey("fox_players.tg_id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Тип приза: "vpn_days", "coins", "balance", "boost", "light"
    prize_type = Column(String(50), nullable=False)
    
    # Значение приза (дни VPN, количество монет, рубли на баланс и т.д.)
    value = Column(Integer, nullable=False)
    
    # Описание для отображения
    description = Column(String(255), nullable=True)
    
    # Статус
    is_used = Column(Boolean, default=False, nullable=False)  # Использован ли приз
    used_at = Column(DateTime, nullable=True)  # Когда использован
    
    # Срок действия (14 дней)
    expires_at = Column(DateTime, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    player = relationship("FoxPlayer", back_populates="prizes")

    @staticmethod
    def default_expiry():
        """Срок действия по умолчанию — 14 дней"""
        return datetime.utcnow() + timedelta(days=14)


class FoxGameHistory(Base):
    """История игр"""
    __tablename__ = "fox_game_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, ForeignKey("fox_players.tg_id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Тип игры: "wheel", "chest", "cards"
    game_type = Column(String(50), nullable=False)
    
    # Результат
    prize_type = Column(String(50), nullable=True)  # Тип выигранного приза (или null если пустышка)
    prize_value = Column(Integer, nullable=True)  # Значение приза
    prize_description = Column(String(255), nullable=True)
    
    # Был ли использован буст
    boost_used = Column(Boolean, default=False, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    player = relationship("FoxPlayer", back_populates="games")


class FoxBoost(Base):
    """Активные бусты пользователя"""
    __tablename__ = "fox_boosts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, ForeignKey("fox_players.tg_id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Тип буста: "luck_10", "luck_20", "luck_30" (увеличение шанса на %)
    boost_type = Column(String(50), nullable=False)
    
    # Количество использований
    uses_left = Column(Integer, default=1, nullable=False)
    
    expires_at = Column(DateTime, nullable=True)  # Может истекать по времени
    created_at = Column(DateTime, default=datetime.utcnow)


class FoxDeal(Base):
    """История сделок с лисой"""
    __tablename__ = "fox_deals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, ForeignKey("fox_players.tg_id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Ставка
    stake_type = Column(String(50), nullable=False)  # "coins", "vpn_days", "spin"
    stake_value = Column(Integer, nullable=False)  # Сколько поставил
    
    # Результат
    won = Column(Boolean, nullable=False)  # Выиграл или проиграл
    multiplier = Column(Float, default=2.0)  # Множитель (x2, x3)
    result_value = Column(Integer, nullable=False)  # Итоговый результат (0 если проиграл)
    
    # Динамический шанс на момент сделки
    chance_percent = Column(Integer, nullable=False)  # Шанс победы в %
    
    # Объяснение от лисы
    fox_comment = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class FoxCasinoGame(Base):
    """История игр в Лисьем казино (реальные ставки!)"""
    __tablename__ = "fox_casino_games"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Ставка в рублях
    bet = Column(Float, nullable=False)
    
    # Результат
    won = Column(Boolean, nullable=False)
    multiplier = Column(Float, nullable=False)  # 0, 2, 3
    payout = Column(Float, nullable=False)  # Выплата
    
    # Двухфазная игра
    phase = Column(Integer, default=1)  # 1 = первый бросок, 2 = рискнул
    was_doubled = Column(Boolean, default=False)  # Игрок рискнул удвоить
    
    # Near miss (почти выиграл)
    near_miss = Column(Boolean, default=False)
    near_miss_text = Column(String(255), nullable=True)
    
    # ID сессии
    session_id = Column(Integer, ForeignKey("fox_casino_sessions.id"), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class FoxCasinoSession(Base):
    """Сессия игры в казино (от входа до выхода)"""
    __tablename__ = "fox_casino_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Статистика сессии
    games_played = Column(Integer, default=0)
    total_bet = Column(Float, default=0)  # Всего поставлено
    total_won = Column(Float, default=0)  # Всего выиграно
    net_result = Column(Float, default=0)  # Итог (+ или -)
    
    # Серии в сессии
    max_win_streak = Column(Integer, default=0)
    max_lose_streak = Column(Integer, default=0)
    
    # Состояние
    is_active = Column(Boolean, default=True)  # Сессия активна
    
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    
    # Связь с играми
    games = relationship("FoxCasinoGame", backref="session", foreign_keys=[FoxCasinoGame.session_id])


class FoxCasinoProfile(Base):
    """Профиль игрока в казино (постоянные данные)"""
    __tablename__ = "fox_casino_profiles"

    tg_id = Column(BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"), primary_key=True)
    
    # Статистика всех времён
    total_visits = Column(Integer, default=0)  # Сколько раз заходил
    total_games = Column(Integer, default=0)  # Всего игр
    total_wagered = Column(Float, default=0)  # Всего поставлено за всё время
    total_won = Column(Float, default=0)  # Всего выиграно
    total_lost = Column(Float, default=0)  # Всего проиграно
    biggest_win = Column(Float, default=0)  # Самый большой выигрыш
    biggest_loss = Column(Float, default=0)  # Самый большой проигрыш за сессию
    
    # Серии (текущие)
    current_win_streak = Column(Integer, default=0)
    current_lose_streak = Column(Integer, default=0)
    
    # Рекорды серий
    best_win_streak = Column(Integer, default=0)
    worst_lose_streak = Column(Integer, default=0)
    
    # Текущая сессия
    current_session_id = Column(Integer, nullable=True)
    
    # Ограничения
    blocked_until = Column(DateTime, nullable=True)  # Самоблокировка
    cooldown_until = Column(DateTime, nullable=True)  # Кулдаун между играми
    forced_break_until = Column(DateTime, nullable=True)  # Принудительный перерыв
    
    # Счётчики для кулдауна
    games_in_row = Column(Integer, default=0)  # Игр подряд без перерыва
    last_game_at = Column(DateTime, nullable=True)
    
    # Дневная статистика
    daily_games = Column(Integer, default=0)
    daily_lost = Column(Float, default=0)
    daily_won = Column(Float, default=0)
    daily_reset_date = Column(DateTime, nullable=True)
    
    # Результат прошлой сессии (для "незакрытого гештальта")
    last_session_result = Column(Float, default=0)  # + или -
    last_session_games = Column(Integer, default=0)
    
    # "Золотой час" - случайный бонусный час
    golden_hour_start = Column(DateTime, nullable=True)
    golden_hour_notified = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FoxQuest(Base):
    """Ежедневные задания"""
    __tablename__ = "fox_quests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tg_id = Column(BigInteger, ForeignKey("fox_players.tg_id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Тип квеста
    quest_type = Column(String(50), nullable=False)
    
    # Прогресс
    progress = Column(Integer, default=0, nullable=False)
    target = Column(Integer, default=1, nullable=False)  # Сколько нужно для выполнения
    
    # Статус
    is_completed = Column(Boolean, default=False, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    is_claimed = Column(Boolean, default=False, nullable=False)  # Забрана ли награда
    claimed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
