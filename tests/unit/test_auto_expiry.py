from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.dtos import TradeCreateDTO
from app.application.service import TradeStoreService
from app.domain.clock import FixedClockService
from app.infrastructure.database import Base
from app.infrastructure.repository import SQLAlchemyTradeRepository
from app.infrastructure.scheduler import TradeExpiryScheduler


@pytest_asyncio.fixture
async def expiry_setup():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    clock = FixedClockService(fixed_date=date(2026, 10, 23))

    async with session_factory() as session:
        repo = SQLAlchemyTradeRepository(session)
        service = TradeStoreService(repository=repo, clock=clock, session=session)
        yield service, clock, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_rule_3_auto_expiry_sweep(expiry_setup):
    service, clock, _ = expiry_setup

    # Store trade maturing in the future: 2026-10-25 (today is 2026-10-23)
    await service.process_trade(
        TradeCreateDTO(
            trade_id="T1",
            version=1,
            counter_party_id="CP-1",
            portfolio_id="B1",
            maturity_date=date(2026, 10, 25),
        ),
        correlation_id="exp-1",
    )

    t1 = await service.get_trade("T1")
    assert t1.expired == "N"

    # Advance clock past maturity: 2026-10-26
    clock.set_date(date(2026, 10, 26))

    # Trigger auto-expiry sweep
    expired_count = await service.run_expiry_sweep()
    assert expired_count == 1

    # Verify status transitioned to 'Y'
    t1_after = await service.get_trade("T1")
    assert t1_after.expired == "Y"


@pytest.mark.asyncio
async def test_rule_3_dynamic_read_time_fallback(expiry_setup):
    service, clock, _ = expiry_setup

    # Store trade maturing on 2026-10-25
    await service.process_trade(
        TradeCreateDTO(
            trade_id="T2",
            version=1,
            counter_party_id="CP-2",
            portfolio_id="B1",
            maturity_date=date(2026, 10, 25),
        ),
        correlation_id="exp-2",
    )

    # Advance time without running the background sweep
    clock.set_date(date(2026, 10, 27))

    # Calling get_trade dynamically catches that maturity passed and returns expired='Y'
    fetched = await service.get_trade("T2")
    assert fetched.expired == "Y"


@pytest.mark.asyncio
async def test_scheduler_lifecycle(expiry_setup):
    service, clock, session_factory = expiry_setup
    scheduler = TradeExpiryScheduler(
        session_factory=session_factory,
        clock=clock,
        interval_seconds=1,
    )
    # Start and stop cleanly
    await scheduler.start()
    assert scheduler.is_running is True
    await scheduler.stop()
    assert scheduler.is_running is False
