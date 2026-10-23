from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Literal


@dataclass
class Trade:
    """Core Trade domain entity enforcing business rules."""

    trade_id: str
    version: int
    counter_party_id: str
    portfolio_id: str
    maturity_date: date
    created_date: date
    expired: Literal["Y", "N"] = "N"
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        # Normalize identifiers to uppercase to prevent casing-based duplicate anomalies
        self.trade_id = self.trade_id.strip().upper()
        self.counter_party_id = self.counter_party_id.strip().upper()
        self.portfolio_id = self.portfolio_id.strip().upper()
        self.expired = self.expired.strip().upper()  # type: ignore

    def is_lower_version(self, incoming_version: int) -> bool:
        """Rule 1A: Returns True if incoming version is strictly lower than current version."""
        return incoming_version < self.version

    def is_same_version(self, incoming_version: int) -> bool:
        """Rule 1B: Returns True if incoming version matches current version."""
        return incoming_version == self.version

    def is_higher_version(self, incoming_version: int) -> bool:
        """Rule 1C: Returns True if incoming version is strictly higher."""
        return incoming_version > self.version

    def is_matured(self, as_of: date) -> bool:
        """Rule 3: Returns True if trade maturity date is strictly earlier than as_of date."""
        return self.maturity_date < as_of

    def mark_expired(self) -> None:
        """Marks the trade as expired ('Y')."""
        self.expired = "Y"
        self.updated_at = datetime.now(timezone.utc)
