from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.models import Trade
from app.infrastructure.database import Base
from app.infrastructure.repository import SQLAlchemyTradeRepository


@pytest_asyncio.fixture
async def repo_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield SQLAlchemyTradeRepository(session)

    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_save_and_retrieve(repo_session):
    trade = Trade(
        trade_id="T1",
        version=1,
        counter_party_id="CP-1",
        portfolio_id="B1",
        maturity_date=date(2027, 5, 20),
        created_date=date(2026, 10, 23),
        expired="N",
    )
    saved = await repo_session.save(trade)
    assert saved.trade_id == "T1"

    fetched = await repo_session.get_by_id("T1")
    assert fetched is not None
    assert fetched.trade_id == "T1"
    assert fetched.version == 1
    assert fetched.counter_party_id == "CP-1"
    assert fetched.portfolio_id == "B1"
    assert fetched.expired == "N"


@pytest.mark.asyncio
async def test_repository_update_trade(repo_session):
    trade = Trade(
        trade_id="T1",
        version=1,
        counter_party_id="CP-1",
        portfolio_id="B1",
        maturity_date=date(2027, 5, 20),
        created_date=date(2026, 10, 23),
        expired="N",
    )
    await repo_session.save(trade)

    # Update trade with same version but CP-2
    trade.counter_party_id = "CP-2"
    updated = await repo_session.update(trade)
    assert updated.counter_party_id == "CP-2"

    refetched = await repo_session.get_by_id("T1")
    assert refetched.counter_party_id == "CP-2"


@pytest.mark.asyncio
async def test_repository_expire_trades_before(repo_session):
    t1 = Trade(
        trade_id="T1",
        version=1,
        counter_party_id="CP-1",
        portfolio_id="B1",
        maturity_date=date(2026, 10, 20),
        created_date=date(2026, 10, 1),
        expired="N",
    )
    t2 = Trade(
        trade_id="T2",
        version=1,
        counter_party_id="CP-2",
        portfolio_id="B1",
        maturity_date=date(2026, 10, 25),
        created_date=date(2026, 10, 1),
        expired="N",
    )
    await repo_session.save(t1)
    await repo_session.save(t2)

    # Run bulk expiry with cutoff date 2026-10-23
    count = await repo_session.expire_trades_before(cutoff_date=date(2026, 10, 23))
    assert count == 1

    t1_updated = await repo_session.get_by_id("T1")
    t2_updated = await repo_session.get_by_id("T2")
    assert t1_updated.expired == "Y"
    assert t2_updated.expired == "N"
