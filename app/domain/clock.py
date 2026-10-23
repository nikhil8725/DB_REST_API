from datetime import date, datetime, timezone
from typing import Protocol


class IClockService(Protocol):
    """Abstract clock interface to allow deterministic time testing."""

    def get_today(self) -> date:
        """Returns the current date in UTC."""
        ...

    def get_now(self) -> datetime:
        """Returns the current timestamp in UTC."""
        ...


class SystemClockService:
    """Production clock using system UTC time."""

    def get_today(self) -> date:
        return datetime.now(timezone.utc).date()

    def get_now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClockService:
    """Deterministic clock for TDD unit and regression tests."""

    def __init__(self, fixed_date: date):
        self._fixed_date = fixed_date
        self._fixed_datetime = datetime(
            fixed_date.year, fixed_date.month, fixed_date.day, 12, 0, 0, tzinfo=timezone.utc
        )

    def set_date(self, new_date: date) -> None:
        self._fixed_date = new_date
        self._fixed_datetime = datetime(
            new_date.year, new_date.month, new_date.day, 12, 0, 0, tzinfo=timezone.utc
        )

    def get_today(self) -> date:
        return self._fixed_date

    def get_now(self) -> datetime:
        return self._fixed_datetime
