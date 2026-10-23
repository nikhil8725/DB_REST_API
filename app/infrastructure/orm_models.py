from datetime import date, datetime, timezone
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class TradeORM(Base):
    """SQLAlchemy ORM model mapping to 'trades' table."""

    __tablename__ = "trades"

    # Trade ID is the business key of the trade record
    trade_id: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    counter_party_id: Mapped[str] = mapped_column(String(32), nullable=False)
    portfolio_id: Mapped[str] = mapped_column(String(32), nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_date: Mapped[date] = mapped_column(Date, nullable=False)
    expired: Mapped[str] = mapped_column(String(1), nullable=False, default="N", index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("idx_trades_maturity_expired", "maturity_date", "expired"),
    )


class TradeAuditEventORM(Base):
    """Immutable audit log of all trade store modifications and rejections."""

    __tablename__ = "trade_audit_events"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    details: Mapped[str] = mapped_column(Text, nullable=True)
