"""Database models for SQLAlchemy."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class PositionSetDB(Base):
    """Position set table."""
    __tablename__ = "position_sets"

    id = Column(Integer, primary_key=True)
    set_id = Column(String(50), unique=True, index=True, nullable=False)
    bias = Column(String(10), nullable=False)
    state = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    opened_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    target_profit_usd = Column(Float, nullable=False)
    max_loss_usd = Column(Float, nullable=True)

    combined_pnl = Column(Float, default=0.0)
    high_water_mark = Column(Float, default=0.0)

    entry_signal_price = Column(Float, nullable=True)
    entry_ema = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)

    # Relationships
    legs = relationship("LegDB", back_populates="position_set", cascade="all, delete-orphan")


class LegDB(Base):
    """Position leg table (perp or option)."""
    __tablename__ = "legs"

    id = Column(Integer, primary_key=True)
    position_set_id = Column(Integer, ForeignKey("position_sets.id"), nullable=False)
    leg_type = Column(String(10), nullable=False)  # perp or option
    symbol = Column(String(50), nullable=False)
    side = Column(String(10), nullable=False)  # short or long
    qty = Column(Float, nullable=False)

    entry_price = Column(Float, nullable=True)
    mark_price = Column(Float, nullable=True)
    unrealized_pnl = Column(Float, default=0.0)

    order_id = Column(String(100), nullable=True)
    client_order_id = Column(String(100), nullable=True)
    filled = Column(Boolean, default=False)
    filled_qty = Column(Float, default=0.0)
    closed = Column(Boolean, default=False)

    # Option-specific
    strike = Column(Float, nullable=True)
    expiry = Column(String(20), nullable=True)
    option_type = Column(String(10), nullable=True)

    # Relationship
    position_set = relationship("PositionSetDB", back_populates="legs")


class SignalDB(Base):
    """Signal log table."""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.now)
    candle_time = Column(DateTime, nullable=False)
    signal_type = Column(String(20), nullable=False)
    price = Column(Float, nullable=False)
    ema = Column(Float, nullable=False)
    bias = Column(String(10), nullable=False)
    acted_upon = Column(Boolean, default=False)


class EventDB(Base):
    """Event log table."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.now)
    event_type = Column(String(50), nullable=False)
    severity = Column(String(20), default="info")
    message = Column(Text, nullable=False)
    details = Column(Text, nullable=True)
