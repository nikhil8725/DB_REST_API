from datetime import UTC, date, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import Trade
from app.infrastructure.orm_models import TradeAuditEventORM, TradeORM


class SQLAlchemyTradeRepository:
    """Async repository implementing trade persistence and audit trail logging."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _to_entity(self, orm: TradeORM) -> Trade:
        return Trade(
            trade_id=orm.trade_id,
            version=orm.version,
            counter_party_id=orm.counter_party_id,
            portfolio_id=orm.portfolio_id,
            maturity_date=orm.maturity_date,
            created_date=orm.created_date,
            expired=orm.expired,  # type: ignore
            updated_at=orm.updated_at,
        )

    async def get_by_id(self, trade_id: str) -> Trade | None:
        """Fetch trade by Trade ID."""
        clean_id = trade_id.strip().upper()
        stmt = select(TradeORM).where(TradeORM.trade_id == clean_id)
        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_entity(orm) if orm else None

    async def get_for_update(self, trade_id: str) -> Trade | None:
        """Fetch trade with a row lock to serialize concurrent access."""
        clean_id = trade_id.strip().upper()
        # SQLite doesn't support with_for_update(), but PostgreSQL does
        bind = self.session.bind
        dialect_name = bind.dialect.name if bind else ""
        stmt = select(TradeORM).where(TradeORM.trade_id == clean_id)
        if dialect_name != "sqlite":
            stmt = stmt.with_for_update()

        result = await self.session.execute(stmt)
        orm = result.scalar_one_or_none()
        return self._to_entity(orm) if orm else None

    async def save(self, trade: Trade) -> Trade:
        """Insert a new trade record into the database."""
        now = datetime.now(UTC)
        orm = TradeORM(
            trade_id=trade.trade_id,
            version=trade.version,
            counter_party_id=trade.counter_party_id,
            portfolio_id=trade.portfolio_id,
            maturity_date=trade.maturity_date,
            created_date=trade.created_date,
            expired=trade.expired,
            updated_at=now,
        )
        self.session.add(orm)
        await self.session.flush()
        return self._to_entity(orm)

    async def update(self, trade: Trade) -> Trade:
        """Update an existing trade record."""
        now = datetime.now(UTC)
        stmt = (
            update(TradeORM)
            .where(TradeORM.trade_id == trade.trade_id)
            .values(
                version=trade.version,
                counter_party_id=trade.counter_party_id,
                portfolio_id=trade.portfolio_id,
                maturity_date=trade.maturity_date,
                created_date=trade.created_date,
                expired=trade.expired,
                updated_at=now,
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()
        return trade

    async def list_all(self) -> list[Trade]:
        """List all trades ordered by trade_id and version."""
        stmt = select(TradeORM).order_by(TradeORM.trade_id, TradeORM.version.desc())
        result = await self.session.execute(stmt)
        return [self._to_entity(orm) for orm in result.scalars().all()]

    async def expire_trades_before(self, cutoff_date: date) -> int:
        """Bulk-update all trades whose maturity_date < cutoff_date and expired == 'N'."""
        now = datetime.now(UTC)
        stmt = (
            update(TradeORM)
            .where(TradeORM.maturity_date < cutoff_date, TradeORM.expired == "N")
            .values(expired="Y", updated_at=now)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def log_audit(
        self,
        trade_id: str,
        version: int,
        action: str,
        correlation_id: str | None = None,
        details: str | None = None,
    ) -> None:
        """Log an immutable audit entry."""
        audit = TradeAuditEventORM(
            trade_id=trade_id.strip().upper(),
            version=version,
            action=action,
            correlation_id=correlation_id,
            created_at=datetime.now(UTC),
            details=details,
        )
        self.session.add(audit)
        await self.session.flush()
