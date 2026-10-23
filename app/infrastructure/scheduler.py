import asyncio
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.clock import IClockService
from app.infrastructure.repository import SQLAlchemyTradeRepository

logger = logging.getLogger("trade_store.scheduler")


class TradeExpiryScheduler:
    """Background asynchronous worker running periodic trade expiry sweeps."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        clock: IClockService,
        interval_seconds: int = 60,
    ):
        self.session_factory = session_factory
        self.clock = clock
        self.interval_seconds = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def run_single_sweep(self) -> int:
        """Executes a single expiry sweep inside a fresh database session."""
        today = self.clock.get_today()
        async with self.session_factory() as session:
            repo = SQLAlchemyTradeRepository(session)
            count = await repo.expire_trades_before(cutoff_date=today)
            if count > 0:
                await repo.log_audit(
                    trade_id="BATCH_SYSTEM",
                    version=0,
                    action="AUTO_EXPIRED_BATCH",
                    details=f"Background scheduler expired {count} trades as of {today}",
                )
                await session.commit()
                logger.info(f"Auto-expiry sweep completed: {count} trade(s) expired as of {today}.")
            return count

    async def _worker_loop(self) -> None:
        """Periodic loop executing until stop event is signaled."""
        logger.info(f"Trade expiry worker started (interval: {self.interval_seconds}s).")
        while not self._stop_event.is_set():
            try:
                await self.run_single_sweep()
            except Exception as e:
                logger.error(f"Error during auto-expiry sweep: {e}", exc_info=True)

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

        logger.info("Trade expiry worker stopped cleanly.")

    async def start(self) -> None:
        """Starts the background worker task."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        """Signals the background worker to stop and awaits completion."""
        if not self.is_running:
            return
        self._stop_event.set()
        if self._task:
            await self._task
            self._task = None
