from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    LowerVersionRejectedException,
    PastMaturityDateException,
    TradeStoreException,
)


def register_exception_handlers(app) -> None:
    """Registers standard RFC-7807 problem details exception handlers."""

    @app.exception_handler(LowerVersionRejectedException)
    async def lower_version_handler(request: Request, exc: LowerVersionRejectedException):
        correlation_id = getattr(request.state, "correlation_id", None)
        return JSONResponse(
            status_code=422,
            content={
                "type": "https://errors.trades.db.com/lower-version-rejected",
                "title": "Lower Version Rejected",
                "status": 422,
                "detail": exc.message,
                "trade_id": exc.trade_id,
                "incoming_version": exc.incoming_version,
                "current_version": exc.current_version,
                "correlation_id": correlation_id,
            },
        )

    @app.exception_handler(PastMaturityDateException)
    async def past_maturity_handler(request: Request, exc: PastMaturityDateException):
        correlation_id = getattr(request.state, "correlation_id", None)
        return JSONResponse(
            status_code=422,
            content={
                "type": "https://errors.trades.db.com/past-maturity-rejected",
                "title": "Past Maturity Date Rejected",
                "status": 422,
                "detail": exc.message,
                "trade_id": exc.trade_id,
                "maturity_date": exc.maturity_date.isoformat(),
                "current_date": exc.current_date.isoformat(),
                "correlation_id": correlation_id,
            },
        )

    @app.exception_handler(TradeStoreException)
    async def general_domain_handler(request: Request, exc: TradeStoreException):
        correlation_id = getattr(request.state, "correlation_id", None)
        return JSONResponse(
            status_code=400,
            content={
                "type": "https://errors.trades.db.com/trade-store-error",
                "title": "Trade Store Validation Error",
                "status": 400,
                "detail": exc.message,
                "correlation_id": correlation_id,
            },
        )
