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

    async def update(self, trade: Trade, enforce_version_ordering: bool = True) -> Trade | None:
        """
        Update an existing trade record atomically.
        If enforce_version_ordering=True, only updates if DB version <= incoming trade version.
        Returns the updated Trade if successful, or None if a concurrent update wrote a higher version.
        """
        now = datetime.now(UTC)
        stmt = update(TradeORM).where(TradeORM.trade_id == trade.trade_id)
        if enforce_version_ordering:
            stmt = stmt.where(TradeORM.version <= trade.version)

        stmt = stmt.values(
            version=trade.version,
            counter_party_id=trade.counter_party_id,
            portfolio_id=trade.portfolio_id,
            maturity_date=trade.maturity_date,
            created_date=trade.created_date,
            expired=trade.expired,
            updated_at=now,
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        if result.rowcount == 0:
            return None
        return trade

    async def list_all(self) -> list[Trade]:
        """List all trades ordered by trade_id and version."""
        stmt = select(TradeORM).order_by(TradeORM.trade_id, TradeORM.version.desc())
        result = await self.session.execute(stmt)
        return [self._to_entity(orm) for orm in result.scalars().all()]

    async def list_paginated(
        self,
        limit: int = 50,
        offset: int = 0,
        expired: str | None = None,
        portfolio_id: str | None = None,
    ) -> tuple[list[Trade], int]:
        """List trades with filtering and pagination, returning (items, total_count)."""
        from sqlalchemy import func

        conditions = []
        if expired is not None:
            conditions.append(TradeORM.expired == expired.strip().upper())
        if portfolio_id is not None:
            conditions.append(TradeORM.portfolio_id == portfolio_id.strip().upper())

        # Count total matching rows
        count_stmt = select(func.count(TradeORM.trade_id))
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar_one()

        # Fetch paginated rows
        stmt = select(TradeORM)
        if conditions:
            stmt = stmt.where(*conditions)
        stmt = stmt.order_by(TradeORM.trade_id).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        items = [self._to_entity(orm) for orm in result.scalars().all()]
        return items, total

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
