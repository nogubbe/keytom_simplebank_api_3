"""Request/response schemas for the accounts API."""

from datetime import datetime
from decimal import Decimal

from ninja import Schema
from pydantic import Field

from .enums import TransactionType


class BalanceOutScheme(Schema):
    """Response body for the current balance."""

    account_number: str
    balance: Decimal


class TransactionOutScheme(Schema):
    """Response body for a single transaction history entry."""

    id: int
    type: TransactionType
    amount: Decimal
    timestamp: datetime


class TransferInScheme(Schema):
    """Request body for creating a transfer."""

    account_number: str
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class TransferOutScheme(Schema):
    """Response body for a successfully created transfer."""

    account_number: str
    amount: Decimal
    fee: Decimal
    total_debited: Decimal


class ErrorOutScheme(Schema):
    """Generic error response body."""

    detail: str
