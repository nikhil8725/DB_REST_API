from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos import TradeCreateDTO, TradeResponseDTO
from app.domain.clock import IClockService
from app.domain.exceptions import LowerVersionRejectedException, PastMaturityDateException
from app.domain.models import Trade
from app.infrastructure.repository import SQLAlchemyTradeRepository


class TradeStoreService:
    """Core trade store service implementing all Deutsche Bank business rules."""

    def __init__(
        self,
        repository: SQLAlchemyTradeRepository,
        clock: IClockService,
        session: AsyncSession,
    ):
        self.repository = repository
        self.clock = clock
        self.session = session

    async def process_trade(
        self,
        dto: TradeCreateDTO,
        correlation_id: str | None = None,
    ) -> TradeResponseDTO:
        """
        Processes an incoming trade transmission applying all validation rules:
        - Rule 2: Rejects trade if maturity_date < today's date.
        - Rule 1: Rejects if lower version; replaces if same version; updates if higher version.
        """
        today = self.clock.get_today()

        # Rule 2: Reject trade if maturity date is earlier than today's date
        if dto.maturity_date < today:
            await self.repository.log_audit(
                trade_id=dto.trade_id,
                version=dto.version,
                action="REJECTED_PAST_MATURITY",
                correlation_id=correlation_id,
                details=f"Maturity {dto.maturity_date} is earlier than today {today}",
            )
            await self.session.commit()
            raise PastMaturityDateException(
                trade_id=dto.trade_id,
                maturity_date=dto.maturity_date,
                current_date=today,
                correlation_id=correlation_id,
            )

        # Concurrency-safe retrieval with lock
        existing_trade = await self.repository.get_for_update(dto.trade_id)

        if existing_trade is None:
            # New Trade (Rule 1: Accept)
            new_trade = Trade(
                trade_id=dto.trade_id,
                version=dto.version,
                counter_party_id=dto.counter_party_id,
                portfolio_id=dto.portfolio_id,
                maturity_date=dto.maturity_date,
                created_date=today,
                expired="N",
            )
            saved = await self.repository.save(new_trade)
            await self.repository.log_audit(
                trade_id=saved.trade_id,
                version=saved.version,
                action="INSERT",
                correlation_id=correlation_id,
                details="Initial version accepted",
            )
            await self.session.commit()
            return self._to_dto(saved)

        # Existing Trade Found: Evaluate Version
        # Rule 1A: Lower version received -> Reject
        if existing_trade.is_lower_version(dto.version):
            await self.repository.log_audit(
                trade_id=dto.trade_id,
                version=dto.version,
                action="REJECTED_LOWER_VERSION",
                correlation_id=correlation_id,
                details=f"Received v{dto.version} < current v{existing_trade.version}",
            )
            await self.session.commit()
            raise LowerVersionRejectedException(
                trade_id=dto.trade_id,
                incoming_version=dto.version,
                current_version=existing_trade.version,
                correlation_id=correlation_id,
            )

        # Rule 1B: Same version received -> Replace current record
        if existing_trade.is_same_version(dto.version):
            existing_trade.counter_party_id = dto.counter_party_id
            existing_trade.portfolio_id = dto.portfolio_id
            existing_trade.maturity_date = dto.maturity_date
            existing_trade.created_date = today
            existing_trade.expired = "N"

            updated = await self.repository.update(existing_trade)
            await self.repository.log_audit(
                trade_id=updated.trade_id,
                version=updated.version,
                action="OVERWRITE_SAME_VERSION",
                correlation_id=correlation_id,
                details="Replaced record with same version",
            )
            await self.session.commit()
            return self._to_dto(updated)

        # Rule 1C: Higher version received -> Upgrade record
        existing_trade.version = dto.version
        existing_trade.counter_party_id = dto.counter_party_id
        existing_trade.portfolio_id = dto.portfolio_id
        existing_trade.maturity_date = dto.maturity_date
        existing_trade.created_date = today
        existing_trade.expired = "N"

        updated = await self.repository.update(existing_trade)
        await self.repository.log_audit(
            trade_id=updated.trade_id,
            version=updated.version,
            action="UPDATE_HIGHER_VERSION",
            correlation_id=correlation_id,
            details=f"Upgraded to version {dto.version}",
        )
        await self.session.commit()
        return self._to_dto(updated)

    async def get_trade(self, trade_id: str) -> TradeResponseDTO | None:
        """Fetch trade with read-time dynamic expiry check."""
        trade = await self.repository.get_by_id(trade_id)
        if not trade:
            return None

        # Dynamic read-time expiry check (ensures zero-stale window)
        today = self.clock.get_today()
        if trade.is_matured(today) and trade.expired == "N":
            trade.mark_expired()
            await self.repository.update(trade)
            await self.session.commit()

        return self._to_dto(trade)

    async def list_trades(self) -> list[TradeResponseDTO]:
        """List all trades with dynamic read-time expiry verification."""
        trades = await self.repository.list_all()
        today = self.clock.get_today()
        result = []
        needs_commit = False

        for t in trades:
            if t.is_matured(today) and t.expired == "N":
                t.mark_expired()
                await self.repository.update(t)
                needs_commit = True
            result.append(self._to_dto(t))

        if needs_commit:
            await self.session.commit()

        return result

    async def run_expiry_sweep(self) -> int:
        """Rule 3: Bulk-expire all trades where maturity_date < today."""
        today = self.clock.get_today()
        count = await self.repository.expire_trades_before(cutoff_date=today)
        if count > 0:
            await self.repository.log_audit(
                trade_id="BATCH_SYSTEM",
                version=0,
                action="AUTO_EXPIRED_BATCH",
                details=f"Expired {count} matured trades as of {today}",
            )
        await self.session.commit()
        return count

    def _to_dto(self, trade: Trade) -> TradeResponseDTO:
        return TradeResponseDTO(
            trade_id=trade.trade_id,
            version=trade.version,
            counter_party_id=trade.counter_party_id,
            portfolio_id=trade.portfolio_id,
            maturity_date=trade.maturity_date,
            created_date=trade.created_date,
            expired=trade.expired,
        )
