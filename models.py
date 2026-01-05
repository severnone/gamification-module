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
    free_spins = Column(Integer, default=1, nullable=False)  # Бесплатные попытки
    last_free_spin_date = Column(DateTime, nullable=True)  # Дата последней бесплатной попытки
    
    # Статистика
    total_games = Column(Integer, default=0, nullable=False)  # Всего игр
    total_wins = Column(Integer, default=0, nullable=False)  # Всего выигрышей
    
    # Серия входов
    login_streak = Column(Integer, default=0, nullable=False)  # Дней подряд
    last_login_date = Column(DateTime, nullable=True)  # Последний вход
    
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
    
    created_at = Column(DateTime, default=datetime.utcnow)
