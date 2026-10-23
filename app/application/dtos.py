import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TradeCreateDTO(BaseModel):
    """Input payload for trade creation or update."""

    trade_id: str = Field(
        ...,
        description="Unique identifier for the financial trade (e.g., T1, T2)",
        min_length=1,
        max_length=32,
        examples=["T1"],
    )
    version: int = Field(
        ...,
        description="Version number of the trade",
        ge=1,
        examples=[1],
    )
    counter_party_id: str = Field(
        ...,
        description="Counterparty trading identifier (e.g., CP-1)",
        min_length=1,
        max_length=32,
        examples=["CP-1"],
    )
    portfolio_id: str = Field(
        ...,
        description="Trading book or portfolio code (e.g., B1)",
        min_length=1,
        max_length=32,
        examples=["B1"],
    )
    maturity_date: date = Field(
        ...,
        description="Contract maturity date (ISO-8601: YYYY-MM-DD)",
        examples=["2027-05-20"],
    )

    @field_validator("trade_id", "counter_party_id", "portfolio_id", mode="before")
    @classmethod
    def normalize_and_sanitize(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Identifier must be a string")
        stripped = value.strip().upper()
        if not re.match(r"^[A-Z0-9_-]{1,32}$", stripped):
            raise ValueError(
                f"Identifier '{value}' contains invalid characters. Must be alphanumeric or hyphen/underscore."
            )
        return stripped


class TradeResponseDTO(BaseModel):
    """Output representation of a stored trade."""

    trade_id: str
    version: int
    counter_party_id: str
    portfolio_id: str
    maturity_date: date
    created_date: date
    expired: Literal["Y", "N"]

    model_config = ConfigDict(from_attributes=True)
