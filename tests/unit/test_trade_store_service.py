from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.application.dtos import TradeCreateDTO
from app.application.service import TradeStoreService
from app.domain.clock import FixedClockService
from app.domain.exceptions import LowerVersionRejectedException, PastMaturityDateException
from app.infrastructure.database import Base
from app.infrastructure.repository import SQLAlchemyTradeRepository


@pytest_asyncio.fixture
async def service_fixture():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    clock = FixedClockService(fixed_date=date(2026, 10, 23))

    async with session_factory() as session:
        repo = SQLAlchemyTradeRepository(session)
        service = TradeStoreService(repository=repo, clock=clock, session=session)
        yield service, clock

    await engine.dispose()


@pytest.mark.asyncio
async def test_rule_1_accept_new_trade(service_fixture):
    service, _ = service_fixture
    dto = TradeCreateDTO(
        trade_id="T1",
        version=1,
        counter_party_id="CP-1",
        portfolio_id="B1",
        maturity_date=date(2027, 5, 20),
    )
    res = await service.process_trade(dto, correlation_id="corr-1")
    assert res.trade_id == "T1"
    assert res.version == 1
    assert res.counter_party_id == "CP-1"
    assert res.portfolio_id == "B1"
    assert res.expired == "N"
    assert res.created_date == date(2026, 10, 23)


@pytest.mark.asyncio
async def test_rule_1_reject_lower_version(service_fixture):
    service, _ = service_fixture
    # Store version 2 first
    dto_v2 = TradeCreateDTO(
        trade_id="T2",
        version=2,
        counter_party_id="CP-2",
        portfolio_id="B1",
        maturity_date=date(2027, 5, 20),
    )
    await service.process_trade(dto_v2, correlation_id="corr-2")

    # Attempt to store version 1 for same trade_id T2 -> MUST REJECT
    dto_v1 = TradeCreateDTO(
        trade_id="T2",
        version=1,
        counter_party_id="CP-1",
        portfolio_id="B1",
        maturity_date=date(2027, 5, 20),
    )
    with pytest.raises(LowerVersionRejectedException) as exc_info:
        await service.process_trade(dto_v1, correlation_id="corr-3")

    assert "rejected" in str(exc_info.value)
    assert exc_info.value.incoming_version == 1
    assert exc_info.value.current_version == 2

    # Verify stored version remains 2
    stored = await service.get_trade("T2")
    assert stored is not None
    assert stored.version == 2
    assert stored.counter_party_id == "CP-2"


@pytest.mark.asyncio
async def test_rule_1_replace_same_version(service_fixture):
    service, _ = service_fixture
    # Store version 1
    dto_v1 = TradeCreateDTO(
        trade_id="T1",
        version=1,
        counter_party_id="CP-1",
        portfolio_id="B1",
        maturity_date=date(2027, 5, 20),
    )
    await service.process_trade(dto_v1, correlation_id="corr-4")

    # Store same version 1 with updated CP-2 and portfolio B2
    dto_v1_same = TradeCreateDTO(
        trade_id="T1",
        version=1,
        counter_party_id="CP-2",
        portfolio_id="B2",
        maturity_date=date(2027, 5, 20),
    )
    res = await service.process_trade(dto_v1_same, correlation_id="corr-5")
    assert res.trade_id == "T1"
    assert res.version == 1
    assert res.counter_party_id == "CP-2"
    assert res.portfolio_id == "B2"


@pytest.mark.asyncio
async def test_rule_1_update_higher_version(service_fixture):
    service, _ = service_fixture
    # Store version 1
    dto_v1 = TradeCreateDTO(
        trade_id="T1",
        version=1,
        counter_party_id="CP-1",
        portfolio_id="B1",
        maturity_date=date(2027, 5, 20),
    )
    await service.process_trade(dto_v1, correlation_id="corr-6")

    # Store higher version 2
    dto_v2 = TradeCreateDTO(
        trade_id="T1",
        version=2,
        counter_party_id="CP-1",
        portfolio_id="B1",
        maturity_date=date(2027, 5, 20),
    )
    res = await service.process_trade(dto_v2, correlation_id="corr-7")
    assert res.trade_id == "T1"
    assert res.version == 2


@pytest.mark.asyncio
async def test_rule_2_reject_past_maturity_date(service_fixture):
    service, clock = service_fixture
    clock.set_date(date(2026, 10, 23))

    # Maturity date is in the past: 2026-10-20 (< 2026-10-23)
    dto_past = TradeCreateDTO(
        trade_id="T3",
        version=1,
        counter_party_id="CP-3",
        portfolio_id="B2",
        maturity_date=date(2026, 10, 20),
    )
    with pytest.raises(PastMaturityDateException) as exc_info:
        await service.process_trade(dto_past, correlation_id="corr-8")

    assert "is earlier than current date" in str(exc_info.value)
    assert exc_info.value.maturity_date == date(2026, 10, 20)


@pytest.mark.asyncio
async def test_rule_2_accept_today_maturity_date(service_fixture):
    service, clock = service_fixture
    clock.set_date(date(2026, 10, 23))

    # Maturity date is today: 2026-10-23 (>= today)
    dto_today = TradeCreateDTO(
        trade_id="T4",
        version=1,
        counter_party_id="CP-4",
        portfolio_id="B2",
        maturity_date=date(2026, 10, 23),
    )
    res = await service.process_trade(dto_today, correlation_id="corr-9")
    assert res.trade_id == "T4"
    assert res.expired == "N"
