from datetime import date
from typing import Optional


class TradeStoreException(Exception):
    """Base exception for all Trade Store domain errors."""

    def __init__(self, message: str, correlation_id: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.correlation_id = correlation_id


class LowerVersionRejectedException(TradeStoreException):
    """Raised when an incoming trade version is lower than the current stored version."""

    def __init__(
        self,
        trade_id: str,
        incoming_version: int,
        current_version: int,
        correlation_id: Optional[str] = None,
    ):
        msg = (
            f"Trade '{trade_id}' rejected: received version {incoming_version} is lower "
            f"than currently stored version {current_version}."
        )
        super().__init__(msg, correlation_id)
        self.trade_id = trade_id
        self.incoming_version = incoming_version
        self.current_version = current_version


class PastMaturityDateException(TradeStoreException):
    """Raised when a trade's maturity date is earlier than today's date."""

    def __init__(
        self,
        trade_id: str,
        maturity_date: date,
        current_date: date,
        correlation_id: Optional[str] = None,
    ):
        msg = (
            f"Trade '{trade_id}' rejected: maturity date {maturity_date.isoformat()} "
            f"is earlier than current date {current_date.isoformat()}."
        )
        super().__init__(msg, correlation_id)
        self.trade_id = trade_id
        self.maturity_date = maturity_date
        self.current_date = current_date
