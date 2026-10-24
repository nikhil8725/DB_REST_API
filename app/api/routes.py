from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.dtos import (
    PaginatedTradeResponseDTO,
    TradeCreateDTO,
    TradeResponseDTO,
)
from app.application.service import TradeStoreService
from app.domain.clock import IClockService, SystemClockService
from app.infrastructure.database import get_db_session
from app.infrastructure.repository import SQLAlchemyTradeRepository

router = APIRouter(prefix="/api/v1/trades", tags=["Trades"])


# Default system clock provider, can be overridden in tests
async def get_clock_service() -> IClockService:
    return SystemClockService()


async def get_trade_service(
    session: AsyncSession = Depends(get_db_session),
    clock: IClockService = Depends(get_clock_service),
) -> TradeStoreService:
    repo = SQLAlchemyTradeRepository(session)
    return TradeStoreService(repository=repo, clock=clock, session=session)


@router.post(
    "",
    response_model=TradeResponseDTO,
    summary="Ingest a financial trade",
    description="Validates and persists a trade. Rejects lower versions and past maturity dates. Replaces same version.",
)
async def ingest_trade(
    payload: TradeCreateDTO,
    request: Request,
    response: Response,
    service: TradeStoreService = Depends(get_trade_service),
):
    correlation_id = getattr(request.state, "correlation_id", None)

    # Check if this is an insert or an update to set appropriate HTTP status code
    existing = await service.repository.get_by_id(payload.trade_id)
    is_new = existing is None

    result = await service.process_trade(payload, correlation_id=correlation_id)

    if is_new:
        response.status_code = status.HTTP_201_CREATED
    else:
        response.status_code = status.HTTP_200_OK

    return result


@router.get(
    "/{trade_id}",
    response_model=TradeResponseDTO,
    summary="Get trade by Trade ID",
)
async def get_trade(
    trade_id: str,
    service: TradeStoreService = Depends(get_trade_service),
):
    trade = await service.get_trade(trade_id)
    if not trade:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trade with id '{trade_id.upper()}' not found.",
        )
    return trade


@router.get(
    "",
    response_model=PaginatedTradeResponseDTO,
    summary="List stored trades with pagination and filtering",
    description="Query stored trades with page limits, offsets, and optional filtering by expired flag or portfolio ID.",
)
async def list_trades(
    limit: int = Query(default=50, ge=1, le=500, description="Page limit (default: 50, max: 500)"),
    offset: int = Query(default=0, ge=0, description="Page offset index"),
    expired: Literal["Y", "N"] | None = Query(
        default=None, description="Filter by expired flag (Y/N)"
    ),
    portfolio_id: str | None = Query(default=None, description="Filter by Portfolio ID (e.g. B1)"),
    service: TradeStoreService = Depends(get_trade_service),
):
    return await service.list_trades_paginated(
        limit=limit,
        offset=offset,
        expired=expired,
        portfolio_id=portfolio_id,
    )
