"""Enumerations used by the accounts app."""

from enum import StrEnum


class TransactionType(StrEnum):
    """The two kinds of ledger entries: credit or debit."""

    CREDIT = 'credit'
    DEBIT = 'debit'
