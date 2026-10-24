import asyncio
import random
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.dtos import TradeCreateDTO
from app.application.service import TradeStoreService
from app.domain.clock import FixedClockService
from app.domain.exceptions import LowerVersionRejectedException
from app.infrastructure.database import Base
from app.infrastructure.repository import SQLAlchemyTradeRepository


@pytest_asyncio.fixture
async def stress_fixture():
    # Setup test in-memory SQLite engine with busy timeout to handle concurrent writes
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"timeout": 30.0},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    clock = FixedClockService(fixed_date=date(2026, 10, 25))

    yield session_factory, clock

    await engine.dispose()


@pytest.mark.asyncio
async def test_high_throughput_burst_100_concurrent_trades(stress_fixture):
    """
    Simulates thousands of trades being sent to a single store simultaneously.
    Fires 100 parallel asynchronous workers ingesting distinct trades in parallel.
    """
    session_factory, clock = stress_fixture

    async def ingest_worker(trade_idx: int):
        async with session_factory() as session:
            repo = SQLAlchemyTradeRepository(session)
            service = TradeStoreService(repository=repo, clock=clock, session=session)
            dto = TradeCreateDTO(
                trade_id=f"BURST_{trade_idx:03d}",
                version=1,
                counter_party_id=f"CP-BURST-{trade_idx % 5}",
                portfolio_id="PORT-STRESS",
                maturity_date=date(2027, 1, 1),
            )
            return await service.process_trade(dto, correlation_id=f"burst-{trade_idx}")

    # Dispatch 100 concurrent ingestion tasks simultaneously
    tasks = [ingest_worker(i) for i in range(100)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 100
    assert all(r.expired == "N" for r in results)

    # Verify total count in database
    async with session_factory() as session:
        repo = SQLAlchemyTradeRepository(session)
        service = TradeStoreService(repository=repo, clock=clock, session=session)
        paginated = await service.list_trades_paginated(limit=200, offset=0)
        assert paginated.total == 100
        assert len(paginated.items) == 100


@pytest.mark.asyncio
async def test_concurrency_race_condition_conflicting_versions(stress_fixture):
    """
    Tests race condition defense when multiple threads/workers attempt to write
    different versions (v1, v2, v3, v4, v5) of the SAME trade concurrently.
    Verifies that the highest version wins and lower versions never overwrite higher versions.
    """
    session_factory, clock = stress_fixture

    # First, persist baseline Version 3
    async with session_factory() as session:
        repo = SQLAlchemyTradeRepository(session)
        service = TradeStoreService(repository=repo, clock=clock, session=session)
        await service.process_trade(
            TradeCreateDTO(
                trade_id="COMPETITIVE_TRADE",
                version=3,
                counter_party_id="CP-INIT",
                portfolio_id="B1",
                maturity_date=date(2027, 5, 20),
            )
        )

    # Now fire 30 concurrent attempts with random versions from 1 to 5
    async def competing_worker(attempt_idx: int, target_version: int):
        # Add random jitter to simulate network interleaving
        await asyncio.sleep(random.uniform(0.001, 0.01))
        async with session_factory() as session:
            repo = SQLAlchemyTradeRepository(session)
            service = TradeStoreService(repository=repo, clock=clock, session=session)
            dto = TradeCreateDTO(
                trade_id="COMPETITIVE_TRADE",
                version=target_version,
                counter_party_id=f"CP-V{target_version}",
                portfolio_id="B1",
                maturity_date=date(2027, 5, 20),
            )
            try:
                return await service.process_trade(dto, correlation_id=f"comp-{attempt_idx}")
            except LowerVersionRejectedException as e:
                return e

    versions_to_submit = [1, 2, 3, 4, 5] * 6  # 30 concurrent submissions
    tasks = [competing_worker(i, v) for i, v in enumerate(versions_to_submit)]
    outcomes = await asyncio.gather(*tasks)

    # Verify that lower versions (1 and 2) were rejected with LowerVersionRejectedException
    rejected_count = sum(1 for o in outcomes if isinstance(o, LowerVersionRejectedException))
    assert rejected_count > 0, "Expected lower versions to be rejected"

    # Verify the final state stored in database has version == 5 (highest submitted version)
    async with session_factory() as session:
        repo = SQLAlchemyTradeRepository(session)
        service = TradeStoreService(repository=repo, clock=clock, session=session)
        final_trade = await service.get_trade("COMPETITIVE_TRADE")
        assert final_trade is not None
        assert final_trade.version == 5, (
            f"Expected final version to be 5, got {final_trade.version}"
        )


@pytest.mark.asyncio
async def test_concurrent_ingestion_interleaved_with_auto_expiry(stress_fixture):
    """
    Tests concurrent background ingestion interleaved with the auto-expiry sweep.
    """
    session_factory, clock = stress_fixture
    clock.set_date(date(2026, 10, 25))

    async def ingest_matured_worker(idx: int):
        async with session_factory() as session:
            repo = SQLAlchemyTradeRepository(session)
            service = TradeStoreService(repository=repo, clock=clock, session=session)
            # Alternate between future and matured dates
            mat_date = date(2026, 10, 24) if idx % 2 == 0 else date(2027, 1, 1)
            # Use FixedClock temporarily set to allow ingestion
            clock.set_date(date(2026, 10, 20))
            dto = TradeCreateDTO(
                trade_id=f"INTERLEAVED_{idx:03d}",
                version=1,
                counter_party_id="CP-1",
                portfolio_id="B1",
                maturity_date=mat_date,
            )
            return await service.process_trade(dto)

    # Ingest 20 trades
    tasks = [ingest_matured_worker(i) for i in range(20)]
    await asyncio.gather(*tasks)

    # Set clock to 2026-10-25 and run expiry sweep concurrently with reads
    clock.set_date(date(2026, 10, 25))

    async def reader_worker():
        async with session_factory() as session:
            repo = SQLAlchemyTradeRepository(session)
            service = TradeStoreService(repository=repo, clock=clock, session=session)
            return await service.list_trades_paginated(limit=50, offset=0)

    async def sweeper_worker():
        async with session_factory() as session:
            repo = SQLAlchemyTradeRepository(session)
            service = TradeStoreService(repository=repo, clock=clock, session=session)
            return await service.run_expiry_sweep()

    sweep_res, read_res = await asyncio.gather(sweeper_worker(), reader_worker())
    assert sweep_res == 10  # 10 matured trades expired
    assert read_res.total == 20
