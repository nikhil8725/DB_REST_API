from datetime import date

import pytest
from pydantic import ValidationError

from app.application.dtos import TradeCreateDTO
from app.domain.clock import SystemClockService
from app.infrastructure.database import get_db_session, init_db


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


@pytest.mark.asyncio
async def test_general_trade_store_exception_handler():
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.exception_handlers import register_exception_handlers
    from app.domain.exceptions import TradeStoreException

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/trigger-error")
    async def trigger():
        raise TradeStoreException("Generic domain failure")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/trigger-error")
        assert res.status_code == 400
        assert res.json()["detail"] == "Generic domain failure"
