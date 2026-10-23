import pytest
from datetime import date
from pydantic import ValidationError

from app.application.dtos import TradeCreateDTO
from app.domain.clock import SystemClockService
from app.domain.exceptions import TradeStoreException
from app.infrastructure.database import get_db_session, init_db
from app.infrastructure.scheduler import TradeExpiryScheduler


def test_dto_validation_invalid_character():
    with pytest.raises(ValidationError):
        TradeCreateDTO(
            trade_id="T1@#$",
            version=1,
            counter_party_id="CP-1",
            portfolio_id="B1",
            maturity_date=date(2027, 5, 20),
        )


def test_dto_validation_non_string():
    with pytest.raises(ValidationError):
        TradeCreateDTO(
            trade_id=12345,  # type: ignore
            version=1,
            counter_party_id="CP-1",
            portfolio_id="B1",
            maturity_date=date(2027, 5, 20),
        )


def test_system_clock_get_now():
    clock = SystemClockService()
    now = clock.get_now()
    assert now is not None


@pytest.mark.asyncio
async def test_database_init_and_get_session():
    await init_db()
    async for session in get_db_session():
        assert session is not None
        break
