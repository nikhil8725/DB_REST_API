import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.exception_handlers import register_exception_handlers
from app.api.middleware import CorrelationIdMiddleware
from app.api.routes import router as trades_router
from app.domain.clock import SystemClockService
from app.infrastructure.database import async_session_factory, init_db
from app.infrastructure.scheduler import TradeExpiryScheduler

# Background scheduler instance
scheduler = TradeExpiryScheduler(
    session_factory=async_session_factory,
    clock=SystemClockService(),
    interval_seconds=int(os.getenv("EXPIRY_SWEEP_INTERVAL_SECONDS", "60")),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables exist and start background auto-expiry worker
    await init_db()
    if os.getenv("ENABLE_BACKGROUND_SCHEDULER", "true").lower() == "true":
        await scheduler.start()
    yield
    # Shutdown: stop worker cleanly
    await scheduler.stop()


def create_app() -> FastAPI:
    """Factory function for FastAPI application."""
    app = FastAPI(
        title="Deutsche Bank Trade Store REST API",
        description="Enterprise Trade Store API with Version Sequencing, TDD, and Automated Expiry Lifecycle.",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(CorrelationIdMiddleware)

    # Global Exception Handlers
    register_exception_handlers(app)

    # Routes
    app.include_router(trades_router)

    @app.get("/healthz", tags=["Health"])
    async def health_check():
        return {"status": "ok", "service": "trade-store", "version": "1.0.0"}

    return app


app = create_app()
